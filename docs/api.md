# API

根路径 `/api/v1`。除注册、登录与根路径 `/health` 外，所有请求使用 `Authorization: Bearer <token>`。日期使用 RFC 3339 带时区格式。服务启动后以 `/docs` 的 OpenAPI 为字段级依据。

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/auth/register`, `/auth/login` | 返回 access_token |
| GET / POST | `/tasks` | 列表 / 新建任务 |
| PUT / DELETE | `/tasks/{id}` | 完整编辑 / 取消任务 |
| POST | `/tasks/{id}/complete` | 完成任务 |
| GET | `/tasks/{id}/sources` | 关联原始通知 |
| GET / POST | `/events` | 固定日程列表 / 新建 |
| PUT / DELETE | `/events/{id}` | 编辑 / 取消固定日程 |
| POST | `/ingest`, `/ingest/notification` | 摄取并处理自然语言 |
| GET | `/inbox` | 最近 200 条 raw + decision + engine |
| POST | `/inbox/{id}/review` | 确认（可纠正字段）或忽略 |
| POST | `/inbox/{id}/retry` | 重试失败识别 |
| GET | `/schedule` | 当前时间块、版本、求解状态、风险 |
| POST | `/schedule/replan` | 主动重排 |
| GET | `/schedule/versions` | 最近 30 个版本与快照 |
| PUT | `/schedule/blocks/{id}/lock` | 锁定 / 解锁并重排 |
| GET | `/connectors` | Canvas 接入状态，不返回令牌 |
| POST | `/connectors/canvas` | 新建或更新学校访问令牌 |
| POST | `/connectors/{id}/sync` | 手动同步 |
| DELETE | `/connectors/{id}` | 停用并清除服务端令牌 |
| GET | `/courses` | Canvas 课程列表 |

摄取示例：

```json
{
  "platform": "wechat",
  "source_type": "notification",
  "external_id": "stable-device-message-hash",
  "channel_name": "计算机网络",
  "title": "计算机网络",
  "content": "实验三延期到下周一提交",
  "source_updated_at": "2026-10-03T20:30:00+08:00"
}
```

`platform=canvas` 与 assignment/announcement 只接受后端受信连接器，不允许客户端伪装成结构化 Canvas 来源。

确认示例（使用原建议）：

```json
{"accept": true}
```

确认并纠正目标或日期：

```json
{
  "accept": true,
  "decision": {
    "action": "UPDATE_TASK",
    "confidence": 0.96,
    "target_id": "existing-task-uuid",
    "task": {"deadline": "2026-10-05T23:59:00+08:00"},
    "reason": "用户核对后的截止时间",
    "requires_confirmation": false
  }
}
```

任务 update 中缺少 deadline 表示保持原值，显式 `deadline: null` 表示清除（除非任务 deadline_locked）。`UPDATE_EVENT` 必须提供完整 `event`（title/start_at/end_at/event_type）。取消动作只需要目标，无需 payload。

主要错误码：401 登录无效；404 不存在或不属于本人；409 重复账户/已处理确认；422 校验失败。识别失败仍保留 raw 并返回 `status=failed`；Canvas 外部故障返回 `error` 字段，客户端必须显示而不能假报同步成功。
