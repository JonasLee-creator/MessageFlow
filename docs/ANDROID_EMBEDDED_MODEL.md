# 手机内置智能规划模型

模型权重和规划代码随APK分发，用户安装后不需要服务器或首次联网下载模型。课程网站与可选LLM功能各自仍需要网络。

## 实现

`ModelPlannerClient` 把当前账号的任务、课表、已锁定计划和过去反馈传给 `EmbeddedModelRuntime`，不发起HTTP请求。后台IO线程调用内置Python的 `deployment.android.run`，复用现有特征编码、在线更新和主规划器；神经网络通过ONNX Runtime Android的CPU执行器计算。每次调用的个人历史来自当前工作空间，不在全局解释器中缓存个人状态。

构建时 `syncEmbeddedPython` 只复制白名单生产模块，`syncEmbeddedAssets` 附带ONNX、特征配置、元数据和校验清单。源码只维护在model目录，避免手机与实验出现两份算法。Python里的Torch加载分支不会执行，APK不打包PyTorch或NumPy。

已训练ONNX大小约1.31MiB，最终APK还会增加Python与ONNX运行库体积，实际大小需以构建结果为准。启动模型时核验SHA256，输出非有限值、特征维度不符或约束冲突会报错，不用先验伪装模型输出。支持arm64-v8a手机（含一加Ace 5）和x86_64模拟器。

## 首次构建所需内容

当前已使用用户同步后的缓存完成Debug APK构建及单元测试；新电脑首次构建仍需以下依赖：

1. Android Studio打开仓库内 `apps/android`；保持整个仓库目录结构，不能只复制android文件夹，因为构建会读取根目录model。
2. Gradle JDK使用21，SDK Platform 35、Build Tools 35.0.0沿用现有配置。
3. 构建电脑准备Python 3.12。如果不在PATH，在用户级 `~/.gradle/gradle.properties` 添加 `chronoflowBuildPython=C:/你的路径/python.exe`，路径使用正斜杠；不要把个人绝对路径提交到仓库。
4. 退出Gradle离线模式，Sync Project。Gradle会获取Chaquopy 17.1.0、Python 3.12 Android运行库、ONNX Runtime Android 1.23.2和tzdata 2025.2；无需手装NDK、CUDA、Docker、PyTorch或Python版onnxruntime。
5. 点击Run安装，或Build APK(s)。模型在构建时写入APK，不需要额外拷贝pt文件到手机。

也可以在Android Studio的Gradle面板中执行任务 `:app:testDebugUnitTest :app:assembleDebug`。当前仓库未附带gradlew启动脚本，不要直接复制旧说明中的gradlew命令。

输出为 `app/build/outputs/apk/debug/app-debug.apk`。2026-10-18构建完成，大小约100.35MiB，已核验内置模型SHA256、Python规划模块及arm64-v8a/x86_64原生运行库。旧APK不含本轮嵌入修改。

本轮修正将Android、Kotlin、Compose与Chaquopy插件版本统一声明在app模块，使Chaquopy的运行依赖配置归属app，避免Android Studio在Kotlin任务中解析根项目配置时缺少项目状态锁。命令行构建已通过；修改后Android Studio需重新Sync。

## 使用与失败处理

在设置中保持「开启本机智能规划」。添加任务、固定课表后可自动尝试重排，首页也可以点击「生成智能计划」。正在计算时会显示状态，首次初始化和复杂规划可能较慢。成功后必须显示「当前计划：本机智能规划」，并出现耗时分位数。默认每天最多安排360分钟，规划未来14天、30分钟槽，一次最多30项活动任务。

本机推理无需授权发送数据。通知采集与LLM文本分析仍各自单独启用。关闭本机模型后使用基础排程。自动重排失败会保存业务修改并明确显示基础计划；手动生成失败保留原计划。锁定块与课表冲突时先调整冲突，不能静默移动锁定块。

## 验收

1. 添加两项任务和一段固定课程；退出可选LLM，保持通知采集关闭。
2. 开启飞行模式，点击「生成智能计划」，确认出现本机智能计划和P50/P80/P95，且不占用固定课程。
3. 锁定一个时间块，再新增任务重排；确认锁定块不移动。
4. 记录完成/跳过/延后，重新生成，确认反馈可用于本机个性化。
5. 强制停止后重启，确认模型计划和数据恢复；切换账号确认没有继承另一账号的任务和反馈。

新增设备测试 `EmbeddedModelTest` 会实际加载APK内权重并调用规划器，可以在飞行模式下运行。也可在Android Studio的Gradle面板执行 `:app:connectedDebugAndroidTest` 运行全部设备测试。自动测试本次未在设备执行；66项Python测试使用模拟推理桥接验证特征与规划一致性，不等于真实Android推理性能评测。

运行库说明：[Chaquopy官方文档](https://chaquo.com/chaquopy/doc/current/android.html)、[ONNX Runtime移动端](https://onnxruntime.ai/docs/get-started/with-mobile.html)。
