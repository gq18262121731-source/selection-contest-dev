class SessionUser {
  final String id;
  final String username;
  final String name;
  final String role;
  final String? familyId;
  final String? communityId;

  SessionUser({
    required this.id,
    required this.username,
    required this.name,
    required this.role,
    this.familyId,
    this.communityId,
  });

  factory SessionUser.fromJson(Map<String, dynamic> json) {
    return SessionUser(
      id: json['id'] as String,
      username: json['username'] as String,
      name: json['name'] as String,
      role: json['role'] as String,
      familyId: json['family_id'] as String?,
      communityId: json['community_id'] as String?,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'username': username,
      'name': name,
      'role': role,
      'family_id': familyId,
      'community_id': communityId,
    };
  }
}

class LoginResponse {
  final String token;
  final SessionUser user;
  final String expiresAt;

  LoginResponse({
    required this.token,
    required this.user,
    required this.expiresAt,
  });

  factory LoginResponse.fromJson(Map<String, dynamic> json) {
    return LoginResponse(
      token: json['token'] as String,
      user: SessionUser.fromJson(json['user'] as Map<String, dynamic>),
      expiresAt: json['expires_at'] as String,
    );
  }
}
