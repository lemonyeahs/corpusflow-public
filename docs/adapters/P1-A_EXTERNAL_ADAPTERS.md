# P1-A 外部处理组件评估

## WeKnora/docreader

官方仓库文档描述 docreader 为 gRPC 服务，`Read`/`ReadStream` 接收文件内容或 URL，返回 Markdown、metadata 和可选的 `SourceBlock` 定位；扫描 PDF 会渲染为图片，再交给外部 OCR/VLM 配置处理。当前 CorpusFlow 没有 docreader endpoint、proto client、OCR/VLM 服务或资源配额，因此 P1-A 不把它加入 Compose，也没有生成外部解析指标。

参考：

- https://github.com/Tencent/WeKnora/blob/main/docreader/README.md
- https://github.com/Tencent/WeKnora/blob/main/docreader/proto/docreader.proto
- https://github.com/Tencent/WeKnora/blob/main/website-docs/03-features/03-document-parsing.md

许可证需在引入具体 commit 和依赖闭包后由业务/法务确认，本仓库不基于仓库名推断可商用范围。

CorpusFlow 已预留 `DocReaderAdapter`。未配置时返回 `ADAPTER_NOT_CONFIGURED`，不会把本地内置解析结果标记为 docreader。

## Data-Juicer

官方文档展示其通过 recipe/CLI 或 Python pipeline 按顺序执行 operator，包含文本清洗、过滤、document exact/MinHash/SimHash dedup 等算子。完整运行通常还涉及其版本锁定、可选模型和 Ray/资源配置。当前锁文件没有 Data-Juicer 依赖，也没有经过许可证、输入输出 schema、资源消耗和结果回归审查，因此不直接嵌入业务模块。

参考：

- https://github.com/datajuicer/data-juicer/blob/main/docs/Operators.md
- https://datajuicer.github.io/data-juicer/en/main/docs/ProcessData.html
- https://github.com/datajuicer/data-juicer/blob/main/LICENSE

CorpusFlow 本轮实现了明确的 `DataJuicerAdapter` 边界。未配置时返回 `ADAPTER_NOT_CONFIGURED`；实际执行使用版本化的内置清洗、精确去重和质量评估算子，并在 NodeRun/Artifact 中记录真实统计。

## 结论

两项外部组件均为 **NOT RUN**，原因是当前开发环境没有完整服务、客户端协议和依赖许可确认。下一步接入必须先提交 commit/tag、许可证、资源预算、输入输出契约和基准回归结果，再启用 adapter。
