class HealthSample {
  final String deviceMac;
  final String timestamp;
  final int heartRate;
  final double temperature;
  final int bloodOxygen;
  final String bloodPressure;
  final int battery;
  final bool sosFlag;
  final int? healthScore;

  const HealthSample({
    required this.deviceMac,
    required this.timestamp,
    required this.heartRate,
    required this.temperature,
    required this.bloodOxygen,
    required this.bloodPressure,
    required this.battery,
    required this.sosFlag,
    required this.healthScore,
  });

  factory HealthSample.fromJson(Map<String, dynamic> json) {
    return HealthSample(
      deviceMac: json['device_mac'] as String,
      timestamp: json['timestamp'] as String,
      heartRate: json['heart_rate'] as int,
      temperature: (json['temperature'] as num).toDouble(),
      bloodOxygen: json['blood_oxygen'] as int,
      bloodPressure: json['blood_pressure'] as String,
      battery: json['battery'] as int,
      sosFlag: json['sos_flag'] as bool,
      healthScore: json['health_score'] as int?,
    );
  }
}
