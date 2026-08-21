class CareDirectory {
  final List<CareDirectoryElder> elders;

  CareDirectory({
    required this.elders,
  });

  factory CareDirectory.fromJson(Map<String, dynamic> json) {
    return CareDirectory(
      elders: (json['elders'] as List? ?? [])
          .map((item) => CareDirectoryElder.fromJson(item as Map<String, dynamic>))
          .toList(),
    );
  }
}

class CareDirectoryElder {
  final String id;
  final String name;
  final String apartment;
  final String deviceMac;
  final List<String> deviceMacs;

  CareDirectoryElder({
    required this.id,
    required this.name,
    required this.apartment,
    required this.deviceMac,
    required this.deviceMacs,
  });

  factory CareDirectoryElder.fromJson(Map<String, dynamic> json) {
    return CareDirectoryElder(
      id: json['id'] as String? ?? '',
      name: json['name'] as String? ?? '未命名老人',
      apartment: json['apartment'] as String? ?? '--',
      deviceMac: json['device_mac'] as String? ?? '',
      deviceMacs: List<String>.from(json['device_macs'] ?? const []),
    );
  }
}
