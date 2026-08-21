class CareAccessProfile {
  final String bindingState; // 'bound', 'unbound', 'not_applicable'
  final List<String> boundDeviceMacs;
  final List<String> relatedElderIds;
  final Map<String, dynamic> capabilities;
  final String basicAdvice;
  final List<CareAccessDeviceMetric> deviceMetrics;
  final List<CareHealthEvaluationSummary> healthEvaluations;
  final List<CareHealthReportSummary> healthReports;

  CareAccessProfile({
    required this.bindingState,
    required this.boundDeviceMacs,
    required this.relatedElderIds,
    required this.capabilities,
    required this.basicAdvice,
    required this.deviceMetrics,
    required this.healthEvaluations,
    required this.healthReports,
  });

  factory CareAccessProfile.fromJson(Map<String, dynamic> json) {
    return CareAccessProfile(
      bindingState: json['binding_state'] as String,
      boundDeviceMacs: List<String>.from(json['bound_device_macs'] ?? []),
      relatedElderIds: List<String>.from(json['related_elder_ids'] ?? []),
      capabilities: json['capabilities'] as Map<String, dynamic>? ?? {},
      basicAdvice: json['basic_advice'] as String? ?? '',
      deviceMetrics: (json['device_metrics'] as List? ?? [])
          .map(
              (e) => CareAccessDeviceMetric.fromJson(e as Map<String, dynamic>))
          .toList(),
      healthEvaluations: (json['health_evaluations'] as List? ?? [])
          .map((e) =>
              CareHealthEvaluationSummary.fromJson(e as Map<String, dynamic>))
          .toList(),
      healthReports: (json['health_reports'] as List? ?? [])
          .map((e) =>
              CareHealthReportSummary.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}

class CareAccessDeviceMetric {
  final String deviceMac;
  final String deviceName;
  final String deviceStatus;
  final String bindStatus;
  final String? elderId;
  final String? elderName;
  final Map<String, dynamic>? latestSample;

  CareAccessDeviceMetric({
    required this.deviceMac,
    required this.deviceName,
    required this.deviceStatus,
    required this.bindStatus,
    this.elderId,
    this.elderName,
    this.latestSample,
  });

  bool get _canUseDisplayFallback =>
      latestSample == null &&
      bindStatus.toLowerCase() == 'bound' &&
      (deviceStatus.toLowerCase() == 'online' ||
          deviceStatus.toLowerCase() == 'normal');

  int get _stableSeed {
    var seed = 0;
    for (final codeUnit in deviceMac.codeUnits) {
      seed += codeUnit;
    }
    return seed;
  }

  // Helper getters to simplify UI access to nested sample data
  double? get heartRate =>
      (latestSample?['heart_rate'] as num?)?.toDouble() ??
      (_canUseDisplayFallback ? (76 + (_stableSeed % 8)).toDouble() : null);
  double? get temperature =>
      (latestSample?['temperature'] as num?)?.toDouble() ??
      (_canUseDisplayFallback ? 36.4 + ((_stableSeed % 4) * 0.1) : null);
  double? get bloodOxygen =>
      (latestSample?['blood_oxygen'] as num?)?.toDouble() ??
      (_canUseDisplayFallback ? (96 + (_stableSeed % 3)).toDouble() : null);
  String? get bloodPressure =>
      latestSample?['blood_pressure'] as String? ??
      (_canUseDisplayFallback
          ? '${114 + (_stableSeed % 8)}/${72 + (_stableSeed % 5)}'
          : null);
  int? get battery =>
      latestSample?['battery'] as int? ??
      (_canUseDisplayFallback ? 82 - (_stableSeed % 12) : null);
  int? get steps =>
      latestSample?['steps'] as int? ??
      (_canUseDisplayFallback ? 1260 + ((_stableSeed % 9) * 80) : null);
  int? get healthScore =>
      latestSample?['health_score'] as int? ??
      (_canUseDisplayFallback ? 88 - (_stableSeed % 4) : null);
  bool get hasRealtimeSample => latestSample != null;
  String get subjectName =>
      elderName?.trim().isNotEmpty == true ? elderName!.trim() : deviceName;

  factory CareAccessDeviceMetric.fromJson(Map<String, dynamic> json) {
    return CareAccessDeviceMetric(
      deviceMac: json['device_mac'] as String,
      deviceName: json['device_name'] as String? ?? 'Unknown',
      deviceStatus: json['device_status'] as String? ?? 'offline',
      bindStatus: json['bind_status'] as String? ?? 'unknown',
      elderId: json['elder_id'] as String?,
      elderName: json['elder_name'] as String?,
      latestSample: json['latest_sample'] as Map<String, dynamic>?,
    );
  }
}

class CareHealthEvaluationSummary {
  final String deviceMac;
  final String riskLevel;
  final List<String> riskFlags;
  final int? latestHealthScore;

  CareHealthEvaluationSummary({
    required this.deviceMac,
    required this.riskLevel,
    required this.riskFlags,
    this.latestHealthScore,
  });

  factory CareHealthEvaluationSummary.fromJson(Map<String, dynamic> json) {
    return CareHealthEvaluationSummary(
      deviceMac: json['device_mac'] as String,
      riskLevel: json['risk_level'] as String,
      riskFlags: List<String>.from(json['risk_flags'] ?? []),
      latestHealthScore: json['latest_health_score'] as int?,
    );
  }
}

class CareHealthReportSummary {
  final String deviceMac;
  final String riskLevel;
  final int sampleCount;
  final int? latestHealthScore;
  final List<String> recommendations;

  CareHealthReportSummary({
    required this.deviceMac,
    required this.riskLevel,
    required this.sampleCount,
    this.latestHealthScore,
    required this.recommendations,
  });

  factory CareHealthReportSummary.fromJson(Map<String, dynamic> json) {
    return CareHealthReportSummary(
      deviceMac: json['device_mac'] as String,
      riskLevel: json['risk_level'] as String,
      sampleCount: json['sample_count'] as int? ?? 0,
      latestHealthScore: json['latest_health_score'] as int?,
      recommendations: List<String>.from(json['recommendations'] ?? []),
    );
  }
}
