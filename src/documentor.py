"""
结构化文档输出模块
生成带 YAML frontmatter 的 Markdown 文档
"""
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import json
import yaml

logger = logging.getLogger(__name__)


class Documentor:
    """
    结构化文档生成器

    输出格式：
    ---
    topic: "课题名称"
    source: "来源URL"
    title: "文章标题"
    fetched_at: "2026-04-27T21:00:00+08:00"
    images_count: 5
    ---

    # 文章标题

    正文内容...
    """

    def __init__(
        self,
        output_dir: str = "output",
        include_metadata: bool = True,
        include_images: bool = True
    ):
        """
        Args:
            output_dir: 输出根目录
            include_metadata: 是否包含 YAML 元数据
            include_images: 是否在文档中引用图片
        """
        self.output_dir = Path(output_dir)
        self.include_metadata = include_metadata
        self.include_images = include_images

        # 创建子目录
        self.searches_dir = self.output_dir / "searches"
        self.pages_dir = self.output_dir / "pages"
        self.reports_dir = self.output_dir / "reports"

        for d in [self.searches_dir, self.pages_dir, self.reports_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def _sanitize_filename(self, title: str, max_length: int = 50) -> str:
        """
        清理标题，生成安全的文件名

        Args:
            title: 原始标题
            max_length: 最大长度

        Returns:
            安全的文件名
        """
        # 替换不安全字符
        import re
        safe = re.sub(r'[^\w\-_\u4e00-\u9fff\s]', '', title)
        safe = re.sub(r'[\s]+', '_', safe.strip())
        safe = safe[:max_length].strip("_")
        return safe or "untitled"

    def _generate_frontmatter(
        self,
        topic: str,
        source: str,
        title: str,
        fetched_at: Optional[str] = None,
        images_count: int = 0,
        **extra
    ) -> str:
        """生成 YAML frontmatter"""
        metadata = {
            "topic": topic,
            "source": source,
            "title": title,
            "fetched_at": fetched_at or datetime.now().isoformat(),
            "images_count": images_count,
            **extra
        }

        # 过滤空值
        metadata = {k: v for k, v in metadata.items() if v}

        lines = ["---", yaml.dump(metadata, allow_unicode=True, default_flow_style=False).strip(), "---"]
        return "\n".join(lines)

    def save_search_results(
        self,
        query: str,
        results: List[Dict[str, str]],
        topic: str = ""
    ) -> str:
        """
        保存搜索结果

        Args:
            query: 搜索关键词
            results: 搜索结果列表
            topic: 所属课题

        Returns:
            保存的文件路径
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"search_{self._sanitize_filename(query, 30)}_{timestamp}.json"
        filepath = self.searches_dir / filename

        output = {
            "query": query,
            "topic": topic,
            "timestamp": datetime.now().isoformat(),
            "result_count": len(results),
            "results": results
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        logger.info(f"Search results saved to {filepath}")
        return str(filepath)

    def save_page(
        self,
        url: str,
        content: str,
        title: str,
        topic: str,
        images: Optional[List[str]] = None,
        metadata: Optional[Dict] = None
    ) -> str:
        """
        保存抓取的页面为 Markdown 文档

        Args:
            url: 来源 URL
            content: 页面内容（Markdown 格式）
            title: 文章标题
            topic: 所属课题
            images: 图片 URL 列表
            metadata: 额外元数据

        Returns:
            保存的文件路径
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_title = self._sanitize_filename(title or url, 40)
        filename = f"page_{safe_title}_{timestamp}.md"
        filepath = self.pages_dir / filename

        parts = []

        # 添加 YAML frontmatter
        if self.include_metadata:
            frontmatter = self._generate_frontmatter(
                topic=topic,
                source=url,
                title=title,
                images_count=len(images) if images else 0,
                **(metadata or {})
            )
            parts.append(frontmatter)
            parts.append("")

        # 添加标题
        if title:
            parts.append(f"# {title}")
            parts.append("")

        # 添加内容
        parts.append(content)

        # 添加图片引用（如果有）
        if self.include_images and images:
            parts.append("")
            parts.append("---")
            parts.append("")
            parts.append("## Images")
            parts.append("")
            for i, img_url in enumerate(images, 1):
                parts.append(f"- [{i}]: {img_url}")

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(parts))

        logger.info(f"Page saved to {filepath}")
        return str(filepath)

    def save_report(
        self,
        topic: str,
        pages: List[Dict],
        summary: Optional[str] = None
    ) -> str:
        """
        生成调研报告

        Args:
            topic: 调研课题
            pages: 抓取页面列表
            summary: 总结摘要

        Returns:
            报告文件路径
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"report_{self._sanitize_filename(topic, 40)}_{timestamp}.md"
        filepath = self.reports_dir / filename

        parts = []

        # YAML frontmatter
        if self.include_metadata:
            frontmatter = self._generate_frontmatter(
                topic=topic,
                source="",
                title=f"调研报告：{topic}",
                pages_count=len(pages)
            )
            parts.append(frontmatter)
            parts.append("")

        # 报告标题
        parts.append(f"# 调研报告：{topic}")
        parts.append("")
        parts.append(f"**生成时间**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ")
        parts.append(f"**页面数量**：{len(pages)}  ")
        parts.append("")

        # 摘要
        if summary:
            parts.append("## 摘要")
            parts.append("")
            parts.append(summary)
            parts.append("")

        # 来源列表
        parts.append("## 信息来源")
        parts.append("")
        for i, page in enumerate(pages, 1):
            parts.append(f"{i}. [{page.get('title', 'Untitled')}]({page.get('url', '')}) - {page.get('url', '')}")
        parts.append("")

        # 各页面摘要
        parts.append("## 详细内容")
        parts.append("")

        for i, page in enumerate(pages, 1):
            parts.append(f"### {i}. {page.get('title', 'Untitled')}")
            parts.append("")
            parts.append(f"来源：{page.get('url', '')}")
            parts.append("")
            if page.get("content"):
                # 截取前500字作为摘要
                content = page.get("content", "")
                preview = content[:500] + "..." if len(content) > 500 else content
                parts.append(preview)
            parts.append("")
            parts.append("---")
            parts.append("")

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(parts))

        logger.info(f"Report saved to {filepath}")
        return str(filepath)

    def save_raw_html(self, url: str, html: str) -> str:
        """
        保存原始 HTML（降级保底用）

        Args:
            url: 来源 URL
            html: 原始 HTML

        Returns:
            保存的文件路径
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        parsed_url = urlparse(url)
        safe_name = self._sanitize_filename(parsed_url.netloc + parsed_url.path, 40)
        filename = f"raw_{safe_name}_{timestamp}.html"
        filepath = self.pages_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)

        logger.info(f"Raw HTML saved to {filepath}")
        return str(filepath)


from urllib.parse import urlparse


def main():
    """测试用主函数"""
    import yaml

    with open("configs/config.yaml", "r") as f:
        config = yaml.safe_load(f)

    doc = Documentor(
        output_dir="output",
        include_metadata=config["output"]["include_metadata"],
        include_images=config["output"]["include_images"]
    )

    # 测试保存搜索结果
    test_results = [
        {"title": "Test Article 1", "url": "https://example.com/1", "snippet": "This is a test..."},
        {"title": "Test Article 2", "url": "https://example.com/2", "snippet": "Another test..."}
    ]
    doc.save_search_results("test query", test_results, topic="测试课题")

    # 测试保存页面
    test_content = """
    这是页面的正文内容。

    ## 小节标题

    一些段落文字...

    ![image](https://example.com/image.jpg)
    """
    doc.save_page(
        url="https://example.com/article",
        content=test_content,
        title="测试文章",
        topic="测试课题",
        images=["https://example.com/image.jpg"]
    )

    print("Documentor test completed.")


if __name__ == "__main__":
    main()
