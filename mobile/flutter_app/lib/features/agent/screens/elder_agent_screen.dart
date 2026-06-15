import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../widgets/logout_action.dart';
import '../../care/models/care_profile_model.dart';
import '../../care/providers/care_provider.dart';
import '../../care/screens/elder_home_screen.dart';
import '../../voice/providers/voice_provider.dart';
import '../models/agent_experience.dart';
import '../providers/agent_provider.dart';
import '../widgets/agent_chat_components.dart';

class ElderAgentScreen extends StatefulWidget {
  final String? deviceMac;

  const ElderAgentScreen({super.key, this.deviceMac});

  @override
  State<ElderAgentScreen> createState() => _ElderAgentScreenState();
}

class _ElderAgentScreenState extends State<ElderAgentScreen> {
  static const AgentExperience _experience = AgentExperience.elder;

  final ScrollController _scrollController = ScrollController();

  AgentProvider? _agentProvider;
  String _lastAssistantSnapshot = '';
  int _lastMessageCount = 0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      final voiceProvider = context.read<VoiceProvider>();
      if (voiceProvider.status == VoiceLoadStatus.initial ||
          voiceProvider.status == VoiceLoadStatus.error ||
          !voiceProvider.isVoiceAvailable) {
        voiceProvider.checkStatus();
      }
      context.read<CareProvider>().fetchProfile();
      context.read<AgentProvider>().init(_experience.introMessage);
    });
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final provider = context.read<AgentProvider>();
    if (!identical(_agentProvider, provider)) {
      _agentProvider?.removeListener(_handleAgentChanged);
      _agentProvider = provider;
      _agentProvider?.addListener(_handleAgentChanged);
    }
  }

  @override
  void dispose() {
    _agentProvider?.removeListener(_handleAgentChanged);
    _scrollController.dispose();
    super.dispose();
  }

  void _handleAgentChanged() {
    if (!mounted) {
      return;
    }

    final provider = _agentProvider;
    if (provider == null) {
      return;
    }

    final messages = provider.messages;
    final currentAssistantSnapshot =
        messages.isNotEmpty ? messages.last.content : '';
    final shouldScroll = messages.length != _lastMessageCount ||
        currentAssistantSnapshot != _lastAssistantSnapshot ||
        provider.status == AgentStatus.loading ||
        provider.status == AgentStatus.streaming;

    _lastMessageCount = messages.length;
    _lastAssistantSnapshot = currentAssistantSnapshot;

    if (shouldScroll) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _scrollToBottom());
    }
  }

  String? _resolveDeviceMac() {
    final directMac = widget.deviceMac?.trim();
    if (directMac != null && directMac.isNotEmpty) {
      return directMac;
    }

    final profile = context.read<CareProvider>().profile;
    return _resolveDeviceMacFromProfile(profile);
  }

  String? _resolveDeviceMacFromProfile(CareAccessProfile? profile) {
    if (profile != null && profile.deviceMetrics.isNotEmpty) {
      final metricMac = profile.deviceMetrics.first.deviceMac.trim();
      if (metricMac.isNotEmpty) {
        return metricMac;
      }
    }

    if (profile != null && profile.boundDeviceMacs.isNotEmpty) {
      final boundMac = profile.boundDeviceMacs.first.trim();
      if (boundMac.isNotEmpty) {
        return boundMac;
      }
    }

    return null;
  }

  Future<void> _sendMessage(String text) async {
    final normalizedText = text.trim();
    if (normalizedText.isEmpty) {
      return;
    }

    final deviceMac = _resolveDeviceMac();
    if (deviceMac == null || deviceMac.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(_experience.missingDeviceHint)),
      );
      return;
    }

    await context.read<AgentProvider>().sendMessage(
          normalizedText,
          deviceMac: deviceMac,
          role: _experience.apiRole,
        );
    _handleAssistantResponse();
    _scrollToBottom();
  }

  void _handleAssistantResponse() {
    if (!mounted) {
      return;
    }

    final messages = context.read<AgentProvider>().messages;
    if (messages.isEmpty || messages.last.role != 'assistant') {
      return;
    }

    final lastContent = messages.last.content.trim();
    if (lastContent.isEmpty) {
      return;
    }

    context.read<VoiceProvider>().processTts(lastContent);
  }

  void _scrollToBottom() {
    if (!_scrollController.hasClients) {
      return;
    }
    Future<void>.delayed(const Duration(milliseconds: 80), () {
      if (!_scrollController.hasClients) {
        return;
      }
      _scrollController.animateTo(
        _scrollController.position.maxScrollExtent,
        duration: const Duration(milliseconds: 240),
        curve: Curves.easeOutCubic,
      );
    });
  }

  void _goToHome() {
    final navigator = Navigator.of(context);
    if (navigator.canPop()) {
      navigator.pop();
      return;
    }
    navigator.pushReplacement(
      MaterialPageRoute<void>(
        builder: (_) => const ElderHomeScreen(),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final agentProvider = context.watch<AgentProvider>();
    final voiceProvider = context.watch<VoiceProvider>();
    final careProvider = context.watch<CareProvider>();
    final currentDeviceMac = widget.deviceMac?.trim().isNotEmpty == true
        ? widget.deviceMac!.trim()
        : _resolveDeviceMacFromProfile(careProvider.profile);

    return Scaffold(
      backgroundColor: const Color(0xFFF8FAFC),
      appBar: AppBar(
        leading: IconButton(
          onPressed: _goToHome,
          icon: const Icon(Icons.home_outlined, color: Color(0xFF64748B)),
          tooltip: '回到主页',
        ),
        title: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Text(
              _experience.title,
              style: const TextStyle(
                color: Color(0xFF0F172A),
                fontSize: 24,
                fontWeight: FontWeight.bold,
              ),
            ),
            Text(
              _experience.subtitle,
              style: const TextStyle(
                color: Color(0xFF64748B),
                fontSize: 12,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
        backgroundColor: Colors.transparent,
        elevation: 0,
        centerTitle: true,
        actions: const <Widget>[LogoutAction()],
      ),
      body: DecoratedBox(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            colors: <Color>[
              Color(0xFFF8FAFC),
              Color(0xFFF1F5F9),
              Color(0xFFF8FAFC),
            ],
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
          ),
        ),
        child: Column(
          children: <Widget>[
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 8, 20, 0),
              child: _buildHeroCard(currentDeviceMac),
            ),
            Expanded(
              child: ListView.builder(
                controller: _scrollController,
                padding: const EdgeInsets.fromLTRB(20, 24, 20, 12),
                itemCount: agentProvider.messages.length +
                    (agentProvider.status == AgentStatus.loading ? 1 : 0),
                itemBuilder: (BuildContext context, int index) {
                  if (index == agentProvider.messages.length) {
                    return AgentLoadingBubble(
                      accent: _experience.accent,
                      assistantIcon: _experience.assistantIcon,
                      label: _experience.loadingLabel,
                    );
                  }

                  final message = agentProvider.messages[index];
                  final isUser = message.role == 'user';
                  final isStreaming = !isUser &&
                      agentProvider.status == AgentStatus.streaming &&
                      index == agentProvider.messages.length - 1;

                  return AgentMessageBubble(
                    text: message.content,
                    isUser: isUser,
                    isStreaming: isStreaming,
                    accent: _experience.accent,
                    assistantIcon: _experience.assistantIcon,
                    assistantLabel: _experience.assistantLabel,
                    userLabel: _experience.userLabel,
                    streamingLabel: _experience.streamingLabel,
                    fontSize: isUser ? 19 : 21,
                  );
                },
              ),
            ),
            if (agentProvider.status != AgentStatus.loading &&
                agentProvider.status != AgentStatus.streaming)
              _buildPresetSection(),
            _buildVoiceInputSection(voiceProvider),
          ],
        ),
      ),
    );
  }

  Widget _buildHeroCard(String? deviceMac) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: const Color(0xFF0F172A),
        borderRadius: BorderRadius.circular(22),
        border: Border.all(
          color: const Color(0xFFE2E8F0),
        ),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: const Color(0xFF0F172A).withValues(alpha: 0.04),
            blurRadius: 24,
            offset: const Offset(0, 12),
          ),
        ],
      ),
      child: Row(
        children: <Widget>[
          Container(
            width: 52,
            height: 52,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: _experience.accent.withValues(alpha: 0.14),
            ),
            child: Icon(
              Icons.watch_outlined,
              color: _experience.accent,
              size: 28,
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                const Text(
                  '我会先看手环最近的变化，再用容易听懂的话告诉您重点。',
                  style: TextStyle(
                    color: Color(0xFF0F172A),
                    fontSize: 16,
                    fontWeight: FontWeight.w800,
                    height: 1.4,
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  deviceMac == null || deviceMac.isEmpty
                      ? '还没有拿到当前手环信息'
                      : '当前分析设备：$deviceMac',
                  style: const TextStyle(
                    color: Color(0xFF64748B),
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
          TextButton(
            onPressed: _goToHome,
            child: const Text('回主页看参数'),
          ),
        ],
      ),
    );
  }

  Widget _buildPresetSection() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 0, 24, 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Text(
              _experience.emptyPromptTitle,
              style: const TextStyle(
                color: Color(0xFF64748B),
                fontSize: 16,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
          ..._experience.presetPrompts.map((String prompt) {
            return Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  onPressed: () => _sendMessage(prompt),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.white,
                    foregroundColor: _experience.accent,
                    padding: const EdgeInsets.symmetric(vertical: 20),
                    elevation: 0,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(18),
                      side: const BorderSide(
                        color: Color(0xFFE2E8F0),
                        width: 1.5,
                      ),
                    ),
                  ),
                  child: Text(
                    prompt,
                    style: const TextStyle(
                      fontSize: 19,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ),
            );
          }),
        ],
      ),
    );
  }

  Widget _buildVoiceInputSection(VoiceProvider voiceProvider) {
    final helperText = voiceProvider.isRecording
        ? '正在听您说话...'
        : (voiceProvider.isProcessing ? '正在整理成问题...' : '长按话筒跟我说话');

    return Container(
      padding: const EdgeInsets.fromLTRB(28, 24, 28, 42),
      decoration: BoxDecoration(
        color: const Color(0xFF0F172A),
        borderRadius: const BorderRadius.vertical(top: Radius.circular(36)),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: const Color(0xFF0F172A).withValues(alpha: 0.06),
            blurRadius: 24,
            offset: const Offset(0, -8),
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Text(
            helperText,
            style: TextStyle(
              color: voiceProvider.isRecording
                  ? _experience.accent
                  : const Color(0xFF64748B),
              fontSize: 20,
              fontWeight: voiceProvider.isRecording
                  ? FontWeight.w800
                  : FontWeight.w600,
            ),
          ),
          const SizedBox(height: 20),
          GestureDetector(
            onLongPressStart: (_) => voiceProvider.startRecording(),
            onLongPressEnd: (_) async {
              final path = await voiceProvider.stopRecording(processOmni: false);
              if (!mounted || path == null) {
                return;
              }
              final deviceMac = _resolveDeviceMac();
              if (deviceMac == null || deviceMac.isEmpty) {
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text(_experience.missingDeviceHint)),
                );
                return;
              }
              await context.read<AgentProvider>().sendVoiceMessageFromPath(
                    path,
                    deviceMac: deviceMac,
                    role: _experience.apiRole,
                  );
              _scrollToBottom();
            },
            child: Stack(
              alignment: Alignment.center,
              children: <Widget>[
                if (voiceProvider.isRecording)
                  TweenAnimationBuilder<double>(
                    tween: Tween<double>(begin: 1.0, end: 1.45),
                    duration: const Duration(milliseconds: 720),
                    builder: (BuildContext context, double value, Widget? child) {
                      return Container(
                        width: 108 * value,
                        height: 108 * value,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          color: _experience.accent.withValues(
                            alpha: 0.22 * (1.65 - value),
                          ),
                        ),
                      );
                    },
                  ),
                CircleAvatar(
                  radius: 56,
                  backgroundColor:
                      voiceProvider.isRecording || voiceProvider.isProcessing
                          ? _experience.accent
                          : const Color(0xFFEFF6FF),
                  child: Icon(
                    voiceProvider.isProcessing ? Icons.graphic_eq : Icons.mic,
                    size: 56,
                    color:
                        voiceProvider.isRecording || voiceProvider.isProcessing
                            ? Colors.white
                            : _experience.accent,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
