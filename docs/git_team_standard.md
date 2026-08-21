# 团队 Git / GitHub 使用规范

## 1. 规范目的

为避免团队成员在 GitHub 上传补丁、修复 Bug、合并代码、使用 AI 编码工具时出现混乱，本规范用于统一：

* 分支命名
* Commit 提交
* Pull Request 描述
* 代码审查
* Bug 修复流程
* 接口修改流程
* AI 辅助编码流程
* 版本冻结和回滚流程

所有成员在进行项目开发、Bug 修复、功能补丁、文档更新、前后端联调、模型文件接入、演示流程调整时，必须遵守本规范。

---

# 一、核心原则

## 1. 禁止直接修改主分支

禁止直接向以下分支提交代码：

```text
main
master
develop
release/*
```

所有修改必须通过新建分支完成，再通过 Pull Request 合并。

---

## 2. 每次修改必须有明确目标

一次提交只解决一个明确问题，例如：

* 修复某个接口错误
* 增加某个页面功能
* 调整某个模型路由
* 修改一份文档
* 修复一个配置问题
* 增加一个测试用例

禁止一次提交同时混入：

* 前端改动
* 后端改动
* 模型文件
* 数据集文件
* 无关格式化
* 临时测试文件
* 个人本地配置
* 无关文档清理

---

## 3. 先同步，再开发

每次开始开发前，必须先更新本地代码：

```bash
git checkout develop
git pull origin develop
```

然后再创建自己的开发分支。

如果项目没有 `develop` 分支，则以负责人指定的集成分支为准。

---

# 二、分支命名规范

## 1. 分支格式

统一使用：

```text
类型/负责人-任务简述
```

示例：

```text
fix/zhang-alert-popup
feat/li-report-export
docs/wang-api-standard
test/chen-fall-alert-case
refactor/zhao-model-router
config/li-env-example
```

---

## 2. 常用分支类型

| 类型 | 用途 | 示例 |
| --- | --- | --- |
| `feat` | 新功能 | `feat/li-export-report` |
| `fix` | Bug 修复 | `fix/wang-alert-popup` |
| `docs` | 文档修改 | `docs/chen-api-standard` |
| `test` | 测试相关 | `test/zhao-alert-api-test` |
| `refactor` | 重构代码，不改变功能 | `refactor/li-detect-service` |
| `style` | 样式或 UI 调整 | `style/wang-dashboard-card` |
| `config` | 配置文件调整 | `config/chen-env-example` |
| `chore` | 构建、依赖、杂项 | `chore/zhao-clean-unused-files` |
| `hotfix` | 紧急修复 | `hotfix/li-demo-crash` |

---

# 三、Commit 提交规范

## 1. Commit 格式

统一使用：

```text
类型(模块): 本次修改内容
```

示例：

```text
fix(alert): 修复家属端未弹出告警的问题
feat(report): 新增社区报告导出接口
docs(api): 补充告警接口字段说明
test(fall): 增加跌倒检测等级判断测试
refactor(model): 拆分模型路由判断逻辑
config(env): 新增环境变量示例文件
```

---

## 2. 常用 Commit 类型

| 类型 | 说明 |
| --- | --- |
| `feat` | 新功能 |
| `fix` | 修复 Bug |
| `docs` | 文档修改 |
| `test` | 测试用例 |
| `refactor` | 重构 |
| `style` | UI 或格式调整 |
| `config` | 配置变更 |
| `chore` | 依赖、构建、清理 |
| `revert` | 回滚修改 |

---

## 3. 禁止使用的 Commit 信息

禁止出现以下无意义提交：

```text
update
fix bug
修改一个
111
临时提交
不知道改了啥
final
last version
```

必须写清楚改了什么。

---

# 四、推荐开发流程

## 1. 创建分支

```bash
git checkout develop
git pull origin develop
git checkout -b fix/zhang-alert-popup
```

## 2. 开发过程中查看修改

```bash
git status
git diff
```

提交前必须确认自己改了哪些文件。

## 3. 添加文件

只添加本次任务相关文件：

```bash
git add backend/app/api/alert.py
git add frontend/src/pages/CommunityAlert.vue
```

不建议直接使用：

```bash
git add .
```

除非已经确认所有变更都属于本次任务。

## 4. 提交代码

```bash
git commit -m "fix(alert): 修复社区端和家属端告警弹窗未触发的问题"
```

## 5. 推送分支

```bash
git push origin fix/zhang-alert-popup
```

## 6. 发起 Pull Request

PR 目标分支通常为：

```text
develop
```

不得直接合并到 `main`，除非负责人确认。

---

# 五、Pull Request 规范

## 1. PR 标题格式

```text
类型(模块): 本次修改内容
```

示例：

```text
fix(alert): 修复老人主动告警后社区端和家属端无弹窗问题
feat(report): 新增社区报告导出功能
docs(api): 新增智能体对接接口文档
```

## 2. PR 描述必须包含

每个 PR 必须写清楚以下内容：

```markdown
## 修改目的

说明为什么要改。

## 修改内容

说明具体改了哪些地方。

## 影响范围

说明影响哪些模块，例如前端、后端、数据库、模型、接口、演示流程。

## 测试结果

说明自己做过哪些验证。

## 风险说明

说明是否可能影响现有功能。

## 是否需要负责人重点检查

例如接口字段、告警逻辑、模型路由、演示页面。
```

---

# 六、代码合并规范

## 1. 合并前必须满足

PR 合并前必须满足：

* 代码能正常运行
* 没有明显报错
* 没有提交无关文件
* 没有提交 `.env`
* 没有提交个人本地路径
* 没有提交缓存文件
* 没有提交无关模型权重或数据集
* PR 描述完整
* 至少一名负责人确认

## 2. 合并方式

推荐使用：

```text
Squash and merge
```

这样可以保持主分支提交历史干净。

## 3. 合并后删除分支

PR 合并后，应删除远程分支，避免分支堆积。

---

# 七、禁止提交的文件

以下文件默认禁止提交到 GitHub：

```text
.env
.env.local
.env.production
*.log
*.tmp
__pycache__/
node_modules/
dist/
build/
.venv/
venv/
.idea/
.vscode/
.DS_Store
*.pt
*.pth
*.onnx
*.engine
*.zip
*.rar
*.7z
datasets/
runs/
weights/
```

## 说明

模型权重、数据集、训练结果、运行日志原则上不直接提交到代码仓库。

如果确实需要提交，必须先经过负责人确认，并说明：

* 文件来源
* 文件大小
* 使用位置
* 是否影响部署
* 是否可以替代为下载链接或说明文档

---

# 八、`.gitignore` 规范

项目必须维护 `.gitignore`，建议包含：

```gitignore
# Python
__pycache__/
*.pyc
.venv/
venv/
.env
.env.*

# Node
node_modules/
dist/
build/

# Logs
*.log
logs/

# IDE
.idea/
.vscode/

# System
.DS_Store
Thumbs.db

# AI / ML
runs/
weights/
datasets/
*.pt
*.pth
*.onnx
*.engine

# Temp
*.tmp
*.bak
```

如需提交环境变量示例，只允许提交：

```text
.env.example
```

禁止提交真实密钥、真实账号、真实服务器地址、真实 Token。

---

# 九、接口修改规范

凡是修改接口，必须同步更新接口文档。

包括：

* 新增接口
* 删除接口
* 修改请求字段
* 修改返回字段
* 修改状态码
* 修改字段含义
* 修改 WebSocket 事件名
* 修改告警类型
* 修改模型返回结构

接口修改 PR 必须写清：

```markdown
## 接口变更说明

- 接口地址：
- 请求方式：
- 新增字段：
- 删除字段：
- 修改字段：
- 返回示例：
- 是否兼容旧版本：
- 对前端影响：
- 对演示流程影响：
```

---

# 十、前后端联调规范

## 1. 后端改接口时

后端成员必须提供：

* 接口地址
* 请求方法
* 请求字段
* 返回字段
* 成功示例
* 失败示例
* 是否需要 Token
* 是否需要 WebSocket
* 是否影响旧页面

## 2. 前端接接口时

前端成员必须确认：

* 接口路径是否正确
* 字段名是否一致
* 异常状态是否处理
* 空数据是否处理
* 加载状态是否处理
* 弹窗是否重复触发
* 页面刷新后是否正常

---

# 十一、Bug 修复规范

修复 Bug 时，必须说明：

```markdown
## Bug 现象

用户看到的问题是什么？

## 复现步骤

如何稳定复现？

## 原因分析

问题大概出在哪里？

## 修复方案

本次怎么修？

## 验证结果

怎么证明已经修好？
```

禁止只写“修好了”。

---

# 十二、AI 辅助编码 / Vibe Coding 规范

使用智能体、AI 编程工具、自动补丁工具时，必须遵守以下规则。

## 1. 给 AI 的任务必须具体

错误示例：

```text
帮我修一下项目。
```

正确示例：

```text
请只修复社区端和家属端无法收到老人主动 SOS 告警弹窗的问题。
不要修改数据库结构。
不要重构无关代码。
修改后列出变更文件、原因、测试方式和风险。
```

## 2. AI 修改代码前必须先分析

要求 AI 先输出：

```markdown
## 问题判断
## 可能涉及文件
## 计划修改内容
## 不会修改的内容
## 风险点
```

负责人确认后再允许它正式改代码。

## 3. AI 每次只能处理一个任务

禁止一次让 AI 同时完成：

* 修 Bug
* 做新功能
* 改 UI
* 改数据库
* 改接口
* 写 PPT
* 清理项目
* 重构代码

每次只允许一个明确任务。

## 4. AI 修改后必须给出交付清单

AI 完成后必须输出：

```markdown
## 修改文件列表
## 每个文件修改原因
## 运行/测试命令
## 测试结果
## 是否有未解决问题
## 是否引入新依赖
## 是否修改接口
## 是否修改数据库
## 是否影响演示流程
## 建议 commit message
```

## 5. AI 禁止做的事情

除非负责人明确允许，AI 不得：

* 删除大量文件
* 重构整个项目
* 修改主流程
* 修改数据库结构
* 修改 `.env`
* 修改部署配置
* 替换模型权重
* 覆盖数据集
* 批量格式化全项目
* 自动合并分支
* 自动推送到 `main`
* 使用 `git add .` 提交全部文件
* 提交包含密钥、Token、账号、个人路径的文件

---

# 十三、版本冻结规范

项目用于比赛、答辩、演示前，必须冻结稳定版本。

## 1. 冻结分支命名

```text
release/demo-2026-xx-xx
```

示例：

```text
release/demo-2026-07-02
```

## 2. 冻结版本后

冻结后禁止随意修改演示主流程。

只能允许：

* 紧急 Bug 修复
* 文案小改
* UI 小修
* 配置说明补充
* 不影响主流程的文档更新

## 3. 冻结版本必须记录

```markdown
## 冻结版本说明

- 冻结日期：
- 冻结分支：
- 对应 commit：
- 可演示功能：
- 暂不演示功能：
- 已知问题：
- 启动方式：
- 测试账号：
- 注意事项：
```

---

# 十四、回滚规范

如果合并后出现严重问题，优先回滚对应 PR。

查看提交记录：

```bash
git log --oneline
```

回滚某次提交：

```bash
git revert <commit_id>
```

禁止在不了解原因的情况下直接强制覆盖代码。

慎用：

```bash
git reset --hard
git push --force
```

除非负责人明确批准。

---

# 十五、成员每日提交要求

每位成员每次提交或 PR 后，必须在团队群里说明：

```markdown
【提交说明】

分支：
提交内容：
影响模块：
是否需要其他人同步：
是否需要负责人检查：
```

示例：

```markdown
【提交说明】

分支：fix/zhang-alert-popup
提交内容：修复 SOS 告警后社区端和家属端无弹窗问题
影响模块：后端告警推送、社区端弹窗、家属端弹窗
是否需要其他人同步：前端成员需要同步最新接口字段
是否需要负责人检查：需要检查告警等级和弹窗逻辑
```

---

# 十六、团队标准 Git 操作流程

## 日常开发

```bash
git checkout develop
git pull origin develop
git checkout -b fix/yourname-task-name

# 修改代码后
git status
git diff

# 添加指定文件
git add path/to/file1
git add path/to/file2

# 提交
git commit -m "fix(module): 说明本次修复内容"

# 推送
git push origin fix/yourname-task-name
```

然后到 GitHub 发起 Pull Request。

## 更新自己分支

如果开发时间较长，需要同步最新代码：

```bash
git checkout develop
git pull origin develop
git checkout fix/yourname-task-name
git merge develop
```

如出现冲突，必须解决冲突后再提交。

---

# 十七、冲突处理规范

遇到冲突时，不要随意删除别人的代码。

必须先确认：

* 冲突文件是谁负责的
* 当前分支改了什么
* 对方分支改了什么
* 是否影响接口或演示流程

解决冲突后：

```bash
git status
git add 冲突文件
git commit -m "fix(merge): 解决 develop 合并冲突"
```

---

# 十八、负责人检查清单

负责人合并 PR 前，应检查：

```markdown
## 基础检查

- [ ] 分支名是否规范
- [ ] Commit 是否清晰
- [ ] PR 描述是否完整
- [ ] 是否只改了本次任务相关文件

## 安全检查

- [ ] 是否提交了 .env
- [ ] 是否提交了密钥 Token
- [ ] 是否提交了个人本地路径
- [ ] 是否提交了无关大文件
- [ ] 是否提交了模型权重或数据集

## 功能检查

- [ ] 是否能正常运行
- [ ] 是否影响已有功能
- [ ] 是否修改接口
- [ ] 是否同步文档
- [ ] 是否需要前后端联调

## 演示检查

- [ ] 是否影响比赛演示流程
- [ ] 是否影响 PPT 讲解口径
- [ ] 是否影响答辩展示页面
- [ ] 是否存在未说明的风险
```

---

# 十九、给智能体使用的固定提示语

以后让智能体修改项目时，可以直接复制以下内容：

```text
你现在是本项目的代码协作智能体，必须严格遵守仓库中的协作规范：

- AGENTS.md
- docs/git_team_standard.md
- .github/PULL_REQUEST_TEMPLATE.md

本次任务要求：

1. 只处理我指定的问题，不要扩展到无关功能。
2. 修改前先分析问题，列出可能涉及的文件、计划修改内容、不会修改的内容和风险点。
3. 未经允许，不要修改 .env、数据库结构、部署配置、模型权重、数据集、主分支配置。
4. 不要批量格式化全项目。
5. 不要删除大量文件。
6. 不要使用 git add . 作为默认提交方式。
7. 不要直接提交到 main/master/develop。
8. 每次修改必须保持原有演示流程稳定。
9. 如果涉及接口，必须说明请求字段、返回字段、兼容性和前端影响。
10. 如果涉及告警、检测、模型、WebSocket、报告导出等核心功能，必须说明风险和验证方式。

完成后必须输出：

- 修改文件列表
- 每个文件的修改原因
- 是否新增依赖
- 是否修改接口
- 是否修改数据库
- 是否影响演示流程
- 测试命令
- 测试结果
- 尚未解决的问题
- 建议提交的 commit message

本次具体任务是：

【在这里填写任务】
```

---

# 二十、最终要求

团队所有成员必须做到：

1. 不直接改主分支。
2. 不提交无关文件。
3. 不提交本地配置和密钥。
4. 不把多个任务混在一个 PR。
5. 每次提交写清楚改了什么。
6. 每个 PR 写清楚目的、内容、影响、测试和风险。
7. 涉及接口必须同步文档。
8. 涉及演示流程必须负责人确认。
9. 使用 AI 编码必须先分析、后修改、再交付清单。
10. 合并前必须经过负责人检查。
