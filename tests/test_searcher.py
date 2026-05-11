from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.searcher import SearXNGSearcher


class DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_search_filters_empty_urls_and_deduplicates(monkeypatch):
    searcher = SearXNGSearcher("https://example.com")

    payload = {
        "results": [
            {"title": "A", "url": "https://a.com", "content": "first"},
            {"title": "A-dup", "url": "https://a.com", "content": "dup"},
            {"title": "Blank", "url": "   ", "content": "blank"},
            {"title": "B", "url": "https://b.com", "description": "second"},
        ]
    }

    def fake_get(url, params, timeout):
        return DummyResponse(payload)

    monkeypatch.setattr(searcher.session, "get", fake_get)

    results = searcher.search("test", limit=10)

    assert results == [
        {"title": "A", "url": "https://a.com", "snippet": "first"},
        {"title": "B", "url": "https://b.com", "snippet": "second"},
    ]


def test_search_respects_limit_after_filtering(monkeypatch):
    searcher = SearXNGSearcher("https://example.com")

    payload = {
        "results": [
            {"title": "A", "url": "https://a.com", "content": "first"},
            {"title": "A-dup", "url": "https://a.com", "content": "dup"},
            {"title": "B", "url": "https://b.com", "content": "second"},
            {"title": "C", "url": "https://c.com", "content": "third"},
        ]
    }

    def fake_get(url, params, timeout):
        return DummyResponse(payload)

    monkeypatch.setattr(searcher.session, "get", fake_get)

    results = searcher.search("test", limit=2)

    assert results == [
        {"title": "A", "url": "https://a.com", "snippet": "first"},
        {"title": "B", "url": "https://b.com", "snippet": "second"},
    ]
