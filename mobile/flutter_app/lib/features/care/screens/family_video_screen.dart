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

enum _FamilyQualityMode {
  smooth,
  balanced,
  hd,
}

extension on _FamilyQualityMode {
  String get apiValue {
    switch (this) {
      case _FamilyQualityMode.smooth:
        return 'smooth';
      case _FamilyQualityMode.balanced:
        return 'balanced';
      case _FamilyQualityMode.hd:
        return 'hd';
    }
  }

  String get label {
    switch (this) {
      case _FamilyQualityMode.smooth:
        return 'Flow';
      case _FamilyQualityMode.balanced:
        return 'Balanced';
      case _FamilyQualityMode.hd:
        return 'HD';
    }
  }

  String get description {
    switch (this) {
      case _FamilyQualityMode.smooth:
        return 'Weak network / lower latency';
      case _FamilyQualityMode.balanced:
        return 'Default mode';
      case _FamilyQualityMode.hd:
        return 'Higher detail / more bandwidth';
    }
  }
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
  Map<String, dynamic>? _cameraStreamStatus;
  Map<String, dynamic>? _visionRuntimeConfig;
  Map<String, dynamic>? _visionSourceStatus;
  String? _lastRequestUrl;
  int? _lastStatusCode;
  String? _lastContentType;
  int? _lastImageBytes;
  String? _lastError;
  String? _lastCameraSource;
  String? _lastFamilyQuality;
  String? _lastFamilySource;
  String? _lastFallbackReason;
  DateTime? _lastProbeAt;
  bool _cameraMetaLoading = false;
  bool _snapshotProbeInFlight = false;
  bool _reconnectScheduled = false;
  bool _qualityInitializedFromServer = false;
  int _streamReloadToken = 0;
  _VideoPlayState _playState = _VideoPlayState.connecting;
  _FamilyQualityMode _qualityMode = _FamilyQualityMode.smooth;

  @override
  void initState() {
    super.initState();
    _statusTimer = Timer.periodic(
      const Duration(seconds: 5),
      (_) => _refreshBackgroundStatus(),
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
    return '${_apiUrl('/api/v1/camera/family-stream.mjpg')}?quality=${_qualityMode.apiValue}&session=$_streamReloadToken';
  }

  String _familySnapshotUrl() {
    return '${_apiUrl('/api/v1/camera/family-snapshot')}?quality=${_qualityMode.apiValue}';
  }

  String _processedDebugUrl() {
    return _apiUrl('/api/v1/camera/processed-stream.mjpg');
  }

  void _resetVideoRuntime() {
    setState(() {
      _cameraSetup = null;
      _cameraHealth = null;
      _cameraStreamStatus = null;
      _visionRuntimeConfig = null;
      _visionSourceStatus = null;
      _lastRequestUrl = null;
      _lastStatusCode = null;
      _lastContentType = null;
      _lastImageBytes = null;
      _lastError = null;
      _lastCameraSource = null;
      _lastFamilyQuality = null;
      _lastFamilySource = null;
      _lastFallbackReason = null;
      _lastProbeAt = null;
      _reconnectScheduled = false;
      _streamReloadToken = 0;
      _playState = _VideoPlayState.connecting;
      _qualityInitializedFromServer = false;
      _qualityMode = _FamilyQualityMode.smooth;
    });
  }

  void _updatePlayState(
    _VideoPlayState nextState, {
    String? error,
  }) {
    if (!mounted) {
      return;
    }
    setState(() {
      _playState = nextState;
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
        _dio.get<Map<String, dynamic>>(_apiUrl('/api/v1/camera/stream-status')),
      ]);

      final setup = responses[0].data ?? <String, dynamic>{};
      final health = responses[1].data ?? <String, dynamic>{};
      final streamStatus = responses[2].data ?? <String, dynamic>{};

      if (!mounted) {
        return;
      }

      setState(() {
        _cameraSetup = setup;
        _cameraHealth = health;
        _cameraStreamStatus = streamStatus;
        if (!_qualityInitializedFromServer) {
          _qualityMode = _serverProfileToQuality(
            setup['camera_stream_profile']?.toString(),
          );
          _qualityInitializedFromServer = true;
        }
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _cameraHealth = <String, dynamic>{
          'configured': false,
          'online': false,
          'error': 'CAMERA_META_LOAD_FAILED',
        };
        _lastError = error.toString();
      });
    } finally {
      _cameraMetaLoading = false;
      if (mounted) {
        setState(() {});
      }
    }
  }

  Future<void> _loadVisionBridgeMeta({bool silent = false}) async {
    try {
      final responses = await Future.wait([
        _dio.get<Map<String, dynamic>>(
          _apiUrl('/api/v1/video-bridge/runtime-config'),
        ),
        _dio.get<Map<String, dynamic>>(
          _apiUrl('/api/v1/video-bridge/vision/source'),
        ),
      ]);

      if (!mounted) {
        return;
      }

      setState(() {
        _visionRuntimeConfig = responses[0].data ?? <String, dynamic>{};
        _visionSourceStatus = responses[1].data ?? <String, dynamic>{};
      });
    } catch (error) {
      if (!mounted || silent) {
        return;
      }
      setState(() {
        _visionRuntimeConfig = null;
        _visionSourceStatus = null;
      });
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
      if (!mounted) {
        return;
      }

      setState(() {
        _lastProbeAt = DateTime.now();
        _lastStatusCode = response.statusCode;
        _lastContentType = response.headers.value('content-type');
        _lastImageBytes = imageBytes.length;
        _lastCameraSource =
            response.headers.value('x-camera-source') ?? 'family-stream';
        _lastFamilyQuality =
            response.headers.value('x-family-quality') ?? _qualityMode.apiValue;
        _lastFamilySource =
            response.headers.value('x-family-source') ?? 'cache';
        _lastFallbackReason =
            response.headers.value('x-fallback-reason') ?? '--';
        if (_playState != _VideoPlayState.playing) {
          _lastError = null;
        }
      });

      if (!silent ||
          _playState == _VideoPlayState.connecting ||
          _playState == _VideoPlayState.reconnecting ||
          _playState == _VideoPlayState.failed) {
        _updatePlayState(_VideoPlayState.playing);
      }
    } catch (error) {
      if (!mounted) {
        return;
      }
      final dioError = error is DioException ? error : null;
      setState(() {
        _lastStatusCode = dioError?.response?.statusCode;
        _lastContentType = dioError?.response?.headers.value('content-type');
        _lastImageBytes = null;
        _lastError = error.toString();
        _lastFallbackReason = null;
      });
      if (!silent || _playState != _VideoPlayState.playing) {
        _handleStreamFailure(error.toString());
      }
    } finally {
      _snapshotProbeInFlight = false;
    }
  }

  Future<void> _refreshStreamHealth({bool silent = false}) async {
    await Future.wait([
      _loadCameraMeta(silent: silent),
      _loadVisionBridgeMeta(silent: silent),
    ]);
    if (_visionFrameReady()) {
      if (!silent && mounted) {
        _updatePlayState(_VideoPlayState.playing);
      }
      return;
    }
    await _probeFamilySnapshot(silent: silent);
  }

  Future<void> _refreshBackgroundStatus() async {
    if (!mounted) {
      return;
    }
    await Future.wait([
      _loadCameraMeta(silent: true),
      _loadVisionBridgeMeta(silent: true),
    ]);
    if (_visionFrameReady()) {
      _updatePlayState(_VideoPlayState.playing);
      return;
    }
    if (_playState != _VideoPlayState.playing) {
      await _probeFamilySnapshot(silent: true);
    }
  }

  void _handleStreamLoading() {
    if (!mounted || _playState == _VideoPlayState.playing) {
      return;
    }
    if (_playState == _VideoPlayState.failed) {
      _updatePlayState(_VideoPlayState.reconnecting);
      return;
    }
    if (_playState != _VideoPlayState.reconnecting) {
      _updatePlayState(_VideoPlayState.connecting);
    }
  }

  void _handleStreamFailure(String message) {
    if (!mounted) {
      return;
    }
    _updatePlayState(_VideoPlayState.failed, error: message);
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
    );
    await _refreshStreamHealth(silent: false);
  }

  Future<void> _switchQuality(_FamilyQualityMode nextMode) async {
    if (_qualityMode == nextMode) {
      return;
    }
    HapticFeedback.selectionClick();
    setState(() {
      _qualityMode = nextMode;
      _lastError = null;
    });
    await _restartVideo(manual: true);
  }

  _FamilyQualityMode _serverProfileToQuality(String? profile) {
    switch ((profile ?? '').trim().toLowerCase()) {
      case 'smooth':
        return _FamilyQualityMode.smooth;
      case 'quality':
        return _FamilyQualityMode.hd;
      default:
        return _FamilyQualityMode.smooth;
    }
  }

  String _qualityToServerProfile(_FamilyQualityMode mode) {
    switch (mode) {
      case _FamilyQualityMode.smooth:
        return 'smooth';
      case _FamilyQualityMode.balanced:
        return 'balanced';
      case _FamilyQualityMode.hd:
        return 'quality';
    }
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
      return 'No probe yet';
    }
    final diff = DateTime.now().difference(_lastProbeAt!);
    if (diff.inSeconds < 1) {
      return 'just now';
    }
    return '${diff.inSeconds}s ago';
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
      return 'Loading...';
    }
    final mode = '${setup['camera_source_mode'] ?? 'auto'}';
    if (mode == 'local') {
      return 'local camera #${setup['camera_local_index'] ?? 0}';
    }
    final ip = '${setup['camera_ip'] ?? ''}'.trim();
    final port = '${setup['camera_rtsp_port'] ?? ''}'.trim();
    final path =
        '${setup['camera_stream_rtsp_path'] ?? setup['camera_rtsp_path'] ?? ''}'
            .trim();
    if (ip.isEmpty) {
      return 'RTSP source not configured';
    }
    return '$ip:$port$path';
  }

  String _cameraHealthLabel() {
    final health = _cameraHealth;
    if (health == null) {
      return _cameraMetaLoading ? 'Checking camera...' : 'No data';
    }
    final configured = health['configured'] == true;
    final online = health['online'] == true;
    final error = '${health['error'] ?? ''}'.trim();
    if (!configured) {
      return 'Camera not configured';
    }
    if (online) {
      return 'Online';
    }
    if (error.isNotEmpty) {
      return 'Offline: $error';
    }
    return 'Unavailable';
  }

  String _playStateLabel() {
    switch (_playState) {
      case _VideoPlayState.connecting:
        return 'Connecting';
      case _VideoPlayState.playing:
        return 'Playing';
      case _VideoPlayState.failed:
        return 'Failed';
      case _VideoPlayState.reconnecting:
        return 'Reconnecting';
    }
  }

  Color _playStateColor() {
    switch (_playState) {
      case _VideoPlayState.connecting:
      case _VideoPlayState.reconnecting:
        return AppColors.warning;
      case _VideoPlayState.playing:
        return AppColors.success;
      case _VideoPlayState.failed:
        return AppColors.error;
    }
  }

  Map<String, dynamic>? _selectedFamilyProfileStatus() {
    final family = _cameraStreamStatus?['family'];
    if (family is! Map<String, dynamic>) {
      return null;
    }
    final profiles = family['profiles'];
    if (profiles is! Map<String, dynamic>) {
      return null;
    }
    final selected = profiles[_qualityMode.apiValue];
    return selected is Map<String, dynamic> ? selected : null;
  }

  String _streamMetric(String key) {
    final selected = _selectedFamilyProfileStatus();
    final value = selected?[key];
    if (value == null || '$value'.isEmpty) {
      return '--';
    }
    return '$value';
  }

  bool _visionFrameReady() {
    final source = _visionSourceStatus;
    if (source == null) {
      return false;
    }
    return source['running'] == true &&
        (source['main_connected'] == true ||
            source['analysis_connected'] == true);
  }

  String? _visionLatestFrameUrl() {
    final runtime = _visionRuntimeConfig;
    if (!_visionFrameReady() || runtime == null) {
      return null;
    }
    final baseUrl = '${runtime['base_url'] ?? ''}'.trim();
    final cameraId = '${runtime['camera_id'] ?? 'camera_01'}'.trim();
    if (baseUrl.isEmpty) {
      return null;
    }
    final normalizedBaseUrl = baseUrl.endsWith('/')
        ? baseUrl.substring(0, baseUrl.length - 1)
        : baseUrl;
    final normalizedCameraId = cameraId.isEmpty ? 'camera_01' : cameraId;
    return '$normalizedBaseUrl/stream/latest-frame.jpg?camera_id=$normalizedCameraId';
  }

  Future<void> _openCameraConfigSheet() async {
    if (_visionFrameReady()) {
      await showModalBottomSheet<void>(
        context: context,
        isScrollControlled: true,
        backgroundColor: Colors.transparent,
        builder: (sheetContext) {
          return _VisionSourceSheet(
            frameUrl: _visionLatestFrameUrl(),
            sourceStatus: _visionSourceStatus,
            runtimeConfig: _visionRuntimeConfig,
          );
        },
      );
      return;
    }

    final draft = _CameraConfigDraft.fromMap(_cameraSetup);
    final sourceMode = ValueNotifier<String>(draft.cameraSourceMode);
    final defaultQuality = ValueNotifier<_FamilyQualityMode>(
      _serverProfileToQuality(draft.cameraStreamProfile),
    );
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
    final qualityPathController =
        TextEditingController(text: draft.cameraStreamQualityPath);
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
              final messenger = ScaffoldMessenger.of(sheetContext);
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
                  'camera_stream_quality_path':
                      qualityPathController.text.trim(),
                  'camera_audio_rtsp_path': audioPathController.text.trim(),
                  'camera_onvif_port': int.parse(onvifPortController.text),
                  'camera_stream_profile':
                      _qualityToServerProfile(defaultQuality.value),
                };

                if (sourceMode.value == 'local') {
                  payload
                    ..remove('camera_ip')
                    ..remove('camera_user')
                    ..remove('camera_password')
                    ..remove('camera_rtsp_port')
                    ..remove('camera_rtsp_path')
                    ..remove('camera_stream_rtsp_path')
                    ..remove('camera_stream_quality_path')
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

                setState(() {
                  _qualityMode = defaultQuality.value;
                  _qualityInitializedFromServer = true;
                });

                navigator.pop();
                await _restartVideo(manual: true);
                if (!mounted) {
                  return;
                }
                messenger.showSnackBar(
                  const SnackBar(
                    content: Text(
                        'Camera source updated. Reconnecting family stream...'),
                  ),
                );
              } on DioException catch (error) {
                if (!mounted) {
                  return;
                }
                final detail = error.response?.data;
                final message = detail is Map<String, dynamic>
                    ? (detail['detail']?.toString() ??
                        error.message ??
                        'Save failed')
                    : (error.message ?? 'Save failed');
                messenger.showSnackBar(
                  SnackBar(content: Text('Save failed: $message')),
                );
              } finally {
                if (mounted) {
                  setSheetState(() {
                    saving = false;
                  });
                }
              }
            }

            Widget pathField({
              required TextEditingController controller,
              required String label,
            }) {
              return TextFormField(
                controller: controller,
                decoration: _inputDecoration(label),
                validator: (value) {
                  if (sourceMode.value == 'local') {
                    return null;
                  }
                  if ((value ?? '').trim().isEmpty) {
                    return 'Required';
                  }
                  return null;
                },
              );
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
                    child: ListView(
                      shrinkWrap: true,
                      children: <Widget>[
                        const Text(
                          'Camera Source',
                          style: TextStyle(
                            color: AppColors.textMain,
                            fontSize: 20,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        const SizedBox(height: 8),
                        const Text(
                          'Family view uses the clean raw MJPEG stream. You can change the normal stream path, HD stream path and default quality here without hardcoding RTSP URLs.',
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
                              decoration: _inputDecoration('Source mode'),
                              items: const <DropdownMenuItem<String>>[
                                DropdownMenuItem(
                                  value: 'rtsp',
                                  child: Text('RTSP camera'),
                                ),
                                DropdownMenuItem(
                                  value: 'auto',
                                  child: Text('Auto'),
                                ),
                                DropdownMenuItem(
                                  value: 'local',
                                  child: Text('Local camera'),
                                ),
                              ],
                              onChanged: (next) {
                                if (next != null) {
                                  sourceMode.value = next;
                                }
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
                                  decoration: _inputDecoration('Camera IP'),
                                  validator: (input) {
                                    if (!rtspEnabled) {
                                      return null;
                                    }
                                    return (input ?? '').trim().isEmpty
                                        ? 'Required'
                                        : null;
                                  },
                                ),
                                const SizedBox(height: 12),
                                TextFormField(
                                  controller: userController,
                                  enabled: rtspEnabled,
                                  decoration: _inputDecoration('Username'),
                                  validator: (input) {
                                    if (!rtspEnabled) {
                                      return null;
                                    }
                                    return (input ?? '').trim().isEmpty
                                        ? 'Required'
                                        : null;
                                  },
                                ),
                                const SizedBox(height: 12),
                                TextFormField(
                                  controller: passwordController,
                                  enabled: rtspEnabled,
                                  obscureText: true,
                                  decoration: _inputDecoration('Password'),
                                  validator: (input) {
                                    if (!rtspEnabled) {
                                      return null;
                                    }
                                    return (input ?? '').trim().isEmpty
                                        ? 'Required'
                                        : null;
                                  },
                                ),
                                const SizedBox(height: 12),
                                TextFormField(
                                  controller: rtspPortController,
                                  enabled: rtspEnabled,
                                  keyboardType: TextInputType.number,
                                  decoration: _inputDecoration('RTSP port'),
                                  validator: (input) {
                                    if (!rtspEnabled) {
                                      return null;
                                    }
                                    return int.tryParse((input ?? '').trim()) ==
                                            null
                                        ? 'Invalid port'
                                        : null;
                                  },
                                ),
                                const SizedBox(height: 12),
                                pathField(
                                  controller: rtspPathController,
                                  label: 'Snapshot / primary RTSP path',
                                ),
                                const SizedBox(height: 12),
                                pathField(
                                  controller: streamPathController,
                                  label: 'Normal stream path',
                                ),
                                const SizedBox(height: 12),
                                pathField(
                                  controller: qualityPathController,
                                  label: 'HD stream path',
                                ),
                                const SizedBox(height: 12),
                                pathField(
                                  controller: audioPathController,
                                  label: 'Audio path',
                                ),
                                const SizedBox(height: 12),
                                TextFormField(
                                  controller: onvifPortController,
                                  enabled: rtspEnabled,
                                  keyboardType: TextInputType.number,
                                  decoration: _inputDecoration('ONVIF port'),
                                  validator: (input) {
                                    if (!rtspEnabled) {
                                      return null;
                                    }
                                    return int.tryParse((input ?? '').trim()) ==
                                            null
                                        ? 'Invalid port'
                                        : null;
                                  },
                                ),
                              ],
                            );
                          },
                        ),
                        const SizedBox(height: 16),
                        const Text(
                          'Default family quality',
                          style: TextStyle(
                            color: AppColors.textMain,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        const SizedBox(height: 10),
                        ValueListenableBuilder<_FamilyQualityMode>(
                          valueListenable: defaultQuality,
                          builder: (_, value, __) {
                            return Wrap(
                              spacing: 10,
                              runSpacing: 10,
                              children: _FamilyQualityMode.values.map((mode) {
                                return ChoiceChip(
                                  label: Text(mode.label),
                                  selected: value == mode,
                                  onSelected: (_) =>
                                      defaultQuality.value = mode,
                                );
                              }).toList(),
                            );
                          },
                        ),
                        const SizedBox(height: 18),
                        Row(
                          children: <Widget>[
                            Expanded(
                              child: OutlinedButton(
                                onPressed: saving
                                    ? null
                                    : () => Navigator.of(sheetContext).pop(),
                                child: const Text('Cancel'),
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
                                    : const Text('Apply'),
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
    defaultQuality.dispose();
    hostController.dispose();
    userController.dispose();
    passwordController.dispose();
    rtspPortController.dispose();
    rtspPathController.dispose();
    streamPathController.dispose();
    qualityPathController.dispose();
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
    final visionFrameUrl = _visionLatestFrameUrl();
    final familyMetrics = _selectedFamilyProfileStatus();

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text(
          'Video',
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
              Icons.linked_camera_outlined,
              color: AppColors.textSub,
            ),
            tooltip: visionFrameUrl != null ? 'Vision source' : 'Camera source',
          ),
          IconButton(
            onPressed: () => _restartVideo(manual: true),
            icon: const Icon(Icons.refresh, color: AppColors.textSub),
            tooltip: 'Reconnect',
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: <Widget>[
          _InfoCard(
            title: 'Family Camera',
            children: <Widget>[
              _MetaRow(label: 'Target', value: _cameraTargetLabel()),
              const SizedBox(height: 8),
              _MetaRow(label: 'Camera', value: _cameraHealthLabel()),
              const SizedBox(height: 8),
              _MetaRow(
                label: 'Base URL',
                value: context.watch<ServerEndpointConfig>().origin,
              ),
              const SizedBox(height: 8),
              _MetaRow(label: 'Stream URL', value: streamUrl),
              const SizedBox(height: 8),
              _MetaRow(label: 'Probe URL', value: snapshotProbeUrl),
              const SizedBox(height: 8),
              _MetaRow(label: 'Mode', value: _qualityMode.label),
              const SizedBox(height: 8),
              _MetaRow(label: 'State', value: _playStateLabel()),
              const SizedBox(height: 8),
              _MetaRow(label: 'Last probe', value: _lastUpdatedLabel()),
            ],
          ),
          const SizedBox(height: 14),
          _InfoCard(
            title: 'Quality',
            subtitle:
                'Family playback stays on clean raw MJPEG. Switch quality without falling back to processed frames.',
            children: <Widget>[
              Wrap(
                spacing: 10,
                runSpacing: 10,
                children: _FamilyQualityMode.values.map((mode) {
                  final selected = mode == _qualityMode;
                  return ChoiceChip(
                    label: Text(mode.label),
                    selected: selected,
                    onSelected: (_) => _switchQuality(mode),
                    tooltip: mode.description,
                  );
                }).toList(),
              ),
              const SizedBox(height: 10),
              Text(
                _qualityMode.description,
                style: const TextStyle(
                  color: AppColors.textSub,
                  fontSize: 13,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          AspectRatio(
            aspectRatio: 16 / 9,
            child: ClipRRect(
              borderRadius: BorderRadius.circular(20),
              child: Stack(
                fit: StackFit.expand,
                children: <Widget>[
                  if (visionFrameUrl != null)
                    _VisionLatestFramePlayer(
                      frameUrl: visionFrameUrl,
                      reloadToken: _streamReloadToken,
                      onPlaying: () =>
                          _updatePlayState(_VideoPlayState.playing),
                      onError: _reportStreamError,
                    )
                  else
                    _FamilyMjpegPlayer(
                      streamUrl: streamUrl,
                      reloadToken: _streamReloadToken,
                      onLoading: _reportStreamLoading,
                      onError: _reportStreamError,
                    ),
                  Positioned(
                    left: 12,
                    top: 12,
                    child: _StatusBadge(
                      label: '${_playStateLabel()} · ${_qualityMode.label}',
                      color: _playStateColor(),
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
                  label: const Text('Refresh / Reconnect'),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: ElevatedButton.icon(
                  onPressed: _openCameraConfigSheet,
                  icon: Icon(
                    visionFrameUrl != null
                        ? Icons.linked_camera_outlined
                        : Icons.tune,
                  ),
                  label: Text(
                    visionFrameUrl != null ? 'Vision Source' : 'Camera Source',
                  ),
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
              'Debug',
              style: TextStyle(
                color: AppColors.textMain,
                fontWeight: FontWeight.bold,
              ),
            ),
            subtitle: const Text(
              'Collapsed by default. Open this only when you need diagnostics.',
              style: TextStyle(color: AppColors.textSub),
            ),
            children: <Widget>[
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    _MetaRow(
                      label: 'Request URL',
                      value: _lastRequestUrl ?? snapshotProbeUrl,
                    ),
                    const SizedBox(height: 8),
                    _MetaRow(
                      label: 'HTTP',
                      value: '${_lastStatusCode ?? '--'}',
                    ),
                    const SizedBox(height: 8),
                    _MetaRow(
                      label: 'Content-Type',
                      value: _lastContentType ?? '--',
                    ),
                    const SizedBox(height: 8),
                    _MetaRow(
                      label: 'Image bytes',
                      value: '${_lastImageBytes ?? '--'}',
                    ),
                    const SizedBox(height: 8),
                    _MetaRow(
                      label: 'Camera source',
                      value: _lastCameraSource ?? 'family-stream',
                    ),
                    const SizedBox(height: 8),
                    _MetaRow(
                      label: 'Quality',
                      value: _lastFamilyQuality ?? _qualityMode.apiValue,
                    ),
                    const SizedBox(height: 8),
                    _MetaRow(
                      label: 'Family source',
                      value: _lastFamilySource ?? '--',
                    ),
                    const SizedBox(height: 8),
                    _MetaRow(
                      label: 'Fallback',
                      value: _lastFallbackReason ?? '--',
                    ),
                    const SizedBox(height: 8),
                    _MetaRow(
                      label: 'Error',
                      value: _lastError ?? '--',
                    ),
                    const SizedBox(height: 12),
                    const Text(
                      'Family stream metrics',
                      style: TextStyle(
                        color: AppColors.textMain,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 8),
                    _MetaRow(
                      label: 'Profile URL',
                      value: streamUrl,
                    ),
                    const SizedBox(height: 8),
                    _MetaRow(
                      label: 'Active quality',
                      value: _streamMetric('active_quality'),
                    ),
                    const SizedBox(height: 8),
                    _MetaRow(
                      label: 'Source path',
                      value:
                          '${familyMetrics?['active_stream_path'] ?? familyMetrics?['active_url'] ?? '--'}',
                    ),
                    const SizedBox(height: 8),
                    _MetaRow(
                      label: 'Source type',
                      value: '${familyMetrics?['active_source_type'] ?? '--'}',
                    ),
                    const SizedBox(height: 8),
                    _MetaRow(
                      label: 'Raw size',
                      value:
                          '${_streamMetric('raw_frame_width')} x ${_streamMetric('raw_frame_height')}',
                    ),
                    const SizedBox(height: 8),
                    _MetaRow(
                      label: 'Output size',
                      value:
                          '${_streamMetric('output_width')} x ${_streamMetric('output_height')}',
                    ),
                    const SizedBox(height: 8),
                    _MetaRow(
                      label: 'FPS',
                      value:
                          'target ${_streamMetric('target_fps')} / source ${_streamMetric('source_fps')} / output ${_streamMetric('output_fps')}',
                    ),
                    const SizedBox(height: 8),
                    _MetaRow(
                      label: 'JPEG',
                      value:
                          'q=${_streamMetric('jpeg_quality')} latest=${_streamMetric('latest_jpeg_bytes')} avg=${_streamMetric('average_jpeg_bytes')}',
                    ),
                    const SizedBox(height: 8),
                    _MetaRow(
                      label: 'Encode',
                      value:
                          'latest ${_streamMetric('encode_ms')} ms / avg ${_streamMetric('average_encode_ms')} ms',
                    ),
                    const SizedBox(height: 8),
                    _MetaRow(
                      label: 'Fallback count',
                      value: _streamMetric('fallback_count'),
                    ),
                    const SizedBox(height: 8),
                    _MetaRow(
                      label: 'Fallback reason',
                      value: _streamMetric('fallback_reason'),
                    ),
                    const SizedBox(height: 8),
                    _MetaRow(
                      label: 'Main frame',
                      value: _streamMetric('last_main_frame_at'),
                    ),
                    const SizedBox(height: 8),
                    _MetaRow(
                      label: 'Encoded frame',
                      value: _streamMetric('last_encoded_frame_at'),
                    ),
                    const SizedBox(height: 8),
                    _MetaRow(
                      label: 'Processed debug',
                      value: _processedDebugUrl(),
                    ),
                    const SizedBox(height: 8),
                    _MetaRow(
                      label: 'Vision frame',
                      value: visionFrameUrl ?? '--',
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
                    const SizedBox(height: 12),
                    const Text(
                      'camera/stream-status',
                      style: TextStyle(
                        color: AppColors.textSub,
                        fontSize: 12,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 6),
                    SelectableText(
                      _prettyJson(_cameraStreamStatus),
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

class _FamilyMjpegPlayer extends StatefulWidget {
  final String streamUrl;
  final int reloadToken;
  final VoidCallback onLoading;
  final void Function(Object error) onError;

  const _FamilyMjpegPlayer({
    required this.streamUrl,
    required this.reloadToken,
    required this.onLoading,
    required this.onError,
  });

  @override
  State<_FamilyMjpegPlayer> createState() => _FamilyMjpegPlayerState();
}

class _FamilyMjpegPlayerState extends State<_FamilyMjpegPlayer> {
  @override
  Widget build(BuildContext context) {
    return Container(
      color: const Color(0xFF020617),
      child: Mjpeg(
        key: ValueKey<String>('${widget.streamUrl}|${widget.reloadToken}'),
        isLive: true,
        stream: widget.streamUrl,
        fit: BoxFit.cover,
        headers: const <String, String>{
          'Cache-Control': 'no-cache',
          'Pragma': 'no-cache',
        },
        loading: (context) {
          widget.onLoading();
          return const _VideoPlaceholder(
            icon: Icons.wifi_tethering_outlined,
            title: 'Connecting family stream...',
            subtitle: 'Using clean raw MJPEG playback',
            showSpinner: true,
          );
        },
        error: (context, error, stack) {
          widget.onError(error ?? StateError('MJPEG_STREAM_FAILED'));
          return _VideoPlaceholder(
            icon: Icons.videocam_off_outlined,
            title: 'Video connection failed',
            subtitle: '$error',
          );
        },
      ),
    );
  }
}

class _VisionLatestFramePlayer extends StatefulWidget {
  final String frameUrl;
  final int reloadToken;
  final VoidCallback onPlaying;
  final void Function(Object error) onError;

  const _VisionLatestFramePlayer({
    required this.frameUrl,
    required this.reloadToken,
    required this.onPlaying,
    required this.onError,
  });

  @override
  State<_VisionLatestFramePlayer> createState() =>
      _VisionLatestFramePlayerState();
}

class _VisionLatestFramePlayerState extends State<_VisionLatestFramePlayer> {
  Timer? _timer;
  int _frameToken = 0;
  Uint8List? _latestFrame;
  Object? _lastError;
  bool _loading = false;
  late final Dio _dio;

  @override
  void initState() {
    super.initState();
    _dio = Dio(
      BaseOptions(
        connectTimeout: const Duration(seconds: 2),
        receiveTimeout: const Duration(seconds: 2),
      ),
    );
    _fetchFrame();
    _startTimer();
  }

  @override
  void didUpdateWidget(covariant _VisionLatestFramePlayer oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.frameUrl != widget.frameUrl ||
        oldWidget.reloadToken != widget.reloadToken) {
      setState(() {
        _frameToken += 1;
        _latestFrame = null;
        _lastError = null;
      });
      _fetchFrame();
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    _dio.close(force: true);
    super.dispose();
  }

  void _startTimer() {
    _timer = Timer.periodic(const Duration(milliseconds: 250), (_) {
      if (!mounted) {
        return;
      }
      _fetchFrame();
    });
  }

  String _currentUrl() {
    final separator = widget.frameUrl.contains('?') ? '&' : '?';
    return '${widget.frameUrl}${separator}ts=${DateTime.now().millisecondsSinceEpoch}&frame=$_frameToken';
  }

  Future<void> _fetchFrame() async {
    if (_loading || !mounted) {
      return;
    }
    _loading = true;
    final nextToken = _frameToken + 1;
    try {
      final response = await _dio.get<List<dynamic>>(
        _currentUrl(),
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
        throw StateError('VISION_FRAME_EMPTY');
      }
      if (!mounted) {
        return;
      }
      setState(() {
        _frameToken = nextToken;
        _latestFrame = Uint8List.fromList(rawBytes.cast<int>());
        _lastError = null;
      });
      widget.onPlaying();
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _lastError = error;
      });
      widget.onError(error);
    } finally {
      _loading = false;
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_latestFrame == null) {
      return _VideoPlaceholder(
        icon: _lastError == null
            ? Icons.wifi_tethering_outlined
            : Icons.videocam_off_outlined,
        title: _lastError == null
            ? 'Connecting vision stream...'
            : 'Vision frame unavailable',
        subtitle: _lastError == null
            ? 'Using latest frame relay from vision subsystem'
            : '$_lastError',
        showSpinner: _lastError == null,
      );
    }
    return Container(
      color: const Color(0xFF020617),
      child: Image.memory(
        _latestFrame!,
        fit: BoxFit.cover,
        gaplessPlayback: true,
        errorBuilder: (context, error, stackTrace) => _VideoPlaceholder(
          icon: Icons.videocam_off_outlined,
          title: 'Vision frame unavailable',
          subtitle: '$error',
        ),
      ),
    );
  }
}

class _VisionSourceSheet extends StatelessWidget {
  final String? frameUrl;
  final Map<String, dynamic>? sourceStatus;
  final Map<String, dynamic>? runtimeConfig;

  const _VisionSourceSheet({
    required this.frameUrl,
    required this.sourceStatus,
    required this.runtimeConfig,
  });

  String _value(Object? value) {
    if (value == null || '$value'.trim().isEmpty) {
      return '--';
    }
    return '$value';
  }

  @override
  Widget build(BuildContext context) {
    return DraggableScrollableSheet(
      initialChildSize: 0.58,
      minChildSize: 0.38,
      maxChildSize: 0.78,
      builder: (context, controller) {
        return Container(
          decoration: const BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
          ),
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 20),
          child: ListView(
            controller: controller,
            children: <Widget>[
              Center(
                child: Container(
                  width: 42,
                  height: 4,
                  decoration: BoxDecoration(
                    color: AppColors.border,
                    borderRadius: BorderRadius.circular(999),
                  ),
                ),
              ),
              const SizedBox(height: 18),
              const Text(
                'Vision Source',
                style: TextStyle(
                  color: AppColors.textMain,
                  fontSize: 22,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 8),
              const Text(
                'The family video view is using the connected vision subsystem. Camera IP and password are not required here.',
                style: TextStyle(
                  color: AppColors.textSub,
                  fontSize: 14,
                  height: 1.45,
                ),
              ),
              const SizedBox(height: 18),
              _InfoCard(
                title: 'Active camera',
                children: <Widget>[
                  _MetaRow(
                    label: 'Camera',
                    value: _value(sourceStatus?['camera_id'] ??
                        runtimeConfig?['camera_id']),
                  ),
                  const SizedBox(height: 8),
                  _MetaRow(
                    label: 'Status',
                    value:
                        '${_value(sourceStatus?['main_stream_state'])} / connected=${_value(sourceStatus?['main_connected'])}',
                  ),
                  const SizedBox(height: 8),
                  _MetaRow(
                    label: 'FPS',
                    value: _value(sourceStatus?['main_capture_fps']),
                  ),
                  const SizedBox(height: 8),
                  _MetaRow(
                    label: 'Frame age',
                    value: '${_value(sourceStatus?['main_frame_age_ms'])} ms',
                  ),
                  const SizedBox(height: 8),
                  _MetaRow(
                    label: 'RTSP',
                    value: _value(sourceStatus?['main_rtsp_url_masked']),
                  ),
                  const SizedBox(height: 8),
                  _MetaRow(
                    label: 'Frame URL',
                    value: _value(frameUrl),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              SizedBox(
                height: 52,
                child: ElevatedButton(
                  onPressed: () => Navigator.of(context).pop(),
                  child: const Text('Done'),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _InfoCard extends StatelessWidget {
  final String title;
  final String? subtitle;
  final List<Widget> children;

  const _InfoCard({
    required this.title,
    this.subtitle,
    required this.children,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
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
          Text(
            title,
            style: const TextStyle(
              color: AppColors.textMain,
              fontSize: 20,
              fontWeight: FontWeight.bold,
            ),
          ),
          if (subtitle != null) ...<Widget>[
            const SizedBox(height: 8),
            Text(
              subtitle!,
              style: const TextStyle(
                color: AppColors.textSub,
                fontSize: 13,
                height: 1.5,
              ),
            ),
          ],
          const SizedBox(height: 14),
          ...children,
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
          width: 96,
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
  final String cameraStreamQualityPath;
  final String cameraAudioRtspPath;
  final int cameraOnvifPort;
  final String cameraStreamProfile;

  const _CameraConfigDraft({
    required this.cameraSourceMode,
    required this.cameraIp,
    required this.cameraUser,
    required this.cameraPassword,
    required this.cameraRtspPort,
    required this.cameraRtspPath,
    required this.cameraStreamRtspPath,
    required this.cameraStreamQualityPath,
    required this.cameraAudioRtspPath,
    required this.cameraOnvifPort,
    required this.cameraStreamProfile,
  });

  factory _CameraConfigDraft.fromMap(Map<String, dynamic>? json) {
    return _CameraConfigDraft(
      cameraSourceMode: '${json?['camera_source_mode'] ?? 'rtsp'}',
      cameraIp: '${json?['camera_ip'] ?? ''}',
      cameraUser: '${json?['camera_user'] ?? 'admin'}',
      cameraPassword: '${json?['camera_password'] ?? ''}',
      cameraRtspPort: _asInt(json?['camera_rtsp_port'], fallback: 10554),
      cameraRtspPath: '${json?['camera_rtsp_path'] ?? '/tcp/av0_0'}',
      cameraStreamRtspPath:
          '${json?['camera_stream_rtsp_path'] ?? '/tcp/av0_1'}',
      cameraStreamQualityPath:
          '${json?['camera_stream_quality_path'] ?? '/tcp/av0_0'}',
      cameraAudioRtspPath: '${json?['camera_audio_rtsp_path'] ?? '/tcp/av0_1'}',
      cameraOnvifPort: _asInt(json?['camera_onvif_port'], fallback: 10080),
      cameraStreamProfile: '${json?['camera_stream_profile'] ?? 'balanced'}',
    );
  }

  static int _asInt(Object? value, {required int fallback}) {
    if (value is int) {
      return value;
    }
    return int.tryParse('$value') ?? fallback;
  }
}
