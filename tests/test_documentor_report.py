from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.documentor import Documentor
from src.analyzer import ResearchAnalyzer


def test_analyzer_limits_keyword_extraction_to_leading_content():
    analyzer = ResearchAnalyzer()
    lead = "压电陶瓷是一种能够将机械能和电能互相转换的功能陶瓷材料。它在受力时产生电压，在加电压时发生形变。"
    long_tail = " ".join(["第一次世界大战 美国 BaTiO3 mnpq"] * 200)
    analysis = analyzer.analyze(
        "压电陶瓷是什么",
        [
            {
                "title": "压电陶瓷说明",
                "url": "https://example.com/piezo",
                "content": lead + ("甲" * 1400) + long_tail,
                "source_type": "web",
            }
        ],
    )

    keywords = analysis["top_keywords"]
    assert "第一次世界大战" not in keywords
    assert "美国" not in keywords
    assert "batio" not in keywords
    assert "mnpq" not in keywords


def test_save_report_includes_stats_and_fetch_warning(tmp_path):
    doc = Documentor(output_dir=str(tmp_path))
    report_path = doc.save_report(
        topic="测试报告",
        pages=[
            {
                "title": "测试页面",
                "url": "https://example.com",
                "content": "这是测试内容",
                "fetch_method": "requests:fallback",
                "warning": "scrapling:stealthy skipped: requires async path in current CLI runtime",
            }
        ],
        analysis={"summary": "测试摘要"},
        stats={"attempted_count": 1, "success_count": 1, "failed_count": 0},
        filename="report_verify.md",
    )

    content = Path(report_path).read_text(encoding="utf-8")
    assert "## 抓取统计" in content
    assert "- 尝试抓取：1" in content
    assert "- 成功抓取：1" in content
    assert "- 失败抓取：0" in content
    assert "抓取方式：requests:fallback" in content
    assert "警告：scrapling:stealthy skipped: requires async path in current CLI runtime" in content
