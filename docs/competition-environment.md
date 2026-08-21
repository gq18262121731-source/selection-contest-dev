# 比赛环境对照

依据《JSG2026038 人工智能赛道-人工智能应用》提取到的关键赛场环境如下：

- 数据科学平台：Anaconda 22.9.0
- 开发语言：Python 3.9 及以上
- 大模型工具：Docker 28.5.1、Dify 1.9.2、Ollama 0.12.9
- 本地模型：Qwen3:1.7B、Deepseek-r1:1.5B
- 数据库：MySQL 5.7 或 PostgreSQL 15
- GPU 环境：CUDA 12.6、cuDNN 8.9.7
- 常用库：Numpy 1.24.4、Pandas 2.0.3、OpenCV 4.11、Torch 2.0.1+cu117 等
- 操作系统：Windows 11 64 位

本项目的 `environment/conda-environment.yml` 沿着赛场约束做了兼容性升级：

- Python 从 3.9+ 固定为 3.10，减少新库冲突。
- Torch 升级为 2.5 + `pytorch-cuda=12.1`，用于适配新驱动和新依赖。
- FastAPI、Pydantic、Scikit-learn 等使用更新版本，避免旧版本安装失败。
- 仍保留 Ollama、PostgreSQL、Vue、ECharts、LangChain 的整体技术路线，方便答辩时对齐规程。

如果现场机器明确只允许与赛场镜像一致，可再降级到规程版本；如果安装失败，优先保留当前兼容版环境。
