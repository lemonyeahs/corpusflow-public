# P2-Closure 复杂文档真实评测

日期：2026-10-25。结论：多栏阅读顺序与基础表格行提取改善；复杂专业文档高保真 **未通过完整验收**。28 次真实执行，结果与原始文本/结构见 `P2_CLOSURE_PARSER_EVIDENCE.json` 和 `closure_parser_outputs/`。

## 数据与参考

4 份新制 CC0 PDF 是真实几何排版，不是用 Markdown 字符串伪装表格或双栏；另复用真实图片型扫描件、损坏和加密 PDF，共 7 输入。原件位于 `tests/fixtures/closure/`、`tests/fixtures/p2/raster.pdf`、`tests/fixtures/p1a/`。设计参考来自 fixture 作者，**不是独立专家标注，也不是真实领域论文的代表性样本**。PDF 已渲染检查；本机预览留在 `.local/closure/render/`。

| 新文件 | 字节数 | SHA-256 |
|---|---:|---|
| columns.pdf | 1724 | `be765a6e43c686dc5553297b37f5a94d82190ed3a92ad770f4e69232a286ed04` |
| table.pdf | 1677 | `b55907c9f6d3e75d30e4aaccf5fe7e8b29906009eb0917e0a569726a567bfaf5` |
| formula.pdf | 1627 | `d9fca0b1eefd813f03808cfabb167a4e0e282c7960f0d98166b4f437f09cc6e4` |
| figure.pdf | 3553 | `b337ad88b305c6d16b405948bb73f16247b8a1587b615b89d7f0610b9d1abde5` |

生成脚本 `scripts/build_closure_fixtures.py` 使用 ReportLab 4.4.9/Pillow；测试读取已提交 PDF，不需要生成器依赖。columns 含交错写入 PDF 内容流的双栏；table 含真实格线、三行三列与合并表头；formula 含上标和分式；figure 含原创嵌入图像及图注。参考和所有旧输入 SHA 均记录在证据 JSON。

## 实测结果

| 解析器 | 7 输入中取得文本 | 多栏成对顺序 | 结构化表格行 | 公式词项 | 扫描件 CER | 7 输入平均耗时 |
|---|---:|---:|---:|---:|---|---:|
| builtin | 4/7 | 12/15 | 0/3 | 7/7 | 不适用/未提取文字 | 1.51 ms |
| ocr | 5/7 | 12/15 | 0/3 | 2/7 | 0.0 | 317.68 ms |
| layout | 4/7 | 15/15 | 3/3 | 7/7 | 不适用/未提取文字 | 20.52 ms |
| docreader-builtin | 4/7 | 12/15 | 0/3 | 7/7 | 不适用/未提取文字 | 257.33 ms |

“取得文本”不等于高质量解析。7 输入包含两个应拒绝的文件，故该分数不能用作成功率排名。耗时为单轮墙钟值，包含失败和外部容器调用开销，不是吞吐 SLA；主机 Poppler 26.03.0，Docker Worker 25.03.0，不能混为同一性能环境。

指标口径：阅读顺序为 6 标记的 15 个有序对；缺失也记不匹配。表格为 3 条参考行的完整单元格匹配，不计算合并格拓扑。公式为 7 词项子串保留，不验证上下标/分子分母关系。OCR CER 为参考字符的编辑距离比例（统一小写、合并空白）；0 只对应这一张清晰英文图片。没有中文、低清扫描、手写或复杂数学 OCR 的有效结论。

版面适配器 4/4 原生页识别作者参考标题；结构化定位覆盖 columns 7/7、table 9/9、formula 5/5、figure 2/2 片段，均含页码和 PDF 点坐标 bbox。它们是定位字段存在率，不是人工框选精度。旧解析器/OCR 有页级 section；OCR 另有词坐标。docreader 本次返回无可映射页码的 Markdown，定位分母 0，不能记为 100%。

## 实现与实际平台验证

`LayoutParserAdapter` 经既有 ParserAdapter 接入，配置 `parser=layout`；真实 `pdftotext -bbox-layout`，独立双栏排序、字号/编号标题启发式、横向空隙表格行启发式。保留 bbox、页码、引擎版本；输入 20 MiB、1–10 页、子进程 30 秒、输出 8 MiB 上限。Worker 读取 MinIO 原件，保存 Markdown/JSON、Run/NodeRun、DocumentVersion 和 Segment，配置与产物沿用既有版本和幂等机制。

`scripts/verify_closure_layout.py` 及真实 Playwright 验证 Docker 的多栏 PDF 上传、异步处理、片段文字/坐标、冻结解析器配置、重复消息无新文档版本；Web 显示真实 parser_name/version。没有自动把旧任务改成新解析器，也不覆盖旧版本。

外部比较实际调用正在运行的 WeKnora docreader gRPC Read，显式选 builtin，引擎/协议已检查；镜像 ID `sha256:59e26f98f17c296c5f4bd216404558f51d31991b580cfef1d204903a01e4b46b`。没有调用 Go 侧 OCR/VLM 或付费模型。扫描件只得到图片引用，标为 IMAGE_ONLY；不是 OCR 成功。此处是实测组件比较，**未把 docreader 接入主平台 ParserAdapter 或交付它的可复现部署**。

## 保留的失败与下一步

- 四个解析器均拒绝损坏和加密输入。内置/版面解析器拒绝扫描件；OCR 提取真实英文文字。docreader 扫描件为 IMAGE_ONLY。错误原文保留。
- 布局解析的合并表头拓扑 NOT_EVALUATED；输出 `grid_verified=false`。只能提取当前对齐行，不能宣称复杂跨行跨列表格完整。
- 所有公式二维语义 NOT_EVALUATED。OCR 词项仅 2/7，明确劣于数字文本；不应无条件对原生数学 PDF 使用 OCR。
- 图像语义 NOT_EVALUATED；docreader 未保留参考图注完整词项。没有图片理解模型结果。
- 多栏启发式仅适用于当前几何约束，复杂脚注、跨栏图表、混合阅读方向、标题穿插尚未建立人工参考；不得推断整篇密码学论文正确。
- 需要许可明确的真实领域文档和独立专家参考，逐页评测；专业表格/数学结构可评估专用模型或 WeKnora Go 侧 OCR，但须独立许可、运行依赖及调用预算确认。本轮停止在现有边界。
