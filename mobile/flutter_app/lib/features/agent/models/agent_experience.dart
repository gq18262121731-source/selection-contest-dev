import 'package:flutter/material.dart';

class AgentExperience {
  final String apiRole;
  final String title;
  final String subtitle;
  final String introMessage;
  final String assistantLabel;
  final String userLabel;
  final String inputHint;
  final String loadingLabel;
  final String streamingLabel;
  final String missingDeviceHint;
  final String emptyPromptTitle;
  final List<String> presetPrompts;
  final IconData assistantIcon;
  final Color accent;

  const AgentExperience({
    required this.apiRole,
    required this.title,
    required this.subtitle,
    required this.introMessage,
    required this.assistantLabel,
    required this.userLabel,
    required this.inputHint,
    required this.loadingLabel,
    required this.streamingLabel,
    required this.missingDeviceHint,
    required this.emptyPromptTitle,
    required this.presetPrompts,
    required this.assistantIcon,
    required this.accent,
  });

  static const AgentExperience elder = AgentExperience(
    apiRole: 'elder',
    title: '智能助手',
    subtitle: '把手环指标翻成简单好懂的话',
    introMessage:
        '您好，我会用最简单、最温和的话帮您解释当前情况。如果需要复测、休息，或者联系家人，我会直接告诉您。',
    assistantLabel: '健康助手',
    userLabel: '我的问题',
    inputHint: '可以直接问我现在的身体情况',
    loadingLabel: '正在结合手环数据整理回答',
    streamingLabel: '正在一句一句整理给您',
    missingDeviceHint: '还没有拿到手环设备信息，请先回到主页确认设备已绑定并在线。',
    emptyPromptTitle: '您也可以直接点下面的问题',
    presetPrompts: <String>[
      '我今天整体情况怎么样？',
      '现在需要再量一次吗？',
      '要不要联系家人？',
    ],
    assistantIcon: Icons.auto_awesome,
    accent: Color(0xFF2563EB),
  );

  static const AgentExperience family = AgentExperience(
    apiRole: 'family',
    title: '家庭守护助手',
    subtitle: '围绕健康监测、异常波动和家属跟进给出建议',
    introMessage:
        '您好，我会结合心率、血氧、血压、步数和告警变化，帮您看清谁需要优先关注、哪些指标有异常波动，以及下一步怎么跟进。',
    assistantLabel: '家庭守护助手',
    userLabel: '家属提问',
    inputHint: '例如：最近哪些监测指标需要重点留意？',
    loadingLabel: '正在整理监测趋势和家属跟进建议',
    streamingLabel: '正在根据最新监测数据持续生成建议',
    missingDeviceHint: '当前还没有可分析的监测设备，请先确认老人已绑定手环并开始上传数据。',
    emptyPromptTitle: '可以先从这些健康监测问题开始',
    presetPrompts: <String>[
      '今天这些监测对象里，谁最需要我优先关注？',
      '最近心率、血氧、血压和步数有哪些异常波动？',
      '结合当前监测数据和告警信息，我下一步应该怎么跟进？',
    ],
    assistantIcon: Icons.shield_outlined,
    accent: Color(0xFF0EA5E9),
  );
}
