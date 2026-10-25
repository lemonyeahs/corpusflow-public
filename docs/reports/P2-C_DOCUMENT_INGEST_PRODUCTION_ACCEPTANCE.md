# P2-C 文档与生产化阶段记录

状态：PARTIAL，未通过全阶段门禁。

## 实际完成

新增 OCRParserAdapter：输入限 20 MiB、最多 10 页；Poppler 按页渲染（长边 2400 像素），Tesseract 英文 OCR 输出文本、页码、每词图像坐标和引擎置信度；临时目录自动清理，每个子进程设置超时。损坏、加密、超限、无文本及执行失败均明确报错。置信度来自引擎，不表示正确率。

本机 tesseract 5.5.1 对真实图片型 raster.pdf 提取出「CorpusFlow OCR evidence: AES block size is 128 bits.」。测试首先确认 PDF 没有文本层，再检查提取内容和坐标。损坏/加密拒绝测试通过。未伪造数学结构、表格或中文 OCR；这些均 NOT_EVALUATED。

## docreader 实测

只读检查已有 WeKnora 项目 1ef38fdb8b19347b82d3a99f6f17d75ac09ad606 及 MIT/第三方许可说明。其 gRPC DocReader 提供 Read/ReadStream/ListEngines；实际 ListEngines 返回 builtin、markitdown、opendataloader available=true。没有直接使用第三方数据库或生产凭据。引擎可用列表不等于文档处理验收成功。

## 尚未完成

OCR 只在本机 Adapter/集成测试运行，Docker Worker 未安装/锁定对应执行环境，也未开放 OCR 模板；不是平台端到端能力。OCR 操作系统级资源隔离、总任务时限、复杂表格/多栏/公式、中文语言包、图注评测尚未通过。

URL/DOI 导入、DNS 固定与重定向 SSRF 防护、IngestPlan 审核流程尚未交付；不能将旧候选元数据接口描述为真实采集。OIDC/SSO、多节点 HA、备份恢复、规模负载、依赖漏洞扫描：NOT RUN，生产不就绪。

旧 P1-A scanned.pdf 实际是空白页。新增 tests/fixtures/p2/raster.pdf 是真实图片型样本；保留旧 fixture，不改写既有报告或负面结果。
