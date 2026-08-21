<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch, type DeepReadonly } from "vue";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { RobotPointCloudFrame } from "../../types/robot";

const props = defineProps<{
  frame: DeepReadonly<RobotPointCloudFrame> | null;
  stale: boolean;
}>();

const host = ref<HTMLDivElement | null>(null);
let renderer: THREE.WebGLRenderer | null = null;
let scene: THREE.Scene | null = null;
let camera: THREE.PerspectiveCamera | null = null;
let controls: OrbitControls | null = null;
let cloud: THREE.Points<THREE.BufferGeometry, THREE.PointsMaterial> | null = null;
let robotMarker: THREE.Mesh | null = null;
let targetMarker: THREE.Mesh | null = null;
let resizeObserver: ResizeObserver | null = null;
let animationFrame = 0;

function updateFrame(frame: DeepReadonly<RobotPointCloudFrame> | null) {
  if (!scene || !frame) return;
  const positions = new Float32Array(frame.point_count * 3);
  const colors = new Float32Array(frame.point_count * 3);
  for (let index = 0; index < frame.point_count; index += 1) {
    const [x, y, z, intensity] = frame.points[index];
    const offset = index * 3;
    positions[offset] = x;
    positions[offset + 1] = z;
    positions[offset + 2] = -y;
    const normalized = Math.min(1, Math.max(0.15, intensity));
    colors[offset] = 0.08 + normalized * 0.2;
    colors[offset + 1] = 0.35 + normalized * 0.45;
    colors[offset + 2] = 0.55 + normalized * 0.4;
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  geometry.computeBoundingSphere();
  if (!cloud) {
    const material = new THREE.PointsMaterial({
      size: 0.045,
      sizeAttenuation: true,
      vertexColors: true,
      transparent: true,
      opacity: 0.88,
    });
    cloud = new THREE.Points(geometry, material);
    scene.add(cloud);
  } else {
    cloud.geometry.dispose();
    cloud.geometry = geometry;
  }

  if (robotMarker) {
    robotMarker.position.set(frame.robot_pose.x, 0.12, -frame.robot_pose.y);
    robotMarker.rotation.y = -frame.robot_pose.yaw;
  }
  if (targetMarker) {
    targetMarker.visible = Boolean(frame.target_pose);
    if (frame.target_pose) {
      targetMarker.position.set(frame.target_pose.x, 0.06, -frame.target_pose.y);
    }
  }
}

function resize() {
  if (!host.value || !renderer || !camera) return;
  const width = Math.max(320, host.value.clientWidth);
  const height = Math.max(300, host.value.clientHeight);
  renderer.setSize(width, height, false);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75));
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
}

function animate() {
  animationFrame = window.requestAnimationFrame(animate);
  if (document.hidden || !renderer || !scene || !camera) return;
  controls?.update();
  renderer.render(scene, camera);
}

function resetView() {
  if (!camera || !controls) return;
  camera.position.set(8, 7, 8);
  controls.target.set(0, 0.4, 0);
  controls.update();
}

onMounted(() => {
  if (!host.value) return;
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0xf5f8fb);
  scene.fog = new THREE.Fog(0xf5f8fb, 12, 28);

  camera = new THREE.PerspectiveCamera(48, 1, 0.05, 100);
  camera.position.set(8, 7, 8);

  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: "high-performance" });
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  host.value.appendChild(renderer.domElement);

  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.minDistance = 3;
  controls.maxDistance = 25;
  controls.maxPolarAngle = Math.PI / 2.02;
  controls.target.set(0, 0.4, 0);

  const grid = new THREE.GridHelper(18, 18, 0x9fb3c8, 0xd8e2ec);
  scene.add(grid);
  scene.add(new THREE.AxesHelper(1.2));

  const robotGeometry = new THREE.ConeGeometry(0.22, 0.52, 5);
  robotGeometry.rotateX(Math.PI / 2);
  robotMarker = new THREE.Mesh(
    robotGeometry,
    new THREE.MeshBasicMaterial({ color: 0x2563eb }),
  );
  scene.add(robotMarker);

  targetMarker = new THREE.Mesh(
    new THREE.RingGeometry(0.2, 0.32, 32),
    new THREE.MeshBasicMaterial({ color: 0xd97706, side: THREE.DoubleSide }),
  );
  targetMarker.rotation.x = -Math.PI / 2;
  targetMarker.visible = false;
  scene.add(targetMarker);

  resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(host.value);
  resize();
  updateFrame(props.frame);
  animate();
});

watch(() => props.frame, updateFrame);

onBeforeUnmount(() => {
  window.cancelAnimationFrame(animationFrame);
  resizeObserver?.disconnect();
  controls?.dispose();
  cloud?.geometry.dispose();
  cloud?.material.dispose();
  if (robotMarker) {
    robotMarker.geometry.dispose();
    (robotMarker.material as THREE.Material).dispose();
  }
  if (targetMarker) {
    targetMarker.geometry.dispose();
    (targetMarker.material as THREE.Material).dispose();
  }
  renderer?.dispose();
  renderer?.forceContextLoss();
  renderer?.domElement.remove();
  renderer = null;
  scene = null;
  camera = null;
  cloud = null;
});
</script>

<template>
  <div class="point-cloud-viewer" :class="{ 'point-cloud-viewer--stale': stale }">
    <div ref="host" class="point-cloud-viewer__canvas" aria-label="Mock 三维点云视图"></div>
    <div v-if="!frame" class="point-cloud-viewer__empty">
      <strong>等待 Mock 点云帧</strong>
      <span>连接建立后将在此显示模拟教室环境。</span>
    </div>
    <div class="point-cloud-viewer__legend" aria-hidden="true">
      <span><i class="dot dot--robot"></i>机器人</span>
      <span><i class="dot dot--target"></i>目标点</span>
      <span>拖拽旋转 · 滚轮缩放</span>
    </div>
    <button type="button" class="point-cloud-viewer__reset" @click="resetView">重置视角</button>
  </div>
</template>

<style scoped>
.point-cloud-viewer {
  position: relative;
  min-height: 380px;
  overflow: hidden;
  border: 1px solid #dbe4ee;
  border-radius: 18px;
  background: #f5f8fb;
}

.point-cloud-viewer--stale::after {
  position: absolute;
  inset: 0;
  content: "";
  pointer-events: none;
  border: 2px solid rgba(217, 119, 6, 0.52);
  border-radius: inherit;
}

.point-cloud-viewer__canvas {
  width: 100%;
  min-height: 380px;
}

.point-cloud-viewer__canvas :deep(canvas) {
  display: block;
  width: 100%;
  height: 100%;
  cursor: grab;
}

.point-cloud-viewer__canvas :deep(canvas:active) {
  cursor: grabbing;
}

.point-cloud-viewer__empty {
  position: absolute;
  inset: 0;
  display: grid;
  place-content: center;
  gap: 6px;
  text-align: center;
  color: #64748b;
  pointer-events: none;
}

.point-cloud-viewer__empty strong {
  color: #334155;
}

.point-cloud-viewer__legend {
  position: absolute;
  right: 14px;
  bottom: 14px;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 8px 11px;
  border: 1px solid rgba(203, 213, 225, 0.9);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.9);
  color: #64748b;
  font-size: 0.74rem;
  backdrop-filter: blur(10px);
}

.point-cloud-viewer__reset {
  position: absolute;
  top: 14px;
  right: 14px;
  padding: 7px 10px;
  border: 1px solid #cbd5e1;
  border-radius: 9px;
  background: rgba(255, 255, 255, .9);
  color: #334155;
  font-size: .72rem;
  font-weight: 750;
  cursor: pointer;
  backdrop-filter: blur(8px);
}
.point-cloud-viewer__reset:hover { background: #fff; color: #1d4ed8; }

.point-cloud-viewer__legend span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.dot--robot { background: #2563eb; }
.dot--target { background: #d97706; }

@media (max-width: 720px) {
  .point-cloud-viewer,
  .point-cloud-viewer__canvas {
    min-height: 320px;
  }
}
</style>
