import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_3d_controller/flutter_3d_controller.dart';

import '../../../core/theme/app_colors.dart';
import '../controllers/robot_3d_controller.dart';
import '../models/robot_status.dart';

class Go2ThreeDView extends StatefulWidget {
  final RobotMode mode;
  final bool enableTouch;
  final bool showLoading;
  final VoidCallback? onLoaded;
  final ValueChanged<String>? onError;

  const Go2ThreeDView({
    super.key,
    required this.mode,
    this.enableTouch = true,
    this.showLoading = true,
    this.onLoaded,
    this.onError,
  });

  @override
  State<Go2ThreeDView> createState() => _Go2ThreeDViewState();
}

class _Go2ThreeDViewState extends State<Go2ThreeDView> {
  final Robot3DController _robotController = Robot3DController();

  bool _checkingAsset = true;
  bool _loaded = false;
  double _progress = 0;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _checkAsset();
  }

  @override
  void didUpdateWidget(covariant Go2ThreeDView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.mode != widget.mode) {
      _robotController.syncMode(widget.mode);
    }
  }

  @override
  void dispose() {
    _robotController.dispose();
    super.dispose();
  }

  Future<void> _checkAsset() async {
    setState(() {
      _checkingAsset = true;
      _errorMessage = null;
      _loaded = false;
      _progress = 0;
    });

    try {
      await rootBundle.load(RobotStatus.modelAssetPath);
      if (!mounted) return;
      setState(() {
        _checkingAsset = false;
        _loaded = false;
      });
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _prepareViewer();
      });
    } catch (_) {
      if (!mounted) return;
      const message = '3D 模型资源尚未放入本地 assets/models/go2/ 目录';
      setState(() {
        _checkingAsset = false;
        _errorMessage = message;
      });
      widget.onError?.call(message);
    }
  }

  Future<void> _prepareViewer() async {
    final ready = await _robotController.prepare(widget.mode);
    if (!mounted) return;
    if (!ready) {
      const message = 'Go2 动画加载超时，请重新进入页面后重试';
      setState(() {
        _loaded = false;
        _errorMessage = message;
      });
      widget.onError?.call(message);
      return;
    }
    setState(() {
      _loaded = true;
      _progress = 1;
    });
    widget.onLoaded?.call();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.all(Radius.circular(24)),
      ),
      clipBehavior: Clip.antiAlias,
      child: Stack(
        fit: StackFit.expand,
        children: [
          if (!_checkingAsset && _errorMessage == null)
            Flutter3DViewer(
              key: const ValueKey(RobotStatus.modelAssetPath),
              progressBarColor: Colors.transparent,
              controller: _robotController.viewer,
              src: RobotStatus.modelAssetPath,
            ),
          if (_checkingAsset ||
              (widget.showLoading && !_loaded && _errorMessage == null))
            _LoadingOverlay(progress: _progress),
          if (_errorMessage != null)
            _ModelError(message: _errorMessage!, onRetry: _checkAsset),
        ],
      ),
    );
  }
}

class _LoadingOverlay extends StatelessWidget {
  final double progress;

  const _LoadingOverlay({required this.progress});

  @override
  Widget build(BuildContext context) {
    final percent = (progress * 100).round().clamp(0, 100);
    return ColoredBox(
      color: AppColors.surface,
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const SizedBox(
              width: 32,
              height: 32,
              child: CircularProgressIndicator(
                strokeWidth: 3,
                color: AppColors.primary,
              ),
            ),
            const SizedBox(height: 14),
            Text(
              percent == 0 ? '正在加载 Go2 数字分身' : '正在加载 $percent%',
              style: const TextStyle(
                color: AppColors.textSub,
                fontSize: 14,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ModelError extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;

  const _ModelError({required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: AppColors.surface,
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(
                Icons.smart_toy_outlined,
                size: 52,
                color: AppColors.primary,
              ),
              const SizedBox(height: 14),
              const Text(
                '3D 模型暂时无法加载',
                style: TextStyle(
                  color: AppColors.textMain,
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                message,
                textAlign: TextAlign.center,
                style: const TextStyle(
                  color: AppColors.textSub,
                  fontSize: 13,
                  height: 1.4,
                ),
              ),
              const SizedBox(height: 16),
              OutlinedButton.icon(
                onPressed: onRetry,
                icon: const Icon(Icons.refresh, size: 18),
                label: const Text('重新检查'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
