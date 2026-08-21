import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:record/record.dart';

class AudioService {
  static const MethodChannel _pcmStreamChannel =
      MethodChannel('ai_health_iot/pcm_stream');

  final AudioRecorder _recorder = AudioRecorder();
  final AudioPlayer _player = AudioPlayer();
  final AudioPlayer _alarmPlayer = AudioPlayer();
  BytesBuilder _pcmBytes = BytesBuilder(copy: false);
  String _pcmBase64Remainder = '';
  int _pcmFlushBytes = 9600;
  int _pcmFrameBytes = 2;
  bool _pcmStreamActive = false;
  bool _alarmLooping = false;

  Future<bool> requestPermissions() async {
    final status = await Permission.microphone.request();
    return status.isGranted;
  }

  Future<String?> startRecording() async {
    try {
      if (await _recorder.isRecording()) {
        await _recorder.stop();
      }

      if (!await requestPermissions()) {
        return null;
      }

      final tempDir = await getTemporaryDirectory();
      final path =
          '${tempDir.path}/speech_${DateTime.now().millisecondsSinceEpoch}.wav';

      const config = RecordConfig(
        encoder: AudioEncoder.wav,
        sampleRate: 16000,
        numChannels: 1,
      );

      await _recorder.start(config, path: path);
      return path;
    } catch (_) {
      return null;
    }
  }

  Future<String?> stopRecording() async {
    try {
      return await _recorder.stop();
    } catch (_) {
      return null;
    }
  }

  Future<List<int>> readBytes(String path) async {
    return File(path).readAsBytes();
  }

  Future<void> play(String source) async {
    try {
      await abortPcmStream();
      if (source.startsWith('http://') || source.startsWith('https://')) {
        await _player.play(UrlSource(source));
        return;
      }

      if (source.startsWith('data:audio')) {
        final data = Uri.parse(source).data;
        final bytes = data?.contentAsBytes();
        if (bytes == null || bytes.isEmpty) {
          return;
        }
        final format = _inferFormatFromDataUri(source);
        await _playBytes(bytes, format);
        return;
      }

      await _player.play(DeviceFileSource(source));
    } catch (_) {
      // Intentionally swallow playback errors in the mobile client.
    }
  }

  Future<void> playBase64(String base64Content, String format) async {
    try {
      await abortPcmStream();
      if (base64Content.trim().isEmpty) {
        return;
      }
      final bytes = base64Decode(base64Content);
      await _playBytes(bytes, format);
    } catch (_) {
      // Intentionally swallow playback errors in the mobile client.
    }
  }

  Future<void> playBytes(List<int> bytes, String format) async {
    await abortPcmStream();
    await _playBytes(bytes, format);
  }

  Future<bool> startPcmStream({
    int sampleRate = 24000,
    int channels = 1,
    String encoding = 'pcm_s16le',
  }) async {
    if (!Platform.isAndroid ||
        encoding.trim().toLowerCase() != 'pcm_s16le' ||
        sampleRate <= 0 ||
        (channels != 1 && channels != 2)) {
      return false;
    }

    await abortPcmStream();
    await _player.stop();
    try {
      final started = await _pcmStreamChannel.invokeMethod<bool>(
            'start',
            <String, Object>{
              'sampleRate': sampleRate,
              'channels': channels,
            },
          ) ??
          false;
      if (!started) {
        return false;
      }

      _pcmBytes = BytesBuilder(copy: false);
      _pcmBase64Remainder = '';
      _pcmFlushBytes =
          (sampleRate * channels * 2 ~/ 5).clamp(2048, 19200).toInt();
      _pcmFrameBytes = channels * 2;
      _pcmStreamActive = true;
      return true;
    } catch (_) {
      _resetPcmStreamState();
      return false;
    }
  }

  Future<bool> writePcmBase64Chunk(String fragment) async {
    if (!_pcmStreamActive) {
      return false;
    }

    try {
      final normalized = fragment.replaceAll(RegExp(r'\s+'), '');
      if (normalized.isEmpty) {
        return true;
      }

      final combined = '$_pcmBase64Remainder$normalized';
      final decodableLength = combined.length - (combined.length % 4);
      if (decodableLength == 0) {
        _pcmBase64Remainder = combined;
        return true;
      }

      final decodable = combined.substring(0, decodableLength);
      _pcmBase64Remainder = combined.substring(decodableLength);
      _pcmBytes.add(base64Decode(decodable));

      if (_pcmBytes.length >= _pcmFlushBytes) {
        return _flushPcmBytes();
      }
      return true;
    } catch (_) {
      await abortPcmStream();
      return false;
    }
  }

  Future<bool> finishPcmStream() async {
    if (!_pcmStreamActive) {
      return false;
    }

    try {
      if (_pcmBase64Remainder.isNotEmpty) {
        final paddedLength = ((_pcmBase64Remainder.length + 3) ~/ 4) * 4;
        final padded = _pcmBase64Remainder.padRight(paddedLength, '=');
        _pcmBytes.add(base64Decode(padded));
        _pcmBase64Remainder = '';
      }

      if (!await _flushPcmBytes()) {
        await abortPcmStream();
        return false;
      }

      final finished =
          await _pcmStreamChannel.invokeMethod<bool>('finish') ?? false;
      _resetPcmStreamState();
      return finished;
    } catch (_) {
      await abortPcmStream();
      return false;
    }
  }

  Future<void> abortPcmStream() async {
    final wasActive = _pcmStreamActive;
    _resetPcmStreamState();
    if (!Platform.isAndroid || !wasActive) {
      return;
    }
    try {
      await _pcmStreamChannel.invokeMethod<void>('abort');
    } catch (_) {
      // The complete-file player remains available as a fallback.
    }
  }

  Future<bool> _flushPcmBytes() async {
    if (!_pcmStreamActive || _pcmBytes.length == 0) {
      return _pcmStreamActive;
    }

    final buffered = _pcmBytes.takeBytes();
    final writableLength = buffered.length - (buffered.length % _pcmFrameBytes);
    if (writableLength == 0) {
      _pcmBytes.add(buffered);
      return true;
    }
    if (writableLength < buffered.length) {
      _pcmBytes.add(buffered.sublist(writableLength));
    }
    final bytes = buffered.sublist(0, writableLength);
    final accepted = await _pcmStreamChannel.invokeMethod<bool>(
          'write',
          <String, Object>{'data': Uint8List.fromList(bytes)},
        ) ??
        false;
    return accepted;
  }

  void _resetPcmStreamState() {
    _pcmStreamActive = false;
    _pcmBase64Remainder = '';
    _pcmFrameBytes = 2;
    _pcmBytes = BytesBuilder(copy: false);
  }

  Future<void> _playBytes(List<int> bytes, String format) async {
    final tempDir = await getTemporaryDirectory();
    final normalizedFormat = _normalizeFormat(format);
    final file = File(
      '${tempDir.path}/tts_${DateTime.now().millisecondsSinceEpoch}.$normalizedFormat',
    );
    await file.writeAsBytes(bytes, flush: true);
    await _player.play(DeviceFileSource(file.path));
  }

  String _inferFormatFromDataUri(String value) {
    final match = RegExp(r'^data:audio/([^;]+);base64,').firstMatch(value);
    return _normalizeFormat(match?.group(1) ?? 'wav');
  }

  String _normalizeFormat(String value) {
    final lower = value.trim().toLowerCase();
    if (lower.isEmpty) {
      return 'wav';
    }
    if (lower == 'mpeg') {
      return 'mp3';
    }
    return lower;
  }

  Future<void> stopPlayback() async {
    await abortPcmStream();
    await _player.stop();
  }

  Future<bool> startAlarmLoop(
      {String assetPath = 'audio/sos_alarm.ogg'}) async {
    if (_alarmLooping) {
      return true;
    }
    _alarmLooping = true;
    try {
      await _alarmPlayer.setReleaseMode(ReleaseMode.loop);
      await _alarmPlayer.play(AssetSource(assetPath), volume: 1.0);
      return true;
    } catch (_) {
      _alarmLooping = false;
      return false;
    }
  }

  Future<void> stopAlarmLoop() async {
    _alarmLooping = false;
    await _alarmPlayer.stop();
    await _alarmPlayer.setReleaseMode(ReleaseMode.stop);
  }

  void dispose() {
    unawaited(abortPcmStream());
    _alarmPlayer.dispose();
    _recorder.dispose();
    _player.dispose();
  }
}
