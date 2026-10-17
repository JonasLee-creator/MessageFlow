# ChronoFlow-DRP v1.3 数据修改建议

> v1.3复查：因果时间、固定区间、被支配候选、未选方案标签和实际执行字段均已修复；两条空Pareto决策已经过滤，审计状态为PASS。剩余内容属于后续数据增强建议。

当前版本已经补齐固定日程、计划快照、语义族留出、显式观察掩码和完整场景样例。下一版应优先修正生成逻辑，而不是继续增加字段。

## P0：训练前必须修复

### 1. 统一事件时间轴

先生成任务发布事件，再允许模型预测和规划：

```text
released_at <= prediction_at <= plan_generated_at <= planned_start
```

推荐生成顺序：

1. 在模拟时钟`t`发布任务并写入`released_at=t`。
2. 在`t`或`t+少量处理延迟`构造特征，写入`prediction_at`。
3. 求解候选日程，写入`plan_generated_at`。
4. 到实际时间后才生成执行结果和完成标签。

所有滚动统计都必须以`prediction_at`为截断点。生成器中加入断言，只要一条记录违反便停止写文件。

### 2. 真正生成三个不同的候选计划

compact、balanced、steady需要分别运行不同权重或风险参数的规划器，并保存各自的完整块：

```json
{
  "plan_id": "balanced",
  "blocks": [
    {"task_id": "t1", "start": "...", "end": "..."}
  ],
  "metrics": {"deadline_risk": 0.12, "free_minutes": 180}
}
```

不要让三个候选共用同一组`block_ids`。计算完指标后执行非支配过滤；如果少于3个非支配解，应继续改变权重搜索，而不是保留被支配解。

### 3. 将固定区间作为硬约束

规划前先计算：

```text
available_intervals = horizon - fixed_intervals - frozen_blocks
```

任何候选块必须满足：

```text
block.end <= fixed.start OR block.start >= fixed.end
```

生成快照前再次断言重叠数为0。课表、会议、睡眠都应执行相同检查。

### 4. 提交生成器

把`evaluation/generate_drp_sim_v1.py`放入`model/evaluation/`，同时记录：

```text
generator_git_commit
generator_config_sha256
source_schema_version
seed
```

增加一个复现测试：随机抽取至少20个`scenario_id`，用seed展开并与`scenario_instances.jsonl`逐字段比较。

### 5. 修复字段契约

- `fixed_intervals`补`data_role=simulation_only`。
- `fixed_intervals`补`known_at`，临时事件必须满足`known_at <= plan_generated_at`才可进入计划特征。
- `UNKNOWN`的`label_executed`和`label_failed_feedback`改为`null`。
- 明确`schedule_version`语义；若块记录创建版本，字段改为`created_in_schedule_version`。
- 将“拒绝并恢复”和“接受后撤销”拆成不同事件类型。

## P1：让实验能证明模型创新点

### 用户个性化

模拟用户参数应随时间缓慢漂移，并为每个用户保留冷启动段、在线适应段和评价段。报告个性化前后：完成率、Brier score、耗时NLL、计划接受率。

### 任务发布到完成

保留`release_to_first_start_minutes`、`release_to_completion_minutes`和删失标记。除了平均时间，使用生存分析指标（C-index、IBS）评估“发布后多久开始/完成”。

### 风险与滚动重排

每个场景保存任务到达、真实耗时、执行结果、固定事件变化和旧计划。比较EDF、确定性规划、概率规划、个性化规划、完整DRP的截止完成率、CVaR、regret和扰动成本。

### 三种互补测试

- 用户留出：评价未见用户。
- 语义族留出：评价未见任务表达；当前29族划分可保留。
- 时间滚动留出：同一用户只用过去更新，评价未来。

## P2：提高仿真真实性

- 保留无截止任务，并增加截止后来补充、延期、取消和依赖任务。
- 模拟考试周、课程临时调整、连续跳过和耗时突增。
- 对缺失反馈、延迟补录和误触完成单独加噪声类型，不与真实失败混合。
- 增加不同用户的风险偏好、稳定性偏好、时段效率和疲劳恢复差异。

## 数据使用边界

- 仿真数据可用于联调、压力测试、Oracle regret和消融管线。
- 不能把仿真结果写成真人用户效果。
- 正式个性化结论需要授权真实数据或明确标注为仿真实验。
- 原始通知、聊天内容、Canvas Token和API Key不得进入训练文件。
