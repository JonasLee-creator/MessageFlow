# AI 接口配置

网页使用同源 Node.js API 网关，提供两种模式：官方接口由开发者配置，用户接口由当前使用者自行配置。两者均采用兼容 Chat Completions 的协议，与登录注册接口、Canvas 接口分开。

## 比赛阶段

在 `apps/web` 目录将 `.env.example` 复制为 `.env`，填写：

```dotenv
CHRONOFLOW_STAGE=competition
CHRONOFLOW_OFFICIAL_BASE_URL=https://api.deepseek.com
CHRONOFLOW_OFFICIAL_MODEL=填写服务商实际支持的模型名
CHRONOFLOW_OFFICIAL_API_KEY=填写开发者密钥
CHRONOFLOW_OFFICIAL_ACCESS_CODE=填写随机生成的16至128位ASCII体验码
```

以上占位文字需要替换，不是可用的凭据。不要提交 `.env`。官方接口仅在开发者密钥、模型及有效体验码均配置后启用。体验码使用无空格的可打印 ASCII 字符。

使用 Node.js 20.6 或以上版本执行 `npm start`（读取 `.env`）。如果只执行 `node server.mjs`，须通过进程环境传入上述变量。账号与游客均可在设置中选择官方接口，填写体验码后使用；浏览器看不到开发者的 API Key。

为避免把开发者额度变成开放代理，官方接口要求体验码，并限制默认每分钟 15 次、每日 200 次和最多 2 个并发请求。连接测试也计入次数并可能产生模型费用。额度计数存于进程内，重启会重置；多个实例分别计数，每日按 UTC 切换。公开比赛服务应在入口网关增加共享限流与持久化额度控制，体验码仅发给授权测试者。

## 正式使用阶段

将部署配置改为：

```dotenv
CHRONOFLOW_STAGE=production
```

重启 / 重新部署 Node.js 服务后，服务端强制关闭官方接口。即使浏览器伪造 `mode=official`，也会被拒绝，不会使用开发者密钥。正式部署建议同时移除官方密钥和体验码。

用户进入“设置 → AI 接口 → 用户接口”，填写 HTTPS Base URL、模型名称和自己的 API Key，保存后测试连接。接口地址支持根路径或 `/v1`；也可填写完整 `/chat/completions` 路径。仅支持默认 443 端口、公网域名及非流式 Chat Completions，不自动兼容其他模型协议。

模型地址和名称保存在当前账号的本机偏好中。用户密钥和体验码只保留在当前标签页会话内，退出登录时清除，也可主动清除；不会放进任务 JSON 导出或账号密码记录。用户密钥会经 HTTPS 发送至本站网关，再转发到用户指定的模型服务；网关仅在请求内使用，不持久化或输出密钥。部署环境与反向代理同样不应记录请求正文或认证头。

当前浏览器账号不构成服务器身份认证。官方模式通过独立体验码授权，用户模式仅转发当前请求自带的密钥，绝不回退使用官方密钥。接入云端任务与用户计费前，需要服务端账号、权限和独立额度管理。

## 网页业务接入

录入通知时可选择规则提取或 AI 识别。规则提取仅在本机运行。AI 识别发送通知正文、课程、参考时间、时区和最多 30 项相关未完成任务；返回最多 8 个待确认事项。

新增任务、修改任务与新增日程沿用原来的确认流程。取消、修改日程、无行动内容或不能明确关联的修改，进入“需要手动核对”，不会误建任务或自动修改记录。AI 故障时显示错误，用户可以主动改用规则提取；不会静默切换密钥来源或发送到另一家服务商。

## HTTP 接口

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| GET | `/api/v1/ai/config` | 返回部署阶段、默认模式和官方服务可用状态，不返回密钥与体验码 |
| POST | `/api/v1/ai/test` | 使用所选模式实际验证模型连接 |
| POST | `/api/v1/ai/analyze` | 识别通知，返回需要确认的结构化事项 |
| POST | `/api/v1/ai/mobile/analyze` | App 通知识别，保留原生动作、目标、证据和子任务协议 |
| POST | `/api/v1/ai/mobile/report` | App 今日摘要、风险预测和每周复盘 |

POST 请求需要同源、`Content-Type: application/json`，最大请求体 32 KB。官方模式通过 `X-ChronoFlow-Access-Code` 提交体验码：

```json
{"mode":"official"}
```

用户模式的请求形状如下；示例省略真实密钥：

```json
{"mode":"user","user":{"baseUrl":"https://provider.example/v1","model":"your-model","apiKey":"user-provided-key"}}
```

`analyze` 请求还需 `input`，包括 `text`、`course`、`receivedAt`（带时区）、`timezone` 与 `tasks`。返回 `mode`、`model`、`items`、`requiresConfirmation: true`。所有错误返回 `{"error":{"code":"...","message":"..."}}`，不透传上游原始报错。

App 的 `/mobile/analyze` 使用 `input.notification`、`reference_time`、`timezone`、`context.tasks/events` 等原生字段；`/mobile/report` 使用 `report_type`（DAILY / RISK / WEEKLY）与记录。返回 `content`（规范化 JSON 字符串），供 App 现有解析器使用；原生请求没有浏览器 Origin，仍校验体验码和额度。详细配置见 [Android 接口说明](../../docs/ANDROID_ACCOUNTS_API.md)。

网关限制 HTTPS、拒绝带认证信息的地址和重定向，检查全部 DNS 结果并固定使用已验证的公网 IP，阻止内网 / 回环 / 保留地址访问；上游 DNS 超时 10 秒、HTTP 总时限 45 秒，响应最多 256 KB。模型输出经过动作、候选目标、时间和原文依据校验。

## 部署与验收

同一站点必须同时运行网页和 Node.js 网关。仓库中的 Sites 静态托管清单只覆盖前端文件，不能运行 `server.mjs`；仅上传静态目录时仍可管理任务，但 AI 服务不会连接。应部署 Node.js 服务，或在正式托管平台实现等价的同源网关，使用运行时密钥，不能把官方密钥放进静态构建产物。

生产环境在反向代理 / 托管平台配置 HTTPS；默认只监听 `127.0.0.1`，需要容器对外监听时显式设置 `HOST=0.0.0.0`，同时由部署环境限制访问。反向代理须保留原始 `Host` 头，确保同源校验能匹配浏览器的 `Origin`；网关不自动信任客户端传入的代理地址头。

`npm run check` 包含离线接口检查，使用替代传输，不消耗真实 API 额度。填入真实配置后，可通过设置页的“测试连接”验证实际服务。
