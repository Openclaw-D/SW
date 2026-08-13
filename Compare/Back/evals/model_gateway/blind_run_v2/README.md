# P5-BlindEval-R2

隔离盲测产物，仅基于固定 manifest、image/PDF/Excel 原件、受控 SceneSpec、v2 prompt 与正式 schema 生成。未读取第一轮产物、答案、评分报告、rubric、guidance、hidden truth、Front 或 `tests/evals`。

## 边界

- `generatedBy=codex_isolated_blind_eval_v2`
- `isSimulated=true`、`advisoryOnly=true`、`notAProviderCall=true`
- `FactVersionWrites=0`
- 三个计分 case：image、PDF、Excel；SceneSpec 仅作为 image case 的声明式受控关联输入。
- `inputHash` 使用对应原件的 manifest SHA-256，保持 request/result 绑定且不引入答案标签。
- 所有候选仍为 `candidate`，所有不确定项均要求人工核验并绑定 anchor。

## 定位策略

- image：精确复用 manifest 的 `focalArea={x:0.18,y:0.2,width:0.64,height:0.58}`；只输出“机床类设备”，不从外观、文件名或说明文字推定子类型、厂商、型号、铭牌。
- PDF：第 1 页逐字段使用归一化 bbox；验证脚本以正式 SourceAnchor schema 检查边界。人工查看时可用同字段原文作 text anchor。
- Excel：使用 `生产记录` 的精确单元格与范围，候选仅取第 78 行单元格，不将时间序列外推为经营结论。

## 本地执行说明

PDF 首选的内置 `pdftoppm` 固定路径不可用，随后使用已存在的 bundled `pypdfium2` 完成单页渲染，并以 `pdfplumber` 提取逐词 bbox。该事件是本地渲染器发现错误，不是 provider 调用错误，因此没有增加 `attemptCount` 或 `retryCount`。

验证命令（从 `Compare/Back` 运行）：

```powershell
..\..\Back\.venv\Scripts\python.exe evals\model_gateway\blind_run_v2\validate_blind_run.py
```

如项目虚拟环境不可用，可使用本机已有且安装了项目 Pydantic 依赖的 Python；禁止为本盲测安装依赖。

本目录不作通过/不通过自评；`run_metrics.json` 仅记录执行事实、耗时、尝试次数、停止原因与本地错误。
