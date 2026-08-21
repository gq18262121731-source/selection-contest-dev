# 当前仓库实现逻辑说明（按代码证据校对版）

本文档只描述当前仓库里“能从代码直接证实”的事实，避免把目标方案、口头规划或条件成立时才出现的行为，写成已经稳定落地的结论。

适用时间：2026-03-19

## 1. 当前项目处于什么状态

当前仓库是“Demo 逻辑仍在运行，同时已经插入一部分正式业务骨架”的混合状态，不适合简单说成“正式注册体系已经完成”。

从代码可以直接确认的事实是：

- 仍存在 mock 登录接口  
  见 [auth_api.py](/D:/ai_helth-main/ai_helth-main/backend/api/auth_api.py#L17)
- 仍存在 Demo 目录构造逻辑  
  见 [care_service.py](/D:/ai_helth-main/ai_helth-main/backend/services/care_service.py#L208)
- 已新增老人注册、子女注册、关系绑定接口  
  见 [user_api.py](/D:/ai_helth-main/ai_helth-main/backend/api/user_api.py#L11) 和 [relation_api.py](/D:/ai_helth-main/ai_helth-main/backend/api/relation_api.py#L11)
- 已新增设备登记、绑定、解绑、换绑、绑定日志接口  
  见 [device_api.py](/D:/ai_helth-main/ai_helth-main/backend/api/device_api.py#L10)
- 目录服务已写成“正式目录优先，否则回退 Demo 目录”  
  见 [care_service.py](/D:/ai_helth-main/ai_helth-main/backend/services/care_service.py#L77)

因此，更准确的判断应该是：

> 当前仓库已经补入正式业务接口和部分后台操作入口，但默认登录、默认目录来源、运行主路径仍明显受 Demo / Mock 逻辑影响。

## 2. 当前已经能从后端代码证实的能力

### 2.1 正式用户注册接口存在

后端已经提供：

- `POST /api/v1/users/elders/register`
- `POST /api/v1/users/families/register`

对应实现见：

- [user_api.py](/D:/ai_helth-main/ai_helth-main/backend/api/user_api.py#L11)
- [user_service.py](/D:/ai_helth-main/ai_helth-main/backend/services/user_service.py#L22)

可以确认的行为：

- 老人注册时会创建 `elder` 用户和老人档案
- 子女注册时会创建 `family` 用户和子女档案
- 手机号重复会报 `PHONE_ALREADY_EXISTS`

需要保守说明的点：

- 当前实现是内存态服务，不是数据库持久化实现
- 这说明“流程能跑”，不等于“正式账号体系已稳定上线”

### 2.2 老人-子女关系接口存在

后端已经提供：

- `POST /api/v1/relations/family-bind`

对应实现见：

- [relation_api.py](/D:/ai_helth-main/ai_helth-main/backend/api/relation_api.py#L11)
- [relation_service.py](/D:/ai_helth-main/ai_helth-main/backend/services/relation_service.py#L14)

可以确认的行为：

- 关系绑定独立于设备存在
- 会校验老人必须是 `elder`
- 会校验子女必须是 `family`
- 重复关系会报 `RELATION_ALREADY_EXISTS`

### 2.3 设备注册与绑定接口存在

后端已经提供：

- `POST /api/v1/devices/register`
- `POST /api/v1/devices/bind`
- `POST /api/v1/devices/unbind`
- `POST /api/v1/devices/rebind`
- `GET /api/v1/devices/{mac_address}/bind-logs`

对应实现见：

- [device_api.py](/D:/ai_helth-main/ai_helth-main/backend/api/device_api.py#L10)
- [device_service.py](/D:/ai_helth-main/ai_helth-main/backend/services/device_service.py#L14)

可以确认的行为：

- 设备登记与设备绑定已经拆开
- 新登记设备默认 `bind_status=unbound`
- 绑定目标用户不存在时会报 `USER_NOT_FOUND`
- 默认只允许绑定到 `elder`
- 已绑定设备不能直接重复绑定到别的老人
- 已保留绑定日志查询

### 2.4 正式目录优先逻辑存在

`CareService.get_directory()` 当前逻辑是：

1. 先尝试 `_build_formal_directory()`
2. 如果没有正式用户，再回退到 `_build_demo_directory()`

对应实现见：

- [care_service.py](/D:/ai_helth-main/ai_helth-main/backend/services/care_service.py#L77)
- [care_service.py](/D:/ai_helth-main/ai_helth-main/backend/services/care_service.py#L132)

这说明：

- “正式目录优先”的代码已经写了
- 但是否真的走到正式目录，取决于运行时是否已经有正式用户

## 3. 当前仍明显是 Demo / Mock 的部分

### 3.1 登录主入口仍是 mock

当前前端登录依赖：

- `GET /api/v1/auth/mock-accounts`
- `POST /api/v1/auth/mock-login`

前端调用见：

- [client.ts](/D:/ai_helth-main/ai_helth-main/frontend/vue-dashboard/src/api/client.ts#L277)

后端实现见：

- [auth_api.py](/D:/ai_helth-main/ai_helth-main/backend/api/auth_api.py#L17)

重要结论：

- 当前登录页看到的账号列表，不是正式注册用户列表
- 正式注册接口已经存在，不代表正式登录已经接管前端

### 3.2 Mock 账号来源仍是 Demo 目录

`mock-accounts` 的账号列表来自 `CareService._build_demo_accounts()`，而不是正式用户服务。

对应实现见：

- [care_service.py](/D:/ai_helth-main/ai_helth-main/backend/services/care_service.py#L180)

其规则是：

- 一定会生成 `community_admin`
- family mock 账号来自 Demo 目录中的 `families`

这也是为什么你现在经常只看到社区账号。

### 3.3 Demo 目录仍然会生效

当 `UserService` 里没有正式用户时，目录会回退到设备推导逻辑。

对应实现见：

- [care_service.py](/D:/ai_helth-main/ai_helth-main/backend/services/care_service.py#L133)
- [care_service.py](/D:/ai_helth-main/ai_helth-main/backend/services/care_service.py#L208)

因此不能把“目录里看到了 elder/family”直接等同于“正式注册已经完成”。

### 3.4 mock 模式启动后仍会自动 seed 设备

在：

- `data_mode == "mock"`
- `use_mock_data == true`

时，依赖初始化会 seed 设备并生成 mock 数据流。

对应实现见：

- [config.py](/D:/ai_helth-main/ai_helth-main/backend/config.py#L58)
- [dependencies.py](/D:/ai_helth-main/ai_helth-main/backend/dependencies.py#L48)

这说明当前默认运行路径仍偏演示态。

## 4. 当前前端到底实现到了哪一步

这里最需要避免写得过头。

### 4.1 可以证实：Vue 已接入后台操作入口

在 `relation` 页里，当前代码确实已经出现了这些表单入口：

- 老人注册
- 子女注册
- 老人-子女关系绑定
- 设备登记
- 设备绑定 / 解绑 / 换绑
- 设备绑定履历

对应代码见：

- [App.vue](/D:/ai_helth-main/ai_helth-main/frontend/vue-dashboard/src/App.vue#L988)
- [App.vue](/D:/ai_helth-main/ai_helth-main/frontend/vue-dashboard/src/App.vue#L1014)

### 4.2 但要保守说明：这不是独立、默认可见的正式注册页

当前这些入口的真实状态是：

- 它们在 `relation` 页内部
- 只有非 `family` 角色可见  
  见 [App.vue](/D:/ai_helth-main/ai_helth-main/frontend/vue-dashboard/src/App.vue#L1014)
- 登录前不可见
- 登录页仍然是 mock 登录入口

所以更准确的表述应该是：

> Vue 看板内已经插入后台操作表单，但它们属于关系页中的后台操作入口，不是独立、默认呈现的正式注册与绑定页面体系。

### 4.3 当前你“只看到社区账号”并不奇怪

从代码看，这是当前实现的自然结果：

1. 登录页只看 mock 账号
2. mock 账号总会生成 `community_admin`
3. family mock 账号依赖 Demo 目录里是否有 family

对应代码见：

- [care_service.py](/D:/ai_helth-main/ai_helth-main/backend/services/care_service.py#L180)
- [care_service.py](/D:/ai_helth-main/ai_helth-main/backend/services/care_service.py#L208)

因此：

- “只能看到社区账号”不代表正式接口不存在
- 但它确实说明当前默认用户入口还是 Demo 入口

## 5. 当前文档里哪些表述容易显得超前

你指出的问题是成立的，主要体现在下面几类句子：

### 5.1 把“接口存在”写成“正式体系已完成”

更准确的写法应该是：

- “后端已提供正式接口骨架”
- 不应直接写成“正式注册体系已经完成”

### 5.2 把“关系页里有后台表单”写成“前端已经完成正式流程页”

更准确的写法应该是：

- “Vue 关系页中已插入后台操作入口”
- 不应直接写成“前端已经完整具备正式注册与绑定流程页”

### 5.3 把“正式目录优先逻辑存在”写成“系统已经完全以正式目录运行”

更准确的写法应该是：

- “目录服务代码已支持正式优先”
- 但运行时仍可能回退到 Demo 目录

## 6. 当前最稳妥的结论

基于当前仓库代码，最稳妥的项目描述应该是：

> 当前仓库已经补入正式用户注册、关系绑定和设备归属相关接口，并在 Vue 关系页中接入了后台操作入口；但默认登录入口、默认运行路径和目录回退逻辑仍明显保留 Demo / Mock 特征，因此项目处于“正式骨架已接入、默认体验仍偏演示态”的过渡阶段。

## 7. 后续建议

如果要让文档与实现长期保持一致，建议后续都按下面原则写：

1. 先写“代码已经存在什么接口/页面/条件判断”
2. 再写“这些能力在什么条件下才会出现”
3. 最后写“哪些仍然是目标态而不是现状”

这样能避免再次出现“文档比代码更超前”的问题。

