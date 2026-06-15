import 'dart:convert';
import 'dart:io';

import 'package:audioplayers/audioplayers.dart';
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:record/record.dart';

class AudioService {
  final AudioRecorder _recorder = AudioRecorder();
  final AudioPlayer _player = AudioPlayer();
  final AudioPlayer _alarmPlayer = AudioPlayer();
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
      final path = '${tempDir.path}/speech_${DateTime.now().millisecondsSinceEpoch}.wav';

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
    await _playBytes(bytes, format);
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
    await _player.stop();
  }

  Future<bool> startAlarmLoop({String assetPath = 'audio/sos_alarm.ogg'}) async {
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
    _alarmPlayer.dispose();
    _recorder.dispose();
    _player.dispose();
  }
}
