import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../../core/network/server_endpoint_config.dart';
import '../../../core/theme/app_colors.dart';

class VisionConnectionDebugDialog extends StatefulWidget {
  const VisionConnectionDebugDialog({super.key});

  @override
  State<VisionConnectionDebugDialog> createState() =>
      _VisionConnectionDebugDialogState();
}

class _VisionConnectionDebugDialogState
    extends State<VisionConnectionDebugDialog> {
  bool _isLoading = false;
  String? _errorMessage;
  Map<String, dynamic>? _jsonPayload;
  String? _rawResponse;

  String get _mainSystemAddress => context.read<ServerEndpointConfig>().origin;

  String get _visionServiceAddress {
    final payload = _jsonPayload;
    if (payload == null) {
      return 'unknown';
    }

    final topLevelBaseUrl = payload['base_url'];
    if (topLevelBaseUrl is String && topLevelBaseUrl.trim().isNotEmpty) {
      return topLevelBaseUrl;
    }

    final visionService = payload['vision_service'];
    if (visionService is Map<String, dynamic>) {
      final nestedBaseUrl = visionService['base_url'];
      if (nestedBaseUrl is String && nestedBaseUrl.trim().isNotEmpty) {
        return nestedBaseUrl;
      }

      final nestedUrl = visionService['url'];
      if (nestedUrl is String && nestedUrl.trim().isNotEmpty) {
        final uri = Uri.tryParse(nestedUrl);
        if (uri != null && uri.hasScheme && uri.host.isNotEmpty) {
          final portPart = uri.hasPort ? ':${uri.port}' : '';
          return '${uri.scheme}://${uri.host}$portPart';
        }
        return nestedUrl;
      }
    }

    return 'unknown';
  }

  String get _cameraId {
    final payload = _jsonPayload;
    if (payload == null) {
      return 'unknown';
    }

    final topLevelCameraId = payload['camera_id'];
    if (topLevelCameraId is String && topLevelCameraId.trim().isNotEmpty) {
      return topLevelCameraId;
    }

    final defaultCameraId = payload['default_camera_id'];
    if (defaultCameraId is String && defaultCameraId.trim().isNotEmpty) {
      return defaultCameraId;
    }

    return 'camera_01';
  }

  String get _connectionStatus {
    if (_errorMessage != null) {
      return _errorMessage!;
    }

    final payload = _jsonPayload;
    if (payload == null) {
      return 'unknown';
    }

    final status = payload['status'];
    if (status is String && status.trim().isNotEmpty) {
      return status;
    }

    final visionService = payload['vision_service'];
    if (visionService is Map<String, dynamic>) {
      final nestedStatus = visionService['status'];
      if (nestedStatus is String && nestedStatus.trim().isNotEmpty) {
        return nestedStatus;
      }

      final reason = visionService['reason'];
      if (reason is String && reason.trim().isNotEmpty) {
        return reason;
      }
    }

    return 'unknown';
  }

  Future<void> _testVisionHealth() async {
    final endpointConfig = context.read<ServerEndpointConfig>();
    final dio = Dio(
      BaseOptions(
        baseUrl: endpointConfig.origin,
        connectTimeout: const Duration(seconds: 3),
        receiveTimeout: const Duration(seconds: 3),
        responseType: ResponseType.plain,
      ),
    );

    setState(() {
      _isLoading = true;
      _errorMessage = null;
      _jsonPayload = null;
      _rawResponse = null;
    });

    try {
      final response = await dio.get<String>('/api/v1/vision/health');
      final rawText = _normalizeRawResponse(response.data);
      Map<String, dynamic>? decoded;
      String? parseError;

      if (rawText.trim().isNotEmpty) {
        try {
          final parsed = jsonDecode(rawText);
          if (parsed is Map<String, dynamic>) {
            decoded = parsed;
          } else {
            parseError = '响应格式异常';
          }
        } catch (_) {
          parseError = '响应格式异常';
        }
      }

      if (!mounted) {
        return;
      }

      setState(() {
        _isLoading = false;
        _errorMessage = parseError;
        _jsonPayload = decoded;
        _rawResponse = rawText;
      });
    } on DioException catch (error) {
      if (!mounted) {
        return;
      }

      setState(() {
        _isLoading = false;
        _rawResponse = _normalizeRawResponse(error.response?.data);
        switch (error.type) {
          case DioExceptionType.connectionTimeout:
          case DioExceptionType.receiveTimeout:
          case DioExceptionType.sendTimeout:
            _errorMessage = '请求超时';
            break;
          case DioExceptionType.connectionError:
            _errorMessage = '主系统不可达';
            break;
          default:
            _errorMessage = '主系统不可达';
            break;
        }
      });
    } catch (_) {
      if (!mounted) {
        return;
      }

      setState(() {
        _isLoading = false;
        _errorMessage = '响应格式异常';
      });
    }
  }

  Future<void> _copySummary() async {
    final summary = [
      'Main System:',
      _mainSystemAddress,
      '',
      'Vision Service:',
      _visionServiceAddress,
      '',
      'Camera ID:',
      _cameraId,
      '',
      'Status:',
      _connectionStatus,
      '',
      'Time:',
      DateTime.now().toIso8601String(),
    ].join('\n');

    await Clipboard.setData(ClipboardData(text: summary));
    if (!mounted) {
      return;
    }

    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('联调摘要已复制')),
    );
  }

  String _normalizeRawResponse(Object? data) {
    if (data == null) {
      return '';
    }
    if (data is String) {
      return data;
    }

    try {
      return const JsonEncoder.withIndent('  ').convert(data);
    } catch (_) {
      return data.toString();
    }
  }

  Widget _buildField(String label, String value, {Color? valueColor}) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(
              color: AppColors.textSub,
              fontSize: 13,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 6),
          SelectableText(
            value,
            style: TextStyle(
              color: valueColor ?? AppColors.textMain,
              fontSize: 14,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }

  Color _statusColor(String value) {
    switch (value) {
      case 'ok':
      case 'online':
        return AppColors.success;
      case 'unavailable':
      case 'timeout':
      case 'connection_error':
      case '请求超时':
      case '主系统不可达':
      case '响应格式异常':
        return AppColors.error;
      case 'degraded':
        return AppColors.warning;
      default:
        return AppColors.textMain;
    }
  }

  @override
  Widget build(BuildContext context) {
    final statusText = _connectionStatus;

    return AlertDialog(
      backgroundColor: const Color(0xFFF8FAFC),
      title: const Text(
        '联调地址确认',
        style:
            TextStyle(color: AppColors.textMain, fontWeight: FontWeight.bold),
      ),
      content: SizedBox(
        width: 420,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _buildField(
                '主系统地址',
                _mainSystemAddress,
                valueColor: AppColors.primary,
              ),
              const SizedBox(height: 12),
              _buildField('Vision Service 地址', _visionServiceAddress),
              const SizedBox(height: 12),
              _buildField('camera_id', _cameraId),
              const SizedBox(height: 12),
              _buildField(
                '连接状态',
                statusText,
                valueColor: _statusColor(statusText),
              ),
              if (_errorMessage != null) ...[
                const SizedBox(height: 12),
                Text(
                  _errorMessage!,
                  style: const TextStyle(
                    color: AppColors.error,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
              const SizedBox(height: 12),
              Theme(
                data: Theme.of(context)
                    .copyWith(dividerColor: Colors.transparent),
                child: ExpansionTile(
                  tilePadding: EdgeInsets.zero,
                  childrenPadding: EdgeInsets.zero,
                  title: const Text(
                    '原始响应',
                    style: TextStyle(
                      color: AppColors.textMain,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  children: [
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: AppColors.border),
                      ),
                      child: SelectableText(
                        (_rawResponse != null &&
                                _rawResponse!.trim().isNotEmpty)
                            ? _rawResponse!
                            : '暂无响应',
                        style: const TextStyle(
                          color: AppColors.textMain,
                          fontSize: 12,
                          height: 1.4,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
      actions: [
        OutlinedButton(
          onPressed: _isLoading ? null : _testVisionHealth,
          style: OutlinedButton.styleFrom(
            foregroundColor: AppColors.textMain,
            side: const BorderSide(color: AppColors.border),
          ),
          child: _isLoading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Text('测试连接'),
        ),
        TextButton(
          onPressed: _isLoading ? null : _copySummary,
          child: const Text('复制联调摘要'),
        ),
        ElevatedButton(
          onPressed: _isLoading ? null : () => Navigator.of(context).pop(),
          style: ElevatedButton.styleFrom(
            backgroundColor: const Color(0xFF2563EB),
            foregroundColor: Colors.white,
          ),
          child: const Text('关闭'),
        ),
      ],
    );
  }
}
