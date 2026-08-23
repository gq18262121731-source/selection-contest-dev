import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_3d_controller/flutter_3d_controller.dart';

import 'package:ai_health_iot_flutter/features/robot/controllers/robot_3d_controller.dart';
import 'package:ai_health_iot_flutter/features/robot/models/robot_animation_mapper.dart';
import 'package:ai_health_iot_flutter/features/robot/models/robot_status.dart';

void main() {
  group('RobotMode', () {
    test('maps API values and labels consistently', () {
      expect(
        RobotModePresentation.fromApiValue('following'),
        RobotMode.following,
      );
      expect(
        RobotModePresentation.fromApiValue('suspected_fall'),
        RobotMode.suspectedFall,
      );
      expect(RobotMode.monitoring.label, '风险监护中');
      expect(RobotMode.following.animationName, 'Walk');
      expect(RobotMode.monitoring.animationName, 'Idle');
    });

    test('unknown API values degrade to offline', () {
      expect(
        RobotModePresentation.fromApiValue('future_mode'),
        RobotMode.offline,
      );
    });
  });

  group('RobotAnimationMapper', () {
    test('uses exact animation names when available', () {
      expect(
        RobotAnimationMapper.resolve(
          mode: RobotMode.following,
          availableAnimations: ['Idle', 'Walk'],
        ),
        'Walk',
      );
    });

    test('falls back safely when the requested animation is absent', () {
      expect(
        RobotAnimationMapper.resolve(
          mode: RobotMode.monitoring,
          availableAnimations: ['Walk', 'Idle'],
        ),
        'Idle',
      );
      expect(
        RobotAnimationMapper.resolve(
          mode: RobotMode.following,
          availableAnimations: const [],
        ),
        isNull,
      );
    });
  });

  group('Robot3DController', () {
    test('polls until both GLB animations are available', () async {
      final viewer = _FakeFlutter3DController([
        const [],
        const ['Idle'],
        const ['Idle', 'Walk'],
      ]);
      final controller = Robot3DController(
        viewer: viewer,
        pollingInterval: Duration.zero,
        maxPollingAttempts: 3,
      );

      expect(await controller.prepare(RobotMode.following), isTrue);
      expect(controller.availableAnimations, ['Idle', 'Walk']);
      expect(controller.activeAnimation, 'Walk');
      expect(viewer.queryCount, 3);
      expect(viewer.playedAnimations, ['Walk']);
    });

    test('switches Idle and Walk 20 times without duplicate playback',
        () async {
      final viewer = _FakeFlutter3DController([
        const ['Idle', 'Walk'],
      ]);
      final controller = Robot3DController(
        viewer: viewer,
        pollingInterval: Duration.zero,
        maxPollingAttempts: 1,
      );

      expect(await controller.prepare(RobotMode.idle), isTrue);
      for (var index = 0; index < 20; index++) {
        controller.syncMode(
          index.isEven ? RobotMode.following : RobotMode.idle,
        );
      }
      controller.syncMode(RobotMode.idle);

      expect(viewer.playedAnimations.length, 21);
      expect(viewer.playedAnimations.first, 'Idle');
      expect(viewer.playedAnimations.last, 'Idle');
      expect(
          viewer.playedAnimations.where((name) => name == 'Walk').length, 10);
      expect(
          viewer.playedAnimations.where((name) => name == 'Idle').length, 11);

      controller.dispose();
      expect(controller.isLoaded, isFalse);
      expect(controller.availableAnimations, isEmpty);
      expect(controller.activeAnimation, isNull);
    });

    test('reports failure when required clips never become available',
        () async {
      final viewer = _FakeFlutter3DController([
        const [],
        const ['Idle'],
      ]);
      final controller = Robot3DController(
        viewer: viewer,
        pollingInterval: Duration.zero,
        maxPollingAttempts: 2,
      );

      expect(await controller.prepare(RobotMode.following), isFalse);
      expect(controller.isLoaded, isFalse);
      expect(viewer.playedAnimations, isEmpty);
    });

    test('does not start playback after disposal during preparation', () async {
      final animations = Completer<List<String>>();
      final viewer = _DelayedFlutter3DController(animations.future);
      final controller = Robot3DController(
        viewer: viewer,
        pollingInterval: Duration.zero,
        maxPollingAttempts: 1,
      );

      final preparation = controller.prepare(RobotMode.following);
      controller.dispose();
      animations.complete(const ['Idle', 'Walk']);

      expect(await preparation, isFalse);
      expect(viewer.playedAnimations, isEmpty);
    });
  });

  test('parses a robot status payload without UI concerns', () {
    final status = RobotStatus.fromJson({
      'robot_id': 'go2_01',
      'connected': true,
      'mode': 'following',
      'battery': 76,
      'target_distance': 1.42,
      'task': 'outdoor_companion',
      'vision_state': 'NON_FALL',
      'elder_state': 'normal',
    });

    expect(status.robotId, 'go2_01');
    expect(status.mode, RobotMode.following);
    expect(status.battery, 76);
    expect(status.targetDistance, 1.42);
    expect(status.isMock, isFalse);
  });
}

class _FakeFlutter3DController extends Flutter3DController {
  final List<List<String>> responses;
  final List<String> playedAnimations = [];
  int queryCount = 0;

  _FakeFlutter3DController(this.responses);

  @override
  Future<List<String>> getAvailableAnimations() async {
    final index =
        queryCount < responses.length ? queryCount : responses.length - 1;
    queryCount++;
    return responses[index];
  }

  @override
  void playAnimation({String? animationName}) {
    if (animationName != null) {
      playedAnimations.add(animationName);
    }
  }
}

class _DelayedFlutter3DController extends Flutter3DController {
  final Future<List<String>> response;
  final List<String> playedAnimations = [];

  _DelayedFlutter3DController(this.response);

  @override
  Future<List<String>> getAvailableAnimations() => response;

  @override
  void playAnimation({String? animationName}) {
    if (animationName != null) {
      playedAnimations.add(animationName);
    }
  }
}
