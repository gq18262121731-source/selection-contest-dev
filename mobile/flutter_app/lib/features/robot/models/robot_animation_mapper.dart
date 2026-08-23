import 'robot_status.dart';

class RobotAnimationMapper {
  const RobotAnimationMapper._();

  static String? resolve({
    required RobotMode mode,
    required List<String> availableAnimations,
  }) {
    if (availableAnimations.isEmpty) {
      return null;
    }

    return _firstMatching(availableAnimations, [mode.animationName, 'Idle']);
  }

  static String? _firstMatching(
    List<String> available,
    List<String> candidates,
  ) {
    for (final candidate in candidates) {
      for (final animation in available) {
        if (animation.toLowerCase() == candidate.toLowerCase()) {
          return animation;
        }
      }
    }
    return null;
  }
}
