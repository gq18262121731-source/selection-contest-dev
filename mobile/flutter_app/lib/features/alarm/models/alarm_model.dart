class AlarmRecord {
  final String id;
  final String deviceMac;
  final String alarmType;
  final String alarmLevel;
  final int? alarmPriority;
  final String message;
  final String createdAt;
  bool acknowledged;
  final double? anomalyProbability;

  AlarmRecord({
    required this.id,
    required this.deviceMac,
    required this.alarmType,
    required this.alarmLevel,
    this.alarmPriority,
    required this.message,
    required this.createdAt,
    this.acknowledged = false,
    this.anomalyProbability,
  });

  factory AlarmRecord.fromJson(Map<String, dynamic> json) {
    final rawLevel = json['alarm_level'];
    return AlarmRecord(
      id: json['id'] as String,
      deviceMac: json['device_mac'] as String,
      alarmType: json['alarm_type'] as String,
      alarmLevel: _normalizeAlarmLevel(rawLevel),
      alarmPriority: _parseAlarmPriority(rawLevel),
      message: json['message'] as String? ?? '',
      createdAt: json['created_at'] as String,
      acknowledged: json['acknowledged'] == true,
      anomalyProbability: (json['anomaly_probability'] as num?)?.toDouble(),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'device_mac': deviceMac,
      'alarm_type': alarmType,
      'alarm_level': alarmPriority ?? alarmLevel,
      'message': message,
      'created_at': createdAt,
      'acknowledged': acknowledged,
      'anomaly_probability': anomalyProbability,
    };
  }

  bool get isSos => alarmType.toLowerCase() == 'sos';

  bool get isCritical =>
      alarmLevel == 'sos' ||
      alarmLevel == 'critical' ||
      ((alarmPriority ?? 99) <= 2);

  DateTime? get createdAtDateTime {
    final parsed = DateTime.tryParse(createdAt);
    return parsed?.toLocal();
  }

  String get createdAtDisplay {
    final parsed = createdAtDateTime;
    if (parsed == null) {
      return createdAt;
    }
    return _formatDateTime(parsed);
  }

  String get createdDateDisplay {
    final parsed = createdAtDateTime;
    if (parsed == null) {
      return createdAt.split('T').first;
    }
    return _formatDate(parsed);
  }

  static int? _parseAlarmPriority(dynamic rawLevel) {
    if (rawLevel is num) {
      return rawLevel.toInt();
    }
    if (rawLevel is String) {
      return int.tryParse(rawLevel);
    }
    return null;
  }

  static String _normalizeAlarmLevel(dynamic rawLevel) {
    if (rawLevel is num) {
      return _levelFromPriority(rawLevel.toInt());
    }
    if (rawLevel is String) {
      final numeric = int.tryParse(rawLevel);
      if (numeric != null) {
        return _levelFromPriority(numeric);
      }
      return rawLevel.toLowerCase();
    }
    return 'info';
  }

  static String _levelFromPriority(int priority) {
    switch (priority) {
      case 1:
        return 'sos';
      case 2:
        return 'critical';
      case 3:
        return 'warning';
      default:
        return 'info';
    }
  }

  static String _formatDateTime(DateTime value) {
    return '${_formatDate(value)} ${_twoDigits(value.hour)}:${_twoDigits(value.minute)}:${_twoDigits(value.second)}';
  }

  static String _formatDate(DateTime value) {
    return '${value.year}-${_twoDigits(value.month)}-${_twoDigits(value.day)}';
  }

  static String _twoDigits(int value) {
    return value.toString().padLeft(2, '0');
  }
}

class AlarmQueueItem {
  final double score;
  final AlarmRecord alarm;

  AlarmQueueItem({
    required this.score,
    required this.alarm,
  });

  factory AlarmQueueItem.fromJson(Map<String, dynamic> json) {
    return AlarmQueueItem(
      score: (json['score'] as num?)?.toDouble() ?? 0.0,
      alarm: AlarmRecord.fromJson(json['alarm'] as Map<String, dynamic>),
    );
  }
}

class MobilePushRecord {
  final String id;
  final String title;
  final String body;
  final String createdAt;

  MobilePushRecord({
    required this.id,
    required this.title,
    required this.body,
    required this.createdAt,
  });

  factory MobilePushRecord.fromJson(Map<String, dynamic> json) {
    return MobilePushRecord(
      id: json['id'] as String,
      title: json['title'] as String,
      body: json['body'] as String,
      createdAt: json['created_at'] as String,
    );
  }
}
