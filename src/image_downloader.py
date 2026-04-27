"""
图片下载模块
自动下载 Markdown/HTML 中的图片，保存到本地目录
"""
import asyncio
import logging
import hashlib
import re
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from urllib.parse import urlparse, urljoin, unquote
import aiohttp
import aiofiles

logger = logging.getLogger(__name__)

# 图片扩展名模式
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp"}


class ImageDownloader:
    """
    图片下载器

    功能：
    1. 从 URL 列表下载图片
    2. 从 Markdown/HTML 内容中提取图片并下载
    3. 替换内容中的图片 URL 为本地路径
    """

    def __init__(
        self,
        output_dir: str = "output/images",
        max_size_mb: int = 10,
        concurrency: int = 5,
        timeout: int = 30
    ):
        """
        Args:
            output_dir: 图片输出目录
            max_size_mb: 单张图片最大大小（MB）
            concurrency: 并发下载数
            timeout: 请求超时（秒）
        """
        self.output_dir = Path(output_dir)
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.concurrency = concurrency
        self.timeout = timeout
        self.session: Optional[aiohttp.ClientSession] = None

        # 确保输出目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 aiohttp session"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session

    def _is_image_url(self, url: str) -> bool:
        """判断 URL 是否为图片"""
        parsed = urlparse(url.lower())
        ext = Path(parsed.path).suffix
        return ext in IMAGE_EXTENSIONS or "image" in parsed.query.lower()

    def _generate_filename(self, url: str, index: int = 0) -> str:
        """为图片生成唯一文件名"""
        parsed = urlparse(url)
        original_name = Path(unquote(parsed.path)).name

        # 如果没有扩展名或扩展名不在允许列表中，使用默认
        ext = Path(original_name).suffix.lower()
        if ext not in IMAGE_EXTENSIONS:
            ext = ".jpg"

        # 使用 URL hash 生成唯一名称，避免特殊字符问题
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        base_name = Path(original_name).stem or f"image"

        # 限制文件名长度
        base_name = base_name[:30]

        return f"{base_name}_{url_hash}_{index}{ext}"

    def extract_images_from_markdown(self, content: str) -> List[str]:
        """
        从 Markdown 内容中提取图片 URL

        Args:
            content: Markdown 文本

        Returns:
            图片 URL 列表
        """
        # Markdown 图片语法：![alt](url)
        pattern = r'!\[([^\]]*)\]\(([^)\s]+)\)'
        matches = re.findall(pattern, content)

        urls = []
        for alt_text, url in matches:
            url = url.strip()
            if url and not url.startswith("data:") and not url.startswith("file://"):
                urls.append(url)

        return urls

    def extract_images_from_html(self, content: str) -> List[str]:
        """
        从 HTML 内容中提取图片 URL

        Args:
            content: HTML 文本

        Returns:
            图片 URL 列表
        """
        # img 标签的 src 属性
        pattern = r'<img[^>]+src=["\']([^"\']+)["\']'
        matches = re.findall(pattern, content, re.IGNORECASE)

        urls = []
        for url in matches:
            url = url.strip()
            if url and not url.startswith("data:") and not url.startswith("file://"):
                urls.append(url)

        return urls

    def extract_images(self, content: str, base_url: str = "") -> List[str]:
        """
        从 Markdown 或 HTML 内容中提取图片 URL

        Args:
            content: 文本内容
            base_url: 用于解析相对 URL 的基础 URL

        Returns:
            图片 URL 列表
        """
        # 尝试 Markdown
        urls = self.extract_images_from_markdown(content)

        # 尝试 HTML
        if not urls:
            urls = self.extract_images_from_html(content)

        # 转换相对 URL 为绝对 URL
        if base_url:
            absolute_urls = []
            for url in urls:
                if url.startswith("//"):
                    url = "https:" + url
                elif url.startswith("/"):
                    # 相对路径，拼接 base_url
                    parsed = urlparse(base_url)
                    url = f"{parsed.scheme}://{parsed.netloc}{url}"
                elif not url.startswith(("http://", "https://")):
                    # 相对路径（无前导斜杠）
                    url = urljoin(base_url, url)
                absolute_urls.append(url)
            return absolute_urls

        return urls

    async def _download_single(
        self,
        session: aiohttp.ClientSession,
        url: str,
        dest_path: Path,
        semaphore: asyncio.Semaphore
    ) -> Tuple[str, bool, str]:
        """
        下载单张图片

        Returns:
            (url, success, local_path_or_error)
        """
        async with semaphore:
            try:
                async with session.get(url, timeout=self.timeout) as response:
                    if response.status != 200:
                        return url, False, f"HTTP {response.status}"

                    content = await response.read()

                    # 检查文件大小
                    if len(content) > self.max_size_bytes:
                        return url, False, f"File too large: {len(content)} bytes"

                    # 保存文件
                    async with aiofiles.open(dest_path, "wb") as f:
                        await f.write(content)

                    logger.debug(f"Downloaded: {url} -> {dest_path}")
                    return url, True, str(dest_path)

            except asyncio.TimeoutError:
                return url, False, "Timeout"
            except Exception as e:
                return url, False, str(e)

    async def download_images(
        self,
        urls: List[str],
        prefix: str = "img"
    ) -> Dict[str, str]:
        """
        下载图片列表

        Args:
            urls: 图片 URL 列表
            prefix: 文件名前缀

        Returns:
            {original_url: local_path}
        """
        if not urls:
            return {}

        session = await self._get_session()
        semaphore = asyncio.Semaphore(self.concurrency)

        # 去重，保持顺序
        unique_urls = list(dict.fromkeys(urls))

        # 准备任务
        tasks = []
        url_to_index = {}
        for i, url in enumerate(unique_urls):
            filename = f"{prefix}_{i:03d}{Path(urlparse(url).path).suffix or '.jpg'}"
            # 过滤不安全的字符
            filename = re.sub(r'[^\w\-_.]', '_', filename)
            dest_path = self.output_dir / filename
            url_to_index[url] = i
            tasks.append(self._download_single(session, url, dest_path, semaphore))

        # 并发下载
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 整理结果
        url_to_local = {}
        for i, result in enumerate(results):
            if isinstance(result, tuple):
                url, success, path_or_error = result
                if success:
                    url_to_local[url] = path_or_error
                else:
                    logger.warning(f"Failed to download {url}: {path_or_error}")
            else:
                logger.warning(f"Download exception for {unique_urls[i]}: {result}")

        return url_to_local

    def replace_images_in_markdown(
        self,
        content: str,
        url_to_local: Dict[str, str],
        relative: bool = True
    ) -> str:
        """
        替换 Markdown 中的图片 URL 为本地路径

        Args:
            content: 原始 Markdown 内容
            url_to_local: {原始URL: 本地路径} 映射
            relative: 是否使用相对路径

        Returns:
            替换后的 Markdown 内容
        """
        def replace_one(match):
            alt_text = match.group(1)
            original_url = match.group(2).strip()

            if original_url in url_to_local:
                local_path = url_to_local[original_url]

                if relative:
                    # 转换为相对路径（从 output/pages 到 output/images）
                    try:
                        local_path = str(Path(local_path).relative_to(self.output_dir.parent / "pages"))
                    except ValueError:
                        pass

                return f'![{alt_text}]({local_path})'

            return match.group(0)  # 保留原样

        # 替换 Markdown 图片语法
        pattern = r'!\[([^\]]*)\]\(([^)\s]+)\)'
        return re.sub(pattern, replace_one, content)

    async def close(self):
        """关闭 session"""
        if self.session and not self.session.closed:
            await self.session.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


def main():
    """测试用主函数"""
    import yaml
    import asyncio

    with open("configs/config.yaml", "r") as f:
        config = yaml.safe_load(f)

    downloader = ImageDownloader(
        output_dir=config["images"]["output_dir"],
        max_size_mb=config["images"]["max_size_mb"],
        concurrency=config["images"]["concurrency"]
    )

    # 测试从 Markdown 提取图片
    test_md = """
    # Test Article

    ![Image 1](https://example.com/image1.jpg)
    ![Image 2](https://example.com/image2.png)

    Some text here.
    """

    urls = downloader.extract_images_from_markdown(test_md)
    print(f"Extracted URLs: {urls}")

    # 测试下载
    async def test_download():
        test_urls = [
            "https://www.google.com/images/branding/googlelogo/2x/googlelogo_color_272x92dp.png"
        ]
        result = await downloader.download_images(test_urls, prefix="test")
        print(f"Download result: {result}")
        await downloader.close()

    asyncio.run(test_download())


if __name__ == "__main__":
    main()
