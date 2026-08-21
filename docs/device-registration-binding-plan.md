# 第二阶段设备注册与绑定收尾说明

本文档用于说明当前项目在第二阶段已经落地的设备管理接口、前端对接点与联调建议。

## 1. 当前第二阶段目标

第二阶段的目标是把设备从演示对象升级为正式受控资产：

- 设备注册和设备绑定分开
- 支持解绑和换绑
- 支持绑定历史追踪
- 正式模式下不再依赖自动补设备完成业务闭环

## 2. 当前已落地接口

### 2.1 用户与关系

- `POST /api/v1/users/elders/register`
- `POST /api/v1/users/families/register`
- `POST /api/v1/relations/family-bind`

### 2.2 设备

- `GET /api/v1/devices`
- `GET /api/v1/devices/{mac_address}`
- `POST /api/v1/devices/register`
- `POST /api/v1/devices/bind`
- `POST /api/v1/devices/unbind`
- `POST /api/v1/devices/rebind`
- `GET /api/v1/devices/{mac_address}/bind-logs`

## 3. 第二阶段接口语义

### 3.1 设备注册

`POST /api/v1/devices/register`

作用：

- 创建设备主档
- 默认 `bind_status=unbound`
- 不要求注册时必须立即绑定

兼容说明：

- 当前接口仍允许传 `user_id`
- 如果传了 `user_id`，后端会转为“注册后立即绑定”
- 推荐前端新流程不要再依赖这个兼容行为，而是走“先注册，再 bind”

### 3.2 设备绑定

`POST /api/v1/devices/bind`

作用：

- 把已注册设备绑定到已存在用户
- 当前默认只允许绑定到 `elder`

主要校验：

- 设备是否存在
- 目标用户是否存在
- 目标用户角色是否为 `elder`
- 设备是否已绑定到其他人

### 3.3 设备解绑

`POST /api/v1/devices/unbind`

作用：

- 把设备从当前老人解绑
- 解绑后 `user_id=null`
- `bind_status=unbound`

### 3.4 设备换绑

`POST /api/v1/devices/rebind`

作用：

- 将设备从老人 A 切换到老人 B
- 保留换绑日志

### 3.5 绑定日志

`GET /api/v1/devices/{mac_address}/bind-logs`

作用：

- 用于后台或社区端查看设备归属历史
- 后续前端可直接做“设备履历”抽屉或详情页

## 4. 关键返回字段

设备对象当前重点关注：

- `mac_address`
- `device_name`
- `user_id`
- `status`
- `bind_status`

其中：

- `status` 表示在线状态，如 `online/offline/warning`
- `bind_status` 表示业务绑定状态，如 `unbound/bound/disabled`

不要在前端把这两类状态混为一谈。

## 5. 前端对接建议

### 5.1 当前已经补到前端 API 客户端的能力

文件：

- `frontend/vue-dashboard/src/api/client.ts`

已补方法：

- `registerElder`
- `registerFamily`
- `bindFamilyRelation`
- `registerDevice`
- `bindDevice`
- `unbindDevice`
- `rebindDevice`
- `listDeviceBindLogs`
- `getDevice`

### 5.2 前端最小改造顺序

推荐顺序：

1. 后台增加“老人注册”表单
2. 后台增加“子女注册”表单
3. 后台增加“老人-子女关系绑定”入口
4. 后台增加“设备注册”入口
5. 后台增加“设备绑定/解绑/换绑”入口
6. 社区端增加“设备履历”查看入口

### 5.3 Vue 看板当前无需立刻重构的点

当前大屏仍主要依赖：

- `GET /api/v1/devices`
- `GET /api/v1/care/directory`
- `GET /api/v1/care/directory/family/{family_id}`

因此第二阶段无需立刻改动主看板展示结构。

推荐做法是：

- 先在后台管理页或调试页接第二阶段新接口
- 大屏继续吃聚合后的目录与设备列表
- 等第三阶段再把正式注册/管理入口整合到统一页面

## 6. 联调重点

前端联调时优先验证：

1. 设备注册后是否返回 `bind_status=unbound`
2. 绑定后 `user_id` 和 `bind_status` 是否更新
3. 换绑后日志顺序是否正确
4. 解绑后目录聚合是否同步更新
5. 正式模式下未注册设备是否被拒绝接入

## 7. 当前限制与后续建议

当前第二阶段已落地的是后端骨架和接口。

仍建议后续继续补：

- 设备绑定日志持久化仓储
- 后台管理页面
- 更细的 operator 权限控制
- 正式账号登录替换 mock 登录
