"""
智能网页抓取模块
基于 smart3w 架构：scrapling + readability-lxml + stealthy-fetch 回退
"""
import logging
import time
from typing import Tuple, Optional, Dict
from pathlib import Path
import requests
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# 尝试导入 scrapling，失败时提示安装
try:
    import scrapling
    from scrapling.core import Extractor
except ImportError:
    scrapling = None
    Extractor = None
    logger.warning("scrapling not installed. Run: pip install scrapling")

# 尝试导入 readability-lxml
try:
    from readability.readability import Document as ReadabilityDocument
    from lxml import html as lxml_html
except ImportError:
    readability = None
    ReadabilityDocument = None
    lxml_html = None
    logger.warning("readability-lxml not installed. Run: pip install readability-lxml")


class SmartScraper:
    """
    智能网页抓取器

    工作流程（来自 smart3w）：
    1. scrapling extract get → 成功 → readability 压缩 → 返回正文
    2. scrapling stealthy-fetch → 成功 → readability 压缩 → 返回正文
    3. 所有方式均失败 → 返回原始 HTML（降级保底）
    """

    def __init__(
        self,
        compress: bool = True,
        timeout: int = 30,
        retry: int = 3,
        user_agent: str = None
    ):
        """
        Args:
            compress: 是否使用 readability 压缩正文
            timeout: 请求超时（秒）
            retry: 失败重试次数
            user_agent: 自定义 User-Agent
        """
        self.compress = compress
        self.timeout = timeout
        self.retry = retry
        self.session = requests.Session()

        default_ua = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        self.session.headers.update({
            "User-Agent": user_agent or default_ua
        })

    def _compress_content(self, raw_html: str, url: str) -> Tuple[str, str]:
        """
        使用 readability-lxml 提取并压缩正文

        Returns:
            (压缩后正文, 文章标题)
        """
        if not self.compress or not ReadabilityDocument:
            return raw_html, ""

        try:
            doc = ReadabilityDocument(raw_html)
            title = doc.title()
            summary = doc.summary()

            # 将 lxml 元素转为字符串
            if hasattr(summary, "text_content"):
                content = summary.text_content()
            else:
                content = str(summary)

            logger.debug(f"Compressed content for {url}: {len(raw_html)} -> {len(content)} bytes")
            return content.strip(), title or ""

        except Exception as e:
            logger.warning(f"Readability compression failed: {e}")
            return raw_html, ""

    def _extract_images(self, raw_html: str) -> list:
        """
        从原始 HTML 中提取所有图片 URL

        Returns:
            图片 URL 列表
        """
        images = []
        if not lxml_html:
            return images

        try:
            tree = lxml_html.fromstring(raw_html)
            # 查找所有 img 标签的 src 属性
            for img in tree.xpath("//img[@src]"):
                src = img.get("src", "")
                if src and not src.startswith("data:"):
                    images.append(src)
        except Exception as e:
            logger.warning(f"Image extraction failed: {e}")

        return images

    def fetch_smart(self, url: str) -> Dict:
        """
        智能抓取：自动选择最佳方式 + 内容压缩

        Args:
            url: 目标 URL

        Returns:
            {
                "content": 抓取内容,
                "title": 文章标题,
                "images": 图片列表,
                "method": 使用的抓取方式,
                "success": 是否成功
            }
        """
        result = {
            "url": url,
            "content": "",
            "title": "",
            "images": [],
            "method": "none",
            "success": False
        }

        # 方法1: scrapling extract get
        if scrapling and Extractor:
            content, method = self._fetch_with_scrapling(url, use_stealthy=False)
            if content:
                result["content"], result["title"] = self._compress_content(content, url)
                result["images"] = self._extract_images(content) if not self.compress else []
                result["method"] = "scrapling:extract:get"
                result["success"] = True
                return result

        # 方法2: scrapling stealthy-fetch（回退）
        if scrapling and Extractor:
            content, method = self._fetch_with_scrapling(url, use_stealthy=True)
            if content:
                result["content"], result["title"] = self._compress_content(content, url)
                result["images"] = self._extract_images(content) if not self.compress else []
                result["method"] = "scrapling:stealthy:fetch"
                result["success"] = True
                return result

        # 方法3: 降级 - 直接 requests
        logger.info(f"Using fallback requests for {url}")
        content = self._fetch_with_requests(url)
        if content:
            result["content"], result["title"] = self._compress_content(content, url)
            result["images"] = self._extract_images(content)
            result["method"] = "requests:fallback"
            result["success"] = True

        return result

    def _fetch_with_scrapling(self, url: str, use_stealthy: bool = False) -> Tuple[Optional[str], str]:
        """使用 scrapling 抓取"""
        if not scrapling or not Extractor:
            return None, ""

        try:
            mode = "stealthy" if use_stealthy else "default"
            logger.debug(f"Trying scrapling {mode} for {url}")

            # 创建抓取器
            if use_stealthy:
                # stealthy 模式
                fetcher = scrapling.StealthyFetcher()
                page = fetcher.get(url, timeout=self.timeout)
            else:
                # 普通模式
                fetcher = scrapling.DefaultFetcher()
                page = fetcher.get(url, timeout=self.timeout)

            extractor = Extractor.from_page(page)
            content = extractor.text

            if content and len(content) > 100:
                return content, f"scrapling:{mode}"
            return None, ""

        except Exception as e:
            logger.debug(f"scrapling {mode} failed: {e}")
            return None, ""

    def _fetch_with_requests(self, url: str) -> Optional[str]:
        """使用 requests 降级抓取"""
        for attempt in range(self.retry):
            try:
                response = self.session.get(url, timeout=self.timeout)
                response.raise_for_status()
                response.encoding = response.apparent_encoding or "utf-8"
                return response.text
            except Exception as e:
                logger.warning(f"requests attempt {attempt + 1} failed: {e}")
                if attempt < self.retry - 1:
                    time.sleep(1)
        return None

    def fetch(self, url: str) -> Dict:
        """fetch 的别名，保持接口一致"""
        return self.fetch_smart(url)


def main():
    """测试用主函数"""
    import yaml

    with open("configs/config.yaml", "r") as f:
        config = yaml.safe_load(f)

    scraper = SmartScraper(
        compress=config["scraping"]["compress"],
        timeout=config["scraping"]["timeout"],
        retry=config["scraping"]["retry"],
        user_agent=config["scraping"]["user_agent"]
    )

    # 测试 URL
    test_url = "https://example.com"
    result = scraper.fetch_smart(test_url)

    print(f"URL: {result['url']}")
    print(f"Success: {result['success']}")
    print(f"Method: {result['method']}")
    print(f"Title: {result['title']}")
    print(f"Content length: {len(result['content'])} chars")
    print(f"Images found: {len(result['images'])}")


if __name__ == "__main__":
    main()
