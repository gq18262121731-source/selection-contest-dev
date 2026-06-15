<script setup lang="ts">
import { ref, computed } from "vue";
import { AlertTriangle } from "lucide-vue-next";

const props = defineProps<{
  canAccessDebug?: boolean;
}>();

const isSimulating = ref(false);

// 模拟设备数据
const mockDevices = [
  { mac: "AA:BB:CC:DD:EE:01", name: "T10-WATCH-001", elder: "张大爷" },
  { mac: "AA:BB:CC:DD:EE:02", name: "T10-WATCH-002", elder: "李奶奶" },
  { mac: "AA:BB:CC:DD:EE:03", name: "T10-WATCH-003", elder: "王大妈" },
];

const selectedDevice = ref(mockDevices[0]);
const triggerType = ref<"long_press" | "double_click">("long_press");

async function simulateSOSAlarm() {
  if (isSimulating.value) return;
  
  isSimulating.value = true;

  try {
    // 创建模拟告警数据，直接通过WebSocket发送到现有系统
    const mockAlarmData = {
      id: `sim_${Date.now()}`,
      device_mac: selectedDevice.value.mac,
      alarm_type: "sos",
      alarm_level: 1,
      alarm_layer: "device",
      message: `${selectedDevice.value.elder} 触发紧急求助`,
      created_at: new Date().toISOString(),
      acknowledged: false,
      metadata: {
        is_real_device: true, // 设置为true让现有系统认为是真实告警
        device_name: selectedDevice.value.name,
        elder_name: selectedDevice.value.elder,
        sos_trigger: triggerType.value,
        simulation_timestamp: Date.now()
      }
    };

    // 通过现有的WebSocket连接发送模拟告警
    // 这里我们直接触发一个自定义事件，让AppShell监听并处理
    const event = new CustomEvent('sos-simulation', {
      detail: mockAlarmData
    });
    window.dispatchEvent(event);
    
  } catch (error) {
    console.error('SOS模拟失败:', error);
  } finally {
    // 延迟重置状态，避免重复点击
    setTimeout(() => {
      isSimulating.value = false;
    }, 2000);
  }
}

// 快速模拟函数
function quickSimulate() {
  if (isSimulating.value) return;
  
  const randomDevice = mockDevices[Math.floor(Math.random() * mockDevices.length)];
  const randomTrigger = Math.random() > 0.5 ? "long_press" : "double_click";
  
  selectedDevice.value = randomDevice;
  triggerType.value = randomTrigger;
  
  simulateSOSAlarm();
}
</script>

<template>
  <div v-if="canAccessDebug" class="sos-simulator">
    <!-- 快速触发按钮（悬浮球） -->
    <button
      type="button"
      class="sos-simulator__quick-trigger"
      :class="{ 'sos-simulator__quick-trigger--loading': isSimulating }"
      :disabled="isSimulating"
      :title="isSimulating ? '模拟中...' : '快速模拟 SOS 告警'"
      @click="quickSimulate"
    >
      <AlertTriangle :size="20" />
    </button>

    <!-- 详细配置面板 -->
    <details class="sos-simulator__panel">
      <summary class="sos-simulator__panel-trigger">
        SOS 模拟器
      </summary>
      
      <div class="sos-simulator__content">
        <div class="sos-simulator__form">
          <label class="sos-simulator__field">
            <span>模拟设备</span>
            <select v-model="selectedDevice" :disabled="isSimulating">
              <option v-for="device in mockDevices" :key="device.mac" :value="device">
                {{ device.elder }} - {{ device.name }}
              </option>
            </select>
          </label>

          <label class="sos-simulator__field">
            <span>触发方式</span>
            <select v-model="triggerType" :disabled="isSimulating">
              <option value="long_press">长按求助</option>
              <option value="double_click">双击求助</option>
            </select>
          </label>

          <button
            type="button"
            class="sos-simulator__trigger-btn"
            :class="{ 'sos-simulator__trigger-btn--loading': isSimulating }"
            :disabled="isSimulating"
            @click="simulateSOSAlarm"
          >
            {{ isSimulating ? "模拟中..." : "触发 SOS 告警" }}
          </button>
        </div>

        <div class="sos-simulator__info">
          <h4>使用说明</h4>
          <ul>
            <li>点击悬浮球可快速触发随机设备的 SOS 告警</li>
            <li>使用详细配置可指定设备和触发方式</li>
            <li>模拟告警会触发现有的红色弹窗和告警音效</li>
            <li>每次模拟后需等待2秒才能再次触发</li>
          </ul>
        </div>
      </div>
    </details>
  </div>
</template>

<style scoped>
.sos-simulator {
  position: fixed;
  bottom: 100px;
  right: 20px;
  z-index: 999;
}

/* 快速触发悬浮球 */
.sos-simulator__quick-trigger {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  border: none;
  background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
  color: white;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 8px 20px rgba(239, 68, 68, 0.4);
  transition: all 200ms ease;
}

.sos-simulator__quick-trigger:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 12px 28px rgba(239, 68, 68, 0.5);
}

.sos-simulator__quick-trigger--loading {
  background: #10b981;
  animation: pulse-loading 2s infinite;
}

.sos-simulator__quick-trigger:disabled {
  cursor: not-allowed;
}

/* 详细配置面板 */
.sos-simulator__panel {
  position: absolute;
  bottom: 70px;
  right: 0;
  width: 320px;
  background: white;
  border-radius: 16px;
  border: 1px solid var(--line-medium);
  box-shadow: 0 20px 40px rgba(15, 23, 42, 0.15);
  overflow: hidden;
}

.sos-simulator__panel-trigger {
  padding: 12px 16px;
  background: #f8fafc;
  border-bottom: 1px solid var(--line-medium);
  cursor: pointer;
  font-weight: 600;
  color: var(--text-main);
  list-style: none;
}

.sos-simulator__panel-trigger::-webkit-details-marker {
  display: none;
}

.sos-simulator__content {
  padding: 16px;
  display: grid;
  gap: 16px;
}

.sos-simulator__form {
  display: grid;
  gap: 12px;
}

.sos-simulator__field {
  display: grid;
  gap: 6px;
}

.sos-simulator__field span {
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--text-sub);
}

.sos-simulator__field select {
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid var(--line-medium);
  background: white;
  font-size: 0.9rem;
}

.sos-simulator__trigger-btn {
  padding: 12px 16px;
  border-radius: 12px;
  border: none;
  background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
  color: white;
  font-weight: 600;
  cursor: pointer;
  transition: all 200ms ease;
}

.sos-simulator__trigger-btn:hover:not(:disabled) {
  background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%);
  transform: translateY(-1px);
}

.sos-simulator__trigger-btn--loading {
  background: #10b981;
  cursor: not-allowed;
}

.sos-simulator__trigger-btn:disabled {
  cursor: not-allowed;
  transform: none;
}

.sos-simulator__info {
  padding: 12px;
  background: #f8fafc;
  border-radius: 8px;
  border: 1px solid var(--line);
}

.sos-simulator__info h4 {
  margin: 0 0 8px 0;
  font-size: 0.9rem;
  color: var(--text-main);
}

.sos-simulator__info ul {
  margin: 0;
  padding-left: 16px;
  color: var(--text-sub);
  font-size: 0.8rem;
  line-height: 1.5;
}

.sos-simulator__info li {
  margin-bottom: 4px;
}

/* 动画效果 */
@keyframes pulse-loading {
  0%, 100% {
    box-shadow: 0 8px 20px rgba(16, 185, 129, 0.4);
  }
  50% {
    box-shadow: 0 8px 28px rgba(16, 185, 129, 0.6);
  }
}

/* 响应式适配 */
@media (max-width: 768px) {
  .sos-simulator {
    bottom: 80px;
    right: 16px;
  }
  
  .sos-simulator__panel {
    width: 280px;
    bottom: 60px;
  }
  
  .sos-simulator__quick-trigger {
    width: 48px;
    height: 48px;
  }
}
</style>