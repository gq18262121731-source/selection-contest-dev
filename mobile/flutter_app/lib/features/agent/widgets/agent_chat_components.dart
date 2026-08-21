import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import '../../../core/theme/app_colors.dart';

class AgentMessageBubble extends StatelessWidget {
  final String text;
  final bool isUser;
  final bool isStreaming;
  final Color accent;
  final IconData assistantIcon;
  final String assistantLabel;
  final String userLabel;
  final String streamingLabel;
  final double fontSize;
  final bool compact;
  final VoidCallback? onSpeak;

  const AgentMessageBubble({
    super.key,
    required this.text,
    required this.isUser,
    required this.isStreaming,
    required this.accent,
    required this.assistantIcon,
    required this.assistantLabel,
    required this.userLabel,
    required this.streamingLabel,
    this.fontSize = 16,
    this.compact = false,
    this.onSpeak,
  });

  @override
  Widget build(BuildContext context) {
    const surfaceColor = AppColors.surface;

    final bubbleDecoration = BoxDecoration(
      color: isUser ? accent : surfaceColor,
      borderRadius: BorderRadius.circular(compact ? 18 : 24).copyWith(
        topLeft: isUser
            ? const Radius.circular(18)
            : Radius.circular(compact ? 6 : 8),
        topRight: isUser
            ? Radius.circular(compact ? 6 : 8)
            : const Radius.circular(18),
      ),
      border: Border.all(
        color: isUser
            ? accent
            : AppColors.border,
      ),
      boxShadow: <BoxShadow>[
        BoxShadow(
          color: Colors.black.withOpacity(0.06),
          blurRadius: compact ? 16 : 24,
          offset: const Offset(0, 8),
        ),
      ],
    );

    return Padding(
      padding: EdgeInsets.only(bottom: compact ? 14 : 22),
      child: Row(
        mainAxisAlignment:
            isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          if (!isUser) _buildAvatar(isUser: false),
          SizedBox(width: compact ? 10 : 12),
          Flexible(
            child: Container(
              padding: EdgeInsets.fromLTRB(
                compact ? 14 : 18,
                compact ? 12 : 16,
                compact ? 14 : 18,
                compact ? 12 : 16,
              ),
              decoration: bubbleDecoration,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      _buildLabel(isUser ? userLabel : assistantLabel),
                      if (!isUser && !isStreaming && onSpeak != null)
                        IconButton(
                          constraints: const BoxConstraints(),
                          padding: EdgeInsets.zero,
                          icon: Icon(Icons.volume_up_rounded, color: accent, size: 20),
                          onPressed: onSpeak,
                          tooltip: '语音播报',
                        ),
                    ],
                  ),
                  SizedBox(height: compact ? 8 : 10),
                  MarkdownBody(
                    data: _normalizeMarkdown(text, isStreaming: isStreaming),
                    selectable: false,
                    softLineBreak: true,
                    styleSheet: _markdownStyle(
                      accent: accent,
                      isUser: isUser,
                      fontSize: fontSize,
                    ),
                  ),
                  if (isStreaming && !isUser) ...<Widget>[
                    SizedBox(height: compact ? 10 : 12),
                    _StreamingFooter(
                      label: streamingLabel,
                      accent: accent,
                    ),
                  ],
                ],
              ),
            ),
          ),
          SizedBox(width: compact ? 10 : 12),
          if (isUser) _buildAvatar(isUser: true),
        ],
      ),
    );
  }

  Widget _buildLabel(String label) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: isUser
            ? Colors.black.withValues(alpha: 0.16)
            : accent.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: isUser ? Colors.white : accent,
          fontSize: compact ? 12 : 14,
          fontWeight: FontWeight.bold,
          letterSpacing: 0.2,
        ),
      ),
    );
  }

  Widget _buildAvatar({required bool isUser}) {
    return Container(
      width: compact ? 36 : 42,
      height: compact ? 36 : 42,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: isUser
            ? accent.withOpacity(0.1)
            : AppColors.background,
        border: Border.all(
          color: isUser ? accent : AppColors.border,
          width: 1.5,
        ),
      ),
      child: Icon(
        isUser ? Icons.person_outline : assistantIcon,
        color: isUser ? Colors.white : accent,
        size: compact ? 18 : 20,
      ),
    );
  }

  MarkdownStyleSheet _markdownStyle({
    required Color accent,
    required bool isUser,
    required double fontSize,
  }) {
    final primaryText = isUser ? Colors.white : AppColors.textMain;
    final mutedText = isUser ? Colors.white70 : AppColors.textSub;

    return MarkdownStyleSheet(
      p: TextStyle(
        color: primaryText,
        fontSize: fontSize,
        height: 1.65,
        fontWeight: isUser ? FontWeight.w600 : FontWeight.w400,
      ),
      strong: TextStyle(
        color: isUser ? Colors.white : accent,
        fontWeight: FontWeight.w700,
      ),
      h1: TextStyle(
        color: primaryText,
        fontSize: fontSize + 6,
        fontWeight: FontWeight.w800,
      ),
      h2: TextStyle(
        color: primaryText,
        fontSize: fontSize + 4,
        fontWeight: FontWeight.w700,
      ),
      h3: TextStyle(
        color: primaryText,
        fontSize: fontSize + 2,
        fontWeight: FontWeight.w700,
      ),
      listBullet: TextStyle(
        color: isUser ? Colors.white : accent,
        fontSize: fontSize,
      ),
      blockquote: TextStyle(
        color: mutedText,
        fontSize: fontSize - 1,
        height: 1.6,
      ),
      blockquoteDecoration: BoxDecoration(
        color: isUser ? Colors.black.withOpacity(0.08) : AppColors.background,
        borderRadius: BorderRadius.circular(12),
        border: Border(
          left: BorderSide(
            color: isUser ? Colors.white54 : accent.withValues(alpha: 0.6),
            width: 4,
          ),
        ),
      ),
      code: TextStyle(
        color: primaryText,
        backgroundColor: isUser ? Colors.black.withOpacity(0.18) : AppColors.background,
        fontSize: fontSize - 1,
      ),
      codeblockDecoration: BoxDecoration(
        color: isUser ? Colors.black.withOpacity(0.12) : AppColors.background,
        borderRadius: BorderRadius.circular(12),
      ),
    );
  }

  static String _normalizeMarkdown(String text, {required bool isStreaming}) {
    final normalized = text.trimRight();
    if (normalized.isNotEmpty) {
      return normalized;
    }
    return isStreaming ? '_正在组织回答…_' : '';
  }
}

class AgentLoadingBubble extends StatelessWidget {
  final Color accent;
  final IconData assistantIcon;
  final String label;
  final bool compact;

  const AgentLoadingBubble({
    super.key,
    required this.accent,
    required this.assistantIcon,
    required this.label,
    this.compact = false,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(bottom: compact ? 14 : 22),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Container(
            width: compact ? 36 : 42,
            height: compact ? 36 : 42,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: AppColors.background,
              border: Border.all(color: AppColors.border, width: 1.5),
            ),
            child: Icon(assistantIcon, color: accent, size: compact ? 18 : 20),
          ),
          SizedBox(width: compact ? 10 : 12),
          Container(
            padding: EdgeInsets.symmetric(
              horizontal: compact ? 14 : 18,
              vertical: compact ? 12 : 16,
            ),
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(compact ? 18 : 24).copyWith(
                topLeft: Radius.circular(compact ? 6 : 8),
              ),
              border: Border.all(color: AppColors.border),
              boxShadow: const [BoxShadow(color: Colors.black12, blurRadius: 8, offset: Offset(0, 4))],
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                SizedBox(
                  width: 14,
                  height: 14,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    color: accent,
                  ),
                ),
                const SizedBox(width: 10),
                Text(
                  label,
                  style: TextStyle(
                    color: AppColors.textSub,
                    fontSize: compact ? 14 : 16,
                    fontWeight: FontWeight.bold,
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

class _StreamingFooter extends StatelessWidget {
  final String label;
  final Color accent;

  const _StreamingFooter({
    required this.label,
    required this.accent,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: AppColors.background,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          SizedBox(
            width: 12,
            height: 12,
            child: CircularProgressIndicator(
              strokeWidth: 1.8,
              color: accent,
            ),
          ),
          const SizedBox(width: 8),
          Text(
            label,
            style: const TextStyle(
              color: AppColors.textSub,
              fontSize: 14,
              fontWeight: FontWeight.bold,
            ),
          ),
        ],
      ),
    );
  }
}
