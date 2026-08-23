import 'package:flutter/material.dart';

import '../../../core/theme/app_colors.dart';

class RobotMetricItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final String? unit;
  final Color color;

  const RobotMetricItem({
    super.key,
    required this.icon,
    required this.label,
    required this.value,
    this.unit,
    this.color = AppColors.primary,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Container(
          width: 36,
          height: 36,
          decoration: BoxDecoration(
            color: color.withValues(alpha: 0.10),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Icon(icon, size: 19, color: color),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                label,
                style: const TextStyle(color: AppColors.textSub, fontSize: 12),
              ),
              const SizedBox(height: 3),
              Text(
                unit == null ? value : '$value $unit',
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  color: AppColors.textMain,
                  fontSize: 15,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
