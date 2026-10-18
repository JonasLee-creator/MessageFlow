# 日程规划评估工程

当前唯一主方法为 **V4 Integrated / drp_full**，默认使用 `config_integrated.json`。

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
  --seeds 11 --methods edf priority_edf deterministic probabilistic global_probability personalized risk_aware drp_full \
  --output evaluation/results/v4-validation
```

锁定配置后，完整测试集（显式指定一个种子）：

```bash
python evaluation/run_evaluation.py \
  --split test --checkpoint checkpoints/chronoflow_best.pt \
  --seeds 11 --methods edf priority_edf deterministic probabilistic global_probability personalized risk_aware drp_full \
  --output evaluation/results/v4-test
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

## V4 主方法与验证

保留原版 V4、revision 1、online 1 的决策规则；内部 `improved_planner.py` 是其参考候选搜索，`plan_utils.py` 提供物理占位比较，不是独立历史版本入口。旧版本、Plus、自适应实验配置与专用脚本已移除。运行器拒绝非 V4 配置及旧实验开关。

V4 使用预测耗时/执行概率与初始估计的固定混合、有限候选 CVaR 搜索、局部修复及计划保留；候选筛选与最终复核使用分离样本，复核失败直接采用参考计划。预测检查不保证实际整段执行一定改善。

```bash
python -m unittest discover -s tests -v
```

测试覆盖硬约束、因果输入隔离、冻结承诺、非拆分连续性、独立复核、配对统计和真实表格转换。无需重新训练 `.pt`。整理前后对40个“状态×方法”人工样例比较时间块与诊断，验证 V4 及 baseline 的决策一致。

## 数据来源和实验范围

项目负责人确认主数据的任务文本和实际耗时来自真实测量。各方法的执行过程仍由回放器模拟，执行概率的来源尚需单独说明。原始数据元信息含 simulated 标记，因此不能仅凭文件标记断言所有原始观测都是人工生成，也不能把回放包装成多方法真实用户试验。原始文件和来源证据保留，不在收尾时改写。

收尾以 V4 的原验证/测试划分为主结果。已看过结果的其他真实任务子集不再作为独立确认性证据。已完成子集、执行概率为1的回放曾出现所有方法完成率均为100%，不支持主方法普遍领先；适用边界仍须说明。清理实验文件不改变这个结论。

## 云端清理已退役实验产物

`scripts/clean_retired_evaluations.py` 默认只列出，`--apply` 才删除。仅操作 `evaluation/results` 的已识别旧版本、冒烟、Plus、自适应和第二轮 `real-replay-*` 结果目录；V4 主验证/测试结果、dataset、checkpoint、exports、原始采集表、Git历史不在删除范围。未识别目录保留。

```bash
python scripts/clean_retired_evaluations.py
python scripts/clean_retired_evaluations.py --apply
```
