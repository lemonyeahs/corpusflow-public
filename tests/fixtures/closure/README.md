# 复杂版面测试资料

四份新 PDF 由仓库脚本 `scripts/build_closure_fixtures.py` 原创生成，按 CC0 提供测试使用。
`reference.json` 保存原件 SHA-256、字节数、作者设计的参考顺序、标题、单元格行和公式字符。
参考值由构造规范确定并经过渲染检查，不是独立人工专家标注，不据此宣称专业论文高保真。

- columns.pdf：真正左右两栏，PDF 内容流刻意逐行交错，参考顺序为左栏完整后右栏。
- table.pdf：真实网格和合并表头；不是打印 Markdown 管道符模拟表格。
- formula.pdf：上标和二维分式；线性字符提取不能证明数学语义恢复。
- figure.pdf：原创位图流程图与原生文本图注；未标注图像语义。

扫描件复用 ../p2/raster.pdf；损坏/加密负例复用 ../p1a。生成器运行依赖 ReportLab 4.4.9 与 Pillow（本次由 bundled runtime 提供），不是 API 的运行依赖。测试直接使用已提交 PDF，不自动重新生成。
