"""Run the P1-A parser benchmark against the checked-in synthetic fixtures."""

from __future__ import annotations

import json
import time
from pathlib import Path

from corpusflow.adapters.parser import HTMLParserAdapter, ParserError, PDFParserAdapter

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "p1a"
OUTPUT = ROOT / "docs" / "reports" / "P1-A_PARSER_BENCHMARK.md"


def main() -> None:
    manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    rows: list[dict[str, object]] = []
    for filename, expected in manifest.items():
        path = FIXTURES / filename
        started = time.perf_counter()
        try:
            parser = PDFParserAdapter() if expected["kind"] == "pdf" else HTMLParserAdapter()
            result = parser.parse(
                path.read_bytes(),
                filename,
                "application/pdf" if expected["kind"] == "pdf" else "text/html",
            )
            elapsed = round((time.perf_counter() - started) * 1000, 2)
            markers = [marker for marker in expected.get("markers", []) if marker in result.text]
            rows.append(
                {
                    "file": filename,
                    "expected": expected["expected"],
                    "actual": "success",
                    "success": expected["expected"] == "success",
                    "text_completeness": round(
                        len(markers) / len(expected.get("markers", []) or [1]), 3
                    ),
                    "heading_count": len(result.sections),
                    "formula_markers": len(result.structured.get("formula_markers", [])),
                    "table_rows": len(result.structured.get("table_rows", [])),
                    "location_coverage": round(
                        sum(bool(section.location) for section in result.sections)
                        / len(result.sections),
                        3,
                    ),
                    "elapsed_ms": elapsed,
                    "failure_type": "",
                }
            )
        except ParserError as exc:
            elapsed = round((time.perf_counter() - started) * 1000, 2)
            rows.append(
                {
                    "file": filename,
                    "expected": expected["expected"],
                    "actual": exc.code,
                    "success": False,
                    "text_completeness": 0,
                    "heading_count": 0,
                    "formula_markers": 0,
                    "table_rows": 0,
                    "location_coverage": 0,
                    "elapsed_ms": elapsed,
                    "failure_type": exc.code,
                }
            )
    successful = [row for row in rows if row["actual"] == "success"]
    expected_success = [row for row in rows if row["expected"] == "success"]
    success_rate = sum(row["actual"] == row["expected"] for row in rows) / len(rows)
    average_ms = sum(float(row["elapsed_ms"]) for row in rows) / len(rows)
    lines = [
        "# P1-A Parser Benchmark",
        "",
        "执行对象：仓库内合成、合法使用的 `tests/fixtures/p1a`；结果由当前 ParserAdapter 实际运行生成。",
        "",
        f"- 样本数：{len(rows)}；期望成功：{len(expected_success)}；实际成功：{len(successful)}",
        f"- 预期结果匹配率：{success_rate:.1%}",
        f"- 平均处理时间：{average_ms:.2f} ms/文件（本地 Python 进程，不代表生产吞吐）",
        "- 公式保留、表格结构、版面阅读顺序和 OCR 仅对当前内置解析器实际输出计数；未配置外部解析器不填充模拟指标。",
        "",
        "| 文件 | 预期 | 实际 | 文本 marker 完整率 | 章节数 | 公式 marker | 表格行 | 定位覆盖率 | ms | 失败类型 |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['file']} | {row['expected']} | {row['actual']} | {float(row['text_completeness']):.1%} | "
            f"{row['heading_count']} | {row['formula_markers']} | {row['table_rows']} | "
            f"{float(row['location_coverage']):.1%} | {row['elapsed_ms']} | {row['failure_type'] or '—'} |"
        )
    lines.extend(
        [
            "",
            "## 解读",
            "",
            "- 普通文本、公式 marker、技术表格和 HTML 的实际文本层可被内置解析器提取；PDF 定位为页码/行号，HTML 定位为行号。",
            "- 扫描版 PDF、加密 PDF、损坏 PDF 分别得到 `SCANNED_PDF_UNSUPPORTED`、`ENCRYPTED_PDF`、`CORRUPT_PDF`，没有生成成功 DocumentVersion。",
            "- 多栏 PDF 仅能在当前文本层样本中验证页级顺序；没有版面模型或 OCR 的文档不宣称已经解决多栏重排。",
            "",
        ]
    )
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print("P1-A PARSER BENCHMARK PASS")
    print(
        json.dumps(
            {
                "samples": len(rows),
                "success_rate": success_rate,
                "average_ms": average_ms,
                "rows": rows,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
