import { ref } from "vue";

export type AuthFlowStep = "login" | "register";
export type AuthFlowRole = "elder" | "family" | "community";

export interface RegisterFlowForm {
  role: AuthFlowRole;
  loginUsername: string;
  password: string;
  confirmPassword: string;
  name: string;
  phone: string;
  relationship: string;
  age: string;
  apartment: string;
}

export interface AuthCompletedCredentials {
  username: string;
  password: string;
  role: AuthFlowRole;
}

export const authRoleOptions = [
  {
    key: "elder",
    badge: "老人",
    label: "老人",
    description: "佩戴设备用户。",
  },
  {
    key: "family",
    badge: "家属",
    label: "家属",
    description: "推荐，查看老人健康、接收提醒。",
  },
  {
    key: "community",
    badge: "社区",
    label: "社区人员",
    description: "管理多个老人和设备。",
  },
] as const satisfies ReadonlyArray<{
  key: AuthFlowRole;
  badge: string;
  label: string;
  description: string;
}>;

export function createRegisterFlowForm(initialRole: AuthFlowRole = "family"): RegisterFlowForm {
  return {
    role: initialRole,
    loginUsername: "",
    password: "123456",
    confirmPassword: "123456",
    name: "",
    phone: "",
    relationship: "daughter",
    age: "78",
    apartment: "",
  };
}

export function useAuthFlow() {
  const currentStep = ref<AuthFlowStep>("login");

  function goToLogin() {
    currentStep.value = "login";
  }

  function openRegister() {
    currentStep.value = "register";
  }

  return {
    currentStep,
    goToLogin,
    openRegister,
  };
}
