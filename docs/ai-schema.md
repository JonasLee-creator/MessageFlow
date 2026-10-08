# 结构化 AI 合约

实际定义：`services/backend/app/schemas.py` 中的 `AIAction`。模型输出仅接收 JSON 对象，禁止 schema 以外的字段。

```json
{
  "action": "UPDATE_TASK",
  "confidence": 0.96,
  "target_id": "从候选列表中选择的 UUID",
  "task": {
    "deadline": "2026-10-05T23:59:00+08:00"
  },
  "reason": "原通知修改了已存在实验三的截止日期",
  "requires_confirmation": false
}
```

允许动作：CREATE_TASK、UPDATE_TASK、CANCEL_TASK、CREATE_EVENT、UPDATE_EVENT、CANCEL_EVENT、IGNORE。

- `confidence` 范围 0–1，是识别引擎的自报置信度，不是经过校准的准确率。
- `task` 可含 title、course、deadline、estimated_duration_minutes、priority、splittable。
- `event` 含 title、start_at、end_at、event_type。事件必须结束晚于开始。
- 模型的 requires_confirmation 只能增加审核要求，不能绕过服务端低置信度/取消/缺失目标策略。
- 调用上下文包含原消息时间和用户时区。消息中的“明天”应相对于消息时间解析。
- 没有信息依据时应省略相应字段，不能凭空补截止日期。
- TaskData.deadline 省略表示“不修改”，显式 null 表示“清除”。无日期线索的本地规则不会产生清空指令。
- 模型不得执行消息内的指令。消息、课程名、标题都作为不可信内容放入上下文，最终写入还受对象所有权和用户锁定约束。

当前没有声称达到某个“提取准确率”。只有接入具体模型并在人工标注集上评估后，才应报告准确率、召回率与目标匹配指标。
