# -*- coding: utf-8 -*-
"""RSS 피드에서 경제/AI/코인 뉴스를 수집하고, 투자자 관심도 기준으로 선별한다.

선별 원칙: 시청자는 "그래서 돈이 어디로 가고 있는데?"를 묻고 있다.
거시경제·AI/반도체·기업 이벤트·코인 뉴스에 가점, 일반 테크 흥미성 기사는 제외.
"""
import time
from urllib.parse import urlparse

import feedparser

from config import (NEWS_FEEDS, NEWS_PER_CATEGORY,
                    NEWS_INCLUDE_KEYWORDS, NEWS_EXCLUDE_KEYWORDS)

# 일부 국내 피드는 기본 UA를 차단하므로 브라우저 UA를 흉내낸다
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def score_title(title: str) -> int:
    """투자 관련성 점수. 0 이하는 콘텐츠에 쓰지 않는다."""
    t = title.lower()
    score = 0
    for kw, w in NEWS_INCLUDE_KEYWORDS.items():
        if kw in t:
            score += w
    for kw in NEWS_EXCLUDE_KEYWORDS:
        if kw in t:
            score -= 5
    return score


def collect_news(feeds: dict[str, list[str]] | None = None,
                 per_category: int | None = None) -> list[dict]:
    feeds = feeds or NEWS_FEEDS
    per_category = per_category or NEWS_PER_CATEGORY

    rows = []
    for category, urls in feeds.items():
        items = []
        for url in urls:
            try:
                parsed = feedparser.parse(url, agent=USER_AGENT)
            except Exception:
                continue
            source = urlparse(url).netloc.replace("www.", "")
            for e in parsed.entries[:30]:
                title = e.get("title", "").strip()
                if not title:
                    continue
                published = ""
                if getattr(e, "published_parsed", None):
                    published = time.strftime("%Y-%m-%d %H:%M", e.published_parsed)
                items.append({
                    "category": category,
                    "title": title,
                    "link": e.get("link", ""),
                    "source": source,
                    "published": published,
                    "score": score_title(title),
                })
        # 투자 관련성 점수 > 0 만 채택, 점수순 → 최신순 정렬
        items = [i for i in items if i["score"] > 0]
        items.sort(key=lambda x: (x["score"], x["published"]), reverse=True)
        rows.extend(items[:per_category])
    return rows


if __name__ == "__main__":
    for r in collect_news():
        print(f"[{r['category']}] ({r['score']}점) {r['title']} ({r['source']})")
