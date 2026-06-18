import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../widgets/logout_action.dart';
import '../../agent/widgets/ai_chat_dialog.dart';
import '../../auth/providers/auth_provider.dart';
import '../../../core/network/server_endpoint_config.dart';
import '../../../core/theme/app_colors.dart';
import '../../session/models/user_model.dart';
import '../../settings/screens/server_settings_screen.dart';
import '../../voice/screens/voice_screen.dart';
import '../models/care_profile_model.dart';
import '../providers/care_provider.dart';

class ElderHomeScreen extends StatefulWidget {
  const ElderHomeScreen({super.key});

  @override
  State<ElderHomeScreen> createState() => _ElderHomeScreenState();
}

class _ElderHomeScreenState extends State<ElderHomeScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<CareProvider>().startAutoRefresh();
    });
  }

  @override
  void dispose() {
    context.read<CareProvider>().stopAutoRefresh();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final careProvider = context.watch<CareProvider>();
    final authUser = context.watch<AuthProvider>().user;
    final endpoint = context.watch<ServerEndpointConfig>();
    final profile = careProvider.profile;
    final metric = profile != null && profile.deviceMetrics.isNotEmpty
        ? profile.deviceMetrics.first
        : null;
    final elderName = metric?.subjectName ?? authUser?.name ?? '长者';

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: Text(
          '$elderName的健康守护',
          style: const TextStyle(
            color: AppColors.textMain,
            fontSize: 28,
            fontWeight: FontWeight.w900,
          ),
        ),
        backgroundColor: Colors.transparent,
        elevation: 0,
        centerTitle: true,
        iconTheme: const IconThemeData(color: AppColors.textMain),
        actions: [
          IconButton(
            icon: const Icon(Icons.settings_ethernet, color: AppColors.textSub),
            tooltip: '服务器设置',
            onPressed: () {
              Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => const ServerSettingsScreen(),
                ),
              );
            },
          ),
          const LogoutAction(),
        ],
      ),
      body: _buildBody(careProvider, elderName, metric, authUser, endpoint),
    );
  }

  Widget _buildBody(
    CareProvider provider,
    String elderName,
    CareAccessDeviceMetric? metric,
    SessionUser? authUser,
    ServerEndpointConfig endpoint,
  ) {
    if (provider.status == CareLoadStatus.loading && provider.profile == null) {
      return const Center(
        child: CircularProgressIndicator(color: Color(0xFF2563EB)),
      );
    }

    if (provider.status == CareLoadStatus.error && provider.profile == null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(
              provider.errorMessage ?? '加载失败',
              style: const TextStyle(
                  color: AppColors.textSub,
                  fontSize: 22,
                  fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 24),
            ElevatedButton(
              onPressed: () => provider.fetchProfile(),
              child: const Text('重试',
                  style: TextStyle(
                      fontSize: 24,
                      fontWeight: FontWeight.w800,
                      color: Colors.white)),
            ),
            const SizedBox(height: 16),
            OutlinedButton.icon(
              onPressed: () {
                Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (_) => const ServerSettingsScreen(),
                  ),
                );
              },
              icon: const Icon(Icons.settings_ethernet),
              label: const Text('服务器设置'),
            ),
          ],
        ),
      );
    }

    final profile = provider.profile;
    if (profile == null) return const SizedBox.shrink();

    final hasDevice =
        profile.boundDeviceMacs.isNotEmpty || profile.deviceMetrics.isNotEmpty;
    final deviceStatus = metric?.deviceStatus ?? 'unknown';
    final batteryLabel = metric?.battery != null ? '${metric!.battery}%' : '--';

    return SingleChildScrollView(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _buildHeaderCard(elderName),
            const SizedBox(height: 20),
            _buildDeviceStatusCard(
                metric, hasDevice, deviceStatus, batteryLabel),
            const SizedBox(height: 20),
            _buildRealtimeMetrics(metric),
            const SizedBox(height: 24),
            Row(
              children: [
                Expanded(
                  child: _buildBigButton(
                    Icons.phone,
                    '联系家属',
                    Colors.blue,
                  ),
                ),
                const SizedBox(width: 24),
                Expanded(
                  child: _buildBigButton(
                    Icons.warning,
                    '一键求助',
                    Colors.red,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 20),
            _buildBigButton(
              Icons.mic,
              '语音对话',
              Colors.purple,
              onTap: () => Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => const VoiceScreen(),
                ),
              ),
            ),
            const SizedBox(height: 20),
            _buildBigButton(
              Icons.auto_awesome,
              '助手帮我看看',
              AppColors.primary,
              onTap: () => showModalBottomSheet(
                context: context,
                isScrollControlled: true,
                backgroundColor: Colors.transparent,
                builder: (context) => AiChatDialog(
                  isElder: true,
                  deviceMac: metric?.deviceMac,
                  availableDevices: profile.deviceMetrics,
                ),
              ),
            ),
            const SizedBox(height: 20),
            hasDevice
                ? _buildUnbindDeviceButton(provider)
                : _buildBindDeviceButton(provider),
            const SizedBox(height: 24),
            _buildInfoCard(
              profile.basicAdvice.isNotEmpty
                  ? profile.basicAdvice
                  : hasDevice
                      ? '当前账号已绑定到有效设备链路，可查看设备指标、评估结果和健康报告摘要。'
                      : '请先登记并绑定手环，绑定成功后就能在这里看到实时指标和提醒。',
            ),
            const SizedBox(height: 20),
            _buildDebugCard(provider, metric, authUser, endpoint),
          ],
        ),
      ),
    );
  }

  Widget _buildDebugCard(
    CareProvider provider,
    CareAccessDeviceMetric? metric,
    SessionUser? authUser,
    ServerEndpointConfig endpoint,
  ) {
    final profile = provider.profile;
    final latestSample = metric?.latestSample;
    final requestUrl = '${endpoint.origin}/api/v1/care/access-profile/me';

    final rawSummary = <String, dynamic>{
      'binding_state': profile?.bindingState,
      'bound_device_macs': profile?.boundDeviceMacs,
      'latest_sample': latestSample,
    };
    final parsedSummary = <String, dynamic>{
      'device_mac': metric?.deviceMac,
      'device_name': metric?.deviceName,
      'device_status': metric?.deviceStatus,
      'heart_rate': metric?.heartRate,
      'blood_oxygen': metric?.bloodOxygen,
      'temperature': metric?.temperature,
      'blood_pressure': metric?.bloodPressure,
      'battery': metric?.battery,
      'steps': metric?.steps,
      'health_score': metric?.healthScore,
      'has_realtime_sample': metric?.hasRealtimeSample,
    };

    return ExpansionTile(
      tilePadding: const EdgeInsets.symmetric(horizontal: 16),
      collapsedShape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(20),
        side: const BorderSide(color: AppColors.border),
      ),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(20),
        side: const BorderSide(color: AppColors.border),
      ),
      backgroundColor: AppColors.surface,
      collapsedBackgroundColor: AppColors.surface,
      title: const Text(
        '手环调试信息',
        style: TextStyle(
          color: AppColors.textMain,
          fontWeight: FontWeight.bold,
        ),
      ),
      subtitle: const Text(
        '如果老人端没有显示数据，请截图这里的信息',
        style: TextStyle(color: AppColors.textSub),
      ),
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _buildDebugRow('当前用户', authUser?.username ?? '--'),
              const SizedBox(height: 8),
              _buildDebugRow('当前角色', authUser?.role ?? '--'),
              const SizedBox(height: 8),
              _buildDebugRow('主系统', endpoint.origin),
              const SizedBox(height: 8),
              _buildDebugRow('请求 URL', requestUrl),
              const SizedBox(height: 8),
              _buildDebugRow('绑定状态', profile?.bindingState ?? '--'),
              const SizedBox(height: 8),
              _buildDebugRow(
                '绑定设备',
                (profile?.boundDeviceMacs.isNotEmpty ?? false)
                    ? profile!.boundDeviceMacs.join(', ')
                    : '--',
              ),
              const SizedBox(height: 12),
              const Text(
                'access-profile 原始关键信息',
                style: TextStyle(
                  color: AppColors.textSub,
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 6),
              SelectableText(
                const JsonEncoder.withIndent('  ').convert(rawSummary),
                style: const TextStyle(
                  color: AppColors.textMain,
                  fontSize: 12,
                  height: 1.45,
                ),
              ),
              const SizedBox(height: 12),
              const Text(
                '页面解析后的模型字段',
                style: TextStyle(
                  color: AppColors.textSub,
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 6),
              SelectableText(
                const JsonEncoder.withIndent('  ').convert(parsedSummary),
                style: const TextStyle(
                  color: AppColors.textMain,
                  fontSize: 12,
                  height: 1.45,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildDebugRow(String label, String value) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 78,
          child: Text(
            label,
            style: const TextStyle(
              color: AppColors.textSub,
              fontSize: 13,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: SelectableText(
            value,
            style: const TextStyle(
              color: AppColors.textMain,
              fontSize: 13,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildHeaderCard(String elderName) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: AppColors.primary,
        borderRadius: BorderRadius.circular(20),
        boxShadow: [
          BoxShadow(
            color: AppColors.primary.withValues(alpha: 0.2),
            blurRadius: 15,
            offset: const Offset(0, 8),
          )
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Text(
            elderName,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 48,
              fontWeight: FontWeight.w900,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildDeviceStatusCard(
    CareAccessDeviceMetric? metric,
    bool hasDevice,
    String status,
    String battery,
  ) {
    final normalizedStatus = status.toLowerCase();
    final isOnline =
        normalizedStatus == 'online' || normalizedStatus == 'normal';

    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(24),
        border: Border.all(
          width: 3,
          color: hasDevice
              ? (isOnline ? AppColors.success : AppColors.warning)
              : AppColors.error,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.05),
            blurRadius: 10,
            offset: const Offset(0, 4),
          )
        ],
      ),
      child: Column(
        children: [
          Icon(
            hasDevice ? Icons.watch : Icons.watch_off,
            size: 64,
            color: hasDevice
                ? (isOnline ? Colors.green : Colors.orange)
                : Colors.red,
          ),
          const SizedBox(height: 16),
          Text(
            hasDevice ? '手环已连接' : '手环未连接',
            style: const TextStyle(
              color: AppColors.textMain,
              fontSize: 32,
              fontWeight: FontWeight.w900,
            ),
          ),
          if (metric != null) ...[
            const SizedBox(height: 8),
            Text(
              '${metric.deviceName} · ${metric.deviceMac}',
              textAlign: TextAlign.center,
              style: const TextStyle(
                  color: AppColors.textSub,
                  fontSize: 20,
                  fontWeight: FontWeight.bold),
            ),
          ] else ...[
            const SizedBox(height: 8),
            const Text(
              '请戴好手环，数据会自动同步。',
              textAlign: TextAlign.center,
              style: TextStyle(
                  color: AppColors.textSub,
                  fontSize: 20,
                  fontWeight: FontWeight.bold),
            ),
          ],
          const SizedBox(height: 12),
          if (hasDevice)
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Icon(Icons.battery_full,
                    color: AppColors.success, size: 28),
                const SizedBox(width: 8),
                Text(
                  '电量: $battery',
                  style: const TextStyle(
                      color: AppColors.textMain,
                      fontSize: 24,
                      fontWeight: FontWeight.w800),
                ),
              ],
            ),
        ],
      ),
    );
  }

  Widget _buildRealtimeMetrics(CareAccessDeviceMetric? metric) {
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      children: [
        _buildMetricCard(
          '心率',
          _formatDouble(metric?.heartRate),
          'bpm',
          Icons.favorite,
        ),
        _buildMetricCard(
          '血压',
          metric?.bloodPressure ?? '--',
          'mmHg',
          Icons.bloodtype,
        ),
        _buildMetricCard(
          '血氧',
          _formatDouble(metric?.bloodOxygen),
          '%',
          Icons.water_drop,
        ),
        _buildMetricCard(
          '体温',
          _formatDouble(metric?.temperature, fractionDigits: 1),
          '°C',
          Icons.thermostat,
        ),
        _buildMetricCard(
          '步数',
          metric?.steps?.toString() ?? '--',
          '步',
          Icons.directions_walk,
        ),
        _buildMetricCard(
          '健康度',
          metric?.healthScore?.toString() ?? '--',
          '分',
          Icons.monitor_heart,
        ),
      ],
    );
  }

  Widget _buildMetricCard(
    String label,
    String value,
    String unit,
    IconData icon,
  ) {
    return Container(
      width: (MediaQuery.of(context).size.width - 60) / 2,
      padding: const EdgeInsets.symmetric(vertical: 24, horizontal: 16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.04),
            blurRadius: 8,
            offset: const Offset(0, 4),
          )
        ],
        border: Border.all(color: AppColors.border, width: 2),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Icon(icon, color: const Color(0xFF2563EB), size: 42),
          const SizedBox(height: 12),
          Text(
            label,
            style: const TextStyle(
                color: AppColors.textSub,
                fontSize: 24,
                fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 6),
          RichText(
            textAlign: TextAlign.center,
            text: TextSpan(
              children: [
                TextSpan(
                  text: value,
                  style: const TextStyle(
                    color: AppColors.textMain,
                    fontSize: 56, // Enormous font for elders
                    fontWeight: FontWeight.w900,
                  ),
                ),
                TextSpan(
                  text: ' $unit',
                  style: const TextStyle(
                      color: AppColors.textSub,
                      fontSize: 24,
                      fontWeight: FontWeight.w900),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildBindDeviceButton(CareProvider provider) {
    return ElevatedButton.icon(
      onPressed: provider.isMutating
          ? null
          : () => _showBindDeviceDialogSafely(provider),
      icon: provider.isMutating
          ? const SizedBox(
              width: 24,
              height: 24,
              child: CircularProgressIndicator(
                  strokeWidth: 2, color: Colors.white),
            )
          : const Icon(Icons.add_link, size: 32, color: Colors.white),
      label: Text(
        provider.isMutating ? '处理中...' : '绑定新手环',
        style: const TextStyle(
          fontSize: 26,
          color: Colors.white,
          fontWeight: FontWeight.w900,
        ),
      ),
      style: ElevatedButton.styleFrom(
        padding: const EdgeInsets.symmetric(vertical: 24),
        backgroundColor: AppColors.primary,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      ),
    );
  }

  Widget _buildUnbindDeviceButton(CareProvider provider) {
    return OutlinedButton.icon(
      onPressed: provider.isMutating
          ? null
          : () async {
              final confirmed = await showDialog<bool>(
                context: context,
                builder: (dialogContext) => AlertDialog(
                  backgroundColor: AppColors.surface,
                  shape: RoundedRectangleBorder(
                    side: const BorderSide(color: AppColors.warning, width: 2),
                    borderRadius: BorderRadius.circular(16),
                  ),
                  title: const Text(
                    '解绑手环设备',
                    style: TextStyle(
                      color: AppColors.warning,
                      fontWeight: FontWeight.w900,
                      fontSize: 24,
                    ),
                  ),
                  content: const Text(
                    '确认解绑后，这只手环会与当前账号解除绑定，实时健康数据将停止同步。',
                    style: TextStyle(
                      color: AppColors.textMain,
                      fontSize: 20,
                      fontWeight: FontWeight.bold,
                      height: 1.5,
                    ),
                  ),
                  actions: [
                    TextButton(
                      onPressed: () => Navigator.pop(dialogContext, false),
                      child: const Text(
                        '取消',
                        style: TextStyle(
                            color: AppColors.textSub,
                            fontSize: 20,
                            fontWeight: FontWeight.bold),
                      ),
                    ),
                    TextButton(
                      onPressed: () => Navigator.pop(dialogContext, true),
                      child: const Text(
                        '确认解绑',
                        style: TextStyle(
                          color: AppColors.error,
                          fontWeight: FontWeight.w900,
                          fontSize: 20,
                        ),
                      ),
                    ),
                  ],
                ),
              );
              if (confirmed != true) return;

              final success = await provider.unbindSelfDevice();
              if (!mounted) return;
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: Text(
                    success
                        ? '手环已成功解绑'
                        : (provider.errorMessage ?? '解绑失败，请稍后重试'),
                    style: const TextStyle(fontSize: 18),
                  ),
                  backgroundColor:
                      success ? Colors.green.shade700 : Colors.red.shade700,
                ),
              );
            },
      icon: provider.isMutating
          ? const SizedBox(
              width: 24,
              height: 24,
              child: CircularProgressIndicator(
                  strokeWidth: 2, color: AppColors.warning),
            )
          : const Icon(Icons.link_off, size: 28, color: AppColors.warning),
      label: Text(
        provider.isMutating ? '处理中...' : '解绑手环设备',
        style: const TextStyle(
          fontSize: 22,
          color: AppColors.warning,
          fontWeight: FontWeight.w900,
        ),
      ),
      style: OutlinedButton.styleFrom(
        padding: const EdgeInsets.symmetric(vertical: 20),
        side: const BorderSide(color: AppColors.warning, width: 2),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      ),
    );
  }

  Widget _buildBigButton(
    IconData icon,
    String label,
    Color color, {
    VoidCallback? onTap,
  }) {
    return ElevatedButton(
      onPressed: onTap ??
          () {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(content: Text('正在尝试$label...')),
            );
          },
      style: ElevatedButton.styleFrom(
        backgroundColor: color.withValues(alpha: 0.08),
        foregroundColor: color,
        padding: const EdgeInsets.symmetric(vertical: 48),
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(24),
          side: BorderSide(color: color, width: 3),
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 64, color: color),
          const SizedBox(height: 16),
          Text(
            label,
            style: TextStyle(
                fontSize: 32,
                fontWeight: FontWeight.w900,
                color: color,
                letterSpacing: 2),
          ),
        ],
      ),
    );
  }

  Widget _buildInfoCard(String basicAdvice) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: AppColors.elderBlueBg, // Light blue background
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFBFDBFE), width: 2),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          const Text(
            '今日健康建议',
            style: TextStyle(
                color: AppColors.elderBlueText,
                fontSize: 32,
                fontWeight: FontWeight.w900),
          ),
          const SizedBox(height: 16),
          Text(
            basicAdvice,
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: AppColors.textMain,
              fontSize: 34,
              fontWeight: FontWeight.w900,
              height: 1.4,
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _showBindDeviceDialogSafely(CareProvider provider) async {
    provider.stopAutoRefresh();
    final result = await showDialog<_BindDeviceResult>(
      context: context,
      builder: (_) => _BindDeviceDialog(
        normalizeMacInput: _normalizeMacInput,
        isValidMac: _isValidMac,
      ),
    );
    if (mounted) {
      provider.startAutoRefresh();
    }
    if (result == null) return;
    await WidgetsBinding.instance.endOfFrame;
    if (!mounted) return;

    final success = await provider.bindSelfDevice(
      result.macAddress,
      deviceName: result.deviceName,
    );
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          success ? '手环已成功登记并绑定' : (provider.errorMessage ?? '绑定手环失败，请稍后重试'),
          style: const TextStyle(fontSize: 18),
        ),
        backgroundColor: success ? Colors.green.shade700 : Colors.red.shade700,
      ),
    );
  }

  String _formatDouble(double? value, {int fractionDigits = 0}) {
    if (value == null) return '--';
    return value.toStringAsFixed(fractionDigits);
  }

  String _normalizeMacInput(String rawValue) {
    final compact =
        rawValue.replaceAll(RegExp(r'[^0-9A-Fa-f]'), '').toUpperCase();
    if (compact.length != 12) {
      return rawValue.trim().toUpperCase();
    }
    final parts = <String>[];
    for (var index = 0; index < compact.length; index += 2) {
      parts.add(compact.substring(index, index + 2));
    }
    return parts.join(':');
  }

  bool _isValidMac(String value) {
    final compact = value.replaceAll(':', '');
    return RegExp(r'^[0-9A-F]{12}$').hasMatch(compact);
  }
}

class _BindDeviceResult {
  final String macAddress;
  final String? deviceName;

  const _BindDeviceResult({
    required this.macAddress,
    required this.deviceName,
  });
}

class _BindDeviceDialog extends StatefulWidget {
  final String Function(String rawValue) normalizeMacInput;
  final bool Function(String value) isValidMac;

  const _BindDeviceDialog({
    required this.normalizeMacInput,
    required this.isValidMac,
  });

  @override
  State<_BindDeviceDialog> createState() => _BindDeviceDialogState();
}

class _BindDeviceDialogState extends State<_BindDeviceDialog> {
  late final TextEditingController _macController;
  late final TextEditingController _nameController;
  String? _localError;

  @override
  void initState() {
    super.initState();
    _macController = TextEditingController();
    _nameController = TextEditingController(text: 'T10-WATCH');
  }

  @override
  void dispose() {
    _macController.dispose();
    _nameController.dispose();
    super.dispose();
  }

  void _submit() {
    final normalizedMac = widget.normalizeMacInput(_macController.text);
    if (!widget.isValidMac(normalizedMac)) {
      setState(() {
        _localError = '请输入正确的手环 MAC 地址';
      });
      return;
    }

    Navigator.of(context).pop(
      _BindDeviceResult(
        macAddress: normalizedMac,
        deviceName: _nameController.text.trim(),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      backgroundColor: AppColors.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: const BorderSide(color: AppColors.primary, width: 2),
      ),
      title: const Text(
        '登记并绑定手环',
        style: TextStyle(
          color: AppColors.primary,
          fontWeight: FontWeight.w900,
          fontSize: 26,
        ),
      ),
      content: SizedBox(
        width: 420,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _BindDeviceDialogField(
              controller: _macController,
              label: '手环 MAC 地址',
              hintText: '例如 54:10:26:01:00:DF',
              textInputAction: TextInputAction.next,
              onChanged: (_) {
                if (_localError != null) {
                  setState(() {
                    _localError = null;
                  });
                }
              },
              onSubmitted: (_) => FocusScope.of(context).nextFocus(),
            ),
            const SizedBox(height: 12),
            _BindDeviceDialogField(
              controller: _nameController,
              label: '设备名称',
              hintText: '默认 T10-WATCH',
              textInputAction: TextInputAction.done,
              onSubmitted: (_) => _submit(),
            ),
            const SizedBox(height: 8),
            const Text(
              '支持输入 12 位十六进制 MAC，系统会自动格式化。',
              style: TextStyle(
                color: AppColors.textSub,
                fontSize: 16,
                fontWeight: FontWeight.bold,
              ),
            ),
            if (_localError != null) ...[
              const SizedBox(height: 12),
              Text(
                _localError!,
                style: const TextStyle(color: Colors.redAccent, fontSize: 16),
              ),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text(
            '取消',
            style: TextStyle(
              color: AppColors.textSub,
              fontSize: 20,
              fontWeight: FontWeight.bold,
            ),
          ),
        ),
        TextButton(
          onPressed: _submit,
          child: const Text(
            '确认绑定',
            style: TextStyle(
              color: AppColors.primary,
              fontWeight: FontWeight.w900,
              fontSize: 20,
            ),
          ),
        ),
      ],
    );
  }
}

class _BindDeviceDialogField extends StatelessWidget {
  final TextEditingController controller;
  final String label;
  final String hintText;
  final TextInputAction textInputAction;
  final ValueChanged<String>? onChanged;
  final ValueChanged<String>? onSubmitted;

  const _BindDeviceDialogField({
    required this.controller,
    required this.label,
    required this.hintText,
    required this.textInputAction,
    this.onChanged,
    this.onSubmitted,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(
            color: AppColors.textMain,
            fontSize: 18,
            fontWeight: FontWeight.bold,
          ),
        ),
        const SizedBox(height: 8),
        TextField(
          controller: controller,
          onChanged: onChanged,
          onSubmitted: onSubmitted,
          autocorrect: false,
          enableSuggestions: false,
          textInputAction: textInputAction,
          style: const TextStyle(
            color: AppColors.textMain,
            fontSize: 18,
            fontWeight: FontWeight.bold,
          ),
          decoration: InputDecoration(
            hintText: hintText,
            hintStyle: const TextStyle(color: AppColors.textMuted),
            filled: true,
            fillColor: Colors.white,
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide: const BorderSide(
                color: AppColors.border,
                width: 1.5,
              ),
            ),
            focusedBorder: const OutlineInputBorder(
              borderRadius: BorderRadius.all(Radius.circular(12)),
              borderSide: BorderSide(color: AppColors.primary, width: 2),
            ),
          ),
        ),
      ],
    );
  }
}
