<template>
  <canvas
    ref="canvasRef"
    class="absolute inset-0 w-full h-full pointer-events-none"
    :style="{ opacity: 0.7 }"
  ></canvas>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';

const canvasRef = ref<HTMLCanvasElement | null>(null);
let animationId: number | null = null;

onMounted(() => {
  const canvas = canvasRef.value;
  if (!canvas) return;

  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  // 设置画布尺寸为全屏
  const resizeCanvas = () => {
    const dpr = window.devicePixelRatio || 1;
    // We update offsetWidth and height to the parent container to keep it within bounds, but we can stick closely to window.innerWidth
    canvas.width = window.innerWidth * dpr;
    canvas.height = window.innerHeight * dpr;
    canvas.style.width = `${window.innerWidth}px`;
    canvas.style.height = `${window.innerHeight}px`;
    ctx.scale(dpr, dpr);
  };

  resizeCanvas();
  window.addEventListener('resize', resizeCanvas);

  const width = window.innerWidth;
  const height = window.innerHeight;
  const centerY = height / 2.5; // Adjusted slightly up for standard view, as original code centers in window
  const beatWidth = 200; // 一个心跳周期的宽度
  let scanX = 0; // 扫描线位置
  const scanSpeed = 1; // 扫描速度
  
  // 生成ECG波形的Y坐标（真实的P-QRS-T波形）
  const getECGY = (x: number): number => {
    const cyclePosition = x % beatWidth;
    const phase = cyclePosition / beatWidth;
    
    let y: number;
    
    // P波 (0-0.15) - 心房除极
    if (phase < 0.15) {
      const t = phase / 0.15;
      y = centerY - 15 * Math.sin(Math.PI * t);
    }
    // PR段 (0.15-0.25) - 房室传导
    else if (phase < 0.25) {
      y = centerY;
    }
    // Q波 (0.25-0.30) - 室间隔除极
    else if (phase < 0.30) {
      const t = (phase - 0.25) / 0.05;
      y = centerY + 20 * Math.sin(Math.PI * t);
    }
    // R波 (0.30-0.38) - 心室除极主峰
    else if (phase < 0.38) {
      const t = (phase - 0.30) / 0.08;
      y = centerY - 120 * Math.sin(Math.PI * t);
    }
    // S波 (0.38-0.43) - 心室除极末期
    else if (phase < 0.43) {
      const t = (phase - 0.38) / 0.05;
      y = centerY + 25 * Math.sin(Math.PI * t);
    }
    // ST段 (0.43-0.55) - 心室复极早期
    else if (phase < 0.55) {
      y = centerY;
    }
    // T波 (0.55-0.80) - 心室复极
    else if (phase < 0.80) {
      const t = (phase - 0.55) / 0.25;
      y = centerY - 35 * Math.sin(Math.PI * t);
    }
    // 基线
    else {
      y = centerY;
    }
    
    return y;
  };

  const animate = () => {
    // 清空画布
    ctx.clearRect(0, 0, width, height);

    // 创建水平方向的颜色渐变（从绿色到蓝色）
    const horizontalGradient = ctx.createLinearGradient(0, 0, width, 0);
    horizontalGradient.addColorStop(0, 'rgba(16, 185, 129, 1)');      // emerald-500
    horizontalGradient.addColorStop(0.3, 'rgba(20, 184, 166, 1)');    // teal-500
    horizontalGradient.addColorStop(0.6, 'rgba(6, 182, 212, 1)');     // cyan-500
    horizontalGradient.addColorStop(1, 'rgba(59, 130, 246, 1)');      // blue-500

    // 绘制已经扫描过的心电图波形（暗色带渐变）
    const darkGradient = ctx.createLinearGradient(0, 0, width, 0);
    darkGradient.addColorStop(0, 'rgba(16, 185, 129, 0.15)');
    darkGradient.addColorStop(0.3, 'rgba(20, 184, 166, 0.15)');
    darkGradient.addColorStop(0.6, 'rgba(6, 182, 212, 0.15)');
    darkGradient.addColorStop(1, 'rgba(59, 130, 246, 0.15)');
    
    ctx.beginPath();
    ctx.strokeStyle = darkGradient;
    ctx.lineWidth = 2.5;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    
    for (let x = 0; x <= scanX; x += 1) {
      const y = getECGY(x);
      if (x === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    }
    ctx.stroke();

    // 绘制扫描线附近的亮波形（多层光效）
    const glowRange = 80;
    
    // 外层大光晕
    ctx.beginPath();
    ctx.strokeStyle = horizontalGradient;
    ctx.globalAlpha = 0.4;
    ctx.lineWidth = 5;
    
    for (let x = Math.max(0, scanX - glowRange); x <= Math.min(width, scanX + 10); x += 1) {
      const y = getECGY(x);
      if (x === Math.max(0, scanX - glowRange)) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    }
    
    ctx.shadowBlur = 30;
    // 根据当前位置选择对应的阴影颜色
    const progress = scanX / width;
    if (progress < 0.3) {
      ctx.shadowColor = 'rgba(16, 185, 129, 0.6)';
    } else if (progress < 0.6) {
      ctx.shadowColor = 'rgba(20, 184, 166, 0.6)';
    } else {
      ctx.shadowColor = 'rgba(59, 130, 246, 0.6)';
    }
    ctx.stroke();
    ctx.globalAlpha = 1;
    
    // 中层光效
    ctx.beginPath();
    ctx.strokeStyle = horizontalGradient;
    ctx.globalAlpha = 0.7;
    ctx.lineWidth = 3.5;
    
    for (let x = Math.max(0, scanX - glowRange); x <= Math.min(width, scanX + 10); x += 1) {
      const y = getECGY(x);
      if (x === Math.max(0, scanX - glowRange)) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    }
    
    ctx.shadowBlur = 20;
    if (progress < 0.3) {
      ctx.shadowColor = 'rgba(5, 150, 105, 0.8)';
    } else if (progress < 0.6) {
      ctx.shadowColor = 'rgba(13, 148, 136, 0.8)';
    } else {
      ctx.shadowColor = 'rgba(37, 99, 235, 0.8)';
    }
    ctx.stroke();
    ctx.globalAlpha = 1;
    
    // 核心亮线
    ctx.beginPath();
    const coreGradient = ctx.createLinearGradient(0, 0, width, 0);
    coreGradient.addColorStop(0, 'rgba(167, 243, 208, 1)');      // emerald-200
    coreGradient.addColorStop(0.3, 'rgba(153, 246, 228, 1)');    // teal-200
    coreGradient.addColorStop(0.6, 'rgba(165, 243, 252, 1)');    // cyan-200
    coreGradient.addColorStop(1, 'rgba(147, 197, 253, 1)');      // blue-300
    
    ctx.strokeStyle = coreGradient;
    ctx.lineWidth = 2;
    
    for (let x = Math.max(0, scanX - glowRange); x <= Math.min(width, scanX + 10); x += 1) {
      const y = getECGY(x);
      if (x === Math.max(0, scanX - glowRange)) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    }
    
    ctx.shadowBlur = 15;
    if (progress < 0.3) {
      ctx.shadowColor = 'rgba(167, 243, 208, 1)';
    } else if (progress < 0.6) {
      ctx.shadowColor = 'rgba(153, 246, 228, 1)';
    } else {
      ctx.shadowColor = 'rgba(147, 197, 253, 1)';
    }
    ctx.stroke();
    ctx.shadowBlur = 0;

    // 更新扫描线位置
    scanX += scanSpeed;
    if (scanX > width) {
      scanX = 0; // 重新从左边开始
    }

    animationId = requestAnimationFrame(animate);
  };

  animate();

  // 清理函数
  onUnmounted(() => {
    window.removeEventListener('resize', resizeCanvas);
    if (animationId !== null) {
      cancelAnimationFrame(animationId);
    }
  });
});
</script>
