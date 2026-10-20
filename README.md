# 时序 · ChronoFlow

面向学生课程与学习任务的智能日程规划工具。Android 应用在手机本地预测任务耗时和时段执行概率，结合课表、截止时间及个人反馈生成学习计划。

**添加任务 → 安排日程 → 执行与反馈 → 个性化重排。**

## 产品功能

- **多来源任务管理**：支持手动录入、Canvas 课程作业同步，以及按需启用的微信 / QQ 群通知采集。同步与通知中的新增或变更事项经过核对后进入任务。
- **本机智能规划**：APK 内置 ONNX 权重和规划运行库，任务与课表在手机内处理。智能排程无需电脑、模型服务器或 LLM API 密钥。
- **可解释耗时预测**：展示 P50 / P80 / P95 耗时分位数，结合候选时段执行概率评价计划风险。
- **受约束的日程安排**：避开固定课表，遵守可用时间、截止日期、每日容量和锁定时间块；按用户确认的剩余工时分配，以 30 分钟为粒度向上取整。
- **反馈驱动的个性化**：利用完成耗时、跳过与延后记录校准后续预测，滚动调整日程，并展示完成统计。
- **本地数据管理**：加密保存工作空间，支持账号隔离和游客使用。通知采集默认关闭，需白名单与系统授权；可选 LLM 文本理解、摘要和复盘独立配置。

Android 是训练模型的产品入口。网页提供基础排程、日历和课程网站导入，工作空间保存在浏览器，当前未接入训练的规划模型。跨设备云同步尚未提供。

## Android 构建与使用

设备要求：Android 8.0（API 26）及以上，支持 arm64-v8a 手机与 x86_64 模拟器。

1. 克隆完整仓库，使用 Android Studio 打开 `apps/android`。保留根目录 `model`，构建会读取其中的部署模型与规划代码。
2. 准备 JDK 21、Android SDK Platform 35、Build Tools 35.0.0 和构建机 Python 3.12，完成 Gradle 依赖同步。
3. 在 Android Studio 的 Gradle 面板执行 `:app:testDebugUnitTest :app:assembleDebug`。
4. 安装 `apps/android/app/build/outputs/apk/debug/app-debug.apk`，在设置中开启「本机智能规划」，添加任务与固定课表，点击「生成智能计划」。

成功后首页显示「当前计划：本机智能规划」与耗时分位数。模型预测用于风险和时段选择，采用更长工时需由用户确认；规划失败会明确提示，手动生成失败保留原计划。Canvas 和可选 LLM 功能需要网络及相应配置。

构建机需要 Python，手机无需另装 Python、Docker 或服务器。仓库未附带 `gradlew` 启动脚本；详细依赖、故障处理及设备验收步骤见 [手机模型嵌入与验收](docs/ANDROID_EMBEDDED_MODEL.md)。

## 网页运行

安装 Node.js 20.6 或更高版本，在 `apps/web` 执行：

```sh
node server.mjs
```

打开 <http://127.0.0.1:4173/>。配置与使用说明见 [网页 README](apps/web/README.md)。

## 模型与验证

ChronoFlow-DRP 使用共享任务编码器，同时预测耗时分布和时间槽执行概率；通过轻量在线校准与 V4 风险感知滚动规划生成日程。Android 构建按白名单复用 `model` 中的特征编码和主规划器，并打包已训练 ONNX、配置及校验清单，无需重新训练。

```sh
# 在仓库根目录检查 Android 工程和模型资源
python scripts/check-local-android.py

# 在 model 目录运行模型与规划测试
python -m unittest discover -s tests -v

# 在 apps/web 目录检查网页
npm run check
```

验证覆盖 75 项 Python 测试、5 项 Android 单元测试、Debug APK 构建及网页检查。真实手机飞行模式推理仍需按设备验收步骤确认。模型输出和研究回放结果不能直接视为真实用户收益，也不保证任务完成或全局最优。

## 项目资料

| 内容 | 入口 |
| --- | --- |
| 技术方案 | [HTML 与配套图片](docs/AIC-技术方案.html) · [PDF](docs/时序-技术方案.pdf) |
| 模型结构、特征、训练与规划 | [模型技术总结](model/MODEL_TECHNICAL_SUMMARY.md) |
| 模型工程与实验 | [模型工程](model/README.md) · [回放评估](model/evaluation/README.md) |
| 手机构建与验收 | [内置模型说明](docs/ANDROID_EMBEDDED_MODEL.md) |
| 功能演示 | [录屏与讲解脚本](docs/DEMO_SCRIPT.md) |
| 配图与数据来源 | [配图来源说明](docs/figure-sources/README.md) |

`apps/android` 为 Kotlin + Jetpack Compose 主工程；`apps/web` 为网页；`model` 为模型、训练、部署与回放代码；`docs` 保存技术方案、配图、引用附件和使用说明。临时预览、重复交付包及本地模型归档不进入 Git。
