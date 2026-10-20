# 技术方案配图来源

正式图片位于 [../figures](../figures)，技术方案见 [HTML](../AIC-技术方案.html) 和 [PDF](../时序-技术方案.pdf)。本目录保留统一重绘使用的提示词、历史回放主表、可编辑 SVG、图表脚本与校验记录。

- `提示词与制作方式.md`：7 张概念图的生成与精修记录；其中“未改写 HTML/PDF”描述当时重绘操作，现已将成稿及图片一并归档。
- `历史回放主表.csv`：既有 350 场景、种子 11 的历史回放数据，不代表真人试用或当前 APK 的收益；本次未重新运行实验。
- `build_redrawn_evaluation_chart.py`：使用 Matplotlib、NumPy 和 Windows 微软雅黑重绘图 10；输出到 `docs/figures`，CSV 与 SVG 输出到本目录。
- `文件校验.json`：相对于 `docs/` 的图片路径及重绘时 SHA256。

`docs/attachments/` 保存技术方案引用的代码、模型元数据与测试记录快照。当前可执行实现以仓库 `apps/` 和 `model/` 为准。
