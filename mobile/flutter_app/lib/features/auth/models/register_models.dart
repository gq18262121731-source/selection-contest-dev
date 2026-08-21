// Registration request/response models mirroring the backend API.

enum RegisterRole { elder, family, community }

extension RegisterRoleExt on RegisterRole {
  String get value {
    switch (this) {
      case RegisterRole.elder:
        return 'elder';
      case RegisterRole.family:
        return 'family';
      case RegisterRole.community:
        return 'community';
    }
  }

  String get label {
    switch (this) {
      case RegisterRole.elder:
        return '老人';
      case RegisterRole.family:
        return '家属';
      case RegisterRole.community:
        return '社区工作人员';
    }
  }

  String get description {
    switch (this) {
      case RegisterRole.elder:
        return '佩戴手环，查看自己的健康数据';
      case RegisterRole.family:
        return '关注家人健康，接收异常提醒';
      case RegisterRole.community:
        return '管理多位老人和设备';
    }
  }
}

class ElderRegisterRequest {
  final String name;
  final String phone;
  final String password;
  final int age;
  final String apartment;
  final String communityId;

  ElderRegisterRequest({
    required this.name,
    required this.phone,
    required this.password,
    required this.age,
    required this.apartment,
    this.communityId = 'community-haitang',
  });

  Map<String, dynamic> toJson() => {
        'name': name,
        'phone': phone,
        'password': password,
        'age': age,
        'apartment': apartment,
        'community_id': communityId,
      };
}

class FamilyRegisterRequest {
  final String name;
  final String phone;
  final String password;
  final String relationship;
  final String communityId;
  final String? loginUsername;

  FamilyRegisterRequest({
    required this.name,
    required this.phone,
    required this.password,
    required this.relationship,
    this.communityId = 'community-haitang',
    this.loginUsername,
  });

  Map<String, dynamic> toJson() => {
        'name': name,
        'phone': phone,
        'password': password,
        'relationship': relationship,
        'community_id': communityId,
        if (loginUsername != null && loginUsername!.isNotEmpty) 'login_username': loginUsername,
      };
}

class CommunityRegisterRequest {
  final String name;
  final String phone;
  final String password;
  final String communityId;
  final String? loginUsername;

  CommunityRegisterRequest({
    required this.name,
    required this.phone,
    required this.password,
    this.communityId = 'community-haitang',
    this.loginUsername,
  });

  Map<String, dynamic> toJson() => {
        'name': name,
        'phone': phone,
        'password': password,
        'community_id': communityId,
        if (loginUsername != null && loginUsername!.isNotEmpty) 'login_username': loginUsername,
      };
}

class RegisterResponse {
  final String id;
  final String name;
  final String role;
  final String phone;
  final String createdAt;

  RegisterResponse({
    required this.id,
    required this.name,
    required this.role,
    required this.phone,
    required this.createdAt,
  });

  factory RegisterResponse.fromJson(Map<String, dynamic> json) {
    return RegisterResponse(
      id: json['id'] as String,
      name: json['name'] as String,
      role: json['role'] as String,
      phone: json['phone'] as String,
      createdAt: json['created_at'] as String,
    );
  }
}
