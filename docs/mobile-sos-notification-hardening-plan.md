# 移动端 SOS 后台提醒加固方案

更新时间：2026-05-01

## 1. 当前问题

当前家属端的 SOS 实时体验主要依赖前台 WebSocket：

- App 在前台时，SOS 可通过 WebSocket 立即到达，并触发弹窗与声音。
- App 退到后台、锁屏、或被系统挂起后，WebSocket 不具备系统级必达保证。
- 一旦 WebSocket 短暂断开，App 会出现告警延迟、漏首条告警、或提醒体验不稳定的问题。

## 2. 官方约束与结论

基于官方资料，当前问题不能只靠“优化轮询”解决，必须分层处理：

### A. 前台与后台是不同运行态

Firebase Flutter 官方文档明确区分了前台、后台和终止态消息处理；后台消息需要单独的后台处理逻辑，终止态则依赖系统推送通道唤醒应用，而不是普通前台连接。

这意味着：

- 前台 WebSocket 适合做“实时 UI”。
- 后台/锁屏/终止态要做“系统级提醒”，必须接入 FCM/APNs 这类远程推送。

### B. Android 13+ 需要运行时通知权限

Android 官方要求 Android 13 及以上在发送通知前申请 `POST_NOTIFICATIONS` 权限，否则高优先级提醒也可能根本不展示。

### C. iOS 的强打断提醒有更严格限制

iOS 的普通通知可以做 alert/sound，但真正更强的“Critical Alerts”需要 Apple entitlement，不是默认就能开。没有 entitlement 时，最佳可行路径通常是 time-sensitive 通知。

## 3. 这次已实施的改造

### 已落地 1：本地系统通知链路

移动端新增本地系统通知服务，用于把当前激活的 SOS 告警同步到系统通知层：

- 建立 SOS 专用高优先级通知通道
- 登录后主动初始化通知能力
- 请求 Android/iOS 通知权限
- 当家属端存在未确认 SOS 且 App 不在前台时，自动投递系统通知
- 当告警已解除或用户退出登录时，自动清理通知

这样可以覆盖：

- App 切到后台但进程仍存活
- WebSocket 仍在或恢复后拿到告警
- 用户没有停留在当前页面时

### 已落地 2：WebSocket 断连兜底刷新

移动端新增低频兜底刷新：

- WebSocket 断开后，不再只等待重连
- 同时以低频轮询 `/alarms` 与 `/alarms/queue`
- 让 SOS 在“实时链路抖动”时仍能被补回

这不能替代远程推送，但能显著提高“网络不稳、切前后台、偶发断连”时的可靠性。

### 已落地 3：系统通知与前台弹窗协同

当前逻辑调整为：

- App 在前台：优先用现有弹窗 + 音效，不保留重复系统通知
- App 不在前台：优先保留系统通知，让提醒落到系统层

这能减少“前台双重打扰”和“后台完全无感知”两种极端情况。

## 4. 仍然存在的边界

### 仍未彻底解决：被系统杀死后的必达

如果 App 已被系统彻底挂起或杀死：

- 本地轮询不会运行
- WebSocket 不会运行
- 本地通知也无法凭空产生

这部分只能依赖远程推送服务。

## 5. 下一阶段详细计划

### P0：已完成

目标：先把“当前 App 进程还活着时”的稳定性做扎实。

已完成项：

- 前台弹窗稳定化
- 告警上下文补全
- 家属端权限过滤
- 本地系统通知
- 通知权限申请
- WebSocket 断连兜底刷新

验收标准：

- 前台 SOS 继续保持秒级弹窗
- App 切后台但未被系统杀死时，可见系统通知
- WebSocket 短暂中断时，告警仍能在兜底刷新内恢复

### P1：推送接入准备

目标：为真正后台/锁屏/终止态提醒打底。

实施项：

1. 后端新增移动设备推送订阅表
2. App 登录后注册设备推送 token
3. App 退出登录/切账号时注销 token
4. 后端告警服务改成“双写”：
   - 写本地 `mobile_pushes`
   - 写远程推送 provider 抽象层
5. 为 family/elder/community 建立可见范围过滤

验收标准：

- 后端知道“哪台手机属于哪个家属账号”
- 同一家庭多终端可被正确投递
- token 过期、重复注册、换机重装不会造成脏数据失控

### P2：FCM / APNs 正式接入

目标：实现后台、锁屏、终止态的系统级到达。

实施项：

1. Flutter 端接入 Firebase Messaging
2. Android 配置 FCM
3. iOS 配置 APNs + Firebase
4. Flutter 增加后台消息 handler
5. 收到远程 push 后，统一转换为本地高优先级 SOS 通知
6. 点击通知后恢复到对应告警页

验收标准：

- Android 锁屏下收到 SOS 可见 heads-up / 通知栏提醒
- iPhone 锁屏下收到 SOS 提示音与横幅
- App 被划掉后仍可收到远程推送

### P3：高级体验与应急升级

目标：把体验从“能提醒”提升到“可运营、可追踪、可兜底”。

实施项：

1. 通知文案分级
   - SOS
   - 跌倒
   - 生命体征危急
2. 通知去重与合并
3. 未确认告警二次提醒
4. 超时升级策略
   - 先家属
   - 再社区
   - 再电话/SMS 网关
5. 埋点与观测
   - 发出时间
   - 到达时间
   - 点击时间
   - 确认时间

验收标准：

- 告警不刷屏
- 未处理告警会升级
- 能量化统计“是否到达、多久到达、谁处理了”

## 6. 当前推荐上线顺序

推荐顺序如下：

1. 先上线本次已完成的本地系统通知与断连兜底刷新
2. 紧接着做推送 token 注册与后端订阅表
3. 再接 FCM / APNs，完成真正后台与锁屏提醒
4. 最后做二次提醒、电话/SMS 升级和监控看板

## 7. 本次代码实现范围

本次已完成代码级改造：

- Flutter 本地通知服务
- Android 通知权限声明
- 登录后通知能力初始化
- SOS 告警与系统通知同步
- WebSocket 断连后的低频兜底刷新

未在本次直接完成的部分：

- FCM / APNs 云端配置
- iOS Critical Alerts entitlement
- 后端设备 token 注册与远程投递服务

## 8. 参考资料

- Firebase Cloud Messaging for Flutter: https://firebase.google.com/docs/cloud-messaging/flutter/receive?hl=zh-cn
- Android notification runtime permission: https://developer.android.com/develop/ui/views/notifications/notification-permission
- Apple UserNotifications authorization options: https://developer.apple.com/documentation/usernotifications/unauthorizationoptions
- flutter_local_notifications package: https://pub.dev/packages/flutter_local_notifications
