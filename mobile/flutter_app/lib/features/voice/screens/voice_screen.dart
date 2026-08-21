import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/voice_provider.dart';
import '../../../widgets/logout_action.dart';
import '../../../core/theme/app_colors.dart';

class VoiceScreen extends StatefulWidget {
  const VoiceScreen({super.key});

  @override
  State<VoiceScreen> createState() => _VoiceScreenState();
}

class _VoiceScreenState extends State<VoiceScreen> {
  final TextEditingController _ttsController = TextEditingController();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<VoiceProvider>().checkStatus();
    });
  }

  @override
  void dispose() {
    _ttsController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final voiceProvider = context.watch<VoiceProvider>();

    return Scaffold(
      backgroundColor: const Color(0xFFF8FAFC),
      appBar: AppBar(
        title: const Text('语音交互', style: TextStyle(color: AppColors.textMain, fontSize: 18, fontWeight: FontWeight.bold)),
        backgroundColor: Colors.transparent,
        elevation: 0,
        actions: const [LogoutAction()],
      ),
      body: _buildBody(voiceProvider),
    );
  }

  Widget _buildBody(VoiceProvider provider) {
    if (provider.status == VoiceLoadStatus.loading) {
      return const Center(child: CircularProgressIndicator(color: AppColors.primary));
    }

    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _buildStatusCard(provider),
          const SizedBox(height: 32),
          if (provider.isVoiceAvailable) ...[
            _buildAsrSection(provider),
            const SizedBox(height: 48),
            _buildTtsSection(provider),
          ] else
            _buildDisabledFallback(),
        ],
      ),
    );
  }

  Widget _buildStatusCard(VoiceProvider provider) {
    final isConfigured = provider.isVoiceAvailable;
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: isConfigured ? AppColors.success.withOpacity(0.5) : AppColors.error.withOpacity(0.5),
        ),
        boxShadow: const [BoxShadow(color: Colors.black12, blurRadius: 4, offset: Offset(0, 2))],
      ),
      child: Row(
        children: [
          Icon(
            isConfigured ? Icons.check_circle : Icons.error_outline,
            color: isConfigured ? AppColors.success : AppColors.error,
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  isConfigured ? '语音服务已就绪' : '语音服务未配置',
                  style: const TextStyle(color: AppColors.textMain, fontWeight: FontWeight.bold),
                ),
                if (isConfigured)
                  Text(
                    '算力提供商: ${provider.voiceStatus?.serviceProvider ?? "默认"}',
                    style: const TextStyle(color: AppColors.textSub, fontSize: 12),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildAsrSection(VoiceProvider provider) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('语音转文字 (ASR)', style: TextStyle(color: AppColors.textMain, fontSize: 14, fontWeight: FontWeight.bold)),
        const SizedBox(height: 16),
        Center(
          child: GestureDetector(
            onLongPressStart: (_) => provider.startRecording(),
            onLongPressEnd: (_) => provider.stopRecording(),
            child: Column(
              children: [
                Stack(
                  alignment: Alignment.center,
                  children: [
                    if (provider.isRecording)
                      TweenAnimationBuilder<double>(
                        tween: Tween(begin: 1.0, end: 1.4),
                        duration: const Duration(milliseconds: 600),
                        builder: (context, value, child) {
                          return Container(
                            width: 80 * value,
                            height: 80 * value,
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              color: const Color(0xFF2563EB).withOpacity(0.2 * (1.6 - value)),
                            ),
                          );
                        },
                      ),
                    CircleAvatar(
                      radius: 40,
                      backgroundColor: provider.isRecording || provider.isProcessing
                          ? AppColors.primary
                          : AppColors.border,
                      child: Icon(
                        provider.isProcessing
                            ? Icons.graphic_eq
                            : (provider.isRecording ? Icons.mic : Icons.mic_none),
                        color: provider.isRecording || provider.isProcessing
                            ? Colors.white
                            : AppColors.textMuted,
                        size: 32,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                Text(
                  provider.isRecording
                      ? '松开 结束录音'
                      : (provider.isProcessing ? '正在识别...' : '长按 开始录音'),
                  style: TextStyle(
                    color: provider.isRecording ? AppColors.primary : AppColors.textMuted,
                    fontSize: 12,
                    fontWeight: provider.isRecording ? FontWeight.bold : FontWeight.normal,
                  ),
                ),
              ],
            ),
          ),
        ),
        if (provider.lastAsrText.isNotEmpty)
          Container(
            margin: const EdgeInsets.only(top: 16),
            padding: const EdgeInsets.all(16),
            width: double.infinity,
            decoration: BoxDecoration(
              color: AppColors.primary.withOpacity(0.05),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: AppColors.primary.withOpacity(0.1)),
            ),
            child: Text(
              '识别结果: ${provider.lastAsrText}',
              style: const TextStyle(color: AppColors.textMain, fontSize: 14, fontWeight: FontWeight.bold),
            ),
          ),
      ],
    );
  }

  Widget _buildTtsSection(VoiceProvider provider) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('文字转语音 (TTS)', style: TextStyle(color: AppColors.textMain, fontSize: 14, fontWeight: FontWeight.bold)),
        const SizedBox(height: 16),
        TextField(
          controller: _ttsController,
          style: const TextStyle(color: Color(0xFF0F172A)),
          decoration: InputDecoration(
            hintText: '输入要播报的内容...',
            hintStyle: const TextStyle(color: AppColors.textMuted),
            filled: true,
            fillColor: AppColors.surface,
            enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: AppColors.border)),
            focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: AppColors.primary, width: 2)),
          ),
        ),
        const SizedBox(height: 16),
        SizedBox(
          width: double.infinity,
          height: 48,
          child: ElevatedButton(
            onPressed: provider.isProcessing
                ? null
                : () => provider.processTts(_ttsController.text),
            style: ElevatedButton.styleFrom(
              backgroundColor: AppColors.primary,
              foregroundColor: Colors.white,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              elevation: 0,
            ),
            child: const Text('开始合成并播报', style: TextStyle(fontWeight: FontWeight.bold)),
          ),
        ),
        if (provider.lastTtsUrl.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 12),
            child: Text(
              '音频链接已生成 (由于插件限制不自动播放)',
              style: TextStyle(color: AppColors.success, fontSize: 10, fontWeight: FontWeight.bold),
            ),
          ),
      ],
    );
  }

  Widget _buildDisabledFallback() {
    return Center(
      child: Column(
        children: [
          const SizedBox(height: 40),
          Icon(Icons.voice_over_off, size: 64, color: AppColors.textMuted.withOpacity(0.2)),
          const SizedBox(height: 24),
          const Text(
            '语音服务当前不可用',
            style: TextStyle(color: AppColors.textMain, fontSize: 16, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 12),
          const Text(
            '后端尚未配置专业 ASR/TTS 算力。您可以继续使用实时监测、历史趋势和告警中心等核心功能。',
            textAlign: TextAlign.center,
            style: TextStyle(color: AppColors.textMuted, fontSize: 13),
          ),
        ],
      ),
    );
  }
}
