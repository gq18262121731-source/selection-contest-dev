import { ref, type Ref } from "vue";
import { ApiError, api, type SessionUser } from "../api/client";

export type BusyKey = "" | "elder" | "family" | "relation" | "device";
export type DeviceActionMode = "register" | "bind" | "rebind" | "unbind";

function formatError(error: unknown, fallback: string) {
  if (error instanceof ApiError && error.detail) return error.detail;
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

function normalizeMacAddressInput(raw: string) {
  const compact = raw.replace(/[^0-9a-fA-F]/g, "").toUpperCase();
  if (compact.length !== 12) return raw.trim().toUpperCase();
  return compact.match(/.{1,2}/g)?.join(":") ?? raw.trim().toUpperCase();
}

export function useRelationActions(options: {
  sessionUser: Ref<SessionUser | null>;
  refreshDashboardData: () => Promise<void>;
  getToken: () => string;
}) {
  const relationBusy = ref<BusyKey>("");
  const relationStatus = ref("");
  const relationError = ref("");
  const lastRegisteredDeviceMac = ref("");
  const elderForm = ref({ name: "", phone: "", password: "123456", age: 78, apartment: "" });
  const familyForm = ref({ name: "", phone: "", password: "123456", relationship: "daughter", loginUsername: "" });
  const relationForm = ref({ elderUserId: "", familyUserId: "", relationType: "daughter", isPrimary: true });
  const deviceForm = ref({
    mode: "register" as DeviceActionMode,
    macAddress: "",
    deviceName: "T10-WATCH",
    modelCode: "t10_v3",
    ingestMode: "serial" as const,
    serviceUuid: "00001803-494C-4F47-4943-544543480000",
    deviceUuid: "52616469-6F6C-616E-642D-541000000000",
    targetUserId: "",
    reason: "",
  });

  function clearRelationFeedback() {
    relationStatus.value = "";
    relationError.value = "";
  }

  async function submitElderRegistration() {
    clearRelationFeedback();
    if (!elderForm.value.name.trim() || !elderForm.value.phone.trim() || !elderForm.value.apartment.trim()) {
      relationError.value = "请完整填写老人姓名、手机号和房间信息。";
      return;
    }

    relationBusy.value = "elder";
    try {
      const result = await api.registerElder(
        {
          name: elderForm.value.name.trim(),
          phone: elderForm.value.phone.trim(),
          password: elderForm.value.password,
          age: Number(elderForm.value.age) || 0,
          apartment: elderForm.value.apartment.trim(),
          community_id: options.sessionUser.value?.community_id,
        },
        options.getToken(),
      );
      relationStatus.value = `已登记老人账号：${result.name}。下一步请为他绑定家属或设备。`;
      relationForm.value.elderUserId = result.id;
      deviceForm.value.targetUserId = result.id;
      elderForm.value = { name: "", phone: "", password: "123456", age: 78, apartment: "" };
      await options.refreshDashboardData();
    } catch (error) {
      relationError.value = formatError(error, "老人登记失败，请稍后重试。");
    } finally {
      relationBusy.value = "";
    }
  }

  async function submitFamilyRegistration() {
    clearRelationFeedback();
    if (!familyForm.value.name.trim() || !familyForm.value.phone.trim()) {
      relationError.value = "请完整填写家属姓名和手机号。";
      return;
    }

    relationBusy.value = "family";
    try {
      const result = await api.registerFamily(
        {
          name: familyForm.value.name.trim(),
          phone: familyForm.value.phone.trim(),
          password: familyForm.value.password,
          relationship: familyForm.value.relationship,
          community_id: options.sessionUser.value?.community_id,
          login_username: familyForm.value.loginUsername.trim() || null,
        },
        options.getToken(),
      );
      relationStatus.value = `已登记家属账号：${result.name}。下一步请建立与老人的关系。`;
      relationForm.value.familyUserId = result.id;
      familyForm.value = { name: "", phone: "", password: "123456", relationship: "daughter", loginUsername: "" };
      await options.refreshDashboardData();
    } catch (error) {
      relationError.value = formatError(error, "家属登记失败，请稍后重试。");
    } finally {
      relationBusy.value = "";
    }
  }

  async function submitRelationBinding() {
    clearRelationFeedback();
    if (!relationForm.value.elderUserId || !relationForm.value.familyUserId) {
      relationError.value = "请先选择老人和家属。";
      return;
    }

    relationBusy.value = "relation";
    try {
      await api.bindFamilyRelation(
        {
          elder_user_id: relationForm.value.elderUserId,
          family_user_id: relationForm.value.familyUserId,
          relation_type: relationForm.value.relationType,
          is_primary: relationForm.value.isPrimary,
        },
        options.getToken(),
      );
      relationStatus.value = "家属关系已建立，家属端将能看到对应老人。";
      await options.refreshDashboardData();
    } catch (error) {
      relationError.value = formatError(error, "关系绑定失败，请检查是否重复提交。");
    } finally {
      relationBusy.value = "";
    }
  }

  async function submitDeviceAction() {
    clearRelationFeedback();
    lastRegisteredDeviceMac.value = "";
    const mac = normalizeMacAddressInput(deviceForm.value.macAddress);
    deviceForm.value.macAddress = mac;
    if (!mac) {
      relationError.value = "请填写或选择设备 MAC。";
      return;
    }
    if (deviceForm.value.mode !== "register" && deviceForm.value.mode !== "unbind" && !deviceForm.value.targetUserId) {
      relationError.value = "请选择设备归属的老人。";
      return;
    }

    relationBusy.value = "device";
    try {
      if (deviceForm.value.mode === "register") {
        await api.registerDevice(
          {
            mac_address: mac,
            device_name: deviceForm.value.deviceName.trim() || "T10-WATCH",
            user_id: deviceForm.value.targetUserId || null,
            model_code: deviceForm.value.modelCode,
            ingest_mode: deviceForm.value.ingestMode,
            service_uuid: deviceForm.value.serviceUuid,
            device_uuid: deviceForm.value.deviceUuid,
          },
          options.getToken(),
        );
        lastRegisteredDeviceMac.value = mac.toUpperCase();
      } else if (deviceForm.value.mode === "bind") {
        await api.bindDevice(
          {
            mac_address: mac,
            target_user_id: deviceForm.value.targetUserId,
            operator_id: options.sessionUser.value?.id ?? null,
          },
          options.getToken(),
        );
      } else if (deviceForm.value.mode === "rebind") {
        await api.rebindDevice(
          {
            mac_address: mac,
            new_user_id: deviceForm.value.targetUserId,
            operator_id: options.sessionUser.value?.id ?? null,
            reason: deviceForm.value.reason.trim() || null,
          },
          options.getToken(),
        );
      } else {
        await api.unbindDevice(
          {
            mac_address: mac,
            operator_id: options.sessionUser.value?.id ?? null,
            reason: deviceForm.value.reason.trim() || null,
          },
          options.getToken(),
        );
      }

      relationStatus.value = deviceForm.value.mode === "register"
        ? `T10 手环已注册${deviceForm.value.targetUserId ? "，并已写入当前成员台账" : "，当前暂未绑定成员"}。采集器接入后，系统会自动锁定这台设备并开始等待完整 A/B 双包。`
        : "设备操作已完成。";
      deviceForm.value.reason = "";
      await options.refreshDashboardData();
    } catch (error) {
      relationError.value = formatError(error, "设备操作失败，请稍后重试。");
    } finally {
      relationBusy.value = "";
    }
  }

  return {
    deviceForm,
    elderForm,
    familyForm,
    lastRegisteredDeviceMac,
    relationBusy,
    relationError,
    relationForm,
    relationStatus,
    submitDeviceAction,
    submitElderRegistration,
    submitFamilyRegistration,
    submitRelationBinding,
  };
}
