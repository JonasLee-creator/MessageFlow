# 时序 · ChronoFlow 手机本地版

当前主线是 **Kotlin + Jetpack Compose 原生 Android 应用**：提取微信、QQ 群系统通知，或通过 Canvas 官方 API 同步课程信息，再使用本地规则或用户主动配置的 DeepSeek API 识别内容，并在手机上确认、保存和安排日程。

**Android Studio 请打开 [apps/android](apps/android)，不是旧的 apps/mobile。**

```text
微信 / QQ 系统通知（仅白名单群）
Canvas API（课程、作业、公告、课程日历）
    → 本地规则或 DeepSeek 提取 → 核对新增 / 修改 / 取消
    → 手机任务与固定日程 → 本地排程 → 时间表与开始提醒
```

## 已写入代码

- 原生中文五页面：今天、发现、任务、日历、设置。
- 微信、QQ 系统通知监听；应用 + 群名白名单；普通正文、长文本、多消息处理与去重。
- Canvas 连接器：用户在学校站点登录并创建个人 Access Token；同步活动课程的作业、公告和课程日历，支持重复过滤与内容/时间变更追踪。
- 常见中文日期、截止、耗时、会议/考试时间段、延期与取消的规则提取。
- 默认确认后应用；可选自动应用明确且完整的新建事项。歧义、修改与取消仍需确认。
- 任务和固定日程；30分钟粒度、14天窗口的本地排程；锁定、连续时段与缺口提示。
- 可选 DeepSeek：多事项拆分、上下文关联、任务拆解、原文依据、每日摘要、风险预测和每周复盘。
- 端侧不确定性感知：对动作、名称、时间、目标匹配和原文证据分别评分，只提出最多两个优先级最高的问题；修改与取消始终需要确认。
- 可学习的个人时间模型：按任务类型、课程、难度、初始估时和实际耗时学习耗时倍率；记录时间块的完成、跳过与延后，优先安排历史上更容易完成的时段。
- 所有个人模型与执行记录均留在本机，并使用 Android Keystore + AES-GCM 加密保存；无需自建服务器。
- 非精确的本地开始提醒，可能受到省电模式和厂商后台限制影响。

## 验证状态

生产核心、Android 工程和 Debug APK 已实际编译；57项核心回归检查通过，包含字段级不确定性、个性化时间模型及100组随机排程检查。Kotlin/Gradle Kotlin DSL语法、Android XML与配置静态检查通过。

Android Debug APK 已完成编译，JVM 单元测试通过，用户已在一加 Ace 5 上完成 USB 调试连接。微信/QQ真实通知、DeepSeek API、后台提醒和不同屏幕的真机验收仍需继续执行。

## 打开与使用

详见 [原生手机端说明](docs/ANDROID_LOCAL.md)。后续需要 Android Studio、Android SDK 和构建依赖，**不需要 Flutter、Python、Docker或数据库服务器**。DeepSeek 功能需要用户自己的 API Key，关闭 AI 后本地功能仍可使用。

```text
apps/android/            当前主线：原生Android本地版
  app/src/main/kotlin/com/chronoflow/local/
    domain/              解析、过滤、状态变更、排程、提醒选择
    ai/                  DeepSeek结构化分析与学习报告
    canvas/              Canvas官方REST API客户端与安全分页
    data/                加密持久化与本地Repository
    notifications/       通知监听、系统提醒
    ui/                  Compose五页面及编辑/确认表单
  app/src/test/          核心回归检查
  app/src/androidTest/   待设备运行的存储与界面测试
scripts/test-local-core.ps1     使用已有Kotlin/JDK，不安装工具
scripts/check-local-android.py 静态工程检查
apps/mobile/            保留的旧Flutter客户端，当前无需运行
services/backend/       保留的旧后端，当前无需运行
```

旧Docker与Flutter脚本不属于当前本地版启动步骤。当前CI已指向原生Android并通过云端构建。

## 使用边界

只能获得系统实际展示的通知，不能读取微信或QQ聊天数据库与历史消息。隐藏正文、免打扰、通知聚合和应用版本差异可能导致遗漏，遗漏可手动粘贴。

本地规则适合明确通知；启用 DeepSeek 后可以拆分复合通知并理解上下文。模型输出还会经过本地字段级校验，低置信度字段会要求核对，但该机制不能保证结果绝对正确。个人时间建议需要逐步积累完成、跳过、延后和实际耗时数据；样本较少时采用保守先验。排程采用启发式算法，显示缺口表示本轮未找到足够时间，不是数学上的无解证明。
