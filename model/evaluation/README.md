# 日程规划评估工程

本工程只在显式执行命令时运行，不安装依赖、不训练、不修改原始数据或检查点。

## 两条评估路径

1. `scripts/evaluate_predictor.py`：使用真实 `.pt` 评估耗时和执行概率，并与仅使用训练集统计量的基线比较。
2. `evaluation/run_evaluation.py`：所有规划器进入同一个离散事件回放环境，比较实际模拟完成结果。输入是 `dataset/scenario_instances.jsonl`，不是 `adapted/test.jsonl`。

当前 `drp_full` 是可执行的有限候选 CVaR 滚动规划参考实现；不是已证明最优的求解器，也没有实现分布鲁棒优化的歧义集合。请勿把参考实现的仿真结果写成真实用户效果或严格 DRO 理论结果。

## 云端命令

在 `/mnt/workspace/MessageFlow/model` 执行。先同步本地新增代码到 GitHub，云端再 `git pull`；本工程不自动推送。

先评估当前检查点：

```bash
python scripts/evaluate_predictor.py \
  --data adapted/test.jsonl --train-data adapted/train.jsonl \
  --checkpoint checkpoints/chronoflow_best.pt \
  --output evaluation/results/predictor-test.json

python scripts/evaluate_predictor.py \
  --data adapted/semantic_test.jsonl --train-data adapted/train.jsonl \
  --checkpoint checkpoints/chronoflow_best.pt \
  --output evaluation/results/predictor-semantic.json
```

小规模检查（明确标记为 DEBUG，不可当正式比赛结果）：

```bash
python evaluation/run_evaluation.py \
  --checkpoint checkpoints/chronoflow_best.pt \
  --output evaluation/results/checkpoint-smoke \
  --limit 5 --seeds 11 --save-traces
```

验证集实验（仅在这里调权重、容量、先验和规划采样数量）：

```bash
python evaluation/run_evaluation.py \
  --split validation --checkpoint checkpoints/chronoflow_best.pt \
  --output evaluation/results/validation-v1
```

锁定配置后，完整测试集、默认五个种子：

```bash
python evaluation/run_evaluation.py \
  --split test --checkpoint checkpoints/chronoflow_best.pt \
  --output evaluation/results/test-v1
```

输出目录必须不存在，防止覆盖已完成的实验。完整回放可能比网络训练更慢，先用 `--limit 5` 测量单场景耗时再估计总耗时。`--save-traces` 会保存全部时间块、反馈和计划快照，完整实验开启后文件数量较多。

不提供 `--checkpoint` 时，仅使用耗时估计、固定方差和执行率先验。报告会标记 `UNTRAINED_PRIOR_REFERENCE`，只能验证评估管道，不能作为已训练模型的实验结果。

## 已实现方法

| 方法 | 耗时 | 概率和偏好 | 目标 |
|---|---|---|---|
| edf | 用户初始估计 | 无 | 截止时间最早优先 |
| priority_edf | 用户初始估计 | 无 | 松弛量/优先级排序 |
| deterministic | 学习P50 | 执行率固定为1 | 单点预测损失 |
| probabilistic | 学习分布 | 全局执行率先验 | 期望损失 |
| global_probability | 学习分布 | 冻结模型概率，无在线更新 | 期望损失 |
| personalized | 学习分布+在线偏差 | 冻结模型概率+因果Beta更新 | 期望损失 |
| risk_aware | 同上 | 同上 | 期望损失+CVaR |
| drp_full | 同上 | 同上 | 期望损失+CVaR+计划扰动 |

所有方法使用相同可行性约束、每日容量、冻结时段、事件触发方式和候选时间网格。概率规划器扫描 P50/P80/P95 与 EDF/Priority 两种顺序；确定性规划器只使用P50。

当前没有精确 Oracle。因此不输出最优遗憾，避免把启发式解称为最优解。`hypervolume3` 提供已测试的三维超体积函数；未构造所有方法公平的参数扫描前沿前，不自动报告该指标。

## 主要指标及口径

| 字段 | 定义 | 方向 |
|---|---|---|
| feasible | 本轮所有计划快照约束违规数是否为0 | ↑ |
| weighted_ontime_rate | 观察窗口内到期任务，按优先级加权按时完成比例 | ↑ |
| completion_rate | 观察窗口内已可获知任务的最终完成率 | ↑ |
| deadline_loss | 1 - weighted_ontime_rate，窗口内无到期任务时为0 | ↓ |
| cvar_deadline_loss | 跨场景和种子的 deadline_loss 最差尾部均值 | ↓ |
| restricted_latency_minutes | 所有任务 min(完成时间,观察末尾)-发布时间，包括未完成任务 | ↓ |
| normalized_restricted_latency | 上项除以每个任务自己的可观察时长 | ↓ |
| first_start_delay_minutes | 首次实际成功工作-发布时间，未开始则取观察末尾 | ↓ |
| censored_fraction | 观察结束仍未完成任务比例 | ↓ |
| unfinished_minutes | 仿真真值总耗时减去保留进度，只供评估器使用 | ↓ |
| completed_tardiness_minutes | 已完成且窗口内到期任务的逾期时间，必须结合删失率解释 | ↓ |
| disruption_minutes | 时间移动、增删块的临近加权成本 | ↓ |
| predicted_cvar_reduction_mean | 同一可见任务集合中新旧计划的预测风险差，仅为诊断 | ↑ |
| planning_seconds_mean/max | 实测规划耗时；不是硬超时上限 | ↓ |

`restricted_latency` 不是 Kaplan–Meier RMST：晚发布任务的随访更短，必须结合归一化版本和删失率解释。没有可靠随访设计前不把它包装成生存分析因果收益。

预测指标包括 MAE、中位绝对误差、sMAPE、NLL、CRPS、P50/P80/P95覆盖率及误差、90%区间宽度、BCE、Brier、AUROC、风险正类Average Precision、未执行召回率、F1和ECE。未知标签被排除。全局中位数、对数正态分布、总体执行率均只从 `--train-data` 计算。

## 仿真和因果边界

- 原始场景中的真实耗时与真实执行概率保存在模拟器的独立 `truth` 中，规划函数只能接收公开 `Task`、已观察进度和历史反馈。
- 各算法使用相同 `SHA256(scenario_id,seed,task_id,minute)` 随机场；改变算法调用顺序不会改变潜在执行结果。
- 只有 `prediction_at` 之后任务才可见；网格离散会把可执行起点向后取整。
- 未来任务不会提前进入计划。课表没有 `known_at`，所以明确假设所有固定课表一开始已知；`class_extend` 只能解释为较拥挤的固定课表，不能声称测到了获知变更后的恢复速度。
- 双跳过压力固定作用于场景起点后120、150分钟；其他场景压力使用现有数据已经物化的耗时、时段概率、课表和紧急任务。
- 每次尝试占用一个时间槽，失败同样占用容量。不可拆任务中断后重新开始；可拆任务保留进度。所有方法遵循同一执行语义。
- 在线Beta概率更新和已完成任务的对数耗时残差更新只使用本次回放过去的反馈。
- 场景没有用户身份，神经网络使用冷启动全零用户状态，执行头使用桶原型特征；实际候选块的完整负荷特征及长期个人状态尚未接入。这是待扩展部分。
- 场景ID按固定哈希划分60/20/20，独立于预测器的用户/语义留出划分。不要把这两种测试混为一谈。

## 输出和统计

每次运行保存：

```text
config.json                 本次实际配置
manifest.json               Git、数据、模型、代码摘要及假设
runs.jsonl                  每个场景/种子/方法的原始指标
summary.csv                 总体、各压力场景、压力等权宏平均
comparisons.json            DRP对各基线的场景聚类配对Bootstrap区间
personalization_lift.json   personalized相对global_probability的差值
report.md                   可查看的主表
traces/                     可选逐任务/事件/执行/快照审计记录
```

重复种子先在场景内部平均，再以场景为单位Bootstrap，避免把重复种子当独立用户。差值始终为 method-baseline：完成率正值更好，损失、延迟、扰动负值更好。区间是探索性95%区间，多个指标未进行显著性多重校正，不自动宣称显著胜出。

`personalization_lift` 比较相同全局预测器和候选规则下开启/关闭在线更新的差值。它反映短期场景内反馈适配收益；场景没有用户身份，所以不能等同于真实用户长期个性化收益。

## 验证

```bash
python -m unittest discover -s tests -v
```

测试覆盖尾部小样本、分位数边界、并列AUROC、未知标签、删失、冻结块删除、未来任务隔离、真值隔离、共同随机数、全部基线可行性和场景聚类统计。

本地只运行小规模功能测试；正式模型和全量实验在云端执行。精确Oracle、真实用户个性化收益、课程变化恢复面积和公平Pareto前沿扫描需要后续数据/求解器支持，当前报告不会输出虚构值。

## V2 规划器优化

V2 通过独立的 `config_v2.json` 启用，默认使用 validation。`config.json` 继续调用V1策略，便于复现策略差异。两者使用同一修正后的回放器，比较必须重跑同一代码版本下的全部Baseline，不能直接拼接此前云端的V1结果。

共同正确性修复：不可拆任务中断后在规划前清除进度，后续时段必须预留完整连续工时。所有Baseline也享有相同修复，避免把模拟器错误制造的优势归给DRP。

V2仅改进DRP-Full的决策：

- 保留EDF初始估计候选和“保留旧计划、填补缺口”的候选；仍由预测评分选择，不查看EDF真实未来结果。
- 时段偏好延迟上限从1440分钟缩减为60分钟，避免为了较高执行概率长时间等待。
- 扫描两种任务顺序、P50/P80/P95、最早执行和偏好执行，以及可拆任务执行缓冲，去除重复计划。
- 预测损失优先反映窗口内到期任务的加权失败，再加入剩余工作和响应延迟。
- 冷启动使用用户估计先验与学习预测的分层混合；完成反馈增加时提高学习预测的权重。混合不是平均两种世界的损失，避免人为压低尾部风险。
- 先筛选主损失距最优不超过 `primary_loss_tolerance` 的候选，再考虑稳定性；防止保留危险旧计划。
- 每个候选执行约束与冻结检查；日志保留候选名称、数量、模型权重和主损失保护信息。

无需重新训练，使用已有 `.pt` 即可验证：

```bash
python evaluation/run_evaluation.py \
  --config evaluation/config_v2.json --split validation \
  --checkpoint checkpoints/chronoflow_best.pt \
  --output evaluation/results/v2-validation-smoke \
  --limit 10 --seeds 11 --save-traces
```

锁定配置之前仅用验证集。验证集未证明收益前，不能承诺V2超过EDF；本地无训练检查点，先验功能测试不能代替云端模型效果测试。候选数量增加也会增加规划耗时，需同时检查延迟和扰动。

## V3：减少无效重排与保守在线更新

当前仅修改代码和运行人工构造的单元测试，不启动任何数据集评估或训练。独立配置为 `config_v3.json`，旧V1/V2入口保留。V3改变策略与在线更新，不修改已训练 `.pt`，也不修改原始数据、已有实验结果或主指标定义。

规划入口 `stable_planner.py`：

- 每次先审查“保留当前计划”和最多影响2个任务的局部修复；局部修复保留其他任务已有安排。
- 局部候选仍有风险、存在未安排任务或新增多项任务时，才考虑全局搜索。全局搜索默认冷却120分钟；尚未过期的紧急截止和不可行输入可以绕过冷却。已经逾期不重复触发紧急绕过。
- 没有新反馈、新任务或紧迫截止时，对无排程容量的重复检查设置复查间隔，减少每个时间槽重新搜索。
- 使用共同预测场景分别计算截止失败期望、截止失败CVaR和总主损失；相对主损失最好的候选，所选方案必须同时满足三个容差，再比较扰动成本。
- 如果保留原计划也满足这些保护条件，且新计划的主损失改善不足门槛，则拒绝低收益重排。
- 冻结、容量与课程约束仍强制检查。上述保护是模型预测下的保护，不能保证实际完成率和风险绝不下降；需在后续授权的验证中确认。

在线更新入口 `online.py`：

- 同一任务、同一时段桶、连续时间槽组成一个执行会话。会话结束后，以成功槽比例计为一个有效观察，避免重复计数；未知或不存在的反馈不更新。
- 先记录预测，反馈到达并结束会话后再更新。全局/个人预测的近期会话均方误差用于回退门控；这是在线诊断，不等同于独立测试证据。
- 默认先验强度20，信任度随有效会话数量增长；证据按7天半衰期衰减。
- 个性化执行概率偏移相对全局值最多0.15。近期个人误差明显更大时，该桶回归全局值；旧误差信息衰减后可以恢复。
- 耗时残差只在任务实际完成后更新，异常残差截断到±log(3)，个人整体耗时偏移限制到±log(1.5)，并使用先验收缩。
- V3中的 personalized/risk_aware/drp_full 使用相同的新在线机制，global_probability关闭个人更新，便于后续比较。冷启动神经用户状态仍为全零，没有假造历史用户信息。

新增诊断输出：`global_searches`、`local_repairs`、`keep_plan_decisions`、`changed_plan_decisions`、`rejected_low_gain_replans`、`affected_tasks_per_decision`、`physical_changed_tasks_per_decision`、`online_sessions`。`replans`依旧表示规划决策次数，包含最终保留旧计划的决策，不等于真正改变计划的次数。

`Movement`原定义保持不变。相邻块编码是否等价，通过实际时间槽占用集合判断，仅供局部范围和新增诊断使用，不会重新定义主扰动指标以美化结果。
