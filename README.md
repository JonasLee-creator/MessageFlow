# 时序 · ChronoFlow 智能日程规划

Android 是当前模型产品入口：已训练的 ONNX 权重、特征编码、风险感知滚动规划器随 APK 打包，任务与课表在手机内处理，无需电脑、模型服务器或 DeepSeek 密钥。网页暂不接入该模型，继续提供基础排程和课程网站导入。

手动任务 / Canvas课程作业 → 核对 → 手机预测耗时和时段执行概率 → 安排日程 → 完成、跳过或延后反馈 → 个性化重排。

- Android Studio 打开 `apps/android`，原生 Kotlin + Compose，内置 Python 规划器和 ONNX Runtime；不是旧 Flutter 工程。
- 默认启用本机模型；首页显示当前计划来源和 P50/P80/P95 耗时。任务或课表变动会尝试更新；推理失败明确标为基础排程，手动生成失败保留原计划。
- Canvas 连接保留课程、作业、公告和日历同步，新增或变更先确认。
- 微信/QQ通知采集默认关闭，需白名单与系统通知访问授权，不影响本机模型使用。
- 可选 LLM 文本理解、摘要和复盘仍需要所选服务的网络/API配置，与本机规划模型独立。
- App本地数据加密保存；无跨设备云同步。网页仍在浏览器保存工作空间。

## 手机端构建

见 [手机模型嵌入与验收](docs/ANDROID_EMBEDDED_MODEL.md)。首次 Gradle 同步需下载 Chaquopy、ONNX Runtime Android、内置 Python 和时区数据。当前构建已使用你同步后的本机缓存离线完成。构建机需 Python 3.12，手机无需另装 Python、Docker 或服务器软件。

模型入口与规划调用的66项Python测试及网页检查已通过。2026-10-18已完成Android单元测试和Debug APK构建，并核验APK内模型权重哈希、规划代码及运行库。手机飞行模式下的真实推理仍待验收；打包成功不等于设备推理已验证。

## 网页

在 `apps/web` 运行 `node server.mjs`，打开 `http://127.0.0.1:4173/`。网页无本项目训练模型的设置、按钮或代理接口；保留任务、日历、课程网站和独立的可选 LLM 文本识别。

## 算法与检查

`model` 中执行 `python -m unittest discover -s tests -v`；`apps/web` 中执行 `npm run check`。

手机直接复用 `model/evaluation` 中的主规划器和 `model/src/chronoflow_model` 中的特征编码，构建时按白名单打包；不包含数据集、实验报告、训练环境或学校凭据。已训练权重来自核验过的归档，SHA256见 `model/deployment/artifacts/checksums.json`，无需重新训练。

回放实验与真实用户试验应分开描述；既有实验分数不能直接当作手机真实使用收益。`model-final` 为本地归档，不进入Git。模型可预测耗时和风险，但不保证任务完成或全局最优。
