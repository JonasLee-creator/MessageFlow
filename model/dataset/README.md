# ChronoFlow-DRP 模拟数据（schema `drp-sim-v1.3`）

> **全部为程序模拟数据。**  
> **仅允许：** 联调、压力测试、消融实验管线。  
> **不允许：** 写成真人试用或正式用户结论。

## v1.3 相对上一轮评审的修复

| 问题 | 结果（见 `splits.json` → `qa`） |
| --- | --- |
| 用 `is_pareto_member=true` 掩盖被支配方案 | 已删除该逻辑。三个方案的五项指标固定成交替最优，`dominates()` 独立复查：`pareto_groups_with_dominated_candidate=0`，`pareto_dominated_candidates=0` |
| 未选中候选块带有执行标签 | 未选块 `outcome`、实际时间、执行标签均为空，`supervision_role=counterfactual_not_for_execution_training`。`counterfactual_blocks_with_execution_labels=0` |
| 已执行块实际时间不完整 | 选中且结果为完成 / 部分完成 / 推迟时，`actual_start`、`actual_end`、`actual_minutes` 同时存在。跳过与未知不带实际时间。两项不完整计数均为 0 |
| 非空三方案时间块完全相同 | `pareto_identical_block_sets=0`。另有 `pareto_empty_candidate_groups`：当天没有可排任务，三个候选都是空列表 |

未选中块不能当作执行监督。只有 `selected_in_snapshot=true` 且 `supervision_role=observed` 的块可以用于执行结果训练。

### `schedule_version` 含义

每个用户单调递增的**计划世代（plan epoch）**。  
同一次规划决策生成的快照、三个 Pareto 候选的全部时间块，共享同一 `schedule_version`。  
未选中的候选块：`selected_in_snapshot=false`。  
后续重排：`schedule_version_before` / `schedule_version_after`。

### 生成器位置（可复现场景）

1. `evaluation/generate_drp_sim_v1.py`（主路径）  
2. `evaluation/data/drp-sim-v1/generate_drp_sim_v1.py`（随数据包）  
3. `model/evaluation/generate_drp_sim_v1.py`（队友约定路径）

```python
from generate_drp_sim_v1 import expand_scenario
expand_scenario(seed, stress_type, horizon_days, n_tasks)
```

## 文件清单

| 文件 | 说明 |
| --- | --- |
| `users.jsonl` | 用户划分 |
| `tasks.jsonl` | 任务；`prediction_at >= released_at` |
| `duration_labels.jsonl` | 耗时标签 |
| `blocks.jsonl` | 含三方案候选块；看 `plan_id` / `selected_in_snapshot` |
| `fixed_intervals.jsonl` | 课表/会议/睡眠；均有 `data_role` |
| `plan_snapshots.jsonl` | 完整快照 + `candidate_block_ids_by_plan` |
| `pareto_choices.jsonl` | 完整候选指标与 block_ids |
| `user_days.jsonl` / `release_completion.jsonl` / `replans.jsonl` | 状态与稳定性 |
| `scenarios.jsonl` / `scenario_instances.jsonl` | 场景头 + 前 2000 完整实例 |
| `splits.json` | 划分、QA、用途限制 |
| `generate_drp_sim_v1.py` | 生成器副本 |
| `SHA256SUMS.txt` | 校验 |

## 重新生成

```powershell
python evaluation/generate_drp_sim_v1.py
```
