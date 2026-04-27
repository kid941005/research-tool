#!/usr/bin/env python3
"""
Research Tool - 调研工具主入口

用法:
    python src/main.py search "关键词" [--limit 10]
    python src/main.py fetch "URL" --topic "课题"
    python src/main.py batch --topics topics.txt
    python src/main.py research "课题关键词" [--depth 10]
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import List, Dict
import yaml

# 添加 src 目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from searcher import SearXNGSearcher
from scraper import SmartScraper
from image_downloader import ImageDownloader
from documentor import Documentor


def setup_logging(level: str = "INFO"):
    """配置日志"""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("logs/research-tool.log", encoding="utf-8")
        ]
    )


def load_config() -> dict:
    """加载配置文件"""
    config_path = Path("configs/config.yaml")
    if not config_path.exists():
        # 使用默认配置
        return {
            "searxng": {"instance": "https://searxng.hqgg.top:59826", "timeout": 10},
            "scraping": {"compress": True, "timeout": 30, "retry": 3},
            "images": {"download": True, "output_dir": "output/images", "max_size_mb": 10, "concurrency": 5},
            "output": {"include_metadata": True, "include_images": True}
        }

    with open(config_path, "r") as f:
        return yaml.safe_load(f)


async def cmd_search(args, config: dict):
    """搜索命令"""
    searcher = SearXNGSearcher(
        instance_url=config["searxng"]["instance"],
        timeout=config["searxng"]["timeout"]
    )

    limit = args.limit or config["searxng"]["result_count"]
    results = searcher.search(args.query, limit=limit)

    # 保存结果
    doc = Documentor()
    filepath = doc.save_search_results(
        query=args.query,
        results=results,
        topic=args.topic or ""
    )

    print(f"\n找到 {len(results)} 条结果")
    print(f"已保存到: {filepath}\n")

    for i, r in enumerate(results, 1):
        print(f"{i}. {r['title']}")
        print(f"   {r['url']}")
        print(f"   {r['snippet'][:100]}...")
        print()


async def cmd_fetch(args, config: dict):
    """抓取命令"""
    scraper = SmartScraper(
        compress=config["scraping"]["compress"],
        timeout=config["scraping"]["timeout"],
        retry=config["scraping"]["retry"]
    )

    print(f"正在抓取: {args.url}")
    result = scraper.fetch_smart(args.url)

    if not result["success"]:
        print("抓取失败！")
        return

    print(f"成功！使用方式: {result['method']}")
    print(f"标题: {result['title']}")
    print(f"内容长度: {len(result['content'])} 字符")
    print(f"发现图片: {len(result['images'])} 张")

    # 下载图片（如需要）
    if config["images"]["download"] and result["images"]:
        downloader = ImageDownloader(
            output_dir=config["images"]["output_dir"],
            max_size_mb=config["images"]["max_size_mb"],
            concurrency=config["images"]["concurrency"]
        )

        url_to_local = await downloader.download_images(result["images"])
        await downloader.close()

        print(f"下载图片: {len(url_to_local)}/{len(result['images'])} 成功")

        # 替换内容中的图片 URL
        if url_to_local:
            content = downloader.replace_images_in_markdown(result["content"], url_to_local)
            result["content"] = content
    else:
        result["images"] = []

    # 保存文档
    doc = Documentor()
    filepath = doc.save_page(
        url=result["url"],
        content=result["content"],
        title=result["title"],
        topic=args.topic or "",
        images=list(config["images"]["download"] and url_to_local.keys() or [])
    )

    print(f"\n已保存到: {filepath}")


async def cmd_batch(args, config: dict):
    """批量抓取命令"""
    # 读取关键词列表
    topics_file = Path(args.topics)
    if not topics_file.exists():
        print(f"文件不存在: {topics_file}")
        return

    topics = [line.strip() for line in topics_file.read_text(encoding="utf-8").splitlines() if line.strip()]

    print(f"开始批量调研，共 {len(topics)} 个课题\n")

    searcher = SearXNGSearcher(
        instance_url=config["searxng"]["instance"],
        timeout=config["searxng"]["timeout"]
    )

    scraper = SmartScraper(
        compress=config["scraping"]["compress"],
        timeout=config["scraping"]["timeout"],
        retry=config["scraping"]["retry"]
    )

    downloader = ImageDownloader(
        output_dir=config["images"]["output_dir"],
        max_size_mb=config["images"]["max_size_mb"],
        concurrency=config["images"]["concurrency"]
    )

    doc = Documentor()

    all_pages = []

    for topic in topics:
        print(f"\n{'='*60}")
        print(f"调研课题: {topic}")
        print(f"{'='*60}")

        # 搜索
        results = searcher.search(topic, limit=args.limit or 5)
        print(f"找到 {len(results)} 条结果")

        # 抓取前 N 个结果
        for i, r in enumerate(results[:args.depth or 3]):
            print(f"\n[{i+1}] 抓取: {r['url']}")
            result = scraper.fetch_smart(r["url"])

            if result["success"]:
                # 下载图片
                images_downloaded = {}
                if config["images"]["download"] and result["images"]:
                    images_downloaded = await downloader.download_images(result["images"])

                # 替换图片 URL
                if images_downloaded:
                    result["content"] = downloader.replace_images_in_markdown(
                        result["content"], images_downloaded
                    )

                # 保存页面
                page_path = doc.save_page(
                    url=result["url"],
                    content=result["content"],
                    title=result["title"] or r["title"],
                    topic=topic,
                    images=list(images_downloaded.keys())
                )
                print(f"    保存: {Path(page_path).name}")

                all_pages.append({
                    "topic": topic,
                    "title": result["title"] or r["title"],
                    "url": result["url"],
                    "content": result["content"]
                })
            else:
                print(f"    抓取失败")

    await downloader.close()

    # 生成汇总报告
    if all_pages:
        print(f"\n\n生成汇总报告...")
        report_path = doc.save_report(topic="批量调研", pages=all_pages)
        print(f"报告已保存: {report_path}")


async def cmd_research(args, config: dict):
    """一键调研命令"""
    print(f"开始调研课题: {args.topic}\n")

    searcher = SearXNGSearcher(
        instance_url=config["searxng"]["instance"],
        timeout=config["searxng"]["timeout"]
    )

    scraper = SmartScraper(
        compress=config["scraping"]["compress"],
        timeout=config["scraping"]["timeout"],
        retry=config["scraping"]["retry"]
    )

    downloader = ImageDownloader(
        output_dir=config["images"]["output_dir"],
        max_size_mb=config["images"]["max_size_mb"],
        concurrency=config["images"]["concurrency"]
    )

    doc = Documentor()

    # 第一步：搜索
    print("第一步：搜索...")
    results = searcher.search(args.topic, limit=args.depth or 10)
    print(f"找到 {len(results)} 条相关结果\n")

    # 保存搜索结果
    doc.save_search_results(query=args.topic, results=results, topic=args.topic)

    # 第二步：抓取页面
    print("第二步：抓取页面...")
    pages = []
    for i, r in enumerate(results):
        print(f"[{i+1}/{len(results)}] 抓取: {r['title'][:40]}...")
        result = scraper.fetch_smart(r["url"])

        if result["success"]:
            # 下载图片
            images_downloaded = {}
            if config["images"]["download"] and result["images"]:
                images_downloaded = await downloader.download_images(result["images"])

            # 替换图片 URL
            if images_downloaded:
                result["content"] = downloader.replace_images_in_markdown(
                    result["content"], images_downloaded
                )

            pages.append({
                "topic": args.topic,
                "title": result["title"] or r["title"],
                "url": result["url"],
                "content": result["content"],
                "images": list(images_downloaded.keys())
            })
            print(f"    ✓ 成功 (内容 {len(result['content'])} 字符, 图片 {len(images_downloaded)} 张)")
        else:
            print(f"    ✗ 失败")

    await downloader.close()

    # 第三步：生成报告
    print("\n第三步：生成报告...")
    report_path = doc.save_report(topic=args.topic, pages=pages)

    print(f"\n{'='*60}")
    print(f"调研完成！")
    print(f"课题: {args.topic}")
    print(f"抓取页面: {len(pages)}/{len(results)}")
    print(f"报告: {report_path}")
    print(f"{'='*60}")


def main():
    """主入口"""
    parser = argparse.ArgumentParser(
        description="Research Tool - 调研工具",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument("--config", default="configs/config.yaml", help="配置文件路径")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # search 命令
    p_search = subparsers.add_parser("search", help="搜索关键词")
    p_search.add_argument("query", help="搜索关键词")
    p_search.add_argument("--limit", type=int, help="结果数量")
    p_search.add_argument("--topic", help="所属课题")

    # fetch 命令
    p_fetch = subparsers.add_parser("fetch", help="抓取单个 URL")
    p_fetch.add_argument("url", help="目标 URL")
    p_fetch.add_argument("--topic", default="", help="所属课题")

    # batch 命令
    p_batch = subparsers.add_parser("batch", help="批量调研（从文件读取关键词列表）")
    p_batch.add_argument("--topics", required=True, help="关键词列表文件（每行一个）")
    p_batch.add_argument("--limit", type=int, default=5, help="每个课题抓取页面数")
    p_batch.add_argument("--depth", type=int, help="每个课题搜索结果数")

    # research 命令
    p_research = subparsers.add_parser("research", help="一键调研（搜索+抓取+报告）")
    p_research.add_argument("topic", help="调研课题/关键词")
    p_research.add_argument("--depth", type=int, default=10, help="搜索结果数量")

    args = parser.parse_args()

    # 设置日志
    setup_logging(args.log_level)

    # 加载配置
    config = load_config()

    # 切换到脚本目录
    script_dir = Path(__file__).parent.parent
    import os
    os.chdir(script_dir)

    # 执行命令
    if args.command == "search":
        asyncio.run(cmd_search(args, config))
    elif args.command == "fetch":
        asyncio.run(cmd_fetch(args, config))
    elif args.command == "batch":
        asyncio.run(cmd_batch(args, config))
    elif args.command == "research":
        asyncio.run(cmd_research(args, config))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
