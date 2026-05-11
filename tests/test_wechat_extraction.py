from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.scraper import SmartScraper


FIXTURES = Path(__file__).parent / "fixtures" / "wechat"


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_wechat_section_article_keeps_body_and_image():
    scraper = SmartScraper()
    html = read_fixture("section_article.html")

    content, title = scraper._compress_wechat(html)

    assert title == "测试公众号文章"
    assert "第一段内容。" in content
    assert "第二段内容。" in content
    assert "https://img.example.com/a.jpg" in content
    assert "关注我们" not in content
    assert "点赞在看" not in content


def test_wechat_error_page_detected():
    scraper = SmartScraper()
    html = read_fixture("error_page.html")

    assert scraper._detect_wechat_error(html) == "wechat error page: 参数错误"

    content, title = scraper._compress_content(html, "https://mp.weixin.qq.com/s/test")
    assert title == "wechat error page: 参数错误"
    assert "参数错误" in content


def test_wechat_real_sample_trims_known_tail_markers():
    scraper = SmartScraper()
    html = """
    <html>
      <head><title>GPT-Image2爆火后，最先出圈的竟然是看手相</title></head>
      <body>
        <div id="js_content">
          <p>第一段正文。</p>
          <p>第二段正文。</p>
          <p>关于AI信息可视化设计的相关话题，欢迎交流~~</p>
          <p>想要加入AI信息图设计交流社群，感兴趣的宝们可加微。</p>
          <p>阅读更多</p>
        </div>
      </body>
    </html>
    """

    content, title = scraper._compress_wechat(html)

    assert title == "GPT-Image2爆火后，最先出圈的竟然是看手相"
    assert "第一段正文。" in content
    assert "第二段正文。" in content
    assert "欢迎交流" not in content
    assert "可加微" not in content
    assert "阅读更多" not in content


def test_generic_readability_summary_is_converted_to_plain_text():
    scraper = SmartScraper()
    html = """
    <html>
      <head><title>Example Domain</title></head>
      <body>
        <main>
          <h1>Example Domain</h1>
          <p>This domain is for use in documentation examples without needing permission.</p>
          <p>Avoid use in operations.</p>
        </main>
      </body>
    </html>
    """

    content, title = scraper._compress_content(html, "https://example.com")

    assert title == "Example Domain"
    assert "This domain is for use in documentation examples without needing permission." in content
    assert "Avoid use in operations." in content
    assert content.startswith("This domain is for use in documentation examples")
    assert content.endswith("Avoid use in operations.")
    assert "Learn more" not in content
    assert "Example Domain\nThis domain is for use in documentation examples" not in content
    assert "<body" not in content.lower()
    assert "<html" not in content.lower()
    assert "readabilitybody" not in content.lower()


def test_generic_title_falls_back_to_heading_when_readability_returns_no_title(monkeypatch):
    scraper = SmartScraper()

    class FakeDocument:
        def __init__(self, raw_html):
            pass

        def title(self):
            return "[no-title]"

        def summary(self):
            return "<html><body><div><h1>Recovered Title</h1><p>正文内容。</p></div></body></html>"

    monkeypatch.setattr("src.scraper.ReadabilityDocument", FakeDocument)

    content, title = scraper._compress_content("<html></html>", "https://example.com")

    assert title == "Recovered Title"
    assert "正文内容。" in content


def test_fetch_with_scrapling_prefers_html_for_generic_pages(monkeypatch):
    scraper = SmartScraper()

    class FakePage:
        @property
        def html_content(self):
            return "<html><head><title>Example Domain</title></head><body><h1>Example Domain</h1><p>正文</p></body></html>"

        @property
        def body(self):
            return b"<html><body>fallback</body></html>"

        @property
        def text(self):
            return "plain text that should not win"

    class FakeFetcher:
        @staticmethod
        def get(url, timeout):
            return FakePage()

    monkeypatch.setattr("src.scraper.scrapling.Fetcher", FakeFetcher)

    content, method = scraper._fetch_with_scrapling("https://example.com")

    assert method == "scrapling:fetch"
    assert "<title>Example Domain</title>" in content
