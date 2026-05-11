"""
智能网页抓取模块
基于 smart3w 架构：scrapling + readability-lxml + stealthy-fetch 回退
"""
import logging
import re
import time
from typing import Tuple, Optional, Dict
from pathlib import Path
import requests
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# 尝试导入 scrapling，失败时提示安装
try:
    import scrapling
except ImportError:
    scrapling = None
    logger.warning("scrapling not installed. Run: pip install 'scrapling[all]>=0.4.2'")

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
        if self._is_wechat_url(url):
            wechat_error = self._detect_wechat_error(raw_html)
            if wechat_error:
                logger.warning(wechat_error)
                return raw_html, wechat_error
            wechat_content, wechat_title = self._compress_wechat(raw_html)
            if wechat_content:
                return wechat_content, wechat_title
            logger.warning("WeChat specialized extraction returned empty result; falling back to generic compression")

        generic_invalid = self._detect_generic_invalid_page(raw_html, url)
        if generic_invalid:
            logger.warning(generic_invalid)
            return "", generic_invalid

        if not self.compress or not ReadabilityDocument:
            return raw_html, ""

        try:
            doc = ReadabilityDocument(raw_html)
            title = doc.title()
            summary = doc.summary()
            summary_tree = None

            if isinstance(summary, str):
                summary_tree = lxml_html.fromstring(summary)
                content = "\n".join(
                    part.strip()
                    for part in summary_tree.xpath("//text()")
                    if part and part.strip()
                )
            elif hasattr(summary, "text_content"):
                content = summary.text_content()
            else:
                content = str(summary)

            cleaned_title = (title or "").strip()
            if cleaned_title in {"", "[no-title]"} and summary_tree is not None:
                for xpath in (".//h1", ".//h2", ".//title"):
                    node = summary_tree.find(xpath)
                    if node is not None and node.text_content().strip():
                        cleaned_title = node.text_content().strip()
                        break

            logger.debug(f"Compressed content for {url}: {len(raw_html)} -> {len(content)} bytes")
            content_lines = [line.strip() for line in content.splitlines() if line.strip()]
            if cleaned_title and content_lines and content_lines[0] == cleaned_title:
                content_lines = content_lines[1:]
            if len(content_lines) >= 2 and len(content_lines[-1]) <= 20 and len(content_lines[-2]) >= 40:
                content_lines = content_lines[:-1]
            content = "\n".join(content_lines)
            return content.strip(), cleaned_title

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

    def _is_wechat_url(self, url: str) -> bool:
        return "mp.weixin.qq.com" in (url or "")

    def _normalize_image_url(self, src: str) -> str:
        if src.startswith("//"):
            return "https:" + src
        return src

    def _detect_wechat_error(self, raw_html: str) -> str:
        checks = [
            ("内容已被删除", "wechat error page: 内容已被删除"),
            ("访问过于频繁", "wechat error page: 访问过于频繁"),
            ("参数错误", "wechat error page: 参数错误"),
            ("weui-msg", "wechat error page: weui-msg"),
        ]
        for marker, message in checks:
            if marker in raw_html:
                return message
        return ""

    def _detect_generic_invalid_page(self, raw_html: str, url: str = "") -> str:
        checks = [
            ("百度安全验证", "invalid page: 百度安全验证"),
            ("安全验证", "invalid page: 安全验证"),
            ("亲爱的用户", "invalid page: 站点公告页"),
            ("产品策略变动", "invalid page: 站点公告页"),
            ("查看公告", "invalid page: 站点公告页"),
            ("欢迎来到知乎", "invalid page: 知乎欢迎页"),
            ("知乎，让每一次点击都充满意义", "invalid page: 知乎欢迎页"),
            ("发现问题背后的世界", "invalid page: 知乎欢迎页"),
            ("%PDF-", "invalid page: raw pdf content"),
            ("endobj", "invalid page: raw pdf content"),
            ("endstream", "invalid page: raw pdf content"),
        ]
        normalized_url = (url or "").lower()
        if normalized_url.endswith(".pdf"):
            return "invalid page: raw pdf content"
        for marker, message in checks:
            if marker in raw_html:
                return message
        return ""

    def _compress_wechat(self, raw_html: str) -> Tuple[str, str]:
        if not raw_html or not raw_html.strip():
            return "", ""

        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.warning("beautifulsoup4 not installed. WeChat extraction skipped")
            return "", ""

        try:
            soup = BeautifulSoup(raw_html, "html.parser")
            title_tag = soup.find("title")
            title = title_tag.get_text(strip=True) if title_tag else ""
            if not title:
                for meta_name in ("og:title", "twitter:title"):
                    meta_tag = soup.find("meta", attrs={"property": meta_name}) or soup.find("meta", attrs={"name": meta_name})
                    if meta_tag and meta_tag.get("content", "").strip():
                        title = meta_tag.get("content", "").strip()
                        break

            for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()

            content_div = soup.find("div", id="js_content")
            if not content_div:
                content_div = soup.find("div", class_="rich_media_content")
            if not content_div:
                return "", title

            parts = []
            seen_items = set()
            for node in content_div.find_all(["p", "section", "blockquote", "ul", "ol", "h1", "h2", "h3", "h4", "img"]):
                if node.find_parent("section") and node.name != "section":
                    continue
                if node.name == "img":
                    src = node.get("data-src") or node.get("src") or node.get("data-original")
                    if src:
                        parts.append(f"![]({self._normalize_image_url(src)})")
                    continue

                text = ""
                if node.name == "p":
                    text = node.get_text(separator=" ", strip=True)
                elif node.name == "section":
                    direct_parts = []
                    for child in node.find_all(["p", "img"], recursive=False):
                        if child.name == "p":
                            child_text = child.get_text(separator=" ", strip=True)
                            if child_text:
                                direct_parts.append(child_text)
                        elif child.name == "img":
                            src = child.get("data-src") or child.get("src") or child.get("data-original")
                            if src:
                                direct_parts.append(f"![]({self._normalize_image_url(src)})")
                    if direct_parts:
                        for item in direct_parts:
                            if item not in seen_items:
                                parts.append(item)
                                seen_items.add(item)
                        continue
                    elif node.find("img") and not node.get_text(strip=True):
                        pass
                    else:
                        text = node.get_text(separator=" ", strip=True)
                else:
                    text = node.get_text(separator=" ", strip=True)

                if text and text not in seen_items:
                    parts.append(text)
                    seen_items.add(text)

                for img in node.find_all("img", recursive=False):
                    src = img.get("data-src") or img.get("src") or img.get("data-original")
                    image_markdown = f"![]({self._normalize_image_url(src)})" if src else ""
                    if image_markdown and image_markdown not in seen_items:
                        parts.append(image_markdown)
                        seen_items.add(image_markdown)

            lines = []
            seen_images = set()
            prev = None
            tail_markers = [
                "课程邀请",
                "我们是谁",
                "推荐阅读",
                "延伸阅读",
                "相关阅读",
                "点击阅读原文",
                "欢迎关注",
                "欢迎交流",
                "扫码",
                "加入社群",
                "加入AI信息图设计交流社群",
                "商务合作",
                "相关推荐",
                "往期推荐",
                "相关阅读：",
                "推荐关注",
                "关注我们",
                "分享收藏",
                "点赞在看",
                "可加微",
                "阅读更多",
            ]
            cutoff_index = None
            for idx, part in enumerate(parts):
                normalized = re.sub(r"\s+", " ", part).strip()
                if normalized and any(marker in normalized for marker in tail_markers):
                    if idx == 0:
                        continue
                    cutoff_index = idx
                    break
            if cutoff_index is not None:
                parts = parts[:cutoff_index]

            for part in parts:
                part = re.sub(r"\s+", " ", part).strip()
                if not part:
                    continue
                if part.startswith("![]("):
                    if part in seen_images:
                        continue
                    seen_images.add(part)
                elif part == prev:
                    continue
                lines.append(part)
                prev = part

            text = "\n\n".join(lines).strip()
            text_length = len(re.sub(r"!\[\]\([^\)]*\)", "", text).strip())
            if text_length > 10:
                return text, title
            return "", title
        except Exception as e:
            logger.warning(f"WeChat extraction failed: {e}")
            return "", ""

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
            "source_type": "wechat" if self._is_wechat_url(url) else "web",
            "warning": "",
            "error": "",
            "success": False
        }

        # 方法1: scrapling fetch
        if scrapling:
            content, error = self._fetch_with_scrapling(url, use_stealthy=False)
            if content:
                result["content"], result["title"] = self._compress_content(content, url)
                result["images"] = self._extract_images(content) if not self.compress else []
                result["method"] = "scrapling:fetch"
                result["success"] = True
                return result
            if error:
                result["warning"] = f"scrapling:fetch failed: {error}"

        # 方法2: scrapling stealthy fetch（当前 CLI 运行时跳过）
        if scrapling:
            content, error = self._fetch_with_scrapling(url, use_stealthy=True)
            if content:
                result["content"], result["title"] = self._compress_content(content, url)
                result["images"] = self._extract_images(content) if not self.compress else []
                result["method"] = "scrapling:stealthy"
                result["success"] = True
                return result
            if error:
                previous = result["warning"]
                result["warning"] = f"{previous}; scrapling:stealthy skipped: {error}" if previous else f"scrapling:stealthy skipped: {error}"

        # 方法3: 降级 - 直接 requests
        logger.info(f"Using fallback requests for {url}")
        content = self._fetch_with_requests(url)
        if content:
            result["content"], result["title"] = self._compress_content(content, url)
            if not result["content"] and result["title"].startswith("invalid page:"):
                result["warning"] = result["title"]
                result["error"] = result["title"]
            else:
                result["images"] = self._extract_images(content) if not self.compress else []
                result["method"] = "requests:fallback"
                if self._is_wechat_url(url):
                    wechat_error = self._detect_wechat_error(content)
                    if wechat_error:
                        result["warning"] = f"{result['warning']}; {wechat_error}" if result["warning"] else wechat_error
                        result["error"] = wechat_error
                result["success"] = True
                return result

        result["error"] = result["warning"] or "all fetch methods failed"
        if not scrapling and not result["warning"]:
            result["error"] = "scrapling not installed and requests fallback failed"
        return result

    def _fetch_with_scrapling(self, url: str, use_stealthy: bool = False) -> Tuple[Optional[str], str]:
        """使用 scrapling 抓取"""
        if not scrapling:
            return None, ""

        try:
            mode = "stealthy" if use_stealthy else "default"
            logger.debug(f"Trying scrapling {mode} for {url}")

            if use_stealthy:
                return None, "requires async path in current CLI runtime"

            fetcher = scrapling.Fetcher
            page = fetcher.get(url, timeout=self.timeout)
            html = getattr(page, "html_content", None)
            if html and len(html) >= 100:
                return str(html), "scrapling:fetch"
            body = getattr(page, "body", None)
            if isinstance(body, bytes) and len(body) > 100:
                return body.decode(getattr(page, "encoding", "utf-8") or "utf-8", errors="ignore"), "scrapling:fetch"
            if body and len(body) > 100:
                return str(body), "scrapling:fetch"
            return self._extract_scrapling_page_text(page), "scrapling:fetch"

        except Exception as e:
            logger.debug(f"scrapling {mode} failed: {e}")
            return None, str(e)

    def _extract_scrapling_page_text(self, page) -> Optional[str]:
        if page is None:
            return None

        content = getattr(page, "text", None)
        if content and len(content) > 100:
            return content

        if self._is_wechat_url(getattr(page, "url", "")):
            for selector in ("div#js_content", "div.rich_media_content"):
                try:
                    nodes = page.css(selector)
                    first = nodes.first if hasattr(nodes, "first") else None
                    if first:
                        html = first.html_content if hasattr(first, "html_content") else None
                        if html and len(html) > 100:
                            return str(html)
                        text = first.get_all_text(separator="\n", strip=True)
                        if text and len(text) > 20:
                            return str(text)
                    raw = nodes.get() if hasattr(nodes, "get") else None
                    if raw and len(raw) > 100:
                        return str(raw)
                except Exception:
                    continue

        get_all_text = getattr(page, "get_all_text", None)
        if callable(get_all_text):
            text = get_all_text(separator="\n", strip=True)
            if text and len(text) > 100:
                return str(text)

        html_content = getattr(page, "html_content", None)
        if html_content and len(html_content) > 100:
            return str(html_content)

        body = getattr(page, "body", None)
        if body:
            if isinstance(body, bytes):
                return body.decode(getattr(page, "encoding", "utf-8") or "utf-8", errors="ignore")
            if len(body) > 100:
                return str(body)

        return None

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
