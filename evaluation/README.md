# ChronoFlow 评测数据（synthetic-v1）

这批数据由 `generate_dataset.py` 按固定模板生成，用来检查数据格式、场景配额和后续评测脚本。

它不是学生授权的真实通知，没有做过双人标注，也不能代替 15 人、14 天试用。字段 `provenance` 固定为 `synthetic`，`adjudicated` 为 `false`。报告里必须写明这一点。

## 数量

| 集合 | 文件 | 条数 |
|---|---|---:|
| 开发集 | `data/development/development-v1.jsonl` | 400 |
| 封闭测试输入 | `data/sealed-test/sealed-test-input.jsonl` | 100 |
| 封闭测试金标准 | `data/sealed-test/sealed-test-gold.jsonl` | 100 |

开发集含金标准。测试输入不含 `gold`。正式跑三组实验前，只把输入文件给实现；三组都跑完再打开金标准。

SHA-256 见 `reports/dataset-hashes.txt`。

## 场景

开发集：新建任务 90，延期/修改/取消 70，日程 60，多事项 50，歧义 50，无关 50，困难样本 30。

测试集：新建 25，修改或取消 15，日程 15，多事项 15，模糊 15，无关 15。

来源按整集配平：微信 45%，QQ 30%，Canvas 15%，手工 10%。课程和群名使用 `<COURSE_DEV_xx>`、`<GROUP_TEST_xx>` 这类占位符。开发集和测试集的标题、课程、群、日期起点都分开，避免同一句改写同时出现在两边。

## 重新生成

```text
python evaluation/generate_dataset.py
```

生成后哈希会变。已经用这批结果做实验之后，不要再改模板。

`data/raw-private/` 只放以后收集的原始通知，不提交 Git。
