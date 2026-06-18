import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../../core/network/server_endpoint_config.dart';
import '../../../core/theme/app_colors.dart';
import '../../../widgets/logout_action.dart';
import '../../alarm/providers/alarm_provider.dart';
import '../../auth/providers/auth_provider.dart';
import '../../care/providers/care_provider.dart';
import '../widgets/vision_connection_debug_dialog.dart';

class ServerSettingsScreen extends StatefulWidget {
  const ServerSettingsScreen({super.key});

  @override
  State<ServerSettingsScreen> createState() => _ServerSettingsScreenState();
}

class _ServerSettingsScreenState extends State<ServerSettingsScreen> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _hostController;
  late final TextEditingController _portController;

  String _scheme = 'http';
  bool _isTesting = false;
  bool _isSaving = false;
  String? _testResult;

  @override
  void initState() {
    super.initState();
    final config = context.read<ServerEndpointConfig>();
    _hostController = TextEditingController(text: config.host);
    _portController = TextEditingController(text: config.port.toString());
    _scheme = config.scheme;
  }

  @override
  void dispose() {
    _hostController.dispose();
    _portController.dispose();
    super.dispose();
  }

  Future<void> _testConnection() async {
    if (!_formKey.currentState!.validate()) {
      return;
    }

    setState(() {
      _isTesting = true;
      _testResult = null;
    });

    final config = context.read<ServerEndpointConfig>();
    final host = _hostController.text;
    final port = int.parse(_portController.text);
    final error = await config.testConnection(
      host: host,
      port: port,
      scheme: _scheme,
    );

    if (error == null) {
      await config.save(
        host: host,
        port: port,
        scheme: _scheme,
      );

      if (!mounted) {
        return;
      }

      final authStatus = context.read<AuthProvider>().status;
      if (authStatus == AuthStatus.authenticated) {
        final careProvider = context.read<CareProvider>();
        careProvider.fetchProfile(silent: true);

        final alarmProvider = context.read<AlarmProvider>();
        alarmProvider.reloadFromEndpointChange();
      }
    }

    if (!mounted) {
      return;
    }

    setState(() {
      _isTesting = false;
      _testResult = error ?? '连接成功，已自动保存并应用当前服务器地址。';
    });
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) {
      return;
    }

    setState(() {
      _isSaving = true;
    });

    final config = context.read<ServerEndpointConfig>();
    await config.save(
      host: _hostController.text,
      port: int.parse(_portController.text),
      scheme: _scheme,
    );

    if (!mounted) {
      return;
    }

    final careProvider = context.read<CareProvider>();
    careProvider.fetchProfile();

    final alarmProvider = context.read<AlarmProvider>();
    alarmProvider.reloadFromEndpointChange();

    setState(() {
      _isSaving = false;
    });

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('服务器地址已更新为 ${config.origin}'),
      ),
    );
    Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    final config = context.watch<ServerEndpointConfig>();

    return Scaffold(
      backgroundColor: const Color(0xFFF8FAFC),
      appBar: AppBar(
        title: const Text(
          '服务器设置',
          style: TextStyle(
            color: AppColors.textMain,
            fontWeight: FontWeight.bold,
          ),
        ),
        backgroundColor: Colors.transparent,
        elevation: 0,
        iconTheme: const IconThemeData(color: AppColors.textMain),
        actions: const [LogoutAction()],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _buildInfoCard(config),
              const SizedBox(height: 16),
              _buildFieldLabel('协议'),
              const SizedBox(height: 8),
              DropdownButtonFormField<String>(
                initialValue: _scheme,
                dropdownColor: AppColors.surface,
                decoration: _inputDecoration(),
                items: const [
                  DropdownMenuItem(value: 'http', child: Text('HTTP')),
                  DropdownMenuItem(value: 'https', child: Text('HTTPS')),
                ],
                onChanged: (value) {
                  if (value == null) {
                    return;
                  }
                  setState(() {
                    _scheme = value;
                  });
                },
              ),
              const SizedBox(height: 16),
              _buildFieldLabel('服务器 IP / 域名'),
              const SizedBox(height: 8),
              TextFormField(
                controller: _hostController,
                style: const TextStyle(
                  color: AppColors.textMain,
                  fontWeight: FontWeight.bold,
                ),
                decoration: _inputDecoration(hintText: '例如 192.168.1.23'),
                validator: (value) {
                  if (value == null || value.trim().isEmpty) {
                    return '请输入服务器地址';
                  }
                  return null;
                },
              ),
              const SizedBox(height: 16),
              _buildFieldLabel('端口'),
              const SizedBox(height: 8),
              TextFormField(
                controller: _portController,
                style: const TextStyle(
                  color: AppColors.textMain,
                  fontWeight: FontWeight.bold,
                ),
                keyboardType: TextInputType.number,
                inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                decoration: _inputDecoration(hintText: '8000'),
                validator: (value) {
                  final port = int.tryParse(value ?? '');
                  if (port == null || port < 1 || port > 65535) {
                    return '请输入 1 到 65535 之间的端口';
                  }
                  return null;
                },
              ),
              const SizedBox(height: 20),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton(
                      onPressed:
                          _isTesting || _isSaving ? null : _testConnection,
                      style: OutlinedButton.styleFrom(
                        side: const BorderSide(color: AppColors.primary),
                        padding: const EdgeInsets.symmetric(vertical: 14),
                      ),
                      child: _isTesting
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Text('测试连接'),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: ElevatedButton(
                      onPressed: _isSaving || _isTesting ? null : _save,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color(0xFF2563EB),
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 14),
                      ),
                      child: _isSaving
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Text('保存并应用'),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(
                  onPressed: _isSaving || _isTesting
                      ? null
                      : () {
                          showDialog<void>(
                            context: context,
                            builder: (_) => const VisionConnectionDebugDialog(),
                          );
                        },
                  style: OutlinedButton.styleFrom(
                    side: const BorderSide(color: AppColors.border),
                    padding: const EdgeInsets.symmetric(vertical: 14),
                  ),
                  icon: const Icon(
                    Icons.monitor_heart_outlined,
                    color: AppColors.textMain,
                  ),
                  label: const Text(
                    '联调地址确认',
                    style: TextStyle(color: AppColors.textMain),
                  ),
                ),
              ),
              if (_testResult != null) ...[
                const SizedBox(height: 16),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: _testResult!.contains('成功')
                        ? Colors.green.withValues(alpha: 0.12)
                        : Colors.orange.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: _testResult!.contains('成功')
                          ? AppColors.success
                          : AppColors.warning,
                    ),
                  ),
                  child: Text(
                    _testResult!,
                    style: const TextStyle(color: AppColors.textMain),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildInfoCard(ServerEndpointConfig config) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.border),
        boxShadow: const [
          BoxShadow(color: Colors.black12, blurRadius: 4, offset: Offset(0, 2)),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            '当前后端地址',
            style: TextStyle(
              color: AppColors.textMain,
              fontSize: 16,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            config.origin,
            style: const TextStyle(
              color: AppColors.primary,
              fontSize: 15,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 12),
          const Text(
            'Android 真机接入同一局域网时，请把这里改成运行 python run.py 后在终端中显示的服务端局域网 IP。',
            style: TextStyle(color: AppColors.textSub, height: 1.5),
          ),
        ],
      ),
    );
  }

  Widget _buildFieldLabel(String label) {
    return Text(
      label,
      style: const TextStyle(
        color: AppColors.textMain,
        fontWeight: FontWeight.w600,
      ),
    );
  }

  InputDecoration _inputDecoration({String? hintText}) {
    return InputDecoration(
      hintText: hintText,
      hintStyle: const TextStyle(color: AppColors.textMuted),
      filled: true,
      fillColor: AppColors.surface,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: const BorderSide(color: AppColors.border),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: const BorderSide(color: AppColors.border),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: const BorderSide(color: AppColors.primary, width: 2),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: const BorderSide(color: AppColors.error),
      ),
      focusedErrorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: const BorderSide(color: AppColors.error, width: 2),
      ),
    );
  }
}
