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

## 独立开关和受控消融入口

三个布尔配置项现在同时支持V2和V3：

| JSON配置 | 命令行覆盖 |
|---|---|
| enable_local_repair | --local-repair on/off |
| enable_replan_cooldown | --replan-cooldown on/off |
| enable_low_gain_rejection | --low-gain-rejection on/off |

V2缺省均为关闭，V3缺省均为开启。关闭开关不会关闭课程、冻结或每日容量约束。V2的局部修复开关增加“保留”和局部补排候选，仍使用原V2评分与主损失保护；V3继续采用自身的分阶段搜索和双风险保护，因此不要把V3关掉开关后的结果直接称为原V2。

`scripts/run_planner_ablations.py` 从同一份V2配置生成受控实验，全部固定 `planner_version=2, online_version=1`。不开启开关的 reference 与原V2决策逻辑一致，单元测试检查了这一点。

默认阶梯：reference → local_only → local_cooldown → combined。
可额外选择 cooldown_only、rejection_only，区分单独效应与组合交互。

仅生成配置（不会评估，更不会训练）：

```bash
python scripts/run_planner_ablations.py --output evaluation/results/control-configs-v1
```

显式运行小规模验证对比，使用新的输出目录：

```bash
python scripts/run_planner_ablations.py \
  --checkpoint checkpoints/chronoflow_best.pt \
  --output evaluation/results/v2-controls-smoke \
  --limit 10 --seeds 11 --run
```

脚本串行执行四组，只评估 drp_full，不重复运行EDF等已固定基线。所有组使用相同检查点、评分权重、验证场景和种子；输出 experiment.json、configs/、各组的完整报告以及 comparison.csv、comparison.md。遇到错误或中断即停止，保留已完成结果。

若只想测试单独机制，增加：

```text
--cases reference local_only cooldown_only rejection_only
```

这些是规划策略消融，不需要重新训练神经网络。所有评估默认只用10个验证场景，不代表正式结论。

## 统一修复入口：config_integrated.json

该配置选择 `integrated_planner.py`，内部版本号4。保持原V2、V3和已有结果，不更改训练模型。默认使用旧在线更新，因为现有验证没有证明新更新能稳定改善结果。它不是对此前三个限制同时打开，而是重新统一其接受规则。

每个需要规划的决策先计算相同状态下的原V2参考计划，原V2权重、候选生成和在线历史保持一致。然后尝试保留旧计划，并依据事件影响、任务松弛时间与参考计划的冲突范围，按1、2、4、全部任务逐步扩大修复范围。局部大小不再固定为2。

所有候选必须通过相同硬约束检查，并相对V2参考计划分别检查：加权完成损失、加权截止失败期望、截止失败CVaR、归一化响应延迟。默认允许恶化量为0。均值差使用配对预测样本和近似置信裕量；尾部使用样本CVaR。这是预测模型下的筛选，不是实际性能保证，也不是严格有限样本统计证明。

冷却只在旧计划通过保护检查时发挥保留作用，不能否决必要修复。低收益拒绝同样只允许保留通过保护的旧计划。始终保留V2参考作为回退路径，避免为了稳定性选择明显较差的预测计划。

候选筛选的采样编号与V2搜索采样编号分离。冻结最终候选后，再使用第三组预测样本复核；如果不通过，直接回退V2，不在复核样本上再次搜索其他方案。

注意：这里的V2参考只是在当前策略已经形成的状态上计算的计划，不等同于另一个从起点独立执行的完整V2策略。因此，即使每次预测保护都通过，最终真实完成率仍可能下降，需要独立配对验证。本次代码修改仅做人工夹具单元测试，没有重跑数据集或根据10个样例调参。

统一配置需要每次计算V2参考并额外采样，不能承诺运行更快。它首先解决决策逻辑一致性和风险保护问题。诊断新增 `reference_plan_selections`、`expanded_repairs`、`verification_fallbacks`，事件记录保留尝试过的修复范围、参考与候选的保护指标。

后续显式评估只需一个入口，无需重新训练 `.pt`：

```bash
python evaluation/run_evaluation.py \
  --config evaluation/config_integrated.json \
  --checkpoint checkpoints/chronoflow_best.pt \
  --split validation --limit 10 --seeds 11 \
  --output evaluation/results/integrated-smoke --save-traces
```

## 优化器细节修订：config_integrated_plus.json

新配置保持原统一版权重、采样数、旧在线更新和三组采样保护，仅设置 `optimizer_revision=2`。旧配置仍可运行；本轮只执行人工夹具单元测试，没有读取验证结果调参或启动数据集评估。

修订内容：

1. 候选工时按 `T > 已执行工作量` 的条件分布生成，避免超时后反复只补一个槽；历史工作量不会再次加到总耗时上。
2. 优先生成保留所有既有预约的补排候选，以及仅裁剪未冻结、可拆任务尾部多余预约的候选。不移动或裁剪正在执行、冻结或不可拆任务。
3. 执行缓冲只按任务实际允许的未来时间窗口、工作时段、固定课程和剩余容量估计；不把不可工作的夜间概率直接平均进去。
4. 紧迫度考虑最早可开始时间与条件剩余耗时，避免把尚未允许开始的任务误判为有大量可用时间。
5. 候选评分预先按任务整理时间块；回归测试确认与未缓存的逐样本计算完全相同。
6. 存在通过检查、且不产生扰动的候选时，避免继续扩大修复搜索；最终独立复核和V2回退仍保留。

共同正确性检查也已统一：正在执行的块属于冻结承诺；约束审查考虑当天已使用容量、观察窗口、工作时段及未知任务ID；嵌套时间块重叠不能漏检。预测指标对长度不匹配、NaN或非法参数明确报错，不再悄悄丢弃样本；配对统计先对齐“场景+种子”，拒绝重复记录，再进行场景聚类Bootstrap。

这些共同修正应用到所有方法，扰动成本和主要指标的数值定义没有修改。回放版本号更新为 `constraint-audited-3`；旧结果继续保留，但正式对比应在同一版本下重跑参考方法，不拼接不同回放版本的结果。

初步配对检查建议两组各20个场景、同一种子，只运行drp_full：

```bash
python evaluation/run_evaluation.py \
  --config evaluation/config_integrated.json \
  --checkpoint checkpoints/chronoflow_best.pt \
  --split validation --methods drp_full --limit 20 --seeds 11 \
  --output evaluation/results/integrated-audit20

python evaluation/run_evaluation.py \
  --config evaluation/config_integrated_plus.json \
  --checkpoint checkpoints/chronoflow_best.pt \
  --split validation --methods drp_full --limit 20 --seeds 11 \
  --output evaluation/results/integrated-plus-audit20
```

不能预先保证这些修正会改善所有指标；新候选的实际收益与评分缓存的耗时收益都需后续测量。检查点和原始数据无需重新生成。

## V5：简单候选与复杂度自适应选择（实验入口）

`config_adaptive.json` 使用 `planner_version=5`，原版 `config_integrated.json` 保持不变，**不采用已出现退步的plus修订**。不改变预测网络、训练检查点、在线更新或baseline算法。

候选包括原EDF、Priority EDF、确定性规划、两个无偏好延迟的P80缓冲候选及可行旧计划。全部候选遵守同一固定安排、工作时间、每日容量、正在执行及冻结承诺。缓冲候选使用DRP已经获得的预测，不获得额外真实标签。

路由仅使用当前已知任务和历史反馈：截止前P80预测需求与可用容量之比、单任务可执行窗口的容量余量、可用时段执行概率及其波动。每日容量不会被贪心地预分给上午，最早可开始时间和其他任务的冻结占位都会限制个体窗口。这只是容量筛查，不是可调度性证明，也不能看到未来任务、真实耗时或模拟执行概率。

- 宽松状态：简单候选在筛选样本上满足预设绝对风险上限后，按预测等待成本加扰动成本选择；小收益保留旧计划。另组样本复核通过后可跳过原版完整搜索。
- 高压状态或低压复核失败：计算原版Integrated参考，仅允许通过配对完成率/截止损失/尾部风险/等待保护的简单候选参与竞争；最终复核失败回退原版。若原版也无法排全任务，保持原版行为，不伪造完整覆盖。
- 原版内部采样编号为0至3N-1，自适应候选筛选使用3N至4N-1，最终复核使用4N至5N-1。复核失败不在该组样本上再选另一个简单候选。

新增汇总诊断：`adaptive_low_complexity_decisions`、`adaptive_complex_reference_calls`、`adaptive_simple_selections`、`adaptive_verification_fallbacks`。事件轨迹另含具体复杂度特征与候选名称。高压场景额外生成和审查候选可能更慢，不能预先宣称整体加速；预测样本保护不等于真实整段执行收益保证。

### 仅在原仿真验证集确定门槛

```bash
python scripts/validate_adaptive_planner.py \
  --checkpoint checkpoints/chronoflow_best.pt \
  --limit 20 --seeds 11 --run \
  --output evaluation/results/adaptive-validation20

cat evaluation/results/adaptive-validation20/comparison.md
cat evaluation/results/adaptive-validation20/selection.json
```

脚本只读取 `dataset/scenario_instances.jsonl` 的validation划分，不提供真实数据或test入口，且拒绝真实回放数据替换。固定比较三组：原版、保守门槛（负荷≤0.25、余量≥240分钟）、均衡门槛（负荷≤0.40、余量≥180分钟）。其他权重、检查点、场景和种子相同；每组仅运行drp_full，因此20场景共60次回放。去掉 `--run` 仅生成配置，`--limit 0` 使用完整原验证集。所有目录必须新建。

所有组完成后检查场景与种子精确配对。候选只有在验证集聚合WOTCR不降低、CVaR不升高、等待不增加且约束满足率100%时才能入选；否则输出原版。合格方案按完成率、CVaR、等待、扰动依次排序，完全相同则优先原版。生成 `frozen_config.json`、对比表、选择记录及数据/检查点哈希。这个规则是描述性验证集选择，不是显著性证明；小子集结果只能用于初筛。

在同一原验证集上扩大到50或完整规模时，创建新输出目录，不能把多次调参结果当成独立测试证据。冻结后对新收集、未用于开发的数据测试：

```bash
python evaluation/run_evaluation.py \
  --dataset real_data/converted-new-independent \
  --config evaluation/results/adaptive-validation20/frozen_config.json \
  --checkpoint checkpoints/chronoflow_best.pt \
  --split all --seeds 11 \
  --methods edf priority_edf deterministic probabilistic global_probability personalized risk_aware drp_full \
  --output evaluation/results/adaptive-new-independent
```

不要再用已经看过结果的20人真实数据选择门槛。新数据若仍为已完成子集且执行概率为假设值，仍须如实说明其选择偏差和回放性质。不得承诺V5所有指标最优，也无需重新训练`.pt`。
