# 安装清单与后续运行

> 此页为旧 Flutter + 服务端版本说明。当前手机本地版见 [ANDROID_LOCAL.md](ANDROID_LOCAL.md)。不需要 Flutter、Python、Docker 或 PostgreSQL。

本次仅编写代码与执行现有环境支持的检查，**未安装以下任何内容，也没有自动运行下载脚本**。

## 需要安装的内容

| 内容 | 用途 | 必需性 |
|---|---|---|
| Flutter SDK **3.29.3**（本工程固定的初始兼容基线，含 Dart） | 分析、测试、构建 App | 安卓开发必需 |
| Android Studio 或 Android SDK 命令行工具 | 管理 Android SDK 与设备 | 安卓构建必需，推荐 Android Studio |
| Android SDK Platform 35、Build Tools 35.0.0、Platform Tools、Command-line Tools | 编译 APK、adb 安装 | 必需 |
| Android NDK **27.0.12077973** | Flutter 3.29 系列 Android 构建所用 NDK | 首次构建准备 |
| JDK 17 | 固定本工程的 Gradle Java 基线 | 推荐；现有 JDK 21 也需在实际构建中验证 |
| Python **3.12** 与 venv/pip | 启动后端 | 后端必需 |
| `services/backend/requirements.txt` 中的 Python 依赖 | FastAPI、SQLAlchemy、OR-Tools 等 | 后端必需 |
| `apps/mobile/pubspec.yaml` 中的 Dart 依赖 | HTTP、国际化、Flutter 测试 | App 必需 |
| PostgreSQL 16 | 服务端关系数据库 | 可选，本地默认 SQLite，无需另装数据库 |
| Docker Desktop | 一键启动后端与 PostgreSQL | 可选，可替代本地后端环境配置 |

现有环境检查发现 Java 21、Git、Docker 命令；Flutter、Dart、adb 未出现在 PATH 中。Codex 自带 Python 3.12 与 Pydantic 可用于当前轻量检查，但这不代表你的终端已配置好独立 Python 后端环境。安装前应先核对现有 Android Studio / SDK，避免重复安装。

Gradle **8.10.2**、Android Gradle Plugin **8.7.3**、Kotlin **2.1.0**、WorkManager **2.10.1** 会由构建工具根据项目配置下载，不需要逐个手动安装。版本为项目起始基线，不声称是最新版本。

## 后端：本地 SQLite 路线

后续同意安装时，在项目根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r services\backend\requirements.txt
.\scripts\run-backend.ps1
```

如果 PowerShell 的执行策略不允许脚本，可直接：

```powershell
cd services\backend
..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

后端默认在 `services/backend/chronoflow.db` 保存数据。默认本地启动自动建表；本地开发密钥首次生成到 `.local-secret`，不要删除或提交。生产使用持久、随机的 `SECRET_KEY` 环境变量。

打开本机 `http://127.0.0.1:8000/docs` 可查看交互式接口；`/health` 可检查服务状态。

**V1 必须单进程运行：`--workers 1`。** 当前异步锁协调 HTTP 与 Canvas 同步事务，不支持多 worker 或多实例并发写入。

## 可选：Docker + PostgreSQL

```powershell
Copy-Item .env.example .env
# 编辑 .env，替换数据库密码和至少 32 字符的随机 SECRET_KEY
docker compose up --build
```

首次执行会下载容器镜像和依赖，故本次没有执行。数据库密码若包含 URI 保留字符，需要相应调整连接 URL；本地可使用长的字母数字随机值。

注意：`.env` 仅供 Docker Compose 使用；直接启动 Python 不会自动加载 `.env`。

## 可选：启用真实 AI

不配置密钥也能手动建任务与排程，以及通过本地规则体验待确认流程。真实 AI 需要你自己的供应商配置。密钥仅放后端：

```powershell
$env:LLM_API_KEY = '<你的密钥>'
$env:LLM_BASE_URL = 'https://<供应商地址>/v1'
$env:LLM_MODEL = '<支持 JSON 输出的模型 ID>'
```

供应商必须支持 `/chat/completions`、`response_format: {type: json_object}`。响应仍由 Pydantic 二次校验。AI 网络错误或格式错误显示“失败”，可在收件箱重试。

## Android 构建

安装完成后先检查：

```powershell
flutter --version
flutter doctor -v
flutter doctor --android-licenses
```

此仓库没有伪造 Gradle wrapper 二进制；下面脚本会使用已安装 Flutter 的官方模板生成并复制 wrapper。仅在准备构建时运行：

```powershell
.\scripts\bootstrap-android.ps1
cd apps\mobile
flutter analyze --no-fatal-infos
flutter test
flutter build apk --debug
```

`bootstrap-android.ps1` 不覆盖 Flutter/Kotlin 业务源码，只复制 `gradlew`、`gradlew.bat`、`gradle-wrapper.jar` 并执行 `flutter pub get`。Flutter 会生成本机 `local.properties`；不要提交其中的 SDK 绝对路径。

预期生成路径（当前尚不存在）：

```text
apps/mobile/build/app/outputs/flutter-apk/app-debug.apk
```

这是本地测试包。正式发行还需要配置自己的签名、HTTPS 服务、验证目标设备及发行渠道要求。

## 手机连接服务器

- Android 模拟器：App「连接」中填写 `http://10.0.2.2:8000`。
- 真机：电脑与手机同一 Wi-Fi，填写电脑局域网 IP，例如 `http://192.168.1.20:8000`。不要在手机填 `localhost`。
- Windows 防火墙需允许该开发端口在当前私有网络被访问。
- Debug 允许 HTTP 方便本地联调；Release 仅允许 HTTPS。
- 在 App 中注册账户，随后新建任务并查看排程。
- 微信采集：填写与系统通知标题完全一致的群名，保存白名单，授权 Android 通知访问，最后打开采集开关。

部分 Android 系统对侧载 App 的通知访问或后台运行有限制，需要在设备应用设置中处理。权限是否可用以设备为准。微信免打扰、隐藏内容、通知聚合或系统不展示正文时，无法保证获取完整通知。

## 测试命令

```powershell
python scripts\check-source.py
cd services\backend
..\..\.venv\Scripts\python.exe -m pytest tests -q
```

Flutter 测试见上面的 Android 构建步骤。GitHub Actions 文件仅是配置，本次没有推送仓库或触发云端运行。

## 官方参考

- [Flutter Android 构建与发布](https://docs.flutter.dev/deployment/android)
- [Android NotificationListenerService](https://developer.android.com/reference/android/service/notification/NotificationListenerService)
- [OR-Tools CP-SAT 求解状态](https://developers.google.com/optimization/cp/cp_solver)
