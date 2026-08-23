import 'package:flutter/foundation.dart';
import 'package:flutter_3d_controller/flutter_3d_controller.dart';

import '../models/robot_animation_mapper.dart';
import '../models/robot_status.dart';

class Robot3DController {
  final Flutter3DController viewer;
  final Duration pollingInterval;
  final int maxPollingAttempts;

  List<String> _availableAnimations = const <String>[];
  bool _isLoaded = false;
  bool _isDisposed = false;
  RobotMode _pendingMode = RobotMode.idle;
  String? _activeAnimation;

  Robot3DController({
    Flutter3DController? viewer,
    this.pollingInterval = const Duration(milliseconds: 500),
    this.maxPollingAttempts = 60,
  }) : viewer = viewer ?? Flutter3DController();

  bool get isLoaded => _isLoaded;
  List<String> get availableAnimations => _availableAnimations;
  String? get activeAnimation => _activeAnimation;

  Future<bool> prepare(RobotMode mode) async {
    _pendingMode = mode;
    for (var attempt = 0; attempt < maxPollingAttempts; attempt++) {
      if (_isDisposed) {
        return false;
      }

      try {
        final animations = await viewer.getAvailableAnimations();
        if (_isDisposed) {
          return false;
        }
        _availableAnimations = List<String>.unmodifiable(animations);
        if (_hasRequiredAnimations(animations)) {
          _isLoaded = true;
          debugPrint('Go2 GLB available animations: $_availableAnimations');
          _playPendingMode();
          return true;
        }
      } catch (_) {
        _availableAnimations = const <String>[];
      }

      if (attempt + 1 < maxPollingAttempts) {
        await Future<void>.delayed(pollingInterval);
      }
    }

    debugPrint(
      'Go2 GLB did not expose required animations after '
      '$maxPollingAttempts attempts: $_availableAnimations',
    );
    return false;
  }

  void syncMode(RobotMode mode) {
    _pendingMode = mode;
    if (!_isLoaded) {
      return;
    }

    _playPendingMode();
  }

  void _playPendingMode() {
    final animationName = RobotAnimationMapper.resolve(
      mode: _pendingMode,
      availableAnimations: _availableAnimations,
    );

    if (animationName == null) {
      if (_activeAnimation != null) {
        viewer.pauseAnimation();
        _activeAnimation = null;
      }
      return;
    }

    if (_activeAnimation == animationName) {
      return;
    }

    viewer.playAnimation(animationName: animationName);
    _activeAnimation = animationName;
  }

  bool _hasRequiredAnimations(List<String> animations) {
    final names = animations.map((name) => name.toLowerCase()).toSet();
    return names.contains('idle') && names.contains('walk');
  }

  void resetCamera() {
    if (_isLoaded) {
      viewer.resetCameraOrbit();
      viewer.resetCameraTarget();
    }
  }

  void dispose() {
    _isDisposed = true;
    _availableAnimations = const <String>[];
    _activeAnimation = null;
    _isLoaded = false;
  }
}
