# P5-BlindEval-R3

本目录只包含隔离模型的原始语义产物，不是后端 `ModelGatewayOutput`，也不是 Provider/Gateway 调用记录。

- `raw_provider_results.json`：image、PDF、Excel 三个直接语义结果；SceneSpec 仅作为 image result 的受控声明式关联。
- `run_metrics.json`：逐 case 计时、重试计数、停止信息与零权威写入声明。
- 未计算或复制 gateway 管理的 `inputHash`，因此 raw 结果不含该字段；后续若需正式契约绑定，应由 gateway 使用原始请求完成。
- 错误读取的 registry PDF 与完整数据 Excel 已登记为不可重试的本地输入选择错误，未用于结果。
- PDF 文本层解析获得精确页码、字段文本和 bbox；本地 raster preview 命令未产出图片，未将该本地错误伪装成 provider 重试。
- 输出未包含 score、decision、hard gate、approval、FactVersion 或权威状态写入，也不提供 PASS 自评。
