<template>
  <section class="modern-auth-shell">
    <!-- 动态背景 -->
    <div class="modern-auth-background" aria-hidden="true">
      <!-- 渐变背景 -->
      <div class="modern-auth-gradient"></div>
      
      <!-- 动态网格 -->
      <div class="modern-auth-grid">
        <div class="modern-auth-grid-line" v-for="i in 20" :key="`v-${i}`" :style="{ left: `${i * 5}%` }"></div>
        <div class="modern-auth-grid-line modern-auth-grid-line--horizontal" v-for="i in 12" :key="`h-${i}`" :style="{ top: `${i * 8.33}%` }"></div>
      </div>

      <!-- 浮动元素 -->
      <div class="modern-auth-floats">
        <div class="modern-auth-float modern-auth-float--1"></div>
        <div class="modern-auth-float modern-auth-float--2"></div>
        <div class="modern-auth-float modern-auth-float--3"></div>
        <div class="modern-auth-float modern-auth-float--4"></div>
      </div>

      <!-- 增强的 ECG 心电图效果 -->
      <svg class="modern-auth-ecg" viewBox="0 0 1600 900" preserveAspectRatio="none">
        <defs>
          <linearGradient id="ecgGradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" style="stop-color: rgba(59, 130, 246, 0.4); stop-opacity: 0" />
            <stop offset="50%" style="stop-color: rgba(59, 130, 246, 1); stop-opacity: 1" />
            <stop offset="100%" style="stop-color: rgba(59, 130, 246, 0.4); stop-opacity: 0" />
          </linearGradient>
          <filter id="ecgGlow">
            <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
            <feMerge>
              <feMergeNode in="coloredBlur"/>
              <feMergeNode in="SourceGraphic"/>
            </feMerge>
          </filter>
        </defs>
        
        <!-- 主心电图线 -->
        <path
          class="modern-auth-ecg-line modern-auth-ecg-line--main"
          d="M-80 450 L200 450 L240 450 L260 420 L280 480 L300 400 L320 450 L800 450 L840 450 L860 430 L880 470 L900 410 L920 450 L1680 450"
          stroke="url(#ecgGradient)"
          stroke-width="3"
          fill="none"
          filter="url(#ecgGlow)"
        />
        
        <!-- 副心电图线（增加层次感） -->
        <path
          class="modern-auth-ecg-line modern-auth-ecg-line--secondary"
          d="M-80 550 L150 550 L190 550 L210 530 L230 570 L250 520 L270 550 L750 550 L790 550 L810 535 L830 565 L850 525 L870 550 L1680 550"
          stroke="rgba(16, 185, 129, 0.5)"
          stroke-width="2"
          fill="none"
          filter="url(#ecgGlow)"
        />
      </svg>
    </div>

    <!-- 内容区域 -->
    <div class="modern-auth-content">
      <div class="modern-auth-container">
        <slot />
      </div>
    </div>
  </section>
</template>

<style scoped>
.modern-auth-shell {
  position: relative;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  overflow: hidden;
}

/* 背景层 */
.modern-auth-background {
  position: absolute;
  inset: 0;
  pointer-events: none;
  overflow: hidden;
}

/* 渐变背景 */
.modern-auth-gradient {
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, 
    #0f172a 0%, 
    #1e293b 25%, 
    #334155 50%, 
    #1e3a5f 75%, 
    #0f172a 100%
  );
}

.modern-auth-gradient::before {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at 20% 30%, rgba(59, 130, 246, 0.15) 0%, transparent 50%),
              radial-gradient(circle at 80% 70%, rgba(16, 185, 129, 0.1) 0%, transparent 50%);
  animation: gradientShift 15s ease-in-out infinite;
}

@keyframes gradientShift {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

/* 网格效果 */
.modern-auth-grid {
  position: absolute;
  inset: 0;
  opacity: 0.2;
}

.modern-auth-grid-line {
  position: absolute;
  background: linear-gradient(to bottom, transparent, rgba(59, 130, 246, 0.4), transparent);
  width: 1px;
  height: 100%;
  animation: gridPulse 3s ease-in-out infinite;
}

.modern-auth-grid-line--horizontal {
  background: linear-gradient(to right, transparent, rgba(59, 130, 246, 0.4), transparent);
  width: 100%;
  height: 1px;
  animation: gridPulse 4s ease-in-out infinite;
}

@keyframes gridPulse {
  0%, 100% { opacity: 0.3; }
  50% { opacity: 0.7; }
}

/* 浮动元素 */
.modern-auth-floats {
  position: absolute;
  inset: 0;
}

.modern-auth-float {
  position: absolute;
  border-radius: 50%;
  filter: blur(60px);
  opacity: 0.4;
  animation: float 20s ease-in-out infinite;
}

.modern-auth-float--1 {
  width: 400px;
  height: 400px;
  background: radial-gradient(circle, rgba(59, 130, 246, 0.4), transparent);
  top: 10%;
  left: 10%;
  animation-delay: 0s;
}

.modern-auth-float--2 {
  width: 300px;
  height: 300px;
  background: radial-gradient(circle, rgba(16, 185, 129, 0.3), transparent);
  top: 60%;
  right: 15%;
  animation-delay: 5s;
}

.modern-auth-float--3 {
  width: 350px;
  height: 350px;
  background: radial-gradient(circle, rgba(99, 102, 241, 0.3), transparent);
  bottom: 20%;
  left: 20%;
  animation-delay: 10s;
}

.modern-auth-float--4 {
  width: 250px;
  height: 250px;
  background: radial-gradient(circle, rgba(59, 130, 246, 0.35), transparent);
  top: 40%;
  right: 30%;
  animation-delay: 15s;
}

@keyframes float {
  0%, 100% {
    transform: translate(0, 0) scale(1);
  }
  25% {
    transform: translate(30px, -30px) scale(1.1);
  }
  50% {
    transform: translate(-20px, 20px) scale(0.9);
  }
  75% {
    transform: translate(20px, 30px) scale(1.05);
  }
}

/* 增强的 ECG 心电图 */
.modern-auth-ecg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  opacity: 0.8;
}

.modern-auth-ecg-line {
  stroke-linecap: round;
  stroke-linejoin: round;
}

.modern-auth-ecg-line--main {
  stroke-dasharray: 1500;
  stroke-dashoffset: 1500;
  animation: ecgDraw 6s linear infinite;
}

.modern-auth-ecg-line--secondary {
  stroke-dasharray: 1500;
  stroke-dashoffset: 1500;
  animation: ecgDraw 8s linear infinite;
  animation-delay: 1s;
}

@keyframes ecgDraw {
  to {
    stroke-dashoffset: 0;
  }
}

/* 内容区域 */
.modern-auth-content {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 1200px;
  display: flex;
  justify-content: center;
  align-items: center;
}

.modern-auth-container {
  width: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
}

/* 响应式 */
@media (max-width: 768px) {
  .modern-auth-shell {
    padding: 16px;
  }

  .modern-auth-float {
    filter: blur(40px);
  }

  .modern-auth-float--1,
  .modern-auth-float--2,
  .modern-auth-float--3,
  .modern-auth-float--4 {
    width: 200px;
    height: 200px;
  }
}
</style>
