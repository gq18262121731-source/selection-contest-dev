import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/theme/app_colors.dart';
import '../../../widgets/logout_action.dart';
import '../models/health_model.dart';
import '../providers/health_provider.dart';
import '../providers/history_provider.dart';
import '../repositories/health_repository.dart';
import 'history_screen.dart';

class DeviceDetailScreen extends StatefulWidget {
  final String deviceMac;

  const DeviceDetailScreen({super.key, required this.deviceMac});

  @override
  State<DeviceDetailScreen> createState() => _DeviceDetailScreenState();
}

class _DeviceDetailScreenState extends State<DeviceDetailScreen> {
  (double?, double?) _parseBloodPressure(String? value) {
    if (value == null || value.trim().isEmpty) {
      return (null, null);
    }

    final parts = value.split('/');
    if (parts.length != 2) {
      return (null, null);
    }

    final systolic = double.tryParse(parts[0].trim());
    final diastolic = double.tryParse(parts[1].trim());
    return (systolic, diastolic);
  }

  String _formatNumber(num? value, {int fractionDigits = 0}) {
    if (value == null) return '--';
    if (fractionDigits == 0) return value.toInt().toString();
    return value.toStringAsFixed(fractionDigits);
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<HealthProvider>().init();
    });
  }

  @override
  Widget build(BuildContext context) {
    final healthProvider = context.watch<HealthProvider>();

    return Scaffold(
      backgroundColor: const Color(0xFFF8FAFC),
      appBar: AppBar(
        title: Text(
          '实时监测: ${widget.deviceMac}',
          style: const TextStyle(color: AppColors.textMain, fontSize: 20, fontWeight: FontWeight.bold), // Increased from 16
        ),
        backgroundColor: Colors.transparent,
        elevation: 0,
        actions: [
          IconButton(
            icon: const Icon(Icons.history, color: AppColors.textSub),
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (context) => ChangeNotifierProvider(
                    create: (context) => HistoryProvider(
                      context.read<HealthRepository>(),
                      widget.deviceMac,
                    ),
                    child: HistoryScreen(deviceMac: widget.deviceMac),
                  ),
                ),
              );
            },
          ),
          const LogoutAction(),
          _buildConnectionStatus(healthProvider),
        ],
      ),
      body: _buildBody(healthProvider),
    );
  }

  Widget _buildConnectionStatus(HealthProvider provider) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Center(
        child: Container(
          width: 12,
          height: 12,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: provider.isWsConnected ? AppColors.success : AppColors.error,
            boxShadow: [
              if (provider.isWsConnected)
                BoxShadow(color: AppColors.success.withOpacity(0.4), blurRadius: 8, spreadRadius: 1),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildBody(HealthProvider provider) {
    if (provider.status == HealthStatus.loading) {
      return const Center(child: CircularProgressIndicator(color: Color(0xFF2563EB)));
    }

    if (provider.status == HealthStatus.error) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.error_outline, size: 48, color: AppColors.error),
            const SizedBox(height: 16),
            Text(provider.errorMessage ?? '加载失败', style: const TextStyle(color: AppColors.textSub)),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: () => provider.init(),
              child: const Text('重试'),
            ),
          ],
        ),
      );
    }

    final data = provider.data;
    if (data == null) {
      return const Center(child: Text('暂无实时数据', style: TextStyle(color: AppColors.textMuted)));
    }

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        children: [
          _buildHealthScoreCard(data.healthScore),
          const SizedBox(height: 16),
          _buildCompactMetrics(data),
          const SizedBox(height: 16),
          if (provider.historyBuffer.isNotEmpty) ...[
            _buildFourRealtimeCharts(provider.historyBuffer),
          ],
          if (data.sosFlag)
            Padding(
              padding: const EdgeInsets.only(top: 24),
              child: Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: AppColors.error.withOpacity(0.05),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: AppColors.error.withOpacity(0.3)),
                ),
                child: const Row(
                  children: [
                    Icon(Icons.warning_amber_rounded, color: AppColors.error),
                    SizedBox(width: 12),
                    Text(
                      '紧急求助（SOS）已触发',
                      style: TextStyle(color: AppColors.error, fontWeight: FontWeight.bold),
                    ),
                  ],
                ),
              ),
            ),
          const SizedBox(height: 24),
          const Text('实时数据会自动刷新，没有新包时会保留最近一次有效样本', style: TextStyle(color: AppColors.textMuted, fontSize: 16)), // Increased from 12
        ],
      ),
    );
  }

  Widget _buildHealthScoreCard(int? score) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [AppColors.primary, AppColors.primary.withOpacity(0.8)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(24),
        boxShadow: [
          BoxShadow(
            color: AppColors.primary.withOpacity(0.2),
            blurRadius: 10,
            offset: const Offset(0, 4),
          )
        ],
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          const Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('实时健康分', style: TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.bold)), // Increased from 16
              SizedBox(height: 6),
              Text('今日状态监测中', style: TextStyle(color: Colors.white70, fontSize: 16)), // Increased from 12
            ],
          ),
          Text(
            '${score ?? '--'}',
            style: const TextStyle(color: Colors.white, fontSize: 56, fontWeight: FontWeight.bold), // Increased from 48
          ),
        ],
      ),
    );
  }

  Widget _buildCompactMetrics(HealthData data) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      alignment: WrapAlignment.spaceEvenly,
      children: [
        _buildChip(Icons.favorite, '心率', _formatNumber(data.heartRate), 'bpm', AppColors.error),
        _buildChip(Icons.water_drop, '血氧', _formatNumber(data.bloodOxygen), '%', AppColors.primary),
        _buildChip(Icons.speed, '血压', data.bloodPressure ?? '--', 'mmHg', Colors.purple),
        _buildChip(Icons.thermostat, '体温', _formatNumber(data.temperature, fractionDigits: 1), '°C', AppColors.warning),
        _buildChip(Icons.directions_walk, '步数', _formatNumber(data.steps), '步', AppColors.success),
        _buildChip(Icons.battery_charging_full, '电量', _formatNumber(data.battery), '%', Colors.teal),
      ],
    );
  }

  Widget _buildChip(IconData icon, String label, String value, String unit, Color color) {
    return Container(
      width: (MediaQuery.of(context).size.width - 48) / 3,
      padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 8),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, size: 16, color: color), // Increased from 14
              const SizedBox(width: 4),
              Text(label, style: const TextStyle(color: AppColors.textSub, fontSize: 13, fontWeight: FontWeight.w500)), // Increased from 11
            ],
          ),
          const SizedBox(height: 8),
          Row(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.baseline,
            textBaseline: TextBaseline.alphabetic,
            children: [
              Text(value, style: const TextStyle(color: AppColors.textMain, fontSize: 18, fontWeight: FontWeight.bold)), // Increased from 16
              if (unit.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(left: 2),
                  child: Text(unit, style: const TextStyle(color: AppColors.textSub, fontSize: 12, fontWeight: FontWeight.w500)), // Increased from 9
                ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildFourRealtimeCharts(List<HealthData> history) {
    if (history.isEmpty) return const SizedBox.shrink();

    final hrSpots = <FlSpot>[];
    final boSpots = <FlSpot>[];
    final sbpSpots = <FlSpot>[];
    final dbpSpots = <FlSpot>[];
    final tempSpots = <FlSpot>[];

    for (int i = 0; i < history.length; i++) {
      final item = history[i];
      if (item.heartRate != null && item.heartRate! > 0) {
        hrSpots.add(FlSpot(i.toDouble(), item.heartRate!.toDouble()));
      }
      if (item.bloodOxygen != null && item.bloodOxygen! > 0) {
        boSpots.add(FlSpot(i.toDouble(), item.bloodOxygen!.toDouble()));
      }
      if (item.temperature != null && item.temperature! > 0) {
        tempSpots.add(FlSpot(i.toDouble(), item.temperature!.toDouble()));
      }

      final (sbp, dbp) = _parseBloodPressure(item.bloodPressure);
      if (sbp != null) sbpSpots.add(FlSpot(i.toDouble(), sbp));
      if (dbp != null) dbpSpots.add(FlSpot(i.toDouble(), dbp));
    }

    return Column(
      children: [
        _buildSingleChart('心率曲线', hrSpots, AppColors.error, 40, 180, 'bpm'),
        const SizedBox(height: 16),
        _buildSingleChart('血氧曲线', boSpots, AppColors.primary, 80, 100, '%'),
        const SizedBox(height: 16),
        _buildDoubleChart('血压曲线（收缩/舒张）', sbpSpots, dbpSpots, Colors.purple, Colors.deepPurple, 40, 200, 'mmHg'),
        const SizedBox(height: 16),
        _buildSingleChart('体温曲线', tempSpots, AppColors.warning, 35, 42, '°C'),
      ],
    );
  }

  Widget _buildSingleChart(String title, List<FlSpot> spots, Color color, double minY, double maxY, String unit) {
    return _buildChartWrapper(
      title: title,
      chart: spots.length < 2
          ? _buildChartEmptyState('等待更多 $unit 数据点...')
          : LineChart(
              LineChartData(
                minY: minY,
                maxY: maxY,
                gridData: FlGridData(
                  show: true,
                  drawVerticalLine: false,
                  getDrawingHorizontalLine: (value) => FlLine(color: Colors.white.withValues(alpha: 0.05), strokeWidth: 1),
                ),
                titlesData: FlTitlesData(
                  show: true,
                  bottomTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                  topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                  rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                  leftTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      reservedSize: 36,
                      getTitlesWidget: (val, meta) => Text(
                        val.toInt().toString(),
                        style: const TextStyle(color: AppColors.textMuted, fontSize: 12), // Increased from 10
                      ),
                    ),
                  ),
                ),
                borderData: FlBorderData(show: false),
                lineBarsData: [
                  LineChartBarData(
                    spots: spots,
                    isCurved: true,
                    color: color,
                    barWidth: 2,
                    isStrokeCapRound: true,
                    dotData: const FlDotData(show: false),
                    belowBarData: BarAreaData(show: true, color: color.withValues(alpha: 0.1)),
                  ),
                ],
              ),
            ),
    );
  }

  Widget _buildDoubleChart(
    String title,
    List<FlSpot> spots1,
    List<FlSpot> spots2,
    Color color1,
    Color color2,
    double minY,
    double maxY,
    String unit,
  ) {
    return _buildChartWrapper(
      title: title,
      chart: spots1.length < 2 && spots2.length < 2
          ? _buildChartEmptyState('等待更多 $unit 数据点...')
          : LineChart(
              LineChartData(
                minY: minY,
                maxY: maxY,
                gridData: FlGridData(
                  show: true,
                  drawVerticalLine: false,
                  getDrawingHorizontalLine: (value) => FlLine(color: Colors.white.withValues(alpha: 0.05), strokeWidth: 1),
                ),
                titlesData: FlTitlesData(
                  show: true,
                  bottomTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                  topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                  rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                  leftTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      reservedSize: 36,
                      getTitlesWidget: (val, meta) => Text(
                        val.toInt().toString(),
                        style: const TextStyle(color: AppColors.textMuted, fontSize: 12), // Increased from 10
                      ),
                    ),
                  ),
                ),
                borderData: FlBorderData(show: false),
                lineBarsData: [
                  if (spots1.isNotEmpty)
                    LineChartBarData(
                      spots: spots1,
                      isCurved: true,
                      color: color1,
                      barWidth: 2,
                      isStrokeCapRound: true,
                      dotData: const FlDotData(show: false),
                    ),
                  if (spots2.isNotEmpty)
                    LineChartBarData(
                      spots: spots2,
                      isCurved: true,
                      color: color2,
                      barWidth: 2,
                      isStrokeCapRound: true,
                      dotData: const FlDotData(show: false),
                    ),
                ],
              ),
            ),
    );
  }

  Widget _buildChartEmptyState(String message) {
    return Center(
      child: Text(
        message,
        style: const TextStyle(color: AppColors.textMuted, fontSize: 14), // Increased from 12
      ),
    );
  }

  Widget _buildChartWrapper({required String title, required Widget chart}) {
    return Container(
      height: 180,
      padding: const EdgeInsets.only(top: 12, right: 16, left: 4, bottom: 8),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(left: 12, bottom: 8),
            child: Row(
              children: [
                const Icon(Icons.show_chart, color: AppColors.textMuted, size: 16),
                const SizedBox(width: 8),
                Text(title, style: const TextStyle(color: AppColors.textSub, fontSize: 14, fontWeight: FontWeight.bold)), // Increased from 11
              ],
            ),
          ),
          Expanded(child: chart),
        ],
      ),
    );
  }
}
