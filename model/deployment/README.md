# 模型交付与端侧运行

当前Android使用内置模型，网页暂不接入。手机构建、依赖和验收见 [Android模型嵌入](../../docs/ANDROID_EMBEDDED_MODEL.md)。不需要启动本目录的HTTP服务才能使用手机模型。

`artifacts`包含从核验归档复制的ONNX、特征配置、元数据及SHA256清单。权重约1.31MiB，无需重新训练。`android.py`复用特征编码和主规划器，通过Kotlin回调调用ONNX Runtime Android，不依赖NumPy、Torch或Python版ONNX Runtime。

`planning.py`负责把任务、课表、既有计划和过去反馈映射到规划器；`runtime.py`及`server.py`保留为可选的独立Python服务工具，当前App与Web均不调用它们。

如以后需要单独研究服务，可自行安装 `requirements.txt` 后，在model目录执行 `python -m deployment.server --host 127.0.0.1 --port 8088`，内部接口为 `GET /health`、`POST /plan`。不要向公网裸露开发服务；它不是当前产品的部署前置条件。

真实端侧推理需要完成依赖同步、APK构建和真机验收。本轮Python协议与规划测试使用模拟ONNX输出，不能视为设备推理已成功。
