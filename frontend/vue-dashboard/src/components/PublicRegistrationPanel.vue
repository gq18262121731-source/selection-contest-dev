<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ApiError, api } from "../api/client";

type RegistrationRole = "elder" | "family" | "community";
type RegistrationStep = 1 | 2 | 3 | 4;
type BindPlan = "now" | "later";
type LandingChoice = "overview" | "report" | "alarm";
type ShiftChoice = "day" | "night" | "flex";

const props = defineProps<{
  initialRole?: RegistrationRole;
}>();

const emit = defineEmits<{
  close: [];
  prefillLogin: [payload: { username: string; password: string; role: RegistrationRole }];
}>();

const registrationStep = ref<RegistrationStep>(1);
const registrationRole = ref<RegistrationRole>(props.initialRole ?? "family");
const submitting = ref(false);
const errorText = ref("");
const successText = ref("");
const completedCredentials = ref<{ username: string; password: string; role: RegistrationRole } | null>(null);

const accountForm = ref({
  name: "",
  phone: "",
  password: "123456",
  confirmPassword: "123456",
  loginUsername: "",
});

const profileForm = ref({
  age: "78",
  apartment: "",
  relationship: "daughter",
  bindPlan: "later" as BindPlan,
  landingChoice: "report" as LandingChoice,
  shift: "day" as ShiftChoice,
  stationLabel: "海棠苑社区值守台",
});

const registrationRoleOptions = [
  {
    key: "elder",
    badge: "老人",
    label: "老人账号",
    title: "老人账号注册",
    description: "先创建账号，再补充房间号与基础资料，用于后续设备归属和健康监测演示。",
    accountHint: "老人账号默认直接使用手机号登录，尽量降低首登理解成本。",
    profileTitle: "完善老人资料",
    profileDescription: "补充房间号和基础信息，方便后续演示设备绑定与照护关系。",
  },
  {
    key: "family",
    badge: "家属",
    label: "家属账号",
    title: "家属账号注册",
    description: "先创建账号，再补充关系与关注重点，进入系统后优先查看状态、报告和异常链路。",
    accountHint: "家属账号支持自定义登录名，也可以直接使用手机号。",
    profileTitle: "完善家属资料",
    profileDescription: "补充关系类型和首屏关注项，完成后会回到登录卡片并回填账号。",
  },
  {
    key: "community",
    badge: "社区",
    label: "社区工作人员",
    title: "社区工作人员注册",
    description: "创建社区值守账号，再补充分工与首屏偏好，方便现场切换到社区总览演示。",
    accountHint: "社区账号建议保留一个清晰的登录名，方便值守席位现场切换。",
    profileTitle: "完善值守资料",
    profileDescription: "补充值守班次与站点说明，让完成态更完整，但不伪造后端未提供的数据。",
  },
] as const satisfies ReadonlyArray<{
  key: RegistrationRole;
  badge: string;
  label: string;
  title: string;
  description: string;
  accountHint: string;
  profileTitle: string;
  profileDescription: string;
}>;

const registrationSteps = [
  { id: 1, title: "身份选择", description: "先确定注册对象" },
  { id: 2, title: "注册账号", description: "只创建登录账号" },
  { id: 3, title: "资料完善", description: "补充进入系统前的信息" },
  { id: 4, title: "完成回填", description: "回到登录并自动回填" },
] as const;

const activeRole = computed(
  () => registrationRoleOptions.find((item) => item.key === registrationRole.value) ?? registrationRoleOptions[1],
);

const currentLoginAccount = computed(() => {
  if (registrationRole.value === "elder") return accountForm.value.phone.trim();
  return accountForm.value.loginUsername.trim() || accountForm.value.phone.trim();
});

const bindPlanCopy = computed(() =>
  profileForm.value.bindPlan === "now"
    ? "当前只记录“需要尽快绑定设备”的引导意图，真实绑定仍由社区端关系台账完成。"
    : "当前选择稍后绑定，注册完成后可继续由社区端补齐设备归属流程。",
);

const profileSummary = computed(() => {
  if (registrationRole.value === "elder") {
    return [
      `房间号：${profileForm.value.apartment || "未填写"}`,
      `年龄：${profileForm.value.age || "未填写"}`,
      `设备计划：${profileForm.value.bindPlan === "now" ? "尽快绑定设备" : "稍后绑定设备"}`,
    ];
  }
  if (registrationRole.value === "family") {
    return [
      `关系类型：${profileForm.value.relationship}`,
      `首屏优先查看：${profileForm.value.landingChoice === "report" ? "健康报告" : profileForm.value.landingChoice === "alarm" ? "异常提醒" : "当前状态概览"}`,
      `设备计划：${profileForm.value.bindPlan === "now" ? "尽快绑定设备" : "稍后绑定设备"}`,
    ];
  }
  return [
    `值守班次：${profileForm.value.shift === "day" ? "日间值守" : profileForm.value.shift === "night" ? "夜间值守" : "灵活值守"}`,
    `值守站点：${profileForm.value.stationLabel || "未填写"}`,
    `首屏偏好：${profileForm.value.landingChoice === "alarm" ? "异常提醒" : profileForm.value.landingChoice === "report" ? "结构化报告" : "社区总览"}`,
  ];
});

watch(
  () => props.initialRole,
  (role) => {
    if (!role) return;
    registrationRole.value = role;
    registrationStep.value = 1;
    errorText.value = "";
    successText.value = "";
    completedCredentials.value = null;
  },
);

function formatError(error: unknown, fallback: string) {
  if (error instanceof ApiError && error.detail) {
    if (error.status === 404) {
      return "当前后端还没有开放该公共注册接口，请先确认后端服务和公开注册路由已启动。";
    }
    return error.detail;
  }
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

function switchRole(role: RegistrationRole) {
  registrationRole.value = role;
  registrationStep.value = 1;
  errorText.value = "";
  successText.value = "";
  completedCredentials.value = null;
}

function nextFromRoleStep() {
  errorText.value = "";
  registrationStep.value = 2;
}

function goToProfileStep() {
  errorText.value = "";
  if (!accountForm.value.name.trim() || !accountForm.value.phone.trim()) {
    errorText.value = "请先完整填写姓名和手机号。";
    return;
  }
  if (!accountForm.value.password.trim()) {
    errorText.value = "请输入密码。";
    return;
  }
  if (accountForm.value.password !== accountForm.value.confirmPassword) {
    errorText.value = "两次输入的密码不一致，请重新确认。";
    return;
  }
  registrationStep.value = 3;
}

function backToStep(step: RegistrationStep) {
  errorText.value = "";
  registrationStep.value = step;
}

async function submitRegistration() {
  errorText.value = "";
  successText.value = "";

  if (registrationRole.value === "elder" && !profileForm.value.apartment.trim()) {
    errorText.value = "请补充老人房间号后再完成注册。";
    return;
  }
  if (registrationRole.value === "family" && !profileForm.value.relationship.trim()) {
    errorText.value = "请先选择家属关系类型。";
    return;
  }
  if (registrationRole.value === "community" && !profileForm.value.stationLabel.trim()) {
    errorText.value = "请先填写值守站点或岗位说明。";
    return;
  }

  submitting.value = true;
  try {
    if (registrationRole.value === "elder") {
      await api.publicRegisterElder({
        name: accountForm.value.name.trim(),
        phone: accountForm.value.phone.trim(),
        password: accountForm.value.password,
        age: Number(profileForm.value.age) || 78,
        apartment: profileForm.value.apartment.trim(),
        community_id: "community-haitang",
      });
      completedCredentials.value = {
        username: accountForm.value.phone.trim(),
        password: accountForm.value.password,
        role: registrationRole.value,
      };
      successText.value = "老人账号已创建完成。回到登录页后，系统会自动回填手机号和密码。";
    } else if (registrationRole.value === "family") {
      await api.publicRegisterFamily({
        name: accountForm.value.name.trim(),
        phone: accountForm.value.phone.trim(),
        password: accountForm.value.password,
        relationship: profileForm.value.relationship,
        community_id: "community-haitang",
        login_username: accountForm.value.loginUsername.trim() || null,
      });
      completedCredentials.value = {
        username: currentLoginAccount.value,
        password: accountForm.value.password,
        role: registrationRole.value,
      };
      successText.value = "家属账号已创建完成。回到登录页后，系统会自动回填可用账号和密码。";
    } else {
      await api.publicRegisterCommunityStaff({
        name: accountForm.value.name.trim(),
        phone: accountForm.value.phone.trim(),
        password: accountForm.value.password,
        community_id: "community-haitang",
        login_username: accountForm.value.loginUsername.trim() || null,
      });
      completedCredentials.value = {
        username: currentLoginAccount.value,
        password: accountForm.value.password,
        role: registrationRole.value,
      };
      successText.value = "社区工作人员账号已创建完成。回到登录页后，系统会自动回填可用账号和密码。";
    }
    registrationStep.value = 4;
  } catch (error) {
    errorText.value = formatError(error, "注册失败，请稍后重试。");
  } finally {
    submitting.value = false;
  }
}

function finishAndPrefill() {
  if (!completedCredentials.value) return;
  emit("prefillLogin", completedCredentials.value);
}
</script>

<template>
  <article class="register-panel" data-testid="registration-panel">
    <div class="register-head">
      <div>
        <p class="section-eyebrow">注册链路</p>
        <h2>{{ activeRole.title }}</h2>
        <p class="subtle-copy">登录页、身份选择、账号注册、资料完善和完成回填都沿用同一套轻玻璃视觉。注册动作仍只调用真实公共注册接口，不走 mock。</p>
      </div>
      <button type="button" class="ghost-btn" @click="emit('close')">返回登录</button>
    </div>

    <div class="register-progress">
      <article
        v-for="step in registrationSteps"
        :key="step.id"
        class="register-progress-item"
        :class="{ active: registrationStep >= step.id, current: registrationStep === step.id }"
      >
        <span>{{ step.id }}</span>
        <div>
          <strong>{{ step.title }}</strong>
          <small>{{ step.description }}</small>
        </div>
      </article>
    </div>

    <div v-if="registrationStep === 1" class="register-stage-card register-stage-card--role">
      <div class="register-stage-copy">
        <p class="section-eyebrow">第 1 步</p>
        <h3>先选择当前注册身份</h3>
        <p>先确认注册对象，再进入账号创建和资料完善。整个流程优先保持中文表达，不在界面里暴露接口名和调试词。</p>
      </div>
      <div class="register-role-grid">
        <button
          v-for="role in registrationRoleOptions"
          :key="role.key"
          type="button"
          class="register-role-card"
          :data-testid="`registration-role-${role.key}`"
          :class="{ active: registrationRole === role.key }"
          @click="switchRole(role.key)"
        >
          <span>{{ role.badge }}</span>
          <strong>{{ role.label }}</strong>
          <p>{{ role.description }}</p>
        </button>
      </div>
      <div class="register-actions">
        <span class="status-tag tone-info">当前身份：{{ activeRole.label }}</span>
        <button type="button" class="primary-btn" data-testid="registration-open-account-step" @click="nextFromRoleStep">进入注册</button>
      </div>
    </div>

    <div v-else-if="registrationStep === 2" class="register-stage-card">
      <div class="register-stage-copy">
        <p class="section-eyebrow">第 2 步</p>
        <h3>注册账号</h3>
        <p>{{ activeRole.accountHint }}</p>
      </div>

      <div class="register-form-grid">
        <label class="form-field">
          <span>姓名</span>
          <input v-model="accountForm.name" data-testid="registration-name" class="text-input" type="text" placeholder="请输入姓名" />
        </label>
        <label class="form-field">
          <span>手机号</span>
          <input v-model="accountForm.phone" data-testid="registration-phone" class="text-input" type="text" placeholder="请输入手机号" />
        </label>
        <label v-if="registrationRole !== 'elder'" class="form-field">
          <span>登录账号</span>
          <input v-model="accountForm.loginUsername" data-testid="registration-login-username" class="text-input" type="text" placeholder="可选，自定义登录账号" />
        </label>
        <label class="form-field">
          <span>设置密码</span>
          <input v-model="accountForm.password" data-testid="registration-password" class="text-input" type="password" placeholder="请输入密码" />
        </label>
        <label class="form-field register-span-2">
          <span>确认密码</span>
          <input v-model="accountForm.confirmPassword" data-testid="registration-confirm-password" class="text-input" type="password" placeholder="请再次输入密码" />
        </label>
      </div>

      <p v-if="errorText" class="feedback-banner feedback-error">{{ errorText }}</p>

      <div class="register-actions">
        <button type="button" class="ghost-btn" @click="backToStep(1)">返回身份选择</button>
        <button type="button" class="primary-btn" data-testid="registration-next-profile" @click="goToProfileStep">进入资料完善</button>
      </div>
    </div>

    <div v-else-if="registrationStep === 3" class="register-stage-card">
      <div class="register-stage-copy">
        <p class="section-eyebrow">第 3 步</p>
        <h3>{{ activeRole.profileTitle }}</h3>
        <p>{{ activeRole.profileDescription }}</p>
      </div>

      <div v-if="registrationRole === 'elder'" class="register-form-grid">
        <label class="form-field">
          <span>房间号</span>
          <input v-model="profileForm.apartment" data-testid="registration-apartment" class="text-input" type="text" placeholder="例如 A-302" />
        </label>
        <label class="form-field">
          <span>年龄</span>
          <input v-model="profileForm.age" data-testid="registration-age" class="text-input" type="number" min="1" placeholder="例如 78" />
        </label>
      </div>

      <div v-else-if="registrationRole === 'family'" class="register-form-grid">
        <label class="form-field">
          <span>关系类型</span>
          <select v-model="profileForm.relationship" data-testid="registration-relationship" class="inline-select relation-select">
            <option value="daughter">女儿</option>
            <option value="son">儿子</option>
            <option value="spouse">配偶</option>
            <option value="granddaughter">孙女</option>
            <option value="grandson">孙子</option>
            <option value="relative">其他亲属</option>
          </select>
        </label>
        <label class="form-field">
          <span>进入系统后优先查看</span>
          <select v-model="profileForm.landingChoice" data-testid="registration-landing-choice" class="inline-select relation-select">
            <option value="report">健康报告</option>
            <option value="overview">当前状态概览</option>
            <option value="alarm">异常提醒</option>
          </select>
        </label>
      </div>

      <div v-else class="register-form-grid">
        <label class="form-field">
          <span>值守班次</span>
          <select v-model="profileForm.shift" data-testid="registration-shift" class="inline-select relation-select">
            <option value="day">日间值守</option>
            <option value="night">夜间值守</option>
            <option value="flex">灵活值守</option>
          </select>
        </label>
        <label class="form-field">
          <span>值守站点</span>
          <input v-model="profileForm.stationLabel" data-testid="registration-station-label" class="text-input" type="text" placeholder="例如 海棠苑社区值守台" />
        </label>
        <label class="form-field register-span-2">
          <span>进入系统后优先查看</span>
          <select v-model="profileForm.landingChoice" data-testid="registration-community-landing-choice" class="inline-select relation-select">
            <option value="overview">社区总览</option>
            <option value="alarm">异常提醒</option>
            <option value="report">结构化报告</option>
          </select>
        </label>
      </div>

      <div v-if="registrationRole !== 'community'" class="register-choice-panel">
        <div>
          <strong>设备绑定计划</strong>
          <p class="helper-copy">{{ bindPlanCopy }}</p>
        </div>
        <div class="mode-switch register-choice-switch">
          <button type="button" data-testid="registration-bind-later" class="switch-btn mini-switch" :class="{ active: profileForm.bindPlan === 'later' }" @click="profileForm.bindPlan = 'later'">稍后绑定</button>
          <button type="button" data-testid="registration-bind-now" class="switch-btn mini-switch" :class="{ active: profileForm.bindPlan === 'now' }" @click="profileForm.bindPlan = 'now'">尽快绑定</button>
        </div>
      </div>

      <p v-if="errorText" class="feedback-banner feedback-error">{{ errorText }}</p>

      <div class="register-actions">
        <button type="button" class="ghost-btn" @click="backToStep(2)">返回账号创建</button>
        <button type="button" data-testid="registration-submit" class="primary-btn" :disabled="submitting" @click="void submitRegistration()">
          {{ submitting ? "提交中..." : "完成资料并创建账号" }}
        </button>
      </div>
    </div>

    <div v-else class="register-stage-card register-stage-card--complete">
      <div class="register-result-mark">OK</div>
      <div class="register-result-copy" data-testid="registration-complete">
        <p class="section-eyebrow">第 4 步</p>
        <h3>注册完成，准备回到登录</h3>
        <p class="feedback-banner feedback-success register-complete-banner">{{ successText || "账号已创建完成。" }}</p>
        <p class="subtle-copy">这一步不会直接跳走。你可以先确认完成态文案、登录账号和下一步去向，再主动回到登录并触发自动回填。</p>

        <div class="register-complete-grid">
          <article class="register-complete-card">
            <span>登录账号</span>
            <strong>{{ completedCredentials?.username || currentLoginAccount || "待回填" }}</strong>
            <p>点击下方主按钮后，登录卡片会出现绿色回填提示，并自动写入账号与密码。</p>
          </article>
          <article class="register-complete-card">
            <span>下一步</span>
            <strong>{{ registrationRole === "community" ? "进入社区总览" : registrationRole === "family" ? "进入家属端主链" : "先验证首登流程" }}</strong>
            <p>完成态负责承接“注册结束 -> 回到登录 -> 进入系统”这段体验，不让用户成功后突然丢失上下文。</p>
          </article>
        </div>

        <ul class="list-copy compact">
          <li v-for="item in profileSummary" :key="item">{{ item }}</li>
          <li>本轮资料完善不新增后端依赖，只展示当前真实接口已经支持的结构化信息。</li>
        </ul>

        <div class="register-actions">
          <button type="button" class="ghost-btn" @click="backToStep(3)">返回资料完善</button>
          <button type="button" data-testid="registration-prefill-login" class="primary-btn" @click="finishAndPrefill">回到登录并自动回填</button>
        </div>
      </div>
    </div>
  </article>
</template>

<style scoped>
.register-panel,
.register-stage-card,
.register-stage-copy,
.register-result-copy {
  display: grid;
  gap: 16px;
}

.register-panel {
  gap: 18px;
}

.register-head,
.register-actions,
.register-choice-panel {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: flex-start;
}

.register-progress {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.register-progress-item {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 14px;
  border-radius: 20px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(248, 250, 252, 0.78);
  color: var(--text-sub);
}

.register-progress-item.active {
  border-color: rgba(14, 165, 233, 0.18);
  background: rgba(240, 249, 255, 0.88);
}

.register-progress-item.current {
  box-shadow: 0 16px 32px rgba(14, 116, 144, 0.12);
}

.register-progress-item span {
  display: inline-flex;
  width: 28px;
  height: 28px;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: rgba(15, 118, 110, 0.12);
  color: var(--brand);
  font-size: 0.76rem;
  font-weight: 800;
}

.register-progress-item strong {
  display: block;
}

.register-progress-item small {
  display: block;
  margin-top: 6px;
  color: var(--text-muted);
  line-height: 1.55;
}

.register-stage-card {
  padding: 22px;
  border-radius: 24px;
  border: 1px solid rgba(255, 255, 255, 0.36);
  background: rgba(255, 255, 255, 0.48);
  backdrop-filter: blur(14px);
}

.register-stage-card--role {
  gap: 18px;
}

.register-stage-copy h3,
.register-result-copy h3 {
  margin: 0;
  font-family: var(--font-display);
  font-size: 1.34rem;
  letter-spacing: -0.03em;
}

.register-stage-copy p,
.register-result-copy .subtle-copy,
.register-complete-card p {
  margin: 0;
  color: var(--text-sub);
  line-height: 1.72;
}

.register-role-grid,
.register-form-grid,
.register-complete-grid {
  display: grid;
  gap: 12px;
}

.register-role-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.register-role-card,
.register-complete-card {
  border-radius: 22px;
  border: 1px solid rgba(15, 118, 110, 0.12);
  background: rgba(255, 255, 255, 0.72);
  padding: 18px;
  text-align: left;
  color: inherit;
}

.register-role-card {
  cursor: pointer;
  transition: transform var(--trans-base), border-color var(--trans-base), box-shadow var(--trans-base);
}

.register-role-card:hover,
.register-role-card.active {
  transform: translateY(-2px);
  border-color: rgba(14, 165, 233, 0.24);
  box-shadow: 0 18px 32px rgba(14, 116, 144, 0.12);
}

.register-role-card span,
.register-complete-card span {
  color: var(--brand);
  font-size: 0.74rem;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.register-role-card strong,
.register-complete-card strong {
  display: block;
  margin-top: 10px;
}

.register-role-card p {
  margin: 8px 0 0;
  color: var(--text-sub);
  line-height: 1.7;
}

.register-form-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.register-span-2 {
  grid-column: span 2;
}

.register-choice-panel {
  padding: 16px 18px;
  border-radius: 20px;
  border: 1px solid rgba(15, 118, 110, 0.12);
  background: rgba(255, 255, 255, 0.56);
}

.register-complete-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.register-complete-card strong {
  font-size: 1.18rem;
  line-height: 1.32;
}

.register-stage-card--complete {
  grid-template-columns: 88px minmax(0, 1fr);
  align-items: start;
}

.register-result-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 72px;
  height: 72px;
  border-radius: 26px;
  background: linear-gradient(135deg, rgba(15, 118, 110, 0.92), rgba(14, 165, 233, 0.88));
  color: #fff;
  font-family: var(--font-display);
  font-size: 1rem;
  font-weight: 800;
  box-shadow: 0 20px 36px rgba(14, 116, 144, 0.18);
}

.register-actions {
  justify-content: flex-end;
  gap: 12px;
}

@media (max-width: 960px) {
  .register-progress,
  .register-role-grid,
  .register-form-grid,
  .register-complete-grid {
    grid-template-columns: 1fr;
  }

  .register-stage-card,
  .register-stage-card--complete {
    grid-template-columns: 1fr;
    padding: 18px;
  }

  .register-head,
  .register-actions,
  .register-choice-panel {
    flex-direction: column;
    align-items: flex-start;
  }

  .register-span-2 {
    grid-column: span 1;
  }
}
</style>
