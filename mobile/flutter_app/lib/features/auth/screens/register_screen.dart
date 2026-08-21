import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../../core/theme/app_colors.dart';
import '../models/register_models.dart';
import '../providers/auth_provider.dart';

class RegisterScreen extends StatefulWidget {
  const RegisterScreen({super.key});

  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  RegisterRole _selectedRole = RegisterRole.family;
  int _step = 0; // 0=角色选择, 1=填写信息

  final _nameCtrl = TextEditingController();
  final _phoneCtrl = TextEditingController();
  final _passwordCtrl = TextEditingController();
  final _loginUsernameCtrl = TextEditingController();
  final _ageCtrl = TextEditingController(text: '78');
  final _apartmentCtrl = TextEditingController();

  String _relationship = 'daughter';
  bool _obscurePassword = true;

  static const _relationships = [
    ('daughter', '女儿'),
    ('son', '儿子'),
    ('spouse', '配偶'),
    ('granddaughter', '孙女'),
    ('grandson', '孙子'),
    ('relative', '亲属'),
  ];

  @override
  void dispose() {
    _nameCtrl.dispose();
    _phoneCtrl.dispose();
    _passwordCtrl.dispose();
    _loginUsernameCtrl.dispose();
    _ageCtrl.dispose();
    _apartmentCtrl.dispose();
    super.dispose();
  }

  String? _validate() {
    if (_nameCtrl.text.trim().isEmpty) return '请输入姓名';
    if (_selectedRole == RegisterRole.elder) {
      if (_phoneCtrl.text.trim().isEmpty) return '请输入手机号';
      final age = int.tryParse(_ageCtrl.text.trim());
      if (age == null || age < 50 || age > 120) return '请输入有效年龄（50-120）';
      if (_apartmentCtrl.text.trim().isEmpty) return '请输入房间号';
    } else {
      if (_phoneCtrl.text.trim().isEmpty) return '请输入手机号';
    }
    if (_passwordCtrl.text.length < 6) return '密码至少 6 位';
    return null;
  }

  Future<void> _submit() async {
    final error = _validate();
    if (error != null) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error), backgroundColor: AppColors.error),
      );
      return;
    }

    final provider = context.read<AuthProvider>();
    provider.resetRegisterState();

    final name = _nameCtrl.text.trim();
    final phone = _phoneCtrl.text.trim();
    final password = _passwordCtrl.text;
    final loginUsername = _loginUsernameCtrl.text.trim();

    bool ok = false;
    if (_selectedRole == RegisterRole.elder) {
      ok = await provider.registerElder(ElderRegisterRequest(
        name: name,
        phone: phone,
        password: password,
        age: int.tryParse(_ageCtrl.text.trim()) ?? 78,
        apartment: _apartmentCtrl.text.trim(),
      ));
    } else if (_selectedRole == RegisterRole.family) {
      ok = await provider.registerFamily(FamilyRegisterRequest(
        name: name,
        phone: phone,
        password: password,
        relationship: _relationship,
        loginUsername: loginUsername.isEmpty ? null : loginUsername,
      ));
    } else {
      ok = await provider.registerCommunity(CommunityRegisterRequest(
        name: name,
        phone: phone,
        password: password,
        loginUsername: loginUsername.isEmpty ? null : loginUsername,
      ));
    }

    if (!mounted) return;
    if (ok) _showSuccessDialog();
  }

  void _showSuccessDialog() {
    final registered = context.read<AuthProvider>().lastRegistered;
    final loginAccount = _selectedRole == RegisterRole.elder
        ? _phoneCtrl.text.trim()
        : (_loginUsernameCtrl.text.trim().isNotEmpty
            ? _loginUsernameCtrl.text.trim()
            : _phoneCtrl.text.trim());

    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.surface,
        surfaceTintColor: Colors.white,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        title: const Text('注册成功', style: TextStyle(color: AppColors.textMain, fontWeight: FontWeight.bold)),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('账号已创建，可以直接登录。', style: TextStyle(color: AppColors.textSub)),
            const SizedBox(height: 16),
            if (registered != null) ...[
              _infoRow('姓名', registered.name),
              _infoRow('角色', registered.role),
              _infoRow('手机号', registered.phone),
              const SizedBox(height: 8),
            ],
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: AppColors.primary.withOpacity(0.1),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: AppColors.primary.withOpacity(0.3)),
              ),
              child: Text(
                '登录账号：$loginAccount',
                style: const TextStyle(color: AppColors.primary, fontWeight: FontWeight.bold),
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () {
              Navigator.of(ctx).pop();
              Navigator.of(context).pop();
            },
            child: const Text('去登录', style: TextStyle(color: AppColors.primary, fontWeight: FontWeight.bold)),
          ),
        ],
      ),
    );
  }

  Widget _infoRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        children: [
          Text('$label：', style: const TextStyle(color: AppColors.textMuted, fontSize: 13)),
          Expanded(child: Text(value, style: const TextStyle(color: AppColors.textMain, fontSize: 13, fontWeight: FontWeight.bold))),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios, color: AppColors.textMain),
          onPressed: () {
            if (_step == 1) {
              setState(() => _step = 0);
            } else {
              Navigator.of(context).pop();
            }
          },
        ),
        title: Text(
          _step == 0 ? '选择注册类型' : '填写注册信息',
          style: const TextStyle(color: AppColors.textMain, fontWeight: FontWeight.bold),
        ),
      ),
      body: AnimatedSwitcher(
        duration: const Duration(milliseconds: 250),
        child: _step == 0
            ? _buildRoleStep()
            : _buildFormStep(),
      ),
    );
  }

  Widget _buildRoleStep() {
    return Padding(
      key: const ValueKey('role'),
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text('选择您的身份',
              style: TextStyle(color: AppColors.textMain, fontSize: 24, fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          const Text('不同角色拥有不同的管理权限和视角，请根据实际情况选择。',
              style: TextStyle(color: AppColors.textSub, fontSize: 14)),
          const SizedBox(height: 32),
          ...RegisterRole.values.map(_buildRoleCard),
          const Spacer(),
          ElevatedButton(
            onPressed: () => setState(() => _step = 1),
            style: ElevatedButton.styleFrom(
              backgroundColor: AppColors.primary,
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(vertical: 16),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              elevation: 0,
            ),
            child: const Text('下一步', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
          ),
        ],
      ),
    );
  }

  Widget _buildRoleCard(RegisterRole role) {
    final isSelected = _selectedRole == role;
    return GestureDetector(
      onTap: () => setState(() => _selectedRole = role),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        margin: const EdgeInsets.only(bottom: 16),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: isSelected ? AppColors.primary.withOpacity(0.08) : AppColors.surface,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: isSelected ? AppColors.primary : AppColors.border,
            width: isSelected ? 2 : 1,
          ),
          boxShadow: isSelected 
            ? [BoxShadow(color: AppColors.primary.withOpacity(0.1), blurRadius: 8, offset: const Offset(0, 4))]
            : [const BoxShadow(color: Colors.black12, blurRadius: 4, offset: Offset(0, 2))],
        ),
        child: Row(
          children: [
            Container(
              width: 56, height: 56,
              decoration: BoxDecoration(
                color: isSelected ? AppColors.primary.withOpacity(0.1) : AppColors.background,
                shape: BoxShape.circle,
              ),
              child: Icon(_roleIcon(role), color: isSelected ? AppColors.primary : AppColors.textMuted, size: 28),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(role.label, style: TextStyle(color: isSelected ? AppColors.primary : AppColors.textMain, fontWeight: FontWeight.bold, fontSize: 18)),
                  const SizedBox(height: 4),
                  Text(role.description, style: const TextStyle(color: AppColors.textSub, fontSize: 13)),
                ],
              ),
            ),
            if (isSelected) const Icon(Icons.check_circle, color: AppColors.primary, size: 24),
          ],
        ),
      ),
    );
  }

  IconData _roleIcon(RegisterRole role) {
    switch (role) {
      case RegisterRole.elder: return Icons.elderly;
      case RegisterRole.family: return Icons.family_restroom;
      case RegisterRole.community: return Icons.business_center;
    }
  }

  Widget _buildFormStep() {
    final authProvider = context.watch<AuthProvider>();
    final isSubmitting = authProvider.registerStatus == RegisterStatus.submitting;
    return SingleChildScrollView(
      key: const ValueKey('form'),
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: BoxDecoration(
              color: AppColors.primary.withOpacity(0.1),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: AppColors.primary.withOpacity(0.2)),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(_roleIcon(_selectedRole), color: AppColors.primary, size: 20),
                const SizedBox(width: 12),
                Text("当前注册：${_selectedRole.label}", style: const TextStyle(color: AppColors.primary, fontWeight: FontWeight.bold, fontSize: 16)),
              ],
            ),
          ),
          const SizedBox(height: 32),
          _buildTextField(_nameCtrl, "真实姓名", Icons.person_outline, hint: "请输入您的真实姓名"),
          const SizedBox(height: 20),
          if (_selectedRole == RegisterRole.elder) ...[
            _buildTextField(_phoneCtrl, "手机号", Icons.phone_outlined, hint: "请输入手机号（作为登录账号）", keyboardType: TextInputType.phone),
            const SizedBox(height: 20),
            _buildTextField(_ageCtrl, "年龄", Icons.cake_outlined, hint: "请输入年龄（50-120 岁）", keyboardType: TextInputType.number),
            const SizedBox(height: 20),
            _buildTextField(_apartmentCtrl, "房间号", Icons.home_outlined, hint: "例如 A-302"),
            const SizedBox(height: 20),
          ] else ...[
            _buildTextField(_phoneCtrl, "手机号", Icons.phone_outlined, hint: "请输入您的常用手机号", keyboardType: TextInputType.phone),
            const SizedBox(height: 20),
            _buildTextField(_loginUsernameCtrl, "登录账号", Icons.account_circle_outlined, hint: "可选，不填则默认使用手机号登录"),
            const SizedBox(height: 20),
          ],
          if (_selectedRole == RegisterRole.family) ...[
            _buildRelationshipSelector(),
            const SizedBox(height: 20),
          ],
          TextFormField(
            controller: _passwordCtrl,
            obscureText: _obscurePassword,
            style: const TextStyle(color: AppColors.textMain, fontWeight: FontWeight.bold),
            decoration: InputDecoration(
              labelText: "密码",
              labelStyle: const TextStyle(color: AppColors.textSub),
              hintText: "请输入至少 6 位密码",
              hintStyle: const TextStyle(color: AppColors.textMuted),
              filled: true,
              fillColor: AppColors.surface,
              enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: AppColors.border)),
              focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: AppColors.primary, width: 2)),
              prefixIcon: const Icon(Icons.lock_outline, color: AppColors.textMuted),
              suffixIcon: IconButton(
                icon: Icon(_obscurePassword ? Icons.visibility_off_outlined : Icons.visibility_outlined, color: AppColors.textMuted),
                onPressed: () => setState(() => _obscurePassword = !_obscurePassword),
              ),
            ),
          ),
          if (authProvider.registerStatus == RegisterStatus.error && authProvider.registerError != null) ...[
            const SizedBox(height: 20),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: AppColors.error.withOpacity(0.1),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: AppColors.error.withOpacity(0.3)),
              ),
              child: Row(
                children: [
                   const Icon(Icons.error_outline, color: AppColors.error, size: 20),
                   const SizedBox(width: 8),
                   Expanded(child: Text(authProvider.registerError!, style: const TextStyle(color: AppColors.error, fontSize: 14))),
                ],
              ),
            ),
          ],
          const SizedBox(height: 40),
          ElevatedButton(
            onPressed: isSubmitting ? null : _submit,
            style: ElevatedButton.styleFrom(
              backgroundColor: AppColors.primary,
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(vertical: 16),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              elevation: 4,
              shadowColor: AppColors.primary.withOpacity(0.4),
            ),
            child: isSubmitting
                ? const SizedBox(height: 24, width: 24, child: CircularProgressIndicator(strokeWidth: 3, color: Colors.white))
                : const Text("提交注册", style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
          ),
          const SizedBox(height: 16),
          Center(
            child: TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text("已有账号？返回登录", style: TextStyle(color: AppColors.primary, fontWeight: FontWeight.bold)),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTextField(TextEditingController controller, String label, IconData icon, {String? hint, TextInputType keyboardType = TextInputType.text}) {
    return TextFormField(
      controller: controller,
      keyboardType: keyboardType,
      style: const TextStyle(color: AppColors.textMain, fontWeight: FontWeight.bold),
      decoration: InputDecoration(
        labelText: label,
        labelStyle: const TextStyle(color: AppColors.textSub),
        hintText: hint,
        hintStyle: const TextStyle(color: AppColors.textMuted),
        filled: true,
        fillColor: AppColors.surface,
        enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: AppColors.border)),
        focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: AppColors.primary, width: 2)),
        prefixIcon: Icon(icon, color: AppColors.textMuted),
      ),
    );
  }

  Widget _buildRelationshipSelector() {
    return DropdownButtonFormField<String>(
      initialValue: _relationship,
      dropdownColor: AppColors.surface,
      style: const TextStyle(color: AppColors.textMain, fontWeight: FontWeight.bold),
      decoration: InputDecoration(
        labelText: "您与老人的关系",
        labelStyle: const TextStyle(color: AppColors.textSub),
        filled: true,
        fillColor: AppColors.surface,
        enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: AppColors.border)),
        focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: AppColors.primary, width: 2)),
        prefixIcon: const Icon(Icons.people_outline, color: AppColors.textMuted),
      ),
      items: _relationships.map((r) => DropdownMenuItem(value: r.$1, child: Text(r.$2))).toList(),
      onChanged: (v) => setState(() => _relationship = v ?? "daughter"),
    );
  }
}
