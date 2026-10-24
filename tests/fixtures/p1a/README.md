# P1-A parser benchmark fixtures

这些文件由 `scripts/build_p1a_fixtures.py` 生成，内容为仓库内合成、合法使用的测试文本，不代表外部论文或真实授权材料。`manifest.json` 记录每份文件的类型、成功/失败预期和人工标注 marker。

覆盖普通文本、公式、表格、多栏顺序提示、HTML、扫描版、加密、损坏文件和密码分析术语。评测脚本只报告实际运行结果，不将失败样本计入解析成功率。
