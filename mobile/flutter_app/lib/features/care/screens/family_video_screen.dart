import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_mjpeg/flutter_mjpeg.dart';
import 'package:provider/provider.dart';

import '../../../core/network/server_endpoint_config.dart';
import '../../../core/theme/app_colors.dart';

enum _VideoPlayState {
  connecting,
  playing,
  failed,
  reconnecting,
}

class FamilyVideoScreen extends StatefulWidget {
  const FamilyVideoScreen({super.key});

  @override
  State<FamilyVideoScreen> createState() => _FamilyVideoScreenState();
}

class _FamilyVideoScreenState extends State<FamilyVideoScreen> {
  final Dio _dio = Dio(
    BaseOptions(
      connectTimeout: const Duration(seconds: 5),
      receiveTimeout: const Duration(seconds: 5),
    ),
  );

  Timer? _statusTimer;
  String? _activeOrigin;
  Map<String, dynamic>? _cameraSetup;
  Map<String, dynamic>? _cameraHealth;
  String? _lastRequestUrl;
  int? _lastStatusCode;
  String? _lastContentType;
  int? _lastImageBytes;
  String? _lastError;
  String? _lastCameraSource;
  DateTime? _lastProbeAt;
  bool _cameraMetaLoading = false;
  bool _snapshotProbeInFlight = false;
  bool _reconnectScheduled = false;
  int _streamReloadToken = 0;
  _VideoPlayState _playState = _VideoPlayState.connecting;
  String _statusMessage = '正在连接家属端清洁视频...';

  @override
  void initState() {
    super.initState();
    _statusTimer = Timer.periodic(
      const Duration(seconds: 5),
      (_) => _refreshStreamHealth(silent: true),
    );
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final origin = context.watch<ServerEndpointConfig>().origin;
    if (_activeOrigin == origin) {
      return;
    }
    _activeOrigin = origin;
    _resetVideoRuntime();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await _refreshStreamHealth();
    });
  }

  @override
  void dispose() {
    _statusTimer?.cancel();
    _dio.close(force: true);
    super.dispose();
  }

  String _apiUrl(String path) {
    final endpointConfig = context.read<ServerEndpointConfig>();
    return '${endpointConfig.origin}$path';
  }

  String _familyStreamUrl() {
    return '${_apiUrl('/api/v1/camera/family-stream.mjpg')}?session=$_streamReloadToken';
  }

  String _familySnapshotUrl() {
    return _apiUrl('/api/v1/camera/family-snapshot');
  }

  String _processedDebugUrl() {
    return _apiUrl('/api/v1/camera/processed-stream.mjpg');
  }

  void _resetVideoRuntime() {
    setState(() {
      _cameraSetup = null;
      _cameraHealth = null;
      _lastRequestUrl = null;
      _lastStatusCode = null;
      _lastContentType = null;
      _lastImageBytes = null;
      _lastError = null;
      _lastCameraSource = null;
      _lastProbeAt = null;
      _reconnectScheduled = false;
      _streamReloadToken = 0;
      _playState = _VideoPlayState.connecting;
      _statusMessage = '正在连接家属端清洁视频...';
    });
  }

  void _updatePlayState(
    _VideoPlayState nextState,
    String message, {
    String? error,
  }) {
    if (!mounted) {
      return;
    }
    setState(() {
      _playState = nextState;
      _statusMessage = message;
      if (error != null && error.trim().isNotEmpty) {
        _lastError = error;
      }
    });
  }

  Future<void> _loadCameraMeta({bool silent = false}) async {
    if (!mounted || _cameraMetaLoading) {
      return;
    }
    _cameraMetaLoading = true;
    if (!silent) {
      setState(() {});
    }

    try {
      final responses = await Future.wait([
        _dio.get<Map<String, dynamic>>(_apiUrl('/api/v1/camera/setup')),
        _dio.get<Map<String, dynamic>>(_apiUrl('/api/v1/camera/health')),
      ]);

      if (!mounted) {
        return;
      }

      setState(() {
        _cameraSetup = responses[0].data ?? <String, dynamic>{};
        _cameraHealth = responses[1].data ?? <String, dynamic>{};
      });
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() {
        _cameraHealth = <String, dynamic>{
          'configured': false,
          'online': false,
          'error': 'CAMERA_META_LOAD_FAILED',
        };
      });
    } finally {
      _cameraMetaLoading = false;
      if (mounted) {
        setState(() {});
      }
    }
  }

  Future<void> _probeFamilySnapshot({bool silent = false}) async {
    if (!mounted || _snapshotProbeInFlight) {
      return;
    }
    _snapshotProbeInFlight = true;

    final snapshotUrl = _familySnapshotUrl();
    _lastRequestUrl = snapshotUrl;

    try {
      final response = await _dio.get<List<dynamic>>(
        snapshotUrl,
        queryParameters: <String, dynamic>{
          'ts': DateTime.now().millisecondsSinceEpoch,
        },
        options: Options(
          responseType: ResponseType.bytes,
          headers: const <String, String>{
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
          },
        ),
      );

      final rawBytes = response.data;
      if (rawBytes == null || rawBytes.isEmpty) {
        throw StateError('EMPTY_IMAGE_RESPONSE');
      }

      final imageBytes = rawBytes.cast<int>();
      final contentType = response.headers.value('content-type');
      final cameraSource =
          response.headers.value('x-camera-source') ?? 'family-stream';

      if (!mounted) {
        return;
      }

      setState(() {
        _lastProbeAt = DateTime.now();
        _lastStatusCode = response.statusCode;
        _lastContentType = contentType;
        _lastImageBytes = imageBytes.length;
        _lastCameraSource = cameraSource;
        if (_lastError != null &&
            (_playState == _VideoPlayState.connecting ||
                _playState == _VideoPlayState.reconnecting ||
                _playState == _VideoPlayState.failed)) {
          _lastError = null;
        }
      });

      if (!silent ||
          _playState == _VideoPlayState.connecting ||
          _playState == _VideoPlayState.reconnecting ||
          _playState == _VideoPlayState.failed) {
        final sourceLabel = cameraSource.contains('raw')
            ? cameraSource
            : 'family-stream';
        _updatePlayState(
          _VideoPlayState.playing,
          '视频播放中，当前来源: $sourceLabel',
        );
      }
    } catch (error) {
      if (!mounted) {
        return;
      }
      final statusCode =
          error is DioException ? error.response?.statusCode : null;
      final contentType = error is DioException
          ? error.response?.headers.value('content-type')
          : null;

      setState(() {
        _lastStatusCode = statusCode;
        _lastContentType = contentType;
        _lastImageBytes = null;
        _lastError = error.toString();
      });

      if (!silent || _playState != _VideoPlayState.playing) {
        _handleStreamFailure(error.toString());
      }
    } finally {
      _snapshotProbeInFlight = false;
    }
  }

  Future<void> _refreshStreamHealth({bool silent = false}) async {
    await _loadCameraMeta(silent: silent);
    await _probeFamilySnapshot(silent: silent);
  }

  void _handleStreamLoading() {
    if (!mounted) {
      return;
    }
    if (_playState == _VideoPlayState.playing) {
      return;
    }
    if (_playState == _VideoPlayState.failed) {
      _updatePlayState(
        _VideoPlayState.reconnecting,
        '正在重连家属端清洁视频...',
      );
      return;
    }
    if (_playState != _VideoPlayState.reconnecting) {
      _updatePlayState(
        _VideoPlayState.connecting,
        '正在连接家属端清洁视频...',
      );
    }
  }

  void _handleStreamFailure(String message) {
    if (!mounted) {
      return;
    }
    _updatePlayState(
      _VideoPlayState.failed,
      '连接失败，正在准备重连...',
      error: message,
    );
    _scheduleReconnect();
  }

  void _scheduleReconnect() {
    if (_reconnectScheduled || !mounted) {
      return;
    }
    _reconnectScheduled = true;
    Future<void>.delayed(const Duration(seconds: 2), () async {
      if (!mounted) {
        return;
      }
      _reconnectScheduled = false;
      await _restartVideo(manual: false);
    });
  }

  Future<void> _restartVideo({required bool manual}) async {
    if (!mounted) {
      return;
    }
    setState(() {
      _streamReloadToken += 1;
      _lastError = null;
    });
    _updatePlayState(
      manual ? _VideoPlayState.reconnecting : _VideoPlayState.connecting,
      manual ? '正在重连家属端清洁视频...' : '正在连接家属端清洁视频...',
    );
    await _refreshStreamHealth(silent: false);
  }

  void _reportStreamLoading() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        _handleStreamLoading();
      }
    });
  }

  void _reportStreamError(dynamic error) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        _handleStreamFailure(error.toString());
      }
    });
  }

  String _lastUpdatedLabel() {
    if (_lastProbeAt == null) {
      return '尚未完成视频探活';
    }
    final diff = DateTime.now().difference(_lastProbeAt!);
    if (diff.inSeconds < 1) {
      return '刚刚更新';
    }
    return '${diff.inSeconds} 秒前更新';
  }

  String _prettyJson(Map<String, dynamic>? payload) {
    if (payload == null || payload.isEmpty) {
      return '--';
    }
    return const JsonEncoder.withIndent('  ').convert(payload);
  }

  String _cameraTargetLabel() {
    final setup = _cameraSetup;
    if (setup == null) {
      return '未加载';
    }
    final mode = '${setup['camera_source_mode'] ?? 'auto'}';
    if (mode == 'local') {
      return '本地摄像头 #${setup['camera_local_index'] ?? 0}';
    }
    final ip = '${setup['camera_ip'] ?? ''}'.trim();
    final port = '${setup['camera_rtsp_port'] ?? ''}'.trim();
    final path =
        '${setup['camera_stream_rtsp_path'] ?? setup['camera_rtsp_path'] ?? ''}'
            .trim();
    if (ip.isEmpty) {
      return '未配置 RTSP 来源';
    }
    return '$ip:$port$path';
  }

  String _cameraHealthLabel() {
    final health = _cameraHealth;
    if (health == null) {
      return _cameraMetaLoading ? '正在检查摄像头状态...' : '尚未检查';
    }
    final configured = health['configured'] == true;
    final online = health['online'] == true;
    final error = '${health['error'] ?? ''}'.trim();
    if (!configured) {
      return '摄像头尚未配置';
    }
    if (online) {
      return '摄像头在线';
    }
    if (error.isNotEmpty) {
      return '摄像头离线: $error';
    }
    return '摄像头暂不可用';
  }

  String _playStateLabel() {
    switch (_playState) {
      case _VideoPlayState.connecting:
        return '正在连接';
      case _VideoPlayState.playing:
        return '视频播放中';
      case _VideoPlayState.failed:
        return '连接失败';
      case _VideoPlayState.reconnecting:
        return '正在重连';
    }
  }

  Color _playStateColor() {
    switch (_playState) {
      case _VideoPlayState.connecting:
      case _VideoPlayState.reconnecting:
        return const Color(0xFFF59E0B);
      case _VideoPlayState.playing:
        return const Color(0xFF10B981);
      case _VideoPlayState.failed:
        return AppColors.error;
    }
  }

  Future<void> _openCameraConfigSheet() async {
    final draft = _CameraConfigDraft.fromMap(_cameraSetup);
    final sourceMode = ValueNotifier<String>(draft.cameraSourceMode);
    final hostController = TextEditingController(text: draft.cameraIp);
    final userController = TextEditingController(text: draft.cameraUser);
    final passwordController =
        TextEditingController(text: draft.cameraPassword);
    final rtspPortController =
        TextEditingController(text: draft.cameraRtspPort.toString());
    final rtspPathController =
        TextEditingController(text: draft.cameraRtspPath);
    final streamPathController =
        TextEditingController(text: draft.cameraStreamRtspPath);
    final audioPathController =
        TextEditingController(text: draft.cameraAudioRtspPath);
    final onvifPortController =
        TextEditingController(text: draft.cameraOnvifPort.toString());
    final formKey = GlobalKey<FormState>();
    bool saving = false;

    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (sheetContext) {
        return StatefulBuilder(
          builder: (context, setSheetState) {
            Future<void> submit() async {
              if (!formKey.currentState!.validate() || saving) {
                return;
              }
              final navigator = Navigator.of(sheetContext);
              final messenger = ScaffoldMessenger.of(context);
              setSheetState(() {
                saving = true;
              });
              try {
                final payload = <String, dynamic>{
                  'camera_source_mode': sourceMode.value,
                  'camera_ip': hostController.text.trim(),
                  'camera_user': userController.text.trim(),
                  'camera_password': passwordController.text,
                  'camera_rtsp_port': int.parse(rtspPortController.text),
                  'camera_rtsp_path': rtspPathController.text.trim(),
                  'camera_stream_rtsp_path': streamPathController.text.trim(),
                  'camera_audio_rtsp_path': audioPathController.text.trim(),
                  'camera_onvif_port': int.parse(onvifPortController.text),
                };

                if (sourceMode.value == 'local') {
                  payload
                    ..remove('camera_ip')
                    ..remove('camera_user')
                    ..remove('camera_password')
                    ..remove('camera_rtsp_port')
                    ..remove('camera_rtsp_path')
                    ..remove('camera_stream_rtsp_path')
                    ..remove('camera_audio_rtsp_path')
                    ..remove('camera_onvif_port');
                }

                await _dio.post<Map<String, dynamic>>(
                  _apiUrl('/api/v1/camera/setup'),
                  data: payload,
                );

                if (!mounted) {
                  return;
                }

                navigator.pop();
                await _restartVideo(manual: true);
                if (!mounted) {
                  return;
                }
                messenger.showSnackBar(
                  const SnackBar(
                    content: Text('摄像头来源已更新，正在重连家属端清洁视频'),
                  ),
                );
              } on DioException catch (error) {
                if (!mounted) {
                  return;
                }
                final detail = error.response?.data;
                final message = detail is Map<String, dynamic>
                    ? (detail['detail']?.toString() ?? error.message ?? '保存失败')
                    : (error.message ?? '保存失败');
                messenger.showSnackBar(
                  SnackBar(content: Text('保存失败: $message')),
                );
              } finally {
                if (mounted) {
                  setSheetState(() {
                    saving = false;
                  });
                }
              }
            }

            return SafeArea(
              child: Padding(
                padding: EdgeInsets.only(
                  left: 16,
                  right: 16,
                  top: 12,
                  bottom: MediaQuery.of(context).viewInsets.bottom + 16,
                ),
                child: Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: AppColors.surface,
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(color: AppColors.border),
                  ),
                  child: Form(
                    key: formKey,
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        const Text(
                          '摄像头来源配置',
                          style: TextStyle(
                            color: AppColors.textMain,
                            fontSize: 20,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        const SizedBox(height: 8),
                        const Text(
                          '家属端默认展示无框 clean 视频流。这里可以修改摄像头 IP、用户名、密码、端口和 RTSP 路径，不需要把地址写死在代码里。',
                          style: TextStyle(
                            color: AppColors.textSub,
                            fontSize: 13,
                            height: 1.5,
                          ),
                        ),
                        const SizedBox(height: 16),
                        ValueListenableBuilder<String>(
                          valueListenable: sourceMode,
                          builder: (_, value, __) {
                            return DropdownButtonFormField<String>(
                              initialValue: value,
                              decoration: _inputDecoration('来源模式'),
                              items: const <DropdownMenuItem<String>>[
                                DropdownMenuItem(
                                  value: 'rtsp',
                                  child: Text('RTSP 摄像头'),
                                ),
                                DropdownMenuItem(
                                  value: 'auto',
                                  child: Text('自动选择'),
                                ),
                                DropdownMenuItem(
                                  value: 'local',
                                  child: Text('本地摄像头'),
                                ),
                              ],
                              onChanged: (next) {
                                if (next == null) {
                                  return;
                                }
                                sourceMode.value = next;
                              },
                            );
                          },
                        ),
                        const SizedBox(height: 12),
                        ValueListenableBuilder<String>(
                          valueListenable: sourceMode,
                          builder: (_, value, __) {
                            final rtspEnabled = value != 'local';
                            return Column(
                              children: <Widget>[
                                TextFormField(
                                  controller: hostController,
                                  enabled: rtspEnabled,
                                  decoration: _inputDecoration(
                                    '摄像头 IP，例如 192.168.8.252',
                                  ),
                                  validator: (input) {
                                    if (!rtspEnabled) {
                                      return null;
                                    }
                                    if (input == null || input.trim().isEmpty) {
                                      return '请输入摄像头 IP';
                                    }
                                    return null;
                                  },
                                ),
                                const SizedBox(height: 12),
                                Row(
                                  children: <Widget>[
                                    Expanded(
                                      child: TextFormField(
                                        controller: userController,
                                        enabled: rtspEnabled,
                                        decoration: _inputDecoration('用户名'),
                                        validator: (input) {
                                          if (!rtspEnabled) {
                                            return null;
                                          }
                                          if (input == null ||
                                              input.trim().isEmpty) {
                                            return '请输入用户名';
                                          }
                                          return null;
                                        },
                                      ),
                                    ),
                                    const SizedBox(width: 12),
                                    Expanded(
                                      child: TextFormField(
                                        controller: passwordController,
                                        enabled: rtspEnabled,
                                        obscureText: true,
                                        decoration: _inputDecoration('密码'),
                                        validator: (input) {
                                          if (!rtspEnabled) {
                                            return null;
                                          }
                                          if (input == null || input.isEmpty) {
                                            return '请输入密码';
                                          }
                                          return null;
                                        },
                                      ),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 12),
                                Row(
                                  children: <Widget>[
                                    Expanded(
                                      child: TextFormField(
                                        controller: rtspPortController,
                                        enabled: rtspEnabled,
                                        keyboardType: TextInputType.number,
                                        inputFormatters: <TextInputFormatter>[
                                          FilteringTextInputFormatter.digitsOnly,
                                        ],
                                        decoration: _inputDecoration('RTSP 端口'),
                                        validator: (input) {
                                          if (!rtspEnabled) {
                                            return null;
                                          }
                                          final port =
                                              int.tryParse(input ?? '');
                                          if (port == null || port <= 0) {
                                            return '端口无效';
                                          }
                                          return null;
                                        },
                                      ),
                                    ),
                                    const SizedBox(width: 12),
                                    Expanded(
                                      child: TextFormField(
                                        controller: onvifPortController,
                                        enabled: rtspEnabled,
                                        keyboardType: TextInputType.number,
                                        inputFormatters: <TextInputFormatter>[
                                          FilteringTextInputFormatter.digitsOnly,
                                        ],
                                        decoration: _inputDecoration('ONVIF 端口'),
                                        validator: (input) {
                                          if (!rtspEnabled) {
                                            return null;
                                          }
                                          final port =
                                              int.tryParse(input ?? '');
                                          if (port == null || port <= 0) {
                                            return '端口无效';
                                          }
                                          return null;
                                        },
                                      ),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 12),
                                TextFormField(
                                  controller: rtspPathController,
                                  enabled: rtspEnabled,
                                  decoration: _inputDecoration(
                                    '抓图路径，例如 /tcp/av0_1',
                                  ),
                                  validator: (input) {
                                    if (!rtspEnabled) {
                                      return null;
                                    }
                                    if (input == null || input.trim().isEmpty) {
                                      return '请输入抓图路径';
                                    }
                                    return null;
                                  },
                                ),
                                const SizedBox(height: 12),
                                TextFormField(
                                  controller: streamPathController,
                                  enabled: rtspEnabled,
                                  decoration: _inputDecoration(
                                    '视频流路径，例如 /tcp/av0_1',
                                  ),
                                  validator: (input) {
                                    if (!rtspEnabled) {
                                      return null;
                                    }
                                    if (input == null || input.trim().isEmpty) {
                                      return '请输入视频流路径';
                                    }
                                    return null;
                                  },
                                ),
                                const SizedBox(height: 12),
                                TextFormField(
                                  controller: audioPathController,
                                  enabled: rtspEnabled,
                                  decoration: _inputDecoration(
                                    '音频路径，例如 /tcp/av0_1',
                                  ),
                                  validator: (input) {
                                    if (!rtspEnabled) {
                                      return null;
                                    }
                                    if (input == null || input.trim().isEmpty) {
                                      return '请输入音频路径';
                                    }
                                    return null;
                                  },
                                ),
                              ],
                            );
                          },
                        ),
                        const SizedBox(height: 16),
                        Row(
                          children: <Widget>[
                            Expanded(
                              child: OutlinedButton(
                                onPressed: saving
                                    ? null
                                    : () => Navigator.of(sheetContext).pop(),
                                child: const Text('取消'),
                              ),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: ElevatedButton(
                                onPressed: saving ? null : submit,
                                child: saving
                                    ? const SizedBox(
                                        width: 18,
                                        height: 18,
                                        child: CircularProgressIndicator(
                                          strokeWidth: 2,
                                          color: Colors.white,
                                        ),
                                      )
                                    : const Text('应用到家属端视频'),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            );
          },
        );
      },
    );

    sourceMode.dispose();
    hostController.dispose();
    userController.dispose();
    passwordController.dispose();
    rtspPortController.dispose();
    rtspPathController.dispose();
    streamPathController.dispose();
    audioPathController.dispose();
    onvifPortController.dispose();
  }

  InputDecoration _inputDecoration(String label) {
    return InputDecoration(
      labelText: label,
      filled: true,
      fillColor: AppColors.background,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: const BorderSide(color: AppColors.border),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: const BorderSide(color: AppColors.border),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: const BorderSide(color: AppColors.primary, width: 2),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final streamUrl = _familyStreamUrl();
    final snapshotProbeUrl = _familySnapshotUrl();

    return Scaffold(
      backgroundColor: const Color(0xFFF8FAFC),
      appBar: AppBar(
        title: const Text(
          '视频查看',
          style: TextStyle(
            color: AppColors.textMain,
            fontWeight: FontWeight.bold,
          ),
        ),
        backgroundColor: Colors.transparent,
        elevation: 0,
        iconTheme: const IconThemeData(color: AppColors.textMain),
        actions: <Widget>[
          IconButton(
            onPressed: _openCameraConfigSheet,
            icon: const Icon(
              Icons.settings_input_component_outlined,
              color: AppColors.textSub,
            ),
            tooltip: '配置摄像头来源',
          ),
          IconButton(
            onPressed: () => _restartVideo(manual: true),
            icon: const Icon(Icons.refresh, color: AppColors.textSub),
            tooltip: '刷新并重连',
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: <Widget>[
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(18),
              border: Border.all(color: AppColors.border),
              boxShadow: const <BoxShadow>[
                BoxShadow(
                  color: Colors.black12,
                  blurRadius: 4,
                  offset: Offset(0, 2),
                ),
              ],
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Row(
                  children: <Widget>[
                    const Expanded(
                      child: Text(
                        '家属端摄像头画面',
                        style: TextStyle(
                          color: AppColors.textMain,
                          fontSize: 22,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                    TextButton.icon(
                      onPressed: _openCameraConfigSheet,
                      icon: const Icon(Icons.tune, size: 18),
                      label: const Text('更改来源'),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                const Text(
                  '当前页面默认连接家属端专用 clean 视频流，优先展示无框 raw 画面，不再默认使用 processed 检测画面。摄像头 IP、账号、端口和 RTSP 路径都可以在这里修改。',
                  style: TextStyle(
                    color: AppColors.textSub,
                    fontSize: 14,
                    height: 1.5,
                  ),
                ),
                const SizedBox(height: 14),
                _MetaRow(label: '当前来源', value: _cameraTargetLabel()),
                const SizedBox(height: 8),
                _MetaRow(label: '摄像头状态', value: _cameraHealthLabel()),
                const SizedBox(height: 8),
                _MetaRow(
                  label: '主系统',
                  value: context.watch<ServerEndpointConfig>().origin,
                ),
                const SizedBox(height: 8),
                _MetaRow(label: '视频接口', value: streamUrl),
                const SizedBox(height: 8),
                _MetaRow(label: '探活接口', value: snapshotProbeUrl),
                const SizedBox(height: 8),
                _MetaRow(label: '播放状态', value: _playStateLabel()),
                const SizedBox(height: 8),
                _MetaRow(label: '最近探活', value: _lastUpdatedLabel()),
              ],
            ),
          ),
          const SizedBox(height: 16),
          AspectRatio(
            aspectRatio: 16 / 9,
            child: Container(
              decoration: BoxDecoration(
                color: Colors.black,
                borderRadius: BorderRadius.circular(20),
                border: Border.all(color: AppColors.border),
              ),
              clipBehavior: Clip.antiAlias,
              child: Stack(
                fit: StackFit.expand,
                children: <Widget>[
                  Mjpeg(
                    key: ValueKey<int>(_streamReloadToken),
                    isLive: true,
                    stream: streamUrl,
                    fit: BoxFit.cover,
                    headers: const <String, String>{
                      'Cache-Control': 'no-cache',
                      'Pragma': 'no-cache',
                    },
                    loading: (context) {
                      _reportStreamLoading();
                      return const _VideoPlaceholder(
                        icon: Icons.wifi_tethering_outlined,
                        title: '正在连接家属端清洁视频...',
                        subtitle: '优先使用 raw MJPEG 连续流',
                        showSpinner: true,
                      );
                    },
                    error: (context, error, stack) {
                      _reportStreamError(error);
                      return _VideoPlaceholder(
                        icon: Icons.videocam_off_outlined,
                        title: '视频连接失败',
                        subtitle: '$error',
                      );
                    },
                  ),
                  Positioned(
                    left: 12,
                    top: 12,
                    child: _StatusBadge(
                      label: _playStateLabel(),
                      color: _playStateColor(),
                    ),
                  ),
                  Positioned(
                    right: 12,
                    bottom: 12,
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 10,
                        vertical: 6,
                      ),
                      decoration: BoxDecoration(
                        color: Colors.black.withValues(alpha: 0.45),
                        borderRadius: BorderRadius.circular(999),
                      ),
                      child: Text(
                        _statusMessage,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          Row(
            children: <Widget>[
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: () => _restartVideo(manual: true),
                  icon: const Icon(Icons.refresh),
                  label: const Text('刷新 / 重连'),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: ElevatedButton.icon(
                  onPressed: _openCameraConfigSheet,
                  icon: const Icon(Icons.settings_input_component_outlined),
                  label: const Text('更换摄像头来源'),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          ExpansionTile(
            tilePadding: const EdgeInsets.symmetric(horizontal: 12),
            collapsedShape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(18),
              side: const BorderSide(color: AppColors.border),
            ),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(18),
              side: const BorderSide(color: AppColors.border),
            ),
            backgroundColor: AppColors.surface,
            collapsedBackgroundColor: AppColors.surface,
            title: const Text(
              '视频调试信息',
              style: TextStyle(
                color: AppColors.textMain,
                fontWeight: FontWeight.bold,
              ),
            ),
            subtitle: const Text(
              '默认折叠，仅在真机联调或排障时展开',
              style: TextStyle(color: AppColors.textSub),
            ),
            children: <Widget>[
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    _MetaRow(
                      label: '请求 URL',
                      value: _lastRequestUrl ?? snapshotProbeUrl,
                    ),
                    const SizedBox(height: 8),
                    _MetaRow(
                      label: 'HTTP 状态',
                      value: '${_lastStatusCode ?? '--'}',
                    ),
                    const SizedBox(height: 8),
                    _MetaRow(
                      label: 'Content-Type',
                      value: _lastContentType ?? '--',
                    ),
                    const SizedBox(height: 8),
                    _MetaRow(
                      label: '图片字节',
                      value: '${_lastImageBytes ?? '--'}',
                    ),
                    const SizedBox(height: 8),
                    _MetaRow(
                      label: '相机来源',
                      value: _lastCameraSource ?? 'family-stream',
                    ),
                    const SizedBox(height: 8),
                    _MetaRow(label: '错误信息', value: _lastError ?? '--'),
                    const SizedBox(height: 8),
                    _MetaRow(label: 'raw MJPEG', value: streamUrl),
                    const SizedBox(height: 8),
                    _MetaRow(
                      label: 'processed 调试',
                      value: _processedDebugUrl(),
                    ),
                    const SizedBox(height: 12),
                    const Text(
                      'camera/setup',
                      style: TextStyle(
                        color: AppColors.textSub,
                        fontSize: 12,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 6),
                    SelectableText(
                      _prettyJson(_cameraSetup),
                      style: const TextStyle(
                        color: AppColors.textMain,
                        fontSize: 12,
                        height: 1.45,
                      ),
                    ),
                    const SizedBox(height: 12),
                    const Text(
                      'camera/health',
                      style: TextStyle(
                        color: AppColors.textSub,
                        fontSize: 12,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 6),
                    SelectableText(
                      _prettyJson(_cameraHealth),
                      style: const TextStyle(
                        color: AppColors.textMain,
                        fontSize: 12,
                        height: 1.45,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _MetaRow extends StatelessWidget {
  final String label;
  final String value;

  const _MetaRow({
    required this.label,
    required this.value,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        SizedBox(
          width: 84,
          child: Text(
            label,
            style: const TextStyle(
              color: AppColors.textSub,
              fontSize: 13,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: SelectableText(
            value,
            style: const TextStyle(
              color: AppColors.textMain,
              fontSize: 13,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
      ],
    );
  }
}

class _StatusBadge extends StatelessWidget {
  final String label;
  final Color color;

  const _StatusBadge({
    required this.label,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.92),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: const TextStyle(
          color: Colors.white,
          fontSize: 12,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }
}

class _VideoPlaceholder extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final bool showSpinner;

  const _VideoPlaceholder({
    required this.icon,
    required this.title,
    required this.subtitle,
    this.showSpinner = false,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      color: const Color(0xFF020617),
      padding: const EdgeInsets.all(24),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            if (showSpinner) ...<Widget>[
              const CircularProgressIndicator(color: Colors.white),
              const SizedBox(height: 18),
            ] else ...<Widget>[
              Icon(icon, color: Colors.white70, size: 42),
              const SizedBox(height: 14),
            ],
            Text(
              title,
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 16,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              subtitle,
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: Colors.white70,
                fontSize: 13,
                height: 1.45,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _CameraConfigDraft {
  final String cameraSourceMode;
  final String cameraIp;
  final String cameraUser;
  final String cameraPassword;
  final int cameraRtspPort;
  final String cameraRtspPath;
  final String cameraStreamRtspPath;
  final String cameraAudioRtspPath;
  final int cameraOnvifPort;

  const _CameraConfigDraft({
    required this.cameraSourceMode,
    required this.cameraIp,
    required this.cameraUser,
    required this.cameraPassword,
    required this.cameraRtspPort,
    required this.cameraRtspPath,
    required this.cameraStreamRtspPath,
    required this.cameraAudioRtspPath,
    required this.cameraOnvifPort,
  });

  factory _CameraConfigDraft.fromMap(Map<String, dynamic>? json) {
    return _CameraConfigDraft(
      cameraSourceMode: '${json?['camera_source_mode'] ?? 'rtsp'}',
      cameraIp: '${json?['camera_ip'] ?? ''}',
      cameraUser: '${json?['camera_user'] ?? 'admin'}',
      cameraPassword: '${json?['camera_password'] ?? ''}',
      cameraRtspPort: _asInt(json?['camera_rtsp_port'], fallback: 10554),
      cameraRtspPath: '${json?['camera_rtsp_path'] ?? '/tcp/av0_1'}',
      cameraStreamRtspPath:
          '${json?['camera_stream_rtsp_path'] ?? '/tcp/av0_1'}',
      cameraAudioRtspPath: '${json?['camera_audio_rtsp_path'] ?? '/tcp/av0_1'}',
      cameraOnvifPort: _asInt(json?['camera_onvif_port'], fallback: 10080),
    );
  }

  static int _asInt(Object? value, {required int fallback}) {
    if (value is int) {
      return value;
    }
    return int.tryParse('$value') ?? fallback;
  }
}
