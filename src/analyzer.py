"""
调研分析模块
对已抓取页面做最小必要的结构化整理，生成可用于正式报告的摘要、主题、证据与建议。
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Dict, List
from urllib.parse import urlparse


class ResearchAnalyzer:
    """基于规则的轻量调研分析器。"""

    STOPWORDS = {
        "the", "and", "for", "that", "with", "from", "this", "were", "have", "has", "will", "into",
        "their", "about", "after", "before", "through", "than", "then", "they", "them", "these", "those",
        "such", "using", "used", "use", "also", "more", "most", "many", "much", "some", "over",
        "under", "within", "without", "because", "while", "where", "when", "what", "which", "whose", "been",
        "being", "could", "should", "would", "there", "here", "your", "you", "ours", "ourselves",
        "research", "report", "analysis", "content", "source", "result", "page", "pages", "data", "information",
        "研究", "报告", "分析", "相关", "以及", "通过", "可以", "进行", "一个", "我们", "他们", "这些", "那些",
        "如果", "因为", "所以", "需要", "使用", "当前", "其中", "内容", "页面", "数据", "信息", "来源", "结果",
        "美国", "batio"
    }

    SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？.!?])\s+|\n+")
    TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z\-]{3,}|[\u4e00-\u9fff]{2,}")

    def analyze(self, topic: str, pages: List[Dict]) -> Dict:
        valid_pages = [page for page in pages if page.get("content")]
        source_domains = [urlparse(page.get("url", "")).netloc for page in valid_pages if page.get("url")]
        domain_counter = Counter(domain for domain in source_domains if domain)
        source_type_counter = Counter(page.get("source_type", "web") for page in valid_pages)

        keyword_counter = Counter()
        findings = []
        source_records = []

        for page in valid_pages:
            title = page.get("title") or "Untitled"
            url = page.get("url") or ""
            domain = urlparse(url).netloc
            content = self._normalize_text(page.get("content", ""))
            analysis_content = content[:1200]
            sentences = self._sentences(analysis_content)
            top_sentence = self._pick_representative_sentence(sentences)
            if top_sentence:
                findings.append({
                    "title": title,
                    "url": url,
                    "domain": domain,
                    "finding": top_sentence,
                })
            source_records.append({
                "title": title,
                "url": url,
                "domain": domain,
                "source_type": page.get("source_type", "web"),
                "sentence_count": len(sentences),
                "content_length": len(content),
            })
            keyword_counter.update(self._extract_keywords(title + "\n" + analysis_content))

        top_keywords = [word for word, _ in keyword_counter.most_common(8)]
        recurring_themes = self._group_themes(findings)
        executive_summary = self._build_executive_summary(topic, valid_pages, domain_counter, top_keywords, recurring_themes)
        key_takeaways = self._build_key_takeaways(recurring_themes)
        recommendations = self._build_recommendations(topic, recurring_themes, domain_counter)
        source_assessment = self._build_source_assessment(source_records)
        source_type_summary = dict(source_type_counter)
        wechat_sources = [
            {
                "title": page.get("title") or "Untitled",
                "url": page.get("url") or "",
            }
            for page in valid_pages
            if page.get("source_type") == "wechat"
        ]

        return {
            "summary": executive_summary,
            "top_keywords": top_keywords,
            "source_domains": domain_counter.most_common(),
            "source_type_summary": source_type_summary,
            "wechat_sources": wechat_sources,
            "findings": findings,
            "recurring_themes": recurring_themes,
            "key_takeaways": key_takeaways,
            "recommendations": recommendations,
            "source_assessment": source_assessment,
        }

    def _normalize_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    def _sentences(self, content: str) -> List[str]:
        return [part.strip() for part in self.SENTENCE_SPLIT_RE.split(content) if part.strip()]

    def _pick_representative_sentence(self, sentences: List[str]) -> str:
        for sentence in sentences:
            if len(sentence) >= 40:
                return sentence[:220] + ("..." if len(sentence) > 220 else "")
        if sentences:
            joined = sentences[0]
            return joined[:220] + ("..." if len(joined) > 220 else "")
        return ""

    def _extract_keywords(self, text: str) -> List[str]:
        keywords = []
        for token in self.TOKEN_RE.findall(text.lower()):
            if token in self.STOPWORDS:
                continue
            if len(token) < 2:
                continue
            keywords.append(token)
        return keywords

    def _group_themes(self, findings: List[Dict]) -> List[Dict]:
        theme_map: Dict[str, Dict] = {}
        for item in findings:
            keywords = self._extract_keywords(item["finding"])
            if not keywords:
                continue
            theme_key = keywords[0]
            bucket = theme_map.setdefault(theme_key, {"keyword": theme_key, "evidence": []})
            bucket["evidence"].append({
                "title": item["title"],
                "url": item["url"],
                "domain": item.get("domain", ""),
                "text": item["finding"],
            })

        themes = []
        for theme in theme_map.values():
            theme["source_count"] = len({e["url"] for e in theme["evidence"] if e.get("url")})
            themes.append(theme)
        themes.sort(key=lambda x: (x["source_count"], len(x["evidence"])), reverse=True)
        return themes[:5]

    def _build_executive_summary(self, topic: str, pages: List[Dict], domain_counter: Counter, top_keywords: List[str], themes: List[Dict]) -> str:
        lines = [f"本次围绕“{topic}”共整理 {len(pages)} 个来源。"]
        if domain_counter:
            top_domains = "、".join([f"{domain}({count})" for domain, count in domain_counter.most_common(5)])
            lines.append(f"来源域名主要集中在：{top_domains}。")
        if any(page.get("source_type") == "wechat" for page in pages):
            wechat_count = sum(1 for page in pages if page.get("source_type") == "wechat")
            lines.append(f"其中微信公众号来源 {wechat_count} 篇，已优先按微信正文结构清理。")
        if top_keywords:
            lines.append(f"高频关键词包括：{'、'.join(top_keywords[:6])}。")
        if themes:
            lines.append("交叉整理后，当前最值得关注的主题包括：")
            for idx, theme in enumerate(themes[:3], 1):
                evidence = theme["evidence"][0]["text"] if theme["evidence"] else ""
                lines.append(f"{idx}. 主题“{theme['keyword']}”（涉及 {theme['source_count']} 个来源）：{evidence}")
        return "\n".join(lines)

    def _build_key_takeaways(self, themes: List[Dict]) -> List[str]:
        takeaways = []
        for theme in themes[:5]:
            if not theme["evidence"]:
                continue
            lead = theme["evidence"][0]["text"]
            takeaways.append(f"围绕“{theme['keyword']}”的表述在 {theme['source_count']} 个来源中重复出现，说明它是当前资料中的高频关注点：{lead}")
        return takeaways

    def _build_recommendations(self, topic: str, themes: List[Dict], domain_counter: Counter) -> List[str]:
        recommendations = []
        if themes:
            recommendations.append(f"优先围绕“{themes[0]['keyword']}”补充更权威来源，以验证其是否构成“{topic}”的主线结论。")
        if len(domain_counter) <= 2:
            recommendations.append("当前来源域名较集中，建议补充不同类型来源（官方、媒体、行业报告）以降低单一来源偏差。")
        if len(themes) >= 2:
            recommendations.append(f"建议对“{themes[0]['keyword']}”与“{themes[1]['keyword']}”做并列比较，提炼它们之间的因果关系或先后顺序。")
        if not recommendations:
            recommendations.append("当前可用页面较少，建议先扩充来源后再形成正式结论。")
        return recommendations

    def _build_source_assessment(self, source_records: List[Dict]) -> List[Dict]:
        grouped = defaultdict(lambda: {"count": 0, "sample_titles": [], "avg_length": 0, "source_type": "web"})
        for record in source_records:
            domain = record["domain"] or "unknown"
            grouped[domain]["count"] += 1
            grouped[domain]["sample_titles"].append(record["title"])
            grouped[domain]["avg_length"] += record["content_length"]
            grouped[domain]["source_type"] = record.get("source_type", grouped[domain]["source_type"])

        assessments = []
        for domain, info in grouped.items():
            avg_length = int(info["avg_length"] / info["count"]) if info["count"] else 0
            assessments.append({
                "domain": domain,
                "count": info["count"],
                "avg_length": avg_length,
                "sample_titles": info["sample_titles"][:2],
                "source_type": info["source_type"],
            })
        assessments.sort(key=lambda x: x["count"], reverse=True)
        return assessments
