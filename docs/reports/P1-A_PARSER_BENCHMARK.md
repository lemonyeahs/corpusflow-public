# P1-A Parser Benchmark

执行对象：仓库内合成、合法使用的 `tests/fixtures/p1a`；结果由当前 ParserAdapter 实际运行生成。

- 样本数：9；期望成功：6；实际成功：6
- 预期结果匹配率：100.0%
- 平均处理时间：0.61 ms/文件（本地 Python 进程，不代表生产吞吐）
- 公式保留、表格结构、版面阅读顺序和 OCR 仅对当前内置解析器实际输出计数；未配置外部解析器不填充模拟指标。

| 文件 | 预期 | 实际 | 文本 marker 完整率 | 章节数 | 公式 marker | 表格行 | 定位覆盖率 | ms | 失败类型 |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| plain_text.pdf | success | success | 100.0% | 1 | 0 | 0 | 100.0% | 1.01 | — |
| math_formula.pdf | success | success | 100.0% | 1 | 2 | 0 | 100.0% | 0.33 | — |
| complex_table.pdf | success | success | 100.0% | 1 | 0 | 3 | 100.0% | 0.42 | — |
| two_column.pdf | success | success | 100.0% | 1 | 0 | 0 | 100.0% | 0.42 | — |
| scanned.pdf | SCANNED_PDF_UNSUPPORTED | SCANNED_PDF_UNSUPPORTED | 0.0% | 0 | 0 | 0 | 0.0% | 0.2 | SCANNED_PDF_UNSUPPORTED |
| encrypted.pdf | ENCRYPTED_PDF | ENCRYPTED_PDF | 0.0% | 0 | 0 | 0 | 0.0% | 1.93 | ENCRYPTED_PDF |
| corrupt.pdf | CORRUPT_PDF | CORRUPT_PDF | 0.0% | 0 | 0 | 0 | 0.0% | 0.35 | CORRUPT_PDF |
| technical.html | success | success | 100.0% | 2 | 0 | 0 | 100.0% | 0.43 | — |
| cryptanalysis.html | success | success | 100.0% | 2 | 0 | 0 | 100.0% | 0.39 | — |

## 解读

- 普通文本、公式 marker、技术表格和 HTML 的实际文本层可被内置解析器提取；PDF 定位为页码/行号，HTML 定位为行号。
- 扫描版 PDF、加密 PDF、损坏 PDF 分别得到 `SCANNED_PDF_UNSUPPORTED`、`ENCRYPTED_PDF`、`CORRUPT_PDF`，没有生成成功 DocumentVersion。
- 多栏 PDF 仅能在当前文本层样本中验证页级顺序；没有版面模型或 OCR 的文档不宣称已经解决多栏重排。
