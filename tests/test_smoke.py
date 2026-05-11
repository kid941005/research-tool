from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.main import cmd_smoke


class Args:
    pass


class FakeScraper:
    def __init__(self, result):
        self.result = result

    def fetch_smart(self, url):
        return self.result


def base_config():
    return {
        "searxng": {"instance": "https://example.invalid", "timeout": 10},
        "scraping": {"compress": True, "timeout": 30, "retry": 3},
        "images": {"download": True, "output_dir": "output/images", "max_size_mb": 10, "concurrency": 5},
    }


def test_cmd_smoke_prints_success_contract(monkeypatch, capsys):
    result = {
        "success": True,
        "method": "scrapling:fetch",
        "content": "ok content",
        "warning": "",
    }

    monkeypatch.setattr("src.main.SmartScraper", lambda **kwargs: FakeScraper(result))

    import asyncio
    asyncio.run(cmd_smoke(Args(), base_config()))

    output = capsys.readouterr().out
    assert "SMOKE: fetch https://example.com" in output
    assert "SMOKE_METHOD: scrapling:fetch" in output
    assert "SMOKE_OK" in output


def test_cmd_smoke_prints_warning_when_present(monkeypatch, capsys):
    result = {
        "success": True,
        "method": "requests:fallback",
        "content": "ok content",
        "warning": "fallback warning",
    }

    monkeypatch.setattr("src.main.SmartScraper", lambda **kwargs: FakeScraper(result))

    import asyncio
    asyncio.run(cmd_smoke(Args(), base_config()))

    output = capsys.readouterr().out
    assert "SMOKE_WARNING: fallback warning" in output
    assert "SMOKE_OK" in output


def test_cmd_smoke_exits_on_failure(monkeypatch, capsys):
    result = {
        "success": False,
        "method": "none",
        "content": "",
        "error": "network error",
    }

    monkeypatch.setattr("src.main.SmartScraper", lambda **kwargs: FakeScraper(result))

    import asyncio
    try:
        asyncio.run(cmd_smoke(Args(), base_config()))
        assert False, "expected SystemExit"
    except SystemExit as exc:
        assert exc.code == 1

    output = capsys.readouterr().out
    assert "SMOKE_FAIL: network error" in output


def test_cmd_research_writes_output_report_with_minimal_flow(monkeypatch, tmp_path):
    from src.main import cmd_research

    class ResearchArgs:
        topic = "example domain"
        depth = 1
        max_pages = 1
        output = str(tmp_path / "report.md")
        bundle_dir = None
        report_name = None
        source_type = "all"

    class FakeSearcher:
        def __init__(self, instance_url, timeout):
            pass

        def search(self, query, limit):
            return [{"title": "Example Domain", "url": "https://example.com", "snippet": "snippet"}]

    class FakeScraper:
        def __init__(self, **kwargs):
            pass

        def fetch_smart(self, url):
            return {
                "success": True,
                "url": url,
                "title": "Example Domain",
                "content": "This domain is for use in documentation examples.",
                "images": [],
                "method": "scrapling:fetch",
                "source_type": "web",
                "warning": "",
            }

    class FakeDownloader:
        def __init__(self, output_dir, max_size_mb, concurrency):
            pass

        async def download_images(self, images):
            return {}

        def replace_images_in_markdown(self, content, url_to_local):
            return content

        async def close(self):
            return None

    monkeypatch.setattr("src.main.SearXNGSearcher", FakeSearcher)
    monkeypatch.setattr("src.main.SmartScraper", FakeScraper)
    monkeypatch.setattr("src.main.ImageDownloader", FakeDownloader)

    import asyncio
    asyncio.run(cmd_research(ResearchArgs(), base_config()))

    report_path = tmp_path / "report.md"
    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    assert "## 抓取统计" in content
    assert "- 尝试抓取：1" in content
    assert "- 成功抓取：1" in content
    assert "抓取方式：scrapling:fetch" in content
    assert "Example Domain" in content
