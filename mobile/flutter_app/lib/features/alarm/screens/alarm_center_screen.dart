import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../models/alarm_model.dart';
import '../../../widgets/logout_action.dart';
import '../../../core/theme/app_colors.dart';
import '../providers/alarm_provider.dart';

class AlarmCenterScreen extends StatefulWidget {
  const AlarmCenterScreen({super.key});

  @override
  State<AlarmCenterScreen> createState() => _AlarmCenterScreenState();
}

class _AlarmCenterScreenState extends State<AlarmCenterScreen> with SingleTickerProviderStateMixin {
  late TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<AlarmProvider>().ensureStarted();
    });
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final alarmProvider = context.watch<AlarmProvider>();

    return Scaffold(
      backgroundColor: const Color(0xFFF8FAFC),
      appBar: AppBar(
        title: const Text('告警中心', style: TextStyle(color: Color(0xFF0F172A), fontSize: 18)),
        backgroundColor: Colors.transparent,
        elevation: 0,
        actions: const [LogoutAction()],
        bottom: TabBar(
          controller: _tabController,
          labelColor: AppColors.primary,
          unselectedLabelColor: AppColors.textSub,
          indicatorColor: AppColors.primary,
          tabs: const [
            Tab(text: '活动告警'),
            Tab(text: '调度队列'),
            Tab(text: '推送记录'),
          ],
        ),
      ),
      body: _buildBody(alarmProvider),
    );
  }

  Widget _buildBody(AlarmProvider provider) {
    if (provider.status == AlarmLoadStatus.loading) {
      return const Center(child: CircularProgressIndicator(color: Color(0xFF2563EB)));
    }

    if (provider.status == AlarmLoadStatus.error) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(provider.errorMessage ?? '加载失败', style: const TextStyle(color: AppColors.textSub)),
            TextButton(onPressed: () => provider.init(), child: const Text('重试', style: TextStyle(color: AppColors.primary))),
          ],
        ),
      );
    }

    return TabBarView(
      controller: _tabController,
      children: [
        _buildAlarmList(provider.alarms, provider),
        _buildQueueList(provider.queue),
        _buildPushList(provider.pushes),
      ],
    );
  }

  Widget _buildAlarmList(List<AlarmRecord> alarms, AlarmProvider provider) {
    if (alarms.isEmpty) {
      return const Center(child: Text('暂无未确认告警', style: TextStyle(color: AppColors.textMuted)));
    }

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: alarms.length,
      itemBuilder: (context, index) => _buildAlarmCard(alarms[index], provider),
    );
  }

  Widget _buildAlarmCard(AlarmRecord alarm, AlarmProvider provider) {
    final isSOS = alarm.isSos;
    final isCritical = alarm.isCritical;

    return Card(
      color: (isSOS || isCritical)
          ? AppColors.error.withOpacity(0.05)
          : AppColors.surface,
      margin: const EdgeInsets.only(bottom: 12),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: (isSOS || isCritical) ? const BorderSide(color: AppColors.error, width: 1) : const BorderSide(color: AppColors.border),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  isSOS ? Icons.sos : Icons.warning_amber_rounded,
                  color: (isSOS || isCritical) ? AppColors.error : AppColors.warning,
                  size: 20,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    alarm.alarmType.toUpperCase(),
                    style: const TextStyle(color: Color(0xFF0F172A), fontWeight: FontWeight.bold),
                  ),
                ),
                Text(
                  alarm.createdDateDisplay,
                  style: const TextStyle(color: AppColors.textMuted, fontSize: 10),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Text(
              alarm.message,
              style: const TextStyle(color: Color(0xFF64748B), fontSize: 14),
            ),
            const SizedBox(height: 8),
            Text(
              '设备: ${alarm.deviceMac}',
              style: const TextStyle(color: AppColors.textMuted, fontSize: 12),
            ),
            const SizedBox(height: 16),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                if (alarm.acknowledged)
                  const Row(
                    children: [
                      Icon(Icons.check_circle, color: AppColors.success, size: 16),
                      SizedBox(width: 4),
                      Text('已确认', style: TextStyle(color: AppColors.success, fontSize: 12)),
                    ],
                  )
                else
                  ElevatedButton(
                    onPressed: () => provider.acknowledge(alarm.id),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF2563EB),
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 0),
                      minimumSize: const Size(80, 32),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                    ),
                    child: const Text('确认告警', style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold)),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildQueueList(List<AlarmQueueItem> queue) {
    if (queue.isEmpty) {
      return const Center(child: Text('调度队列为空', style: TextStyle(color: AppColors.textMuted)));
    }

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: queue.length,
      itemBuilder: (context, index) {
        final item = queue[index];
        return ListTile(
          leading: CircleAvatar(
            backgroundColor: Color.lerp(Colors.orange, Colors.red, item.score / 10),
            radius: 4,
          ),
          title: Text('MAC: ${item.alarm.deviceMac}', style: const TextStyle(color: AppColors.textMain, fontSize: 14)),
          subtitle: Text('优先级: ${item.score} | 状态: ${item.alarm.alarmLevel}', style: const TextStyle(color: AppColors.textSub, fontSize: 12)),
          trailing: const Icon(Icons.low_priority, color: AppColors.border),
        );
      },
    );
  }

  Widget _buildPushList(List<MobilePushRecord> pushes) {
    if (pushes.isEmpty) {
      return const Center(child: Text('暂无历史推送', style: TextStyle(color: AppColors.textMuted)));
    }

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: pushes.length,
      itemBuilder: (context, index) {
        final push = pushes[index];
        return Card(
          color: AppColors.surface,
          child: ListTile(
            title: Text(push.title, style: const TextStyle(color: AppColors.textMain, fontSize: 14)),
            subtitle: Text(push.body, style: const TextStyle(color: AppColors.textSub, fontSize: 12)),
            trailing: Text(_formatPushDate(push.createdAt), style: const TextStyle(color: AppColors.textMuted, fontSize: 10)),
          ),
        );
      },
    );
  }

  String _formatPushDate(String raw) {
    final parsed = DateTime.tryParse(raw)?.toLocal();
    if (parsed == null) {
      return raw.split('T').first;
    }
    return '${parsed.year}-${parsed.month.toString().padLeft(2, '0')}-${parsed.day.toString().padLeft(2, '0')}';
  }
}
