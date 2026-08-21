class VoiceStatus {
  final bool configured;
  final String? serviceProvider;
  final List<String> supportedLanguages;

  VoiceStatus({
    required this.configured,
    this.serviceProvider,
    required this.supportedLanguages,
  });

  factory VoiceStatus.fromJson(Map<String, dynamic> json) {
    return VoiceStatus(
      configured: json['configured'] as bool? ?? false,
      serviceProvider: json['service_provider'] as String? ?? json['provider'] as String?,
      supportedLanguages: (json['supported_languages'] as List? ?? <Object?>[]).cast<String>(),
    );
  }
}

class AsrResponse {
  final bool ok;
  final String text;
  final double confidence;
  final String audioBase64;
  final String audioFormat;
  final String audioUrl;
  final String? error;

  const AsrResponse({
    required this.ok,
    required this.text,
    required this.confidence,
    this.audioBase64 = '',
    this.audioFormat = 'wav',
    this.audioUrl = '',
    this.error,
  });

  bool get hasAudio => audioBase64.trim().isNotEmpty || audioUrl.trim().isNotEmpty;

  factory AsrResponse.fromJson(Map<String, dynamic> json) {
    return AsrResponse(
      ok: json['ok'] as bool? ?? true,
      text: json['text'] as String? ?? json['answer'] as String? ?? '',
      confidence: (json['confidence'] as num?)?.toDouble() ?? 0.0,
      audioBase64: json['audio_b64'] as String? ?? '',
      audioFormat: json['fmt'] as String? ?? 'wav',
      audioUrl: json['audio_url'] as String? ?? '',
      error: json['error'] as String?,
    );
  }
}

class TtsResponse {
  final bool ok;
  final String audioUrl;
  final String audioBase64;
  final String format;
  final String? error;

  const TtsResponse({
    required this.ok,
    required this.audioUrl,
    required this.audioBase64,
    required this.format,
    this.error,
  });

  bool get hasAudio => audioBase64.trim().isNotEmpty || audioUrl.trim().isNotEmpty;

  factory TtsResponse.fromJson(Map<String, dynamic> json) {
    return TtsResponse(
      ok: json['ok'] as bool? ?? true,
      audioUrl: json['audio_url'] as String? ?? '',
      audioBase64: json['audio_b64'] as String? ?? '',
      format: json['fmt'] as String? ?? 'mp3',
      error: json['error'] as String?,
    );
  }
}
