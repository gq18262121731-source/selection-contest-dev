# Demo UI Polish Spec

适用范围：`frontend/vue-dashboard`

目标：把当前前端统一到一套可演示的视觉和交互语言，前端工程师可以直接按 token、类名和页面层级落地，不需要再从零猜样式。

当前阶段说明：
- 当前执行重点重新收窄到登录/注册链路
- 结构支持文档见：
  - `docs/login-register-structure-support.md`
- 业务页统一延伸在本阶段暂停，不作为当前 FE/UI 实施边界

## 1. Visual Baseline

视觉基线文件：
- `frontend/vue-dashboard/src/demo-theme.css`

字体：
- 正文：`Noto Sans SC`
- 标题：`Manrope`
- 等宽：`JetBrains Mono`

核心 token：
- 背景：`--bg-base` `--bg-top` `--bg-bottom`
- 面板：`--panel` `--panel-strong` `--panel-tinted`
- 文本：`--text-main` `--text-sub` `--text-muted`
- 品牌色：`--brand` `--brand-2`
- 风险色：`--risk-high` `--risk-medium` `--risk-low`
- 圆角：`--radius-xl` `--radius-lg` `--radius-md`
- 阴影：`--shadow-sm` `--shadow` `--shadow-lg`

基础原则：
- 页面先用大层级分组，再在组内用卡片展示，不把所有字段平铺。
- 面板默认使用半透明白底，避免深色重压。
- 中文正文优先保证行高和留白，段落尽量保持 `1.7+` 的行高。
- 风险信息只在必要区域用高饱和色，不让全页长期处于红橙色。

## 2. Primitive

已统一的基础组件样式：
- 卡片：`.panel`
- 主按钮：`.primary-btn`
- 次按钮：`.ghost-btn`
- 输入框 / 下拉：`.text-input` `.inline-select`
- 元信息标签：`.meta-pill`
- 状态标签：`.status-tag` + `tone-info|tone-neutral|tone-warning|tone-stable|tone-critical`
- 风险标签：`.risk-pill`

推荐标题结构：
- 模块眉标：`.section-eyebrow`
- 模块标题：`h2` / `h3`
- 辅助说明：`.panel-subtitle` 或 `.subtle-copy`

## 3. State Spec

统一状态块：
- 空状态：`.state-block.state-empty`
- 加载状态：`.state-block.state-loading`
- 大空状态：`.state-block.state-empty.state-large`
- 错误反馈：`.feedback-banner.feedback-error`
- 成功反馈：`.feedback-banner.feedback-success`

落地要求：
- Empty state 必须说明“为什么现在是空的”和“下一步会发生什么”。
- Loading state 不只写“加载中”，要说明当前在生成或拉取什么。
- Error state 使用横幅，不要只在按钮旁边塞一行红字。
- 表单反馈优先放在动作区附近，避免用户提交后找不到错误。

## 4. Page Hierarchy

登录页作为全站视觉基线：
- 登录页确定整体配色、卡片圆角、按钮体系、状态标签和背景氛围。
- 其它页面不重新发明视觉，只沿用这套基线做结构延伸。
- 登录页解决“第一眼气质”，业务页解决“信息层级和操作路径”。

登录 / 注册：
- 先选身份，再登录或注册。
- 登录页至少保留三层：身份选择、输入区、快捷账号 / 注册区。
- 注册页至少保留三层：步骤条、身份卡、表单 / 成功回填。
- 登录/注册链路的 5 个小页面结构，以 `docs/login-register-structure-support.md` 为准。

健康评估 / 报告：
- 固定展示顺序：
  1. `summary`
  2. `risk level`
  3. `metrics`
  4. `recommendations`
  5. `key findings`

异常 / 报警流：
- 固定展示顺序：
  1. 当前阶段
  2. 当前处理建议或告警信息
  3. 阶段轨道
  4. 判断依据
  5. 观察阈值

社区总览：
- 固定展示顺序：
  1. 页面眉标 / 页面标题 / 辅助说明
  2. KPI 卡片
  3. 待处理对象表格
  4. 社区智能体建议

成员与设备：
- 产品展示名称优先使用 `成员与设备`
- 路由或内部实现仍可保持原有 `relation` 标识
- 固定展示顺序：
  1. 页面说明和操作规则
  2. 四段操作卡：
     - 老人登记
     - 家属登记
     - 关系绑定
     - 设备归属
  3. 成员关系表
  4. 设备清单
  5. 绑定历史

家属首页：
- 固定展示顺序：
  1. 照护对象选择
  2. 当前摘要
  3. 指标卡
  4. 趋势摘要
  5. 结构化报告
  6. 异常到报警链路
  7. 家庭智能体

## 5. Common Blocks

建议统一复用的页面块：
- 页面头卡：`页面眉标 + 标题 + 说明 + meta pill`
- KPI 卡：`标签 + 核心数值 + 状态色`
- 表格卡：`标题 + 副说明 + 表格 + 空状态`
- 表单卡：`步骤说明 + 表单字段 + 主按钮`
- 智能体卡：`summary + recommendations + ask`
- 图表卡：`标题 + 时间范围 + 指标变化 + 图表画布`

建议统一的命名语义：
- 用户看见的页面名称优先产品化
- 例如：
  - `成员与设备` 优于 `关系台账`
  - `家庭智能体` / `社区智能体` 优于内部 agent 术语

## 6. Chart Language

图表统一语言：
- 不使用重黑底大屏风格
- 图表面板仍然放在浅底卡片里
- 坐标轴和辅助线优先使用低对比灰蓝
- 系列颜色优先从：
  - 主绿色
  - 青绿色
  - 淡蓝色
  中选取
- 琥珀色只用于阈值、警戒线、提示性强调

推荐映射：
- 主趋势线：绿色 / 青绿色
- 次趋势线：淡蓝
- 柱图补充：浅绿色或浅蓝绿色
- 阈值线：琥珀色

交互要求：
- tooltip 清爽，不做深色悬浮大窗
- legend 保持低干扰
- data zoom 仍使用低饱和品牌色

## 7. Responsive Rules

断点策略：
- `<= 1280px`：双栏切单栏
- `<= 960px`：表单、登录卡、阶段卡和指标卡全部转单列
- `<= 720px`：顶部导航、按钮组和标签组允许纵向堆叠

窄屏要求：
- 不保留仅桌面可读的左右双栏说明文案。
- 重要 CTA 按钮保持整行或高可点击区域。
- 指标卡允许单列堆叠，优先保留标题、数值、说明三层。

## 8. Reuse Checklist

新页面落地前先检查：
- 是否优先复用了 `demo-theme.css` 里的 token 和基础类。
- 是否明确区分了 empty / loading / error。
- 是否把摘要、数据、建议拆成至少两层以上。
- 是否在 `960px` 以下仍然能顺序阅读。
- 是否没有引入新的后端字段依赖。
- 是否沿用登录页已经确认的按钮、卡片和状态标签体系。
- 是否没有把单个页面做成独立视觉孤岛。
