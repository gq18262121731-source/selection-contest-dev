enum RobotMode {
  offline,
  idle,
  companionStarting,
  following,
  targetLost,
  suspectedFall,
  monitoring,
  recovering,
  resolved,
}

extension RobotModePresentation on RobotMode {
  String get apiValue {
    switch (this) {
      case RobotMode.offline:
        return 'offline';
      case RobotMode.idle:
        return 'idle';
      case RobotMode.companionStarting:
        return 'companion_starting';
      case RobotMode.following:
        return 'following';
      case RobotMode.targetLost:
        return 'target_lost';
      case RobotMode.suspectedFall:
        return 'suspected_fall';
      case RobotMode.monitoring:
        return 'monitoring';
      case RobotMode.recovering:
        return 'recovering';
      case RobotMode.resolved:
        return 'resolved';
    }
  }

  String get label {
    switch (this) {
      case RobotMode.offline:
        return '离线';
      case RobotMode.idle:
        return '待机';
      case RobotMode.companionStarting:
        return '准备伴随';
      case RobotMode.following:
        return '陪伴中';
      case RobotMode.targetLost:
        return '目标暂时丢失';
      case RobotMode.suspectedFall:
        return '正在核验异常';
      case RobotMode.monitoring:
        return '风险监护中';
      case RobotMode.recovering:
        return '恢复确认中';
      case RobotMode.resolved:
        return '事件已解除';
    }
  }

  String get description {
    switch (this) {
      case RobotMode.offline:
        return '机器人暂时离线，数字分身保持可查看';
      case RobotMode.idle:
        return '机器人已连接，当前没有执行中的任务';
      case RobotMode.companionStarting:
        return '正在确认陪伴任务和目标位置';
      case RobotMode.following:
        return '正在跟随老人执行陪伴任务';
      case RobotMode.targetLost:
        return '暂时没有获取到目标位置';
      case RobotMode.suspectedFall:
        return '正在核验视觉异常，暂未确认风险';
      case RobotMode.monitoring:
        return '已进入现场安全监护状态';
      case RobotMode.recovering:
        return '正在确认老人是否恢复站立';
      case RobotMode.resolved:
        return '风险事件已解除，等待恢复陪伴';
    }
  }

  String get animationName {
    switch (this) {
      case RobotMode.following:
        return 'Walk';
      case RobotMode.offline:
      case RobotMode.idle:
      case RobotMode.companionStarting:
      case RobotMode.targetLost:
      case RobotMode.suspectedFall:
      case RobotMode.monitoring:
      case RobotMode.recovering:
      case RobotMode.resolved:
        return 'Idle';
    }
  }

  bool get isRiskState =>
      this == RobotMode.suspectedFall || this == RobotMode.monitoring;

  bool get isConnected => this != RobotMode.offline;

  static RobotMode fromApiValue(String? value) {
    switch (value?.trim().toLowerCase()) {
      case 'idle':
        return RobotMode.idle;
      case 'companion_starting':
      case 'companionstarting':
        return RobotMode.companionStarting;
      case 'following':
        return RobotMode.following;
      case 'target_lost':
      case 'targetlost':
        return RobotMode.targetLost;
      case 'suspected_fall':
      case 'suspectedfall':
        return RobotMode.suspectedFall;
      case 'monitoring':
        return RobotMode.monitoring;
      case 'recovering':
        return RobotMode.recovering;
      case 'resolved':
        return RobotMode.resolved;
      case 'offline':
      default:
        return RobotMode.offline;
    }
  }
}

class RobotStatus {
  static const modelAssetPath = 'assets/models/go2/go2_mobile.glb';

  final String robotId;
  final RobotMode mode;
  final bool connected;
  final int? battery;
  final double? targetDistance;
  final String task;
  final String visionState;
  final String elderState;
  final Duration eventDuration;
  final bool isMock;

  const RobotStatus({
    required this.robotId,
    required this.mode,
    required this.connected,
    required this.battery,
    required this.targetDistance,
    required this.task,
    required this.visionState,
    required this.elderState,
    required this.eventDuration,
    required this.isMock,
  });

  factory RobotStatus.demo({
    RobotMode mode = RobotMode.following,
    String robotId = 'go2_01',
  }) {
    return RobotStatus(
      robotId: robotId,
      mode: mode,
      connected: mode.isConnected,
      battery: 76,
      targetDistance: mode == RobotMode.following ? 1.42 : null,
      task: mode == RobotMode.following ? '散步陪伴' : '安全监护',
      visionState: mode.isRiskState ? 'FALL' : 'NON_FALL',
      elderState: mode.isRiskState ? '疑似跌倒' : '正常',
      eventDuration:
          mode.isRiskState ? const Duration(seconds: 12) : Duration.zero,
      isMock: true,
    );
  }

  factory RobotStatus.fromJson(Map<String, dynamic> json) {
    final mode = RobotModePresentation.fromApiValue(json['mode'] as String?);
    final rawDistance = json['target_distance'];
    final rawBattery = json['battery'];
    return RobotStatus(
      robotId: json['robot_id'] as String? ?? 'go2_01',
      mode: mode,
      connected: json['connected'] as bool? ?? mode.isConnected,
      battery: rawBattery is num ? rawBattery.toInt() : null,
      targetDistance: rawDistance is num ? rawDistance.toDouble() : null,
      task: json['task'] as String? ?? '--',
      visionState: json['vision_state'] as String? ?? 'UNKNOWN',
      elderState: json['elder_state'] as String? ?? '未知',
      eventDuration: Duration(
        seconds: (json['event_duration_seconds'] as num?)?.toInt() ?? 0,
      ),
      isMock: false,
    );
  }

  RobotStatus copyWith({
    String? robotId,
    RobotMode? mode,
    bool? connected,
    int? battery,
    double? targetDistance,
    String? task,
    String? visionState,
    String? elderState,
    Duration? eventDuration,
    bool? isMock,
  }) {
    return RobotStatus(
      robotId: robotId ?? this.robotId,
      mode: mode ?? this.mode,
      connected: connected ?? this.connected,
      battery: battery ?? this.battery,
      targetDistance: targetDistance ?? this.targetDistance,
      task: task ?? this.task,
      visionState: visionState ?? this.visionState,
      elderState: elderState ?? this.elderState,
      eventDuration: eventDuration ?? this.eventDuration,
      isMock: isMock ?? this.isMock,
    );
  }
}
