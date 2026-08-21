# 环境安装说明

推荐直接运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_env.ps1
```

如果你的梯子提供本地 HTTP 代理，比如 `7890`，建议这样运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_env.ps1 -ProxyUrl http://127.0.0.1:7890
```

如果你的代理已经是 TUN / 全局模式，可以不传 `-ProxyUrl`。

## 脚本特点

- 强制使用 `conda classic solver`
- 临时关闭 conda 插件，避免 ToS / cache 权限报错
- 默认把环境装到 `D:\conda-envs\ai-health-iot`，避开项目目录里的空格路径
- 优先单独安装 `torch 2.0.1 + CUDA 11.7`
- 最后自动验证 `torch.cuda.is_available()`

## 可选参数

- `-EnvPath`: 自定义环境路径
- `-ProxyUrl`: 设置终端代理
- `-SkipConnectivityCheck`: 跳过联网预检查
- `-UseYamlInstall`: 直接按 `environment/conda-environment.yml` 一次性创建环境
