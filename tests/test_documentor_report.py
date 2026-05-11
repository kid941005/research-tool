from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.documentor import Documentor


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
