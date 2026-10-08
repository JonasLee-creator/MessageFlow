# 验证记录

2026-10-05 更新：原生手机本地版通过42项Kotlin核心检查（含100组随机排程），语法和配置静态检查通过。Android完整构建及真机验证尚未执行。详情见 [ANDROID_LOCAL.md](ANDROID_LOCAL.md)。以下为旧服务端记录。

日期：2026-10-03。按用户要求，未安装依赖、未下载 SDK、未启动云端构建。

## 已实际执行

- Python AST 语法检查：后端、迁移、测试与检查脚本通过。
- 4 份 Android XML 解析通过。
- Flutter → Kotlin MethodChannel 的 5 个方法名称对应检查通过。
- Android 通知监听绑定权限、Release 禁止明文网络配置检查通过。
- 使用现有 Python/Pydantic 环境运行 `test_schemas_standalone.py`：**8 项通过**。

8 项数据校验覆盖：无时区日期拒绝、耗时/优先级边界、日程时间区间、合法 Action 与置信度、额外字段拒绝、带时区截止时间、日期省略与显式清空区分、空消息拒绝。

## 已编写但未执行

- 18 项后端集成/排程测试：去重、创建/变更/取消闭环、跨账户访问、锁定字段、缺失目标、Canvas 修订、识别失败、不重复排程、连续性、容量冲突、过期风险、版本记录。
- Flutter 五页面导航测试。
- GitHub Actions 后端测试与 debug APK 构建配置。

## 暂未验证

- Flutter analyzer、Dart/Kotlin 编译与 Gradle 依赖解析。
- APK 安装与 Android 真机通知权限、WorkManager、厂商后台限制。
- PostgreSQL/Alembic 迁移实跑、Docker 启动。
- 真实 Canvas 账户同步与真实 LLM 输出。
- 系统日历导出、不同屏幕尺寸的视觉验收。

因此当前交付应称为 **V1 基础源码完成，待安装环境后编译联调**，不能称为已生成可安装软件或全部测试通过。
