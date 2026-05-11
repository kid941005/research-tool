"""
SearXNG 搜索封装
"""
import json
import logging
import time
from typing import List, Dict, Optional
import requests

logger = logging.getLogger(__name__)


class SearXNGSearcher:
    """SearXNG 元搜索引擎封装"""

    def __init__(self, instance_url: str, timeout: int = 10):
        """
        Args:
            instance_url: SearXNG 实例地址
            timeout: 请求超时（秒）
        """
        self.instance_url = instance_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })

    def search(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        """
        执行搜索

        Args:
            query: 搜索关键词
            limit: 返回结果数量

        Returns:
            结果列表，每项包含 title, url, snippet
        """
        logger.info(f"Searching SearXNG: {query}")

        search_url = f"{self.instance_url}/search"
        params = {
            "q": query,
            "format": "json",
            "engines": "",  # 空表示使用默认引擎
            "categories": "general",
            "pageno": 1,
        }

        try:
            response = self.session.get(search_url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()

            results = []
            seen_urls = set()
            for item in data.get("results", []):
                url = item.get("url", "").strip()
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                results.append({
                    "title": item.get("title", ""),
                    "url": url,
                    "snippet": item.get("content", item.get("description", "")),
                })
                if len(results) >= limit:
                    break

            logger.info(f"Found {len(results)} results for: {query}")
            return results

        except requests.exceptions.RequestException as e:
            logger.error(f"SearXNG search failed: {e}")
            return []

    def batch_search(self, queries: List[str], delay: float = 1.0) -> Dict[str, List[Dict[str, str]]]:
        """
        批量搜索

        Args:
            queries: 关键词列表
            delay: 两次搜索之间的延迟（秒）

        Returns:
            {关键词: 结果列表}
        """
        results = {}
        for query in queries:
            results[query] = self.search(query)
            if delay > 0 and query != queries[-1]:
                time.sleep(delay)
        return results


def main():
    """测试用主函数"""
    import yaml

    with open("configs/config.yaml", "r") as f:
        config = yaml.safe_load(f)

    searcher = SearXNGSearcher(
        instance_url=config["searxng"]["instance"],
        timeout=config["searxng"]["timeout"]
    )

    results = searcher.search("AVAS 低速提示音 汽车", limit=5)
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
