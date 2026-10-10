# 原生 Android 手机端（本地核心 + 可选 DeepSeek）

更新：2026-10-10。当前范围：手机端提取微信/QQ群系统通知，使用本地规则或用户主动配置的 DeepSeek API 理解信息并安排日程。主工程是 `apps/android`，旧Flutter与FastAPI工程保留但不参与运行。

## 所有业务在手机运行

通知过滤、结果确认、数据保存、任务管理、时间安排、个人耗时学习、风险规则与提醒均在手机完成。DeepSeek 默认关闭；启用后，白名单通知正文、群名和相关事项会直接从手机发送到 DeepSeek API，不经过自建后端。API Key 与本地数据一起使用 Android Keystore 加密保存。

## DeepSeek AI 功能

- 一条通知拆分多个任务或日程，并识别新建、修改、延期和取消。
- 结合相同群聊的近期通知及已有任务，关联同一事项并生成变化摘要。
- 对模糊信息生成最少量追问；确认页允许用户补全后再应用。
- 为大任务建议最多8个子任务，并在任务页逐项勾选。
- 显示置信度、重要性、原文依据和 AI 推测字段。
- 在「今天」生成今日摘要、风险预测和每周复盘。
- 已完成任务可记录实际用时；新建相似任务时在本地给出历史耗时建议。
- 本地风险层会识别24小时内未排完、历史估时偏低和截止时间反复变化。

AI 结果不会自动修改已有事项；修改、取消和模糊结果始终进入「发现」确认。DeepSeek 不可用时，通知自动回退到本地规则识别。

## Android Studio 打开与后续构建

工程已使用 Gradle 8.10.2 完成 Debug APK 编译和单元测试。

1. 安装或使用已有Android Studio，选择 **Open**，打开 `D:\Lecture Resources\AIC\apps\android`。
2. 准备 Android SDK Platform 35、Build Tools 35.0.0、Platform Tools，以及模拟器或安卓真机。
3. Gradle JDK 使用 JDK21。本机已用 `jbr-21.0.11` 完成完整Gradle构建；JDK25与当前Gradle组合不兼容。
4. 同步Gradle。固定初始基线：AGP8.7.3、Gradle8.10.2、Kotlin/Compose compiler2.1.0、Compose BOM2025.02.00，不声称为最新版本。
5. 选择 `app` 配置和设备，点击Run。测试APK可通过Build菜单生成。

首次在新电脑同步/构建时，Android Studio 可能需要下载 Gradle 和 Maven 依赖。

遵照不下载的要求，本仓库提供wrapper版本配置，但尚未获取官方 `gradle-wrapper.jar` 和wrapper启动脚本。Android Studio可依据wrapper properties选择Gradle分发；若当前IDE提示缺少wrapper，使用已安装Gradle执行 `gradle wrapper --gradle-version 8.10.2`，或从Android Studio新建空项目复制wrapper JAR与启动脚本，并保留本工程版本配置。不要覆盖业务源码。

已有Gradle8.10.2时也可执行：

```powershell
gradle -p apps/android testDebugUnitTest assembleDebug
```

Debug APK：`apps/android/app/build/outputs/apk/debug/app-debug.apk`。

**无需Flutter、Dart、Python后端、Docker或数据库服务器。** DeepSeek 功能需要用户自己的 API Key；关闭 AI 后其余本地功能仍可使用。最低系统配置Android8.0/API26，编译/目标API35。尚无商店发行签名配置。

## 手机上的操作

1. 在「设置」分别选择微信或QQ，添加课程群名。
2. 点击「打开系统授权设置」，授予时序通知访问。
3. 回到App，打开「开始采集群通知」。默认只生成待确认提议。
4. 群中作业、考试、会议或延期通知进入「发现」。核对对象、时间与耗时，确认后更新计划。
5. 「任务」保存要完成的工作；「日历」显示固定日程与专注时间；「今天」展示当天安排。
6. 每日可用时间在设置中调整。固定课程通过日历的「固定日程」添加，排程会避让。
7. 如需开始提醒，允许系统显示通知。使用普通非精确定时，省电或后台限制可能造成延迟。
8. 如需 AI，在「设置」填写 DeepSeek API Key、模型名并明确开启。可在「今天」生成三类报告，在「发现」查看 AI 的依据和置信度。

首次启动无示例假数据、无需登录。尚未授权时，可用「发现→录入通知」先测试流程。

## 测试句子

日期以通知时间为基准，使用设置中的排程时区。

| 输入 | 预期 |
|---|---|
| 实验三明天18:00前提交，预计2小时 | 创建任务；提取期限与耗时 |
| 实验三周五之前提交 | 提取日期，暂按23:59，要求核对 |
| 明天下午三点到四点开班会 | 创建固定日程 |
| 实验三不用周五交了，改到下周一18:00提交 | 匹配同群任务，提出更新，需要确认 |
| 实验三取消，不用交了 | 取消任务提议，需要确认 |
| 明天高数取消 | 若已有同群高数日程，则提出取消 |
| 明天三点开会 | 上午/下午与结束时间不明，需要补充 |
| 晚上有人吃饭吗 | 无关消息忽略 |

一条通知按一个事项提议，多事项需拆开录入。规则不是通用语言模型；无法识别时手动纠正。日程缺少开始或结束时间时，不能直接确认成功。

## 通知边界

- 当前支持微信官方包 `com.tencent.mm`、QQ官方包 `com.tencent.mobileqq`，不含企业微信和TIM。
- 白名单区分应用和群名，避免跨应用同名群误匹配。
- 支持群名标题、conversationTitle、QQ的“发送者(群名)”、常见未读条数后缀、MessagingStyle、多行与长文本。
- 跳过系统群组摘要；无法确定白名单群名则不采集。
- Android没有对所有第三方应用统一提供“这是群聊”标记。请勿将私人联系人名称填入白名单。
- 仅能读取系统实际提供的通知文字。免打扰、隐藏内容、通知聚合、应用版本和机型差异可能导致遗漏。
- 不读取聊天数据库、历史聊天或没有产生系统通知的消息。
- 侧载限制或厂商后台管理需要在实际设备中验证，不能保证所有机型行为相同。

## 本地存储

数据使用Android Keystore密钥和AES-GCM加密，保存在应用私有目录 `local-state.enc`，通过AtomicFile原子写入。设置 `allowBackup=false`，无需共享存储权限。

成功保存后才更新界面；无法解密已有文件时停止写入，不以空数据覆盖。卸载或清除应用数据会删除计划，V1暂未实现备份导出。

原始通知最多保留1000条，任务和日程继续保留。早期来源被裁剪时界面会说明。停止采集不会删除已有计划。

去重按来源、群名、发送者、正文与时间进行：相同内容10分钟内的重复通知只保留一次。短时间内真实重复发布的相同消息也会合并。

## 排程

- 未来14天，默认每天08:00–22:00，可修改；30分钟粒度，工作量向上取整。
- 按截止时间优先、再看优先级。这是启发式算法，不保证全局最优。
- 避开固定日程、锁定或已经开始的块；检查块结束不越过deadline。
- 不可拆分任务需连续时段。可拆分任务尽量安排可用部分，未安排部分显示分钟缺口。
- 锁定块工作量从需求扣除，避免重复安排。锁定时间与新事件冲突时保留锁定并明确提示。
- 无截止的任务使用当前14天窗口。时间块过去不代表任务完成，请手动完成或修改剩余耗时。
- 通知确认、任务与日程修改、可用时间变化、锁定变化及手动刷新会触发重排。
- 时区保存在设置中，旅行后可选择“使用当前手机时区”。

## 已验证与待验证

已实际执行：

- 使用已有IntelliJ Kotlin编译器编译生产domain代码及测试入口。
- **47项核心检查通过**，包括通知兼容过滤，以及一项含100组随机排程的冲突与截止约束检查。
- 整个原生工程Kotlin/Gradle Kotlin DSL的PSI语法解析通过。
- Gradle Android 完整编译、Debug APK打包与 JVM 单元测试通过。
- Android XML、可选 DeepSeek 网络权限、无Flutter构建依赖等静态检查通过。

复现核心测试：

```powershell
.\scripts\test-local-core.ps1
```

脚本默认使用这台电脑已有IntelliJ的Kotlin目录，可通过 `-KotlinHome` 指定其他已安装版本；不会安装工具。

已编写但尚未执行：Android `LocalStorageTest`（schema/加密存储/重启读取）、`NavigationTest`（五页面导航）。原生CI已完成云端编译、测试和APK上传。

尚未验证：真实 DeepSeek API Key 请求、实际微信/QQ通知的完整机型覆盖、设备Keystore重启测试、后台提醒及屏幕/大字体视觉效果。

## 真机验收

1. 手动录入示例、确认后检查任务和日历；重启App检查数据仍在。
2. 添加会议，验证避让；锁定任务块后重排，验证时间不变且工作量没有重复。
3. 输入延期通知，确认同一任务更新、来源增加；取消后未来时间块消失。
4. 分别验证白名单微信/QQ群，非白名单群和私人聊天不应进入收件箱。
5. 验证重复、多条、长文本、截断和隐藏内容。
6. 禁用采集后新通知不进入；断网仍可确认、编辑和排程。
7. 验证提醒权限拒绝/允许、手机重启、时区变化和省电模式。

## 官方参考

- [通知监听服务](https://developer.android.com/reference/android/service/notification/NotificationListenerService)
- [通知字段与MessagingStyle](https://developer.android.com/reference/android/app/Notification)
- [Compose编译插件](https://developer.android.com/develop/ui/compose/setup-compose-dependencies-and-compiler)
