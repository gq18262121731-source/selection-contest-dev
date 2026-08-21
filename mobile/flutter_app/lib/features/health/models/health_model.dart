class HealthData {
  final String deviceMac;
  final DateTime timestamp;
  final double? heartRate;
  final double? temperature;
  final double? bloodOxygen;
  final String? bloodPressure;
  final int? battery;
  final bool sosFlag;
  final int? steps;
  final int? healthScore;

  HealthData({
    required this.deviceMac,
    required this.timestamp,
    this.heartRate,
    this.temperature,
    this.bloodOxygen,
    this.bloodPressure,
    this.battery,
    this.sosFlag = false,
    this.steps,
    this.healthScore,
  });

  factory HealthData.fromJson(Map<String, dynamic> json) {
    return HealthData(
      deviceMac: json['device_mac'] as String? ?? '',
      timestamp: json['timestamp'] != null
          ? DateTime.parse(json['timestamp'] as String)
          : DateTime.now(),
      heartRate: (json['heart_rate'] as num?)?.toDouble(),
      temperature: (json['temperature'] as num?)?.toDouble(),
      bloodOxygen: (json['blood_oxygen'] as num?)?.toDouble(),
      bloodPressure: json['blood_pressure'] as String?,
      battery: json['battery'] as int?,
      sosFlag: json['sos_flag'] == true || (json['sos_value'] as num? ?? 0) > 0,
      steps: json['steps'] as int?,
      healthScore: json['health_score'] as int?,
    );
  }

  HealthData mergeWith(HealthData incoming) {
    return HealthData(
      deviceMac: incoming.deviceMac.isNotEmpty ? incoming.deviceMac : deviceMac,
      timestamp: incoming.timestamp,
      heartRate: _preferPositiveNumber(heartRate, incoming.heartRate),
      temperature: _preferPositiveNumber(temperature, incoming.temperature),
      bloodOxygen: _preferPositiveNumber(bloodOxygen, incoming.bloodOxygen),
      bloodPressure:
          _preferBloodPressure(bloodPressure, incoming.bloodPressure),
      battery: _preferIncrementalInt(battery, incoming.battery),
      sosFlag: incoming.sosFlag,
      steps: _preferIncrementalInt(steps, incoming.steps),
      healthScore: _preferIncrementalInt(healthScore, incoming.healthScore),
    );
  }

  static double? _preferPositiveNumber(double? previous, double? incoming) {
    if (incoming != null && incoming > 0) return incoming;
    return previous ?? incoming;
  }

  static int? _preferIncrementalInt(int? previous, int? incoming) {
    if (incoming != null && incoming > 0) return incoming;
    return previous ?? incoming;
  }

  static String? _preferBloodPressure(String? previous, String? incoming) {
    return _normalizeBloodPressure(incoming) ??
        _normalizeBloodPressure(previous);
  }

  static String? _normalizeBloodPressure(String? value) {
    if (value == null || value.trim().isEmpty) return null;
    final parts = value.split('/');
    if (parts.length != 2) return null;
    final systolic = int.tryParse(parts[0].trim());
    final diastolic = int.tryParse(parts[1].trim());
    if (systolic == null || diastolic == null) return null;
    if (systolic <= 0 || diastolic <= 0) return null;
    return '$systolic/$diastolic';
  }
}
