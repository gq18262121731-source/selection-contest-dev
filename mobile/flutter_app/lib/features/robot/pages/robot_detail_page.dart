import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/theme/app_colors.dart';
import '../models/robot_status.dart';
import '../providers/robot_provider.dart';
import '../widgets/go2_3d_view.dart';
import '../widgets/robot_metric_item.dart';
import '../widgets/robot_status_card.dart';

class RobotDetailPage extends StatelessWidget {
  final String subjectName;
  final String? deviceMac;

  const RobotDetailPage({super.key, required this.subjectName, this.deviceMac});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) => RobotProvider(),
      child: _RobotDetailView(subjectName: subjectName, deviceMac: deviceMac),
    );
  }
}

class _RobotDetailView extends StatelessWidget {
  final String subjectName;
  final String? deviceMac;

  const _RobotDetailView({required this.subjectName, required this.deviceMac});

  @override
  Widget build(BuildContext context) {
    final status = context.watch<RobotProvider>().status;

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text(
          'Go2 数字分身',
          style: TextStyle(
            color: AppColors.textMain,
            fontWeight: FontWeight.bold,
          ),
        ),
        backgroundColor: Colors.transparent,
        elevation: 0,
        iconTheme: const IconThemeData(color: AppColors.textMain),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 4, 16, 28),
        children: [
          _buildHeader(status),
          const SizedBox(height: 14),
          SizedBox(
            height: 320,
            child: Go2ThreeDView(mode: status.mode, onError: (_) {}),
          ),
          const SizedBox(height: 14),
          const Text(
            '拖动旋转 · 双指缩放',
            textAlign: TextAlign.center,
            style: TextStyle(color: AppColors.textMuted, fontSize: 12),
          ),
          const SizedBox(height: 18),
          RobotStatusCard(status: status),
          const SizedBox(height: 14),
          _buildMetrics(status),
          const SizedBox(height: 14),
          _buildSafetyCard(status),
          if (kDebugMode) ...[
            const SizedBox(height: 18),
            _buildDebugSelector(context, status.mode),
          ],
        ],
      ),
    );
  }

  Widget _buildHeader(RobotStatus status) {
    final connected = status.connected && status.mode != RobotMode.offline;
    return Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '小康 · ${status.mode.label}',
                style: const TextStyle(
                  color: AppColors.textMain,
                  fontSize: 24,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 5),
              Text(
                '$subjectName 的陪伴监护设备',
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(color: AppColors.textSub, fontSize: 13),
              ),
            ],
          ),
        ),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
          decoration: BoxDecoration(
            color: (connected ? AppColors.success : AppColors.textMuted)
                .withValues(alpha: 0.10),
            borderRadius: BorderRadius.circular(999),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                Icons.circle,
                size: 9,
                color: connected ? AppColors.success : AppColors.textMuted,
              ),
              const SizedBox(width: 6),
              Text(
                connected ? '在线' : '离线',
                style: TextStyle(
                  color: connected ? AppColors.success : AppColors.textMuted,
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildMetrics(RobotStatus status) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            '机器人状态',
            style: TextStyle(
              color: AppColors.textMain,
              fontSize: 16,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: RobotMetricItem(
                  icon: Icons.battery_5_bar,
                  label: '机器人电量',
                  value: status.battery == null ? '--' : '${status.battery}%',
                  color: AppColors.success,
                ),
              ),
              Expanded(
                child: RobotMetricItem(
                  icon: Icons.social_distance,
                  label: '与老人距离',
                  value: status.targetDistance?.toStringAsFixed(2) ?? '--',
                  unit: status.targetDistance == null ? null : 'm',
                  color: AppColors.primary,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: RobotMetricItem(
                  icon: Icons.task_alt,
                  label: '当前任务',
                  value: status.task,
                  color: AppColors.secondary,
                ),
              ),
              Expanded(
                child: RobotMetricItem(
                  icon: Icons.wifi,
                  label: '网络状态',
                  value: status.connected ? '良好' : '离线',
                  color: status.connected ? AppColors.success : AppColors.error,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildSafetyCard(RobotStatus status) {
    final isRisk = status.mode.isRiskState;
    final color = isRisk ? AppColors.error : AppColors.success;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
          color: isRisk ? color.withValues(alpha: 0.35) : AppColors.border,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                isRisk ? Icons.health_and_safety : Icons.shield_outlined,
                color: color,
                size: 21,
              ),
              const SizedBox(width: 8),
              const Text(
                '安全监护',
                style: TextStyle(
                  color: AppColors.textMain,
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
          const SizedBox(height: 15),
          _SafetyRow(
            label: '老人状态',
            value: status.elderState,
            valueColor: color,
          ),
          _SafetyRow(label: '视觉状态', value: status.visionState),
          _SafetyRow(
            label: '风险事件',
            value: isRisk ? '机器狗现场监护' : '无',
            valueColor: isRisk ? AppColors.error : AppColors.success,
          ),
        ],
      ),
    );
  }

  Widget _buildDebugSelector(BuildContext context, RobotMode selectedMode) {
    const modes = [
      RobotMode.idle,
      RobotMode.following,
      RobotMode.targetLost,
      RobotMode.suspectedFall,
      RobotMode.monitoring,
      RobotMode.recovering,
      RobotMode.resolved,
    ];

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.elderBlueBg,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: AppColors.primary.withValues(alpha: 0.18)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.developer_mode, size: 19, color: AppColors.primary),
              SizedBox(width: 8),
              Text(
                'Debug 状态切换',
                style: TextStyle(
                  color: AppColors.textMain,
                  fontSize: 15,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          DropdownButtonFormField<RobotMode>(
            initialValue: modes.contains(selectedMode)
                ? selectedMode
                : RobotMode.following,
            decoration: const InputDecoration(
              isDense: true,
              labelText: '演示机器人状态',
            ),
            items: modes
                .map(
                  (mode) => DropdownMenuItem<RobotMode>(
                    value: mode,
                    child: Text(mode.label),
                  ),
                )
                .toList(),
            onChanged: (mode) {
              if (mode != null) {
                context.read<RobotProvider>().setMode(mode);
              }
            },
          ),
        ],
      ),
    );
  }
}

class _SafetyRow extends StatelessWidget {
  final String label;
  final String value;
  final Color? valueColor;

  const _SafetyRow({required this.label, required this.value, this.valueColor});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        children: [
          SizedBox(
            width: 86,
            child: Text(
              label,
              style: const TextStyle(color: AppColors.textSub, fontSize: 13),
            ),
          ),
          Expanded(
            child: Text(
              value,
              textAlign: TextAlign.right,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: valueColor ?? AppColors.textMain,
                fontSize: 13,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
