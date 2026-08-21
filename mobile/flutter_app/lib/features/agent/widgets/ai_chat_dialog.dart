import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../care/models/care_profile_model.dart';
import '../../care/providers/care_provider.dart';
import '../../voice/providers/voice_provider.dart';
import '../models/agent_experience.dart';
import '../providers/agent_provider.dart';
import 'agent_chat_components.dart';
import '../../../core/theme/app_colors.dart';

class AiChatDialog extends StatefulWidget {
  final String? deviceMac;
  final List<CareAccessDeviceMetric> availableDevices;
  final bool isElder;

  const AiChatDialog({
    super.key,
    this.deviceMac,
    this.availableDevices = const <CareAccessDeviceMetric>[],
    this.isElder = false,
  });

  @override
  State<AiChatDialog> createState() => _AiChatDialogState();
}

class _AiChatDialogState extends State<AiChatDialog> {
  final TextEditingController _textController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  final FocusNode _focusNode = FocusNode();
  final Set<String> _selectedDeviceMacs = <String>{};

  AgentProvider? _agentProvider;
  String _lastAssistantSnapshot = '';
  int _lastMessageCount = 0;

  AgentExperience get _experience =>
      widget.isElder ? AgentExperience.elder : AgentExperience.family;

  @override
  void initState() {
    super.initState();
    _selectedDeviceMacs.addAll(_buildInitialSelection());
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
    _textController.dispose();
    _scrollController.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  List<String> _buildInitialSelection() {
    final available = widget.availableDevices
        .map((CareAccessDeviceMetric item) => item.deviceMac.trim())
        .where((String mac) => mac.isNotEmpty)
        .toList(growable: false);
    if (available.isNotEmpty) {
      return available;
    }

    final primary = widget.deviceMac?.trim() ?? '';
    return primary.isEmpty ? const <String>[] : <String>[primary];
  }

  List<CareAccessDeviceMetric> _resolvedAvailableDevices() {
    if (widget.availableDevices.isNotEmpty) {
      return widget.availableDevices;
    }
    if (!widget.isElder) {
      return const <CareAccessDeviceMetric>[];
    }
    return context.read<CareProvider>().profile?.deviceMetrics ??
        const <CareAccessDeviceMetric>[];
  }

  String? _fallbackDeviceMac() {
    final directMac = widget.deviceMac?.trim();
    if (directMac != null && directMac.isNotEmpty) {
      return directMac;
    }

    final devices = _resolvedAvailableDevices();
    if (devices.isNotEmpty) {
      final metricMac = devices.first.deviceMac.trim();
      if (metricMac.isNotEmpty) {
        return metricMac;
      }
    }

    final profile = context.read<CareProvider>().profile;
    if (profile != null && profile.boundDeviceMacs.isNotEmpty) {
      final boundMac = profile.boundDeviceMacs.first.trim();
      if (boundMac.isNotEmpty) {
        return boundMac;
      }
    }
    return null;
  }

  List<String> _orderedSelectedMacs() {
    final ordered = <String>[];
    final seen = <String>{};

    void collect(String mac) {
      final normalized = mac.trim();
      if (normalized.isEmpty || seen.contains(normalized)) {
        return;
      }
      seen.add(normalized);
      ordered.add(normalized);
    }

    for (final device in _resolvedAvailableDevices()) {
      if (_selectedDeviceMacs.contains(device.deviceMac.trim())) {
        collect(device.deviceMac);
      }
    }
    for (final mac in _selectedDeviceMacs) {
      collect(mac);
    }
    collect(_fallbackDeviceMac() ?? '');
    return ordered;
  }

  void _handleAgentChanged() {
    final provider = _agentProvider;
    if (!mounted || provider == null) {
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

  Future<void> _sendMessage(String text) async {
    final normalizedText = text.trim();
    if (normalizedText.isEmpty) {
      return;
    }

    final selectedMacs = _orderedSelectedMacs();
    if (selectedMacs.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(_experience.missingDeviceHint)),
      );
      return;
    }

    _textController.clear();
    _focusNode.unfocus();

    await context.read<AgentProvider>().sendMessage(
          normalizedText,
          deviceMac: selectedMacs.first,
          deviceMacs: selectedMacs,
          role: _experience.apiRole,
        );
    _scrollToBottom();
  }

  Future<void> _recordAndSend() async {
    if (!widget.isElder) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('请长按下方语音按钮开始说话')),
      );
      return;
    }

    final voiceProvider = context.read<VoiceProvider>();
    if (!voiceProvider.isVoiceAvailable) {
      if (voiceProvider.status == VoiceLoadStatus.initial) {
        await voiceProvider.checkStatus();
      }
      if (!mounted) {
        return;
      }
    }

    if (!voiceProvider.isVoiceAvailable) {
      await _sendDemoVoiceFallback();
      return;
    }

    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('请长按语音按钮说话，松开后会自动发送')),
    );
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
        duration: const Duration(milliseconds: 220),
        curve: Curves.easeOutCubic,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    context.watch<CareProvider>();
    final provider = context.watch<AgentProvider>();
    final voiceProvider = context.watch<VoiceProvider>();
    final availableDevices = _resolvedAvailableDevices();

    return Container(
      decoration: BoxDecoration(
        color: AppColors.background,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(28)),
        border: Border.all(color: AppColors.border),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.12),
            blurRadius: 24,
            offset: const Offset(0, -12),
          ),
        ],
      ),
      padding: EdgeInsets.only(
        top: 18,
        left: 18,
        right: 18,
        bottom: MediaQuery.of(context).viewInsets.bottom + 18,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          _buildHeader(),
          const SizedBox(height: 14),
          _buildDeviceBanner(),
          if (availableDevices.length > 1) ...<Widget>[
            const SizedBox(height: 12),
            _buildDeviceSelector(availableDevices),
          ],
          const SizedBox(height: 14),
          Flexible(
            child: ConstrainedBox(
              constraints: BoxConstraints(
                maxHeight: MediaQuery.of(context).size.height * 0.58,
              ),
              child: ListView.builder(
                controller: _scrollController,
                shrinkWrap: true,
                itemCount: provider.messages.length +
                    (provider.status == AgentStatus.loading ? 1 : 0),
                itemBuilder: (BuildContext context, int index) {
                  if (index == provider.messages.length) {
                    return AgentLoadingBubble(
                      accent: _experience.accent,
                      assistantIcon: _experience.assistantIcon,
                      label: _experience.loadingLabel,
                      compact: !widget.isElder,
                    );
                  }

                  final message = provider.messages[index];
                  final isUser = message.role == 'user';
                  final isStreaming = !isUser &&
                      provider.status == AgentStatus.streaming &&
                      index == provider.messages.length - 1;

                  return AgentMessageBubble(
                    text: message.content,
                    isUser: isUser,
                    isStreaming: isStreaming,
                    accent: _experience.accent,
                    assistantIcon: _experience.assistantIcon,
                    assistantLabel: _experience.assistantLabel,
                    userLabel: _experience.userLabel,
                    streamingLabel: _experience.streamingLabel,
                    fontSize: widget.isElder ? 18 : 14,
                    compact: !widget.isElder,
                    onSpeak: () => provider.ttsSpeak(context, message.content),
                  );
                },
              ),
            ),
          ),
          const SizedBox(height: 12),
          if (provider.status != AgentStatus.loading &&
              provider.status != AgentStatus.streaming)
            _buildPresetSection(),
          const SizedBox(height: 12),
          if (widget.isElder) ...<Widget>[
            _buildVoiceQuickEntry(voiceProvider),
            const SizedBox(height: 12),
          ],
          _buildInputBar(voiceProvider),
        ],
      ),
    );
  }

  Widget _buildHeader() {
    return Row(
      children: <Widget>[
        Container(
          width: 42,
          height: 42,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: _experience.accent.withValues(alpha: 0.16),
          ),
          child: Icon(
            _experience.assistantIcon,
            color: _experience.accent,
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(
                _experience.title,
                style: const TextStyle(
                  color: AppColors.textMain,
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                _experience.subtitle,
                style: const TextStyle(
                  color: AppColors.textSub,
                  fontSize: 12,
                ),
              ),
            ],
          ),
        ),
        IconButton(
          icon: const Icon(Icons.close, color: AppColors.textMuted),
          onPressed: () => Navigator.pop(context),
        ),
      ],
    );
  }

  Widget _buildDeviceBanner() {
    final selectedMacs = _orderedSelectedMacs();
    final label = selectedMacs.isEmpty
        ? _experience.missingDeviceHint
        : selectedMacs.length == 1
            ? '当前分析对象：${selectedMacs.first}'
            : '当前分析对象：已选 ${selectedMacs.length} 台设备，可一起提问';

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
          color: selectedMacs.isEmpty
              ? AppColors.border
              : _experience.accent.withValues(alpha: 0.3),
        ),
      ),
      child: Row(
        children: <Widget>[
          Icon(
            selectedMacs.isEmpty ? Icons.info_outline : Icons.devices_outlined,
            color:
                selectedMacs.isEmpty ? AppColors.textMuted : _experience.accent,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              label,
              style: const TextStyle(
                color: AppColors.textSub,
                fontSize: 13,
                height: 1.45,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildDeviceSelector(List<CareAccessDeviceMetric> availableDevices) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Padding(
          padding: const EdgeInsets.only(left: 2, bottom: 8),
          child: Text(
            '问答对象可多选',
            style: const TextStyle(
              color: AppColors.textMain,
              fontSize: 13,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
        Wrap(
          spacing: 10,
          runSpacing: 10,
          children: availableDevices.map((CareAccessDeviceMetric device) {
            final mac = device.deviceMac.trim();
            final isSelected = _selectedDeviceMacs.contains(mac);
            return FilterChip(
              selected: isSelected,
              showCheckmark: false,
              selectedColor: _experience.accent.withValues(alpha: 0.15),
              backgroundColor: AppColors.surface,
              side: BorderSide(
                color: isSelected ? _experience.accent : AppColors.border,
              ),
              label: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    device.subjectName,
                    style: TextStyle(
                      color:
                          isSelected ? _experience.accent : AppColors.textMain,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    mac,
                    style: const TextStyle(
                      color: AppColors.textMuted,
                      fontSize: 11,
                    ),
                  ),
                ],
              ),
              onSelected: (bool next) {
                setState(() {
                  if (next) {
                    _selectedDeviceMacs.add(mac);
                  } else {
                    _selectedDeviceMacs.remove(mac);
                  }
                });
              },
            );
          }).toList(),
        ),
      ],
    );
  }

  Widget _buildPresetSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Padding(
          padding: const EdgeInsets.only(left: 4, bottom: 10),
          child: Text(
            _experience.emptyPromptTitle,
            style: const TextStyle(
              color: AppColors.textSub,
              fontSize: 13,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
        Wrap(
          spacing: 10,
          runSpacing: 10,
          children: _experience.presetPrompts.map((String prompt) {
            return ActionChip(
              backgroundColor: AppColors.surface,
              side: BorderSide(
                color: _experience.accent.withValues(alpha: 0.3),
              ),
              label: Text(
                prompt,
                style: TextStyle(
                  color: _experience.accent,
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                ),
              ),
              onPressed: () => _sendMessage(prompt),
            );
          }).toList(),
        ),
      ],
    );
  }

  String _buildVoiceUnavailableText() {
    final voiceProvider = context.read<VoiceProvider>();
    if (voiceProvider.status == VoiceLoadStatus.loading) {
      return '正在检查语音服务，请稍候';
    }
    if (voiceProvider.status == VoiceLoadStatus.error) {
      return voiceProvider.errorMessage ?? '无法连接后端服务，请检查服务器是否启动';
    }
    return '语音服务未就绪，请确认后端已启动且 DASHSCOPE_API_KEY 已配置';
  }

  Future<void> _sendDemoVoiceFallback() async {
    final selectedMacs = _orderedSelectedMacs();
    if (selectedMacs.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(_experience.missingDeviceHint)),
      );
      return;
    }

    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('语音服务未配置，已切换为演示语音问答')),
    );
    await context.read<AgentProvider>().sendMessage(
          _experience.presetPrompts.first,
          deviceMac: selectedMacs.first,
          deviceMacs: selectedMacs,
          role: _experience.apiRole,
        );
    _scrollToBottom();
  }

  Widget _buildVoiceQuickEntry(VoiceProvider voiceProvider) {
    final isAvailable = voiceProvider.isVoiceAvailable;
    final useDemoFallback = widget.isElder && !isAvailable;
    final helperText = voiceProvider.isRecording
        ? '正在听您说话，松开后自动发送'
        : (voiceProvider.isProcessing
            ? '正在识别并整理问题...'
            : isAvailable
                ? '长按大按钮直接说话'
                : (useDemoFallback
                    ? '语音服务未配置，点击麦克风可使用演示语音问答'
                    : _buildVoiceUnavailableText()));

    return Container(
      padding: const EdgeInsets.fromLTRB(18, 18, 18, 20),
      decoration: BoxDecoration(
        color: const Color(0xFF0F172A),
        borderRadius: BorderRadius.circular(24),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: const Color(0xFF0F172A).withValues(alpha: 0.08),
            blurRadius: 18,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Column(
        children: <Widget>[
          Text(
            helperText,
            textAlign: TextAlign.center,
            style: TextStyle(
              color:
                  voiceProvider.isRecording ? _experience.accent : Colors.white,
              fontSize: 15,
              fontWeight: FontWeight.w700,
              height: 1.4,
            ),
          ),
          const SizedBox(height: 16),
          GestureDetector(
            onTap: useDemoFallback ? _sendDemoVoiceFallback : null,
            onLongPressStart:
                isAvailable ? (_) => voiceProvider.startRecording() : null,
            onLongPressEnd: isAvailable
                ? (_) async {
                    final path =
                        await voiceProvider.stopRecording(processOmni: false);
                    if (!mounted) {
                      return;
                    }
                    if (path == null) {
                      return;
                    }
                    final selectedMacs = _orderedSelectedMacs();
                    if (selectedMacs.isEmpty) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(content: Text(_experience.missingDeviceHint)),
                      );
                      return;
                    }
                    await context
                        .read<AgentProvider>()
                        .sendVoiceMessageFromPath(
                          path,
                          deviceMac: selectedMacs.first,
                          role: _experience.apiRole,
                        );
                    _scrollToBottom();
                  }
                : null,
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 180),
              width: 92,
              height: 92,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: isAvailable
                    ? _experience.accent
                    : (useDemoFallback
                        ? const Color(0xFF334155)
                        : Colors.white10),
                boxShadow: (isAvailable || useDemoFallback)
                    ? <BoxShadow>[
                        BoxShadow(
                          color: _experience.accent
                              .withValues(alpha: isAvailable ? 0.28 : 0.16),
                          blurRadius: 24,
                          offset: const Offset(0, 8),
                        ),
                      ]
                    : const <BoxShadow>[],
              ),
              child: Icon(
                voiceProvider.isProcessing ? Icons.graphic_eq : Icons.mic,
                size: 42,
                color: (isAvailable || useDemoFallback)
                    ? Colors.white
                    : Colors.white54,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildInputBar(VoiceProvider voiceProvider) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: AppColors.border),
      ),
      child: Row(
        children: <Widget>[
          Expanded(
            child: TextField(
              controller: _textController,
              focusNode: _focusNode,
              style: const TextStyle(
                  color: AppColors.textMain, fontWeight: FontWeight.bold),
              minLines: 1,
              maxLines: 4,
              decoration: InputDecoration(
                hintText: _experience.inputHint,
                hintStyle: const TextStyle(color: AppColors.textMuted),
                border: InputBorder.none,
              ),
              onSubmitted: (String value) => _sendMessage(value),
            ),
          ),
          IconButton(
            icon: Icon(
              widget.isElder
                  ? Icons.keyboard_voice_rounded
                  : Icons.mic_none_rounded,
              color: voiceProvider.isVoiceAvailable
                  ? _experience.accent
                  : AppColors.textMuted,
            ),
            onPressed: _recordAndSend,
          ),
          IconButton(
            icon: Icon(Icons.send_rounded, color: _experience.accent),
            onPressed: () => _sendMessage(_textController.text),
          ),
        ],
      ),
    );
  }
}
