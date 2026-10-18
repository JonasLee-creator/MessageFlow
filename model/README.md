# ChronoFlow-DRP 模型工程

日程效果及Baseline对比代码见 [evaluation/README.md](evaluation/README.md)。新增 `scripts/evaluate_predictor.py` 提供可解释预测指标和训练集统计基线；`evaluation/run_evaluation.py` 提供统一仿真回放、八种规划策略、配对统计和报告导出。不会自动训练或执行全量实验。

这个目录保存 ChronoFlow-DRP 的独立研究与训练代码。它与 Android、网页运行时代码隔离：这里产生训练检查点和部署模型，App/网页只加载导出的 ONNX，不直接加载 `.pt`，也不在用户设备上训练全局模型。

本目录不会自动安装依赖或启动训练。当前数据可先执行审计和`--check-only`适配检查；只有两者通过后才应生成训练视图。

## 结构

```text
model/
  config/base.json                 模型、特征和训练配置
  src/chronoflow_model/
    config.py                      配置读取与校验
    records.py                     训练样本数据契约
    features.py                    跨端一致的字符 n-gram 哈希与数值特征
    network.py                     共享任务编码器、耗时头、执行概率头
    losses.py                      对数正态耗时损失与执行概率损失
    dataset.py                     JSONL 数据集与可变时间槽批处理
    personalization.py             手机端可复现的轻量在线个性化更新
    planning.py                    CVaR、稳定性和 Pareto 评估参考实现
    training.py                    训练循环与检查点保存
    artifacts.py                   部署元数据与文件校验
    relational_adapter.py          多表模拟数据到训练视图的无泄漏适配
  scripts/
    prepare_dataset.py             按用户隔离训练/验证/测试集
    adapt_relational_dataset.py    关联现有多表并生成训练JSONL
    filter_empty_pareto.py         过滤无候选块的空偏好决策并重建校验和
    train.py                       显式启动训练的入口
    evaluate.py                    离线评估入口
    export_onnx.py                 从 `.pt` 导出 ONNX
    validate_export.py             PyTorch/ONNX 输出一致性检查
  tests/                           不需要训练的轻量单元测试
```

## 数据文件

训练输入使用 JSONL，每行是一项任务及其候选执行时间槽。原始通知、聊天记录、Canvas Token、API Key 不应进入训练文件。

```json
{
  "task_id": "task-001",
  "user_id": "anonymous-user-001",
  "title": "完成机器学习实验报告",
  "category": "REPORT",
  "course_id": "anonymous-course-a",
  "difficulty": 4,
  "priority": 8,
  "splittable": true,
  "subtask_count": 4,
  "estimated_minutes": 120,
  "released_at": "2026-10-01T02:00:00Z",
  "observed_at": "2026-10-01T03:00:00Z",
  "earliest_start_at": "2026-10-01T08:00:00Z",
  "deadline_at": "2026-10-04T10:00:00Z",
  "actual_work_minutes": 155,
  "completed_at": "2026-10-03T12:00:00Z",
  "user_state": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
  "slot_samples": [
    {
      "features": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
      "user_state": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
      "outcome": 1
    }
  ]
}
```

`outcome` 为 `1` 表示执行，`0` 表示明确跳过或延后，`null` 表示没有可靠反馈。没有反馈的时间槽不会被当作失败样本。

## 产物边界

训练完成后应保留：

```text
checkpoints/chronoflow_best.pt       可继续训练的主检查点
exports/chronoflow_predictor.onnx    跨端部署模型
exports/feature_config.json          哈希与特征顺序
exports/normalization.json           数值归一化参数
exports/model_metadata.json          版本、指标和文件摘要
```

神经模型只预测耗时分布和时间槽执行概率。课表硬约束、滚动重排、场景采样、CVaR、计划稳定性、Pareto 选择与反事实解释由确定性规划代码完成。

## 以后显式执行的流程

以下命令是完整流程。当前只执行了审计和`--check-only`，没有安装依赖、生成训练视图或启动训练：

```powershell
cd model
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
$env:PYTHONPATH = "src"
python scripts\audit_dataset.py --dataset dataset
python scripts\filter_empty_pareto.py --dataset dataset
python scripts\filter_empty_pareto.py --dataset dataset --apply
python scripts\adapt_relational_dataset.py --dataset dataset --check-only
python scripts\adapt_relational_dataset.py --dataset dataset --output adapted
python scripts\train.py --data adapted --config config\base.json --output checkpoints
python scripts\evaluate.py --data adapted\test.jsonl --checkpoint checkpoints\chronoflow_best.pt --config config\base.json
python scripts\export_onnx.py --checkpoint checkpoints\chronoflow_best.pt --config config\base.json --output exports\chronoflow_predictor.onnx
python scripts\validate_export.py --checkpoint checkpoints\chronoflow_best.pt --onnx exports\chronoflow_predictor.onnx --config config\base.json
```

适配器对`prediction_at < released_at`和“计划生成早于任务发布”执行硬拦截。它还会将语义族留出样本写入独立的`semantic_test.jsonl`，并从train/validation编码器训练视图中排除这些样本。用户留出测试仍使用`test.jsonl`。

正式实验前应固定 Python 和依赖版本，并记录数据版本、随机种子、Git 提交和模型文件 SHA-256。

适配器遵循因果时间规则：任务耗时与执行概率都只读取`prediction_at`之前的用户历史；同日负荷只通过预测时已经存在的“此前负荷”字段进入。`UNKNOWN`执行结果输出为`null`并由损失掩码排除。

# 当前交付：V4 主方法

日程规划统一使用 `evaluation/config_integrated.json`（V4 Integrated，revision 1，原在线更新）。默认比较全部7个baseline，种子11；旧实验入口已移除。训练和部署代码继续保留，收尾不重新训练。

```bash
python -m unittest discover -s tests -v
python evaluation/run_evaluation.py --checkpoint checkpoints/chronoflow_best.pt --split validation --output evaluation/results/v4-validation
python evaluation/run_evaluation.py --checkpoint checkpoints/chronoflow_best.pt --split test --output evaluation/results/v4-test
```

详细指标、数据来源和结论边界见 [评估说明](evaluation/README.md)。完整测试结果继续保存在云端原结果目录；请保留对应manifest、runs和检查点哈希，不能用小规模样例替代正式记录。

