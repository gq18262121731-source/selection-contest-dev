import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../care/providers/care_provider.dart';
import '../models/history_model.dart';
import '../providers/history_provider.dart';
import '../../../widgets/logout_action.dart';
import '../../../core/theme/app_colors.dart';

class HistoryScreen extends StatefulWidget {
  final String deviceMac;

  const HistoryScreen({super.key, required this.deviceMac});

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<HistoryProvider>().fetchHistory();
    });
  }

  @override
  Widget build(BuildContext context) {
    final historyProvider = context.watch<HistoryProvider>();
    final careProvider = context.watch<CareProvider>();

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text('历史趋势与报告', style: TextStyle(color: AppColors.textMain, fontSize: 18, fontWeight: FontWeight.bold)),
        backgroundColor: Colors.transparent,
        elevation: 0,
        actions: const [LogoutAction()],
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(48),
          child: _buildWindowToggle(historyProvider),
        ),
      ),
      body: _buildBody(historyProvider, careProvider),
    );
  }

  Widget _buildWindowToggle(HistoryProvider provider) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Row(
        children: [
          _buildToggleItem('日视图', 'day', provider),
          const SizedBox(width: 8),
          _buildToggleItem('周视图', 'week', provider),
        ],
      ),
    );
  }

  Widget _buildToggleItem(String label, String value, HistoryProvider provider) {
    final isSelected = provider.currentWindow == value;
    return GestureDetector(
      onTap: () => provider.setWindow(value),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
        decoration: BoxDecoration(
          color: isSelected ? AppColors.primary : AppColors.surface,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: isSelected ? AppColors.primary : AppColors.border),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: isSelected ? Colors.white : AppColors.textSub,
            fontSize: 12,
            fontWeight: FontWeight.bold,
          ),
        ),
      ),
    );
  }

  Widget _buildBody(HistoryProvider history, CareProvider care) {
    if (history.status == HistoryLoadStatus.loading) {
      return const Center(child: CircularProgressIndicator(color: AppColors.primary));
    }

    if (history.status == HistoryLoadStatus.error) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(history.errorMessage ?? '加载失败', style: const TextStyle(color: AppColors.textSub, fontWeight: FontWeight.bold)),
            TextButton(onPressed: () => history.fetchHistory(), child: const Text('重试', style: TextStyle(color: AppColors.primary, fontWeight: FontWeight.bold))),
          ],
        ),
      );
    }

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        _buildTrendSection('心率趋势 (bpm)', history.trends),
        const SizedBox(height: 24),
        _buildHistoryListSection(history.history?.points ?? []),
        const SizedBox(height: 24),
        _buildReportsSection(care.profile?.healthReports ?? []),
      ],
    );
  }

  Widget _buildTrendSection(String title, List<TrendPoint> points) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(title, style: const TextStyle(color: AppColors.textMain, fontSize: 16, fontWeight: FontWeight.bold)),
        const SizedBox(height: 16),
        Container(
          height: 120,
          width: double.infinity,
          padding: const EdgeInsets.all(8),
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: AppColors.border),
          ),
          child: points.isEmpty
              ? const Center(child: Text('暂无趋势数据', style: TextStyle(color: AppColors.textMuted)))
              : CustomPaint(painter: SparklinePainter(points.map((e) => e.value).toList(), color: AppColors.primary)),
        ),
      ],
    );
  }

  Widget _buildHistoryListSection(List<HistoryBucket> buckets) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('数据概览', style: TextStyle(color: AppColors.textMain, fontSize: 16, fontWeight: FontWeight.bold)),
        const SizedBox(height: 12),
        if (buckets.isEmpty)
          const Text('暂无历史记录', style: TextStyle(color: AppColors.textMuted))
        else
          ...buckets.map((b) => _buildHistoryItem(b)),
      ],
    );
  }

  Widget _buildHistoryItem(HistoryBucket bucket) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.surface,
        border: Border(bottom: BorderSide(color: AppColors.border)),
      ),
      child: Row(
        children: [
          Expanded(
            flex: 2,
            child: Text(
              _formatBucketTime(bucket.bucketStart),
              style: const TextStyle(color: AppColors.textSub, fontSize: 12),
            ),
          ),
          Expanded(
            child: _buildBadge('心率', '${bucket.heartRate?.toInt() ?? '--'}'),
          ),
          Expanded(
            child: _buildBadge('步数', '${bucket.steps}'),
          ),
          Expanded(
            child: _buildBadge('SOS', '${bucket.sosCount}', color: bucket.sosCount > 0 ? AppColors.error : null),
          ),
        ],
      ),
    );
  }

  String _formatBucketTime(String iso) {
    try {
      final dt = DateTime.parse(iso);
      return '${dt.month}/${dt.day} ${dt.hour}:${dt.minute.toString().padLeft(2, '0')}';
    } catch (_) {
      return iso;
    }
  }

  Widget _buildBadge(String label, String value, {Color? color}) {
    return Column(
      children: [
        Text(value, style: TextStyle(color: color ?? AppColors.textMain, fontWeight: FontWeight.bold, fontSize: 14)),
        Text(label, style: const TextStyle(color: AppColors.textMuted, fontSize: 10)),
      ],
    );
  }

  Widget _buildReportsSection(List<dynamic> reports) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('健康报告摘要', style: TextStyle(color: AppColors.textMain, fontSize: 16, fontWeight: FontWeight.bold)),
        const SizedBox(height: 12),
        if (reports.isEmpty)
          const Text('暂无专业报告', style: TextStyle(color: AppColors.textMuted))
        else
          ...reports.map((r) => Card(
            color: AppColors.surface,
            elevation: 0,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12), side: BorderSide(color: AppColors.border)),
            child: ListTile(
              title: Text(r.title, style: const TextStyle(color: AppColors.textMain, fontSize: 14, fontWeight: FontWeight.bold)),
              subtitle: Text(r.createdAt, style: const TextStyle(color: AppColors.textSub, fontSize: 11)),
              trailing: const Icon(Icons.description_outlined, color: AppColors.primary),
            ),
          )),
      ],
    );
  }
}

class SparklinePainter extends CustomPainter {
  final List<double> values;
  final Color color;
  SparklinePainter(this.values, {required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    if (values.length < 2) return;

    final paint = Paint()
      ..color = color
      ..strokeWidth = 2.0
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;

    final maxVal = values.reduce((a, b) => a > b ? a : b);
    final minVal = values.reduce((a, b) => a < b ? a : b);
    final range = (maxVal - minVal).clamp(1.0, double.infinity);

    final path = Path();
    final xStep = size.width / (values.length - 1);

    for (var i = 0; i < values.length; i++) {
      final x = i * xStep;
      final y = size.height - ((values[i] - minVal) / range * size.height);
      if (i == 0) {
        path.moveTo(x, y);
      } else {
        path.lineTo(x, y);
      }
    }

    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => true;
}
