from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.main import filter_results_by_source_type


def test_filter_results_by_source_type_all_returns_all():
    results = [
        {"url": "https://mp.weixin.qq.com/s/a", "title": "wechat"},
        {"url": "https://example.com", "title": "web"},
    ]

    assert filter_results_by_source_type(results, "all") == results


def test_filter_results_by_source_type_wechat_only():
    results = [
        {"url": "https://mp.weixin.qq.com/s/a", "title": "wechat"},
        {"url": "https://example.com", "title": "web"},
        {"url": "https://example.org", "title": "explicit wechat", "source_type": "wechat"},
    ]

    assert filter_results_by_source_type(results, "wechat") == [
        {"url": "https://mp.weixin.qq.com/s/a", "title": "wechat"},
        {"url": "https://example.org", "title": "explicit wechat", "source_type": "wechat"},
    ]


def test_filter_results_by_source_type_web_only():
    results = [
        {"url": "https://mp.weixin.qq.com/s/a", "title": "wechat"},
        {"url": "https://example.com", "title": "web"},
        {"url": "https://mp.weixin.qq.com/s/b", "title": "explicit web", "source_type": "web"},
    ]

    assert filter_results_by_source_type(results, "web") == [
        {"url": "https://example.com", "title": "web"},
        {"url": "https://mp.weixin.qq.com/s/b", "title": "explicit web", "source_type": "web"},
    ]
