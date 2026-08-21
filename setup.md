# Windows 本地部署与启动指南

这份文档面向第一次在 Windows 上跑通本项目的同学，重点说明本机环境准备、依赖安装、Redis 启动、后端启动、前端启动、验证方式和常见问题处理。

如果你只是想快速了解项目结构和整体功能，请优先看 `README.md`；如果你现在的目标是把项目在自己电脑上稳定跑起来，请按本文步骤执行。

补充说明：

- 当前实际文件名是 `setup.md`，不是 `set_up.md`
- 本文档和 `README.md` 保持一致，以项目当前标准命令为准

## 1. 项目标准运行规则

本项目禁止混用 Python 环境。默认规则如下：

- 所有 Python 命令都优先使用 `conda run -n helth python ...`
- 所有 pytest 命令都优先使用 `conda run -n helth pytest ...`
- 后端启动优先使用仓库内脚本，而不是手写裸命令
- 当前仓库支持 `--reload` 快速热重载

因此，本文不会把裸 `python`、裸 `pytest` 作为正式推荐入口。

## 2. 推荐运行方式

当前仓库推荐使用下面这套本地开发组合：

- Docker Desktop：用于启动 Redis
- conda 环境 `helth`：用于运行后端和测试
- Node.js 本地环境：用于运行前端
- ChromaDB：默认使用 `pip` 安装后的本地持久化模式，不强制使用 Docker 容器

这套方式依赖更少、排错更直接，也更适合日常联调。

## 3. 环境准备

### 3.1 Windows 和 WSL 2

建议先将系统更新到 Windows 10 22H2 或更新版本。这样更容易兼容 Docker Desktop 和 WSL 2。

然后用管理员身份打开 PowerShell，安装 WSL：

```powershell
wsl --install
```

安装完成后重启电脑，再检查 WSL 是否可用：

```powershell
wsl --version
```

如果能够看到版本号，说明 WSL 已经安装成功。

### 3.2 安装 Docker Desktop

Docker Desktop 官方下载地址：

[Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/)

安装时建议保持 `Use WSL 2 instead of Hyper-V` 勾选。安装完成后启动 Docker Desktop，确认左下角显示 Engine running。

如果你所在网络访问 Docker Hub 不稳定，可以在 Docker Desktop 的 `Settings -> Docker Engine` 中配置镜像源。例如：

```json
{
  "builder": {
    "gc": {
      "defaultKeepStorage": "20GB",
      "enabled": true
    }
  },
  "experimental": false,
  "registry-mirrors": [
    "https://docker.m.daocloud.io"
  ]
}
```

如果你平时通过本地代理上网，例如 `http://127.0.0.1:7890`，更推荐在 Docker Desktop 的 `Settings -> Resources -> Proxies` 中配置 `HTTP Proxy` 和 `HTTPS Proxy`，通常会比公共镜像源更稳定。

### 3.3 Python 和 Node.js

项目的 Python 版本要求见 `pyproject.toml`，当前为 `>=3.10`。推荐使用 conda 创建独立环境，避免污染已有环境。

示例：

```powershell
conda create -n helth python=3.11 -y
```

如果你喜欢交互式切换环境，也可以执行：

```powershell
conda activate helth
```

但本文后续所有标准命令都默认写成 `conda run -n helth ...`，这样更不容易因为终端状态混乱而跑错解释器。

前端使用 Vite，建议本机准备 Node.js 18 或更高版本。

## 4. 安装项目依赖

### 4.1 初始化环境变量

先在项目根目录复制一份本地环境文件：

```powershell
Copy-Item .env.example .env
```

`.env.example` 用于提供示例配置，真正的本地配置应写在 `.env` 中，便于你按需修改且不影响示例文件。

### 4.2 切换到真实串口采集模式

如果你当前不是只想跑前后端演示，而是要把 T10 手环通过蓝牙采集器真正接进系统，建议把 `.env` 切到真实串口模式。

推荐至少修改下面这些配置：

```env
DATA_MODE=serial
USE_MOCK_DATA=false
SERIAL_ENABLED=true
SERIAL_BAUDRATE=115200
SERIAL_PACKET_TYPE=5
SERIAL_MAC_FILTER=535708000000
SERIAL_AUTO_CONFIGURE=true
```

如果你已经知道采集器对应的串口号，例如 `COM3`，可以再补上：

```env
SERIAL_PORT=COM3
```

如果你暂时还不知道串口号，也可以先留空：

```env
SERIAL_PORT=
```

此时系统会优先尝试自动识别候选串口。

这些配置项的含义如下：

- `DATA_MODE=serial`：切换到真实串口采集模式
- `USE_MOCK_DATA=false`：关闭模拟数据，避免真实数据与演示数据混在一起
- `SERIAL_ENABLED=true`：启用串口采集线程
- `SERIAL_BAUDRATE=115200`：采集器串口波特率，按 T10 协议文档配置
- `SERIAL_PACKET_TYPE=5`：默认优先采集回应包
- `SERIAL_MAC_FILTER=535708000000`：保留给支持前缀过滤的采集器使用
- `SERIAL_APPLY_MAC_FILTER=false`：当前这块采集器在 `TYPE=5` 下加过滤会无输出，因此默认关闭
- `SERIAL_APPLY_PACKET_TYPE=true`：启动时主动切到 `AT+TYPE=5`
- `SERIAL_FALLBACK_DEVICE_MAC=`：当前采集器会在串口行前缀里带真实 MAC，因此默认不再强制兜底
- `SERIAL_ENABLE_BROADCAST_SOS_OVERLAY=true`：主跑 `TYPE=5` 的同时，周期性切到 `TYPE=4` 补抓 SOS
- `SERIAL_RESPONSE_CYCLE_SECONDS=8`：回应包模式持续时长
- `SERIAL_BROADCAST_CYCLE_SECONDS=2`：广播包模式持续时长
- `SERIAL_AUTO_CONFIGURE=true`：启动后自动下发采集器初始化指令

当 `SERIAL_AUTO_CONFIGURE=true` 时，系统启动后会自动尝试执行以下采集器初始化流程：

```text
AT+SCANSTOP
AT+UUID=NO
AT+TYPE=5
AT+SCANSTART
```

如果开启 `SERIAL_ENABLE_BROADCAST_SOS_OVERLAY=true`，系统会在运行期自动按下面的节奏切换：

```text
AT+TYPE=5  持续 8 秒，优先拿完整健康数据
AT+TYPE=4  持续 2 秒，补抓广播包里的 SOS
```

广播包进来后，系统会保留最近一次回应包里的电量、步数、血压、环境温度、表面温度，只用广播包补 `sos_flag` 和实时心率/体温。

如果你后续要切回演示模式，可把 `.env` 改回：

```env
DATA_MODE=mock
USE_MOCK_DATA=true
SERIAL_ENABLED=false
```

### 4.3 安装 Python 依赖

默认请安装 `requirements.txt`：

```powershell
conda run -n helth python -m pip install -r requirements.txt
```

这里的 `requirements.txt` 是完整开发依赖，适合本地开发、调试 and 联调使用。

项目里还有一个 `requirements-runtime.txt`，它是精简运行依赖，只适合“尽快把服务跑起来”的场景，不建议把它当作默认安装入口。

## 5. 启动基础服务

### 5.1 启动 Redis

当前本地开发最少需要先把 Redis 启动起来。进入 `docker` 目录后执行：

```powershell
cd docker
docker compose up -d redis
```

如果看到容器 `ai-health-iot-redis` 运行成功，就说明 Redis 已经就绪。

也可以进一步检查：

```powershell
docker ps
```

### 5.2 关于 PostgreSQL、Ollama 和 ChromaDB

这些服务在仓库里都有预留，但不是你第一次本地跑通时的硬性前置条件。

- PostgreSQL：当前默认配置下项目可先使用 SQLite，本地联调时不是必须
- Ollama：如果你要体验本地大模型能力，再额外启动即可
- ChromaDB：推荐直接使用本地 `pip` 安装模式，不强制用 Docker

如果你后续确实需要这些服务，再单独补启会更稳。

## 6. 启动后端

### 6.1 主推荐方式：使用项目脚本

回到项目根目录后，优先使用下面的标准命令启动 FastAPI 后端：

```powershell
conda run -n helth powershell -ExecutionPolicy Bypass -File .\scripts\start_server.ps1
```

这个脚本会调用项目里的 `scripts/start_server.ps1`，默认监听 `0.0.0.0:8000`，适合局域网真机直接访问。

### 6.2 备选方式：手动启动 Uvicorn

如果你暂时不想走脚本，也可以使用下面的手动命令：

```powershell
conda run -n helth python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

如果你确实需要热重载，再额外追加 `--reload`：

```powershell
conda run -n helth python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

注意：之前项目在 OneDrive 目录下建议关闭 `--reload`，现在移动到本地目录后可放心开启。

## 7. 启动前端

### 7.1 主推荐方式：使用项目脚本

新开一个终端，优先使用下面的标准命令启动前端：

```powershell
conda run -n helth powershell -ExecutionPolicy Bypass -File .\scripts\start_frontend.ps1
```

这个脚本会调用项目里的 `scripts/start_frontend.ps1`，默认监听 `127.0.0.1:5173`。如果本地还没有 `node_modules`，脚本会先执行安装。

### 7.2 备选方式：手动进入前端目录启动

如果你想手动启动，也可以执行：

```powershell
cd frontend\vue-dashboard
npm install
npm run dev
```

前端是标准的 Vite 开发服务。启动成功后，终端通常会给出本地访问地址，例如：

```text
http://127.0.0.1:5173/
```

这时用浏览器打开该地址即可。

### 7.3 登录与角色页面

新版前端已按角色分成“社区端”和“子女端”，启动后先进入登录页。默认演示账号和密码由后端接口生成，密码统一为：

```text
123456
```

你可以在页面下拉框里直接选择账号：

- `community_admin`：社区端账号，可查看全社区总览与关系台账
- `family01` / `family02` ...：子女端账号，只能查看该账号绑定老人

如果你不确定当前有哪些可用账号，可通过接口查看：

```powershell
curl http://127.0.0.1:8000/api/v1/auth/mock-accounts
```

## 8. 验证运行成功

后端启动成功后，建议至少做下面三步检查。

### 8.1 后端健康检查

```powershell
curl http://127.0.0.1:8000/healthz
```

如果接口正常返回，说明后端已经启动成功。

### 8.1.1 局域网联调补充

如果要让 Android 真机访问服务端，再额外做下面几步：

1. 在服务端电脑执行 `ipconfig`，记下局域网 IP。
2. 放行 Windows 防火墙中的 `8000` 端口。
3. 保证手机和电脑连接到同一 Wi-Fi。
4. 在 Flutter 家庭端的“服务器设置”页面填入 `http://<服务器IP>:8000`。
5. 先点“测试连接”，通过后再保存。

### 8.2 后端 HTTP smoke 检查

```powershell
conda run -n helth powershell -ExecutionPolicy Bypass -File .\scripts\smoke_backend_http.ps1
```

### 8.3 联调整体验证

```powershell
conda run -n helth powershell -ExecutionPolicy Bypass -File .\scripts\run_smoke_tests.ps1 -BuildFrontend
```

### 8.4 主系统与视觉服务对接说明

如果当前工作重点是“独立视觉服务接入本项目主系统”，请直接查看：

- [主系统视频桥接对接说明](docs/main-system-video-bridge-integration.md)

这份说明单独整理了：

- 独立视觉服务和主系统的角色划分
- 主系统 `/api/v1/video-bridge/*` 接口
- 视觉服务应提供的 `/healthz`、`/stream/*`、`/integration/results/*`、`/alerting/*` 接口约定
- 运行时桥接配置、轮询方式、推送方式与联调验收步骤
- 2026-06-09 的实测联通结果和已发现问题

## 9. 推荐启动顺序

如果你想按最稳妥的顺序执行，建议按下面的步骤来：

1. 创建 conda 环境：`conda create -n helth python=3.11 -y`
2. 复制 `.env.example` 为 `.env`
3. 安装依赖：`conda run -n helth python -m pip install -r requirements.txt`
4. 启动 Redis：`docker compose up -d redis`
5. 启动后端：`conda run -n helth powershell -ExecutionPolicy Bypass -File .\scripts\start_server.ps1`
6. 启动前端：`conda run -n helth powershell -ExecutionPolicy Bypass -File .\scripts\start_frontend.ps1`
7. 验证后端健康检查、HTTP smoke 和前端页面是否正常打开

## 10. 常见问题

### 10.1 `docker-compose.yml` 提示 `version is obsolete`

如果你看到类似下面的警告：

```text
the attribute `version` is obsolete, it will be ignored
```

这是新版 Docker Compose 的兼容性提示，不会阻止容器启动，可以暂时忽略。

### 10.2 Docker 拉取镜像失败

如果 Redis、PostgreSQL、Ollama 或 ChromaDB 拉取镜像失败，通常是网络、镜像源或代理问题，而不是项目代码问题。

优先排查这几项：

- Docker Desktop 是否已经启动
- 是否需要在 Docker Desktop 中配置代理
- `Docker Engine` 中的镜像源 JSON 是否格式正确
- 当前镜像源是否可用

如果只是 ChromaDB 容器拉取失败，可以先跳过，因为本项目默认不强制依赖 Docker 版 ChromaDB。

### 10.3 PowerShell 报脚本执行策略错误

如果你看到类似下面的提示：

```text
无法加载文件 ... profile.ps1，因为在此系统上禁止运行脚本
```

这通常表示 PowerShell 的执行策略较严格。项目标准脚本已经通过 `-ExecutionPolicy Bypass` 调用，如果你仍然报错，优先确认你执行的是否就是本文里的完整命令。

### 10.4 不知道该装哪个 requirements 文件

默认安装：

```powershell
conda run -n helth python -m pip install -r requirements.txt
```

原因很简单：

- `requirements.txt`：完整开发依赖，适合本地开发与联调
- `requirements-runtime.txt`：精简运行依赖，只适合快速试跑

如果你没有特别明确的精简需求，就以 `requirements.txt` 为准。

### 10.5 前端能打开，但接口报错

这种情况通常说明前端已经正常启动，但后端没有启动、端口不对，或者 Redis 没起来。

建议按下面顺序检查：

1. 后端终端是否仍在运行
2. `http://127.0.0.1:8000/healthz` 是否可访问；真机联调时还要确认 `http://<局域网IP>:8000/healthz` 可访问
3. Redis 容器是否在运行
4. `.env` 中的配置是否被错误修改

## 11. 最小可用命令清单

如果你只想快速抄一份最短命令流程，可以直接用下面这组：

```powershell
conda create -n helth python=3.11 -y
Copy-Item .env.example .env
conda run -n helth python -m pip install -r requirements.txt
cd docker
docker compose up -d redis
cd ..
conda run -n helth python run.py
```

然后新开一个终端进入前端目录执行：

```powershell
cd frontend\vue-dashboard
npm install
npm run dev
```

## 12. GPU 与稳定化补充

### 12.1 推荐的 PyTorch GPU 环境

如果现场演示机器带 NVIDIA GPU，推荐把 `helth` 环境切到 `torch 2.2.2 + cu121`：

```powershell
conda run -n helth python -m pip uninstall -y torch torchvision torchaudio
conda run -n helth python -m pip install --index-url https://download.pytorch.org/whl/cu121 torch==2.2.2 torchvision==0.17.2 torchaudio==2.2.2
```

安装后验证：

```powershell
conda run -n helth python -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu')"
```

项目当前支持：
- `MODEL_DEVICE=auto`：优先 CUDA，失败时回退 CPU
- `MODEL_DEVICE=cpu`：强制使用 CPU
- `MODEL_DEVICE=cuda`：强制使用 GPU，不可用时直接报错

### 12.2 现场演示的稳定化输出

新的健康评分链路已经加入“稳定值判分 + 去抖 + 事件聚合”，现场高频采样时建议重点查看这些返回字段：
- `stabilized_vitals`
- `active_events`
- `score_adjustment_reason`

对应接口：
- `POST /api/v1/health/score`
- `POST /api/v1/health/warning/check`
- `POST /api/v1/agent/health/explain`

当前 `window_data` 已经不再只看最后一个点，而是会返回 `window_mode=event_aggregated_window`，用于抑制边界抖动造成的误报。

## 13. 启动移动端

本项目提供了基于 Flutter 开发的移动端应用（如老人端/子女端）。启动前请确保：

1.  本机已安装并配置好 Flutter 环境。
2.  **开启 Windows 开发人员模式 (Developer Mode)**：Flutter 在 Windows 上构建（特别是使用插件时）需要符号链接 (Symlink) 支持。
    -   您可以运行以下命令快速打开设置页面：
        ```powershell
        start ms-settings:developers
        ```
    -   在打开的页面中，将“开发人员模式”开关切至“开”。

新开一个终端，进入移动端目录执行：

```powershell
cd mobile\flutter_app
 
flutter run
```

如果连接了多个设备，可以用下面命令查看设备列表：

```powershell
flutter devices
```

然后指定设备运行：

```powershell
flutter run -d <device_id>
```

以下账号已绑定到对应的虚拟设备，登录后要求实时显示 mock data；老人端账号与家庭端账号联动，并为每位老人分配演示姓名。

| 账号 | 角色 | 姓名 | 默认密码 | 联动家庭账号 | 备注 |
| --- | --- | --- | --- | --- | --- |
| `community_admin` | 社区端 | 社区管理员 | `123456` | - | 社区总入口 |
| `family01` | 家庭端 | 家属 01 | `123456` | `family01` | 绑定对应虚拟设备组，登录后实时显示 mock data |
| `elder01_01` | 老人端 | 张三 | `123456` | `family01` | 与 `family01` 联动，登录后需要做真实设备绑定解绑演示 |
| `elder01_02` | 老人端 | 李四 | `123456` | `family01` | 与 `family01` 联动，登录后实时显示 mock data |
| `family02` | 家庭端 | 家属 02 | `123456` | `family02` | 绑定对应虚拟设备组，登录后实时显示 mock data |
| `elder02_01` | 老人端 | 王五 | `123456` | `family02` | 与 `family02` 联动，登录后实时显示 mock data |
| `elder02_02` | 老人端 | 赵六 | `123456` | `family02` | 与 `family02` 联动，登录后实时显示 mock data |
| `family03` | 家庭端 | 家属 03 | `123456` | `family03` | 绑定对应虚拟设备组，登录后实时显示 mock data |
| `elder03_01` | 老人端 | 钱七 | `123456` | `family03` | 与 `family03` 联动，登录后实时显示 mock data |
| `elder03_02` | 老人端 | 孙八 | `123456` | `family03` | 与 `family03` 联动，登录后实时显示 mock data |
| `family04` | 家庭端 | 家属 04 | `123456` | `family04` | 绑定对应虚拟设备组，登录后实时显示 mock data |
| `elder04_01` | 老人端 | 周九 | `123456` | `family04` | 与 `family04` 联动，登录后实时显示 mock data |
| `elder04_02` | 老人端 | 吴十 | `123456` | `family04` | 与 `family04` 联动，登录后实时显示 mock data |
| `family05` | 家庭端 | 家属 05 | `123456` | `family05` | 绑定对应虚拟设备组，登录后实时显示 mock data |
| `elder05_01` | 老人端 | 郑十一 | `123456" | `family05` | 与 `family05` 联动，登录后实时显示 mock data |
| `elder05_02` | 老人端 | 卫十二 | `123456` | `family05` | 与 `family05` 联动，登录后实时显示 mock data |
| `family06` | 家庭端 | 家属 06 | `123456` | `family06` | 绑定对应虚拟设备组，登录后实时显示 mock data |
| `elder06_01` | 老人端 | 韩十三 | `123456` | `family06` | 与 `family06` 联动，登录后实时显示 mock data |

cd docker
docker compose up -d redis

conda activate health
python D:\health_original\health1\run.py

cd frontend\vue-dashboard
npm run dev

community_admin

## 14. Vibe Coding / Codex 调试规则

当前项目新增一条必须优先遵守的联调规则：

- [主系统与视频系统地址确认规则](docs/codex-debug-rules.md)

凡是涉及主系统、Vision Service、视频系统、跌倒检测、`/api/v1/vision/*`、`/integration/results/*`、告警联调、前端弹窗联调的任务，都必须先按该规则确认“谁是主系统、谁是 Vision Service”，再继续调试。

## 15. 主系统代码真相源与联调版本记录

主系统唯一代码真相源默认固定为：

`D:\health_original\health1`

除非明确说明“当前部署目录不是 GitHub 最新版本”，否则后续所有主系统问题分析、联调验证、功能开发都默认基于这个仓库进行，不再把 `D:\Program\410health` 作为代码真相源。

每次联调前必须先记录以下版本信息：

```text
Main System Commit:
xxxxxxxx

Main System Branch:
xxxxxxxx

Main System Tags:
xxxxxxxx
```

如果发现部署目录与 GitHub 不一致，必须先记录：

```text
Deploy Commit:
xxxxxxxx

GitHub Commit:
xxxxxxxx
```

记录完成后，才能继续进行主系统、Vision Service、告警链路或前端弹窗排查。
