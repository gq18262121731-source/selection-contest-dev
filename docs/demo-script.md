# 比赛演示脚本

## 场景一：SOS 秒级告警

1. 打开后端 Mock 流或向 `/api/v1/health/ingest` 注入 `sos_flag=true` 的样本。
2. 大屏右侧告警面板立即出现高优先级事件。
3. 子女端或社区端同步收到告警提示。
4. 调用 `/api/v1/chat/analyze`，展示 AI 给出的应急建议。

## 场景二：隐性异常识别

1. 选中某个设备，观察趋势图中心率、体温缓慢漂移。
2. 实时层未触发硬阈值时，Z-Score 仍可给出预警。
3. 社区总览页展示 `intelligent_anomaly_score`。

## 场景三：社区群体态势

1. 打开 `/api/v1/health/community/overview`。
2. 展示健康、关注、危险三类设备数量。
3. 说明系统可接入大屏热力图或社区地图进一步扩展。
