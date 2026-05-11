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
import json
import logging
import shutil
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
from analyzer import ResearchAnalyzer


def filter_results_by_source_type(results: List[Dict], source_type: str) -> List[Dict]:
    if source_type == "all":
        return results
    filtered = []
    for item in results:
        item_source_type = item.get("source_type") or (
            "wechat" if "mp.weixin.qq.com" in item.get("url", "") else "web"
        )
        if item_source_type == source_type:
            filtered.append(item)
    return filtered


def setup_logging(level: str = "INFO"):
    """配置日志"""
    Path("logs").mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("logs/research-tool.log", encoding="utf-8")
        ]
    )


def load_config(config_path: str = "configs/config.yaml") -> dict:
    """加载配置文件"""
    config_path = Path(config_path)
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


def copy_delivery_file(src_path: str, dest_path: str) -> str:
    """复制报告到用户指定交付路径。"""
    source = Path(src_path)
    target = Path(dest_path)

    if target.is_dir() or str(dest_path).endswith(("/", "\\")):
        target.mkdir(parents=True, exist_ok=True)
        target = target / source.name
    else:
        target.parent.mkdir(parents=True, exist_ok=True)

    shutil.copy2(source, target)
    return str(target)


def make_topic_slug(topic: str) -> str:
    """把课题名转为适合归档的简短 slug。"""
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in topic.strip())
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "untitled-topic"


def build_delivery_bundle(
    bundle_dir: str,
    report_path: str,
    search_paths: List[str],
    page_paths: List[str],
    manifest: Dict | None = None,
) -> str:
    """生成交付包目录：报告 + 搜索结果 + 页面原文。"""
    bundle = Path(bundle_dir)
    bundle.mkdir(parents=True, exist_ok=True)

    report_target = bundle / "report"
    report_target.mkdir(exist_ok=True)
    delivered_report = report_target / Path(report_path).name
    shutil.copy2(report_path, delivered_report)

    searches_target = bundle / "searches"
    searches_target.mkdir(exist_ok=True)
    delivered_searches = []
    for path in search_paths:
        if path:
            target = searches_target / Path(path).name
            shutil.copy2(path, target)
            delivered_searches.append(str(target))

    pages_target = bundle / "pages"
    pages_target.mkdir(exist_ok=True)
    delivered_pages = []
    for path in page_paths:
        if path:
            target = pages_target / Path(path).name
            shutil.copy2(path, target)
            delivered_pages.append(str(target))

    if manifest is not None:
        manifest_path = bundle / "manifest.json"
        manifest_payload = {
            **manifest,
            "report_name": delivered_report.name,
            "report": str(delivered_report),
            "searches": delivered_searches,
            "pages": delivered_pages,
        }
        manifest_path.write_text(json.dumps(manifest_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return str(bundle)


async def cmd_search(args, config: dict):
    """搜索命令"""
    searcher = SearXNGSearcher(
        instance_url=config["searxng"]["instance"],
        timeout=config["searxng"]["timeout"]
    )

    limit = args.limit or config["searxng"]["result_count"]
    results = searcher.search(args.query, limit=limit)
    results = filter_results_by_source_type(results, args.source_type)

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
        prefix = "[微信] " if "mp.weixin.qq.com" in r.get("url", "") else ""
        print(f"{i}. {prefix}{r['title']}")
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
        if result.get("error"):
            print(f"原因: {result['error']}")
        return

    print(f"成功！使用方式: {result['method']}")
    if result.get("warning"):
        print(f"警告: {result['warning']}")
    print(f"标题: {result['title']}")
    print(f"内容长度: {len(result['content'])} 字符")
    print(f"发现图片: {len(result['images'])} 张")

    url_to_local = {}

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
        images=list(config["images"]["download"] and url_to_local.keys() or []),
        metadata={
            "source_type": result.get("source_type", "web"),
            "fetch_method": result.get("method", "none"),
        },
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
    search_paths = []
    page_paths = []
    attempted_count = 0
    success_count = 0
    failed_count = 0

    for topic in topics:
        print(f"\n{'='*60}")
        print(f"调研课题: {topic}")
        print(f"{'='*60}")

        # 搜索
        results = searcher.search(topic, limit=args.limit or 5)
        results = filter_results_by_source_type(results, args.source_type)
        print(f"找到 {len(results)} 条结果")
        search_paths.append(doc.save_search_results(query=topic, results=results, topic=topic))

        # 抓取前 N 个结果
        for i, r in enumerate(results[:args.depth or 3]):
            attempted_count += 1
            print(f"\n[{i+1}] 抓取: {r['url']}")
            result = scraper.fetch_smart(r["url"])

            if result["success"]:
                success_count += 1
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
                    images=list(images_downloaded.keys()),
                    metadata={
                        "source_type": result.get("source_type", "web"),
                        "fetch_method": result.get("method", "none"),
                    },
                )
                page_paths.append(page_path)
                print(f"    保存: {Path(page_path).name}")
                if result.get("warning"):
                    print(f"    警告: {result['warning']}")

                all_pages.append({
                    "topic": topic,
                    "title": result["title"] or r["title"],
                    "url": result["url"],
                    "content": result["content"],
                    "source_type": "wechat" if "mp.weixin.qq.com" in result["url"] else "web",
                    "fetch_method": result.get("method", "none"),
                    "warning": result.get("warning", ""),
                })
            else:
                failed_count += 1
                reason = result.get("error") or "unknown error"
                print(f"    抓取失败: {reason}")

    await downloader.close()

    # 生成汇总报告
    if all_pages:
        print(f"\n\n生成汇总报告...")
        selected_pages = all_pages[:args.max_pages] if args.max_pages else all_pages
        analysis = ResearchAnalyzer().analyze("批量调研", selected_pages)
        report_path = doc.save_report(
            topic="批量调研",
            pages=selected_pages,
            analysis=analysis,
            filename=args.report_name,
            stats={
                "attempted_count": attempted_count,
                "success_count": success_count,
                "failed_count": failed_count,
            },
        )
        if args.bundle_dir:
            bundle_manifest = {
                "topic": "批量调研",
                "topic_slug": make_topic_slug("批量调研"),
                "generated_at": __import__("datetime").datetime.now().isoformat(),
                "report_pages_count": len(selected_pages),
                "search_result_files_count": len(search_paths),
                "page_files_count": len(page_paths),
                "attempted_count": attempted_count,
                "success_count": success_count,
                "failed_count": failed_count,
            }
            bundle_path = build_delivery_bundle(args.bundle_dir, report_path, search_paths, page_paths, manifest=bundle_manifest)
            print(f"交付包已保存: {bundle_path}")
        elif args.output:
            report_path = copy_delivery_file(report_path, args.output)
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
    page_paths = []
    attempted_count = 0
    success_count = 0
    failed_count = 0

    # 第一步：搜索
    print("第一步：搜索...")
    results = searcher.search(args.topic, limit=args.depth or 10)
    results = filter_results_by_source_type(results, args.source_type)
    print(f"找到 {len(results)} 条相关结果\n")

    # 保存搜索结果
    search_path = doc.save_search_results(query=args.topic, results=results, topic=args.topic)

    # 第二步：抓取页面
    print("第二步：抓取页面...")
    pages = []
    for i, r in enumerate(results):
        attempted_count += 1
        print(f"[{i+1}/{len(results)}] 抓取: {r['title'][:40]}...")
        result = scraper.fetch_smart(r["url"])

        if result["success"]:
            success_count += 1
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
                "images": list(images_downloaded.keys()),
                "source_type": "wechat" if "mp.weixin.qq.com" in result["url"] else "web",
                "fetch_method": result.get("method", "none"),
                "warning": result.get("warning", ""),
            })
            page_paths.append(
                doc.save_page(
                    url=result["url"],
                    content=result["content"],
                    title=result["title"] or r["title"],
                    topic=args.topic,
                    images=list(images_downloaded.keys()),
                    metadata={
                        "source_type": result.get("source_type", "web"),
                        "fetch_method": result.get("method", "none"),
                    },
                )
            )
            print(f"    ✓ 成功 (内容 {len(result['content'])} 字符, 图片 {len(images_downloaded)} 张)")
            if result.get("warning"):
                print(f"    警告: {result['warning']}")
        else:
            failed_count += 1
            reason = result.get("error") or "unknown error"
            print(f"    ✗ 失败: {reason}")

    await downloader.close()

    # 第三步：生成报告
    print("\n第三步：生成报告...")
    selected_pages = pages[:args.max_pages] if args.max_pages else pages
    analysis = ResearchAnalyzer().analyze(args.topic, selected_pages)
    report_path = doc.save_report(
        topic=args.topic,
        pages=selected_pages,
        analysis=analysis,
        filename=args.report_name,
        stats={
            "attempted_count": attempted_count,
            "success_count": success_count,
            "failed_count": failed_count,
        },
    )
    if args.bundle_dir:
        bundle_manifest = {
            "topic": args.topic,
            "topic_slug": make_topic_slug(args.topic),
            "generated_at": __import__("datetime").datetime.now().isoformat(),
            "report_pages_count": len(selected_pages),
            "search_result_files_count": 1,
            "page_files_count": len(page_paths),
            "attempted_count": attempted_count,
            "success_count": success_count,
            "failed_count": failed_count,
        }
        bundle_path = build_delivery_bundle(args.bundle_dir, report_path, [search_path], page_paths, manifest=bundle_manifest)
        print(f"交付包已保存: {bundle_path}")
    elif args.output:
        report_path = copy_delivery_file(report_path, args.output)

    print(f"\n{'='*60}")
    print(f"调研完成！")
    print(f"课题: {args.topic}")
    print(f"抓取页面: {len(pages)}/{len(results)}")
    print(f"报告: {report_path}")
    print(f"{'='*60}")


async def cmd_smoke(args, config: dict):
    """最小自检命令"""
    test_url = "https://example.com"
    print(f"SMOKE: fetch {test_url}")

    scraper = SmartScraper(
        compress=config["scraping"]["compress"],
        timeout=config["scraping"]["timeout"],
        retry=config["scraping"]["retry"]
    )

    result = scraper.fetch_smart(test_url)
    if not result["success"]:
        reason = result.get("error") or "unknown error"
        print(f"SMOKE_FAIL: {reason}")
        raise SystemExit(1)

    if not result.get("content", "").strip():
        print("SMOKE_FAIL: empty content")
        raise SystemExit(1)

    print(f"SMOKE_METHOD: {result['method']}")
    if result.get("warning"):
        print(f"SMOKE_WARNING: {result['warning']}")
    print("SMOKE_OK")


def main():
    """主入口"""
    parser = argparse.ArgumentParser(
        description="Research Tool - 调研工具",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument("--config", default="configs/config.yaml", help="配置文件路径（全局参数，必须放在子命令前）")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # search 命令
    p_search = subparsers.add_parser("search", help="搜索关键词")
    p_search.add_argument("query", help="搜索关键词")
    p_search.add_argument("--limit", type=int, help="结果数量")
    p_search.add_argument("--topic", help="所属课题")
    p_search.add_argument("--source-type", choices=["all", "wechat", "web"], default="all", help="来源类型过滤")

    # fetch 命令
    p_fetch = subparsers.add_parser("fetch", help="抓取单个 URL")
    p_fetch.add_argument("url", help="目标 URL")
    p_fetch.add_argument("--topic", default="", help="所属课题")

    # smoke 命令
    subparsers.add_parser("smoke", help="最小自检（验证基础抓取链路）")

    # batch 命令
    p_batch = subparsers.add_parser("batch", help="批量调研（从文件读取关键词列表）")
    p_batch.add_argument("--topics", required=True, help="关键词列表文件（每行一个）")
    p_batch.add_argument("--limit", type=int, default=5, help="每个课题抓取页面数")
    p_batch.add_argument("--depth", type=int, help="每个课题搜索结果数")
    p_batch.add_argument("--max-pages", type=int, help="最终报告最多收录多少篇页面")
    p_batch.add_argument("--source-type", choices=["all", "wechat", "web"], default="all", help="来源类型过滤")
    p_batch.add_argument("--output", help="报告交付路径；可指定文件或目录")
    p_batch.add_argument("--bundle-dir", help="交付包目录；包含报告、搜索结果和页面原文")
    p_batch.add_argument("--report-name", help="自定义报告文件名（默认自动带时间戳）")

    # research 命令
    p_research = subparsers.add_parser("research", help="一键调研（搜索+抓取+报告）")
    p_research.add_argument("topic", help="调研课题/关键词")
    p_research.add_argument("--depth", type=int, default=10, help="搜索结果数量")
    p_research.add_argument("--max-pages", type=int, help="最终报告最多收录多少篇页面")
    p_research.add_argument("--source-type", choices=["all", "wechat", "web"], default="all", help="来源类型过滤")
    p_research.add_argument("--output", help="报告交付路径；可指定文件或目录")
    p_research.add_argument("--bundle-dir", help="交付包目录；包含报告、搜索结果和页面原文")
    p_research.add_argument("--report-name", help="自定义报告文件名（默认自动带时间戳）")

    args = parser.parse_args()

    # 设置日志
    setup_logging(args.log_level)

    # 加载配置
    config = load_config(args.config)

    # 切换到脚本目录
    script_dir = Path(__file__).parent.parent
    import os
    os.chdir(script_dir)

    # 执行命令
    if args.command == "search":
        asyncio.run(cmd_search(args, config))
    elif args.command == "fetch":
        asyncio.run(cmd_fetch(args, config))
    elif args.command == "smoke":
        asyncio.run(cmd_smoke(args, config))
    elif args.command == "batch":
        asyncio.run(cmd_batch(args, config))
    elif args.command == "research":
        asyncio.run(cmd_research(args, config))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
