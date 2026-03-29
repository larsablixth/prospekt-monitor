"""
scrapers/nasdaq_rss.py — Bevakar Nasdaq officiella RSS-flöden.

Filtrerar på nyckelord som indikerar ny notering på First North eller Main Market Sverige.
"""

import hashlib
import logging

import feedparser

RSS_FEEDS = {
    "first_north": "https://api.news.eu.nasdaq.com/news/rss/firstNorthNotices",
    "main_market":  "https://api.news.eu.nasdaq.com/news/rss/mainMarketNotices",
    "nordic_news":  "https://api.news.eu.nasdaq.com/news/rss/nasdaqNordicNews",
}

# Nyckelord som indikerar ny notering (svenska + engelska)
LISTING_KEYWORDS = [
    "upptas till handel",
    "notering",
    "first day of trading",
    "admitted to trading",
    "new listing",
    "ipo",
    "erbjudande",
    "emission",
    "börsnot",
]

# Uteslut rena tekniska/IT-meddelanden
EXCLUDE_KEYWORDS = [
    "technical notice",
    "it notice",
    "trading halt",
    "trading resumed",
    "market notice",
]

log = logging.getLogger(__name__)


def _doc_id(entry_id: str) -> str:
    return "nasdaq_" + hashlib.md5(entry_id.encode()).hexdigest()[:12]


def _is_listing(title: str, summary: str) -> bool:
    text = (title + " " + summary).lower()
    if any(kw in text for kw in EXCLUDE_KEYWORDS):
        return False
    return any(kw in text for kw in LISTING_KEYWORDS)


def fetch_new(conn, config: dict) -> list[dict]:
    """
    Returnerar lista med nya noteringsnyheter från Nasdaq RSS.
    Dessa har ingen PDF — url pekar på nyhetssidan.
    """
    from db import is_new

    new_docs = []

    for feed_name, feed_url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(feed_url)
        except Exception as e:
            log.error(f"Nasdaq RSS ({feed_name}): fel vid hämtning: {e}")
            continue

        for entry in feed.entries:
            title   = entry.get("title", "")
            summary = entry.get("summary", "")
            link    = entry.get("link", "")
            entry_id = entry.get("id", link)

            if not _is_listing(title, summary):
                continue

            doc_id = _doc_id(entry_id)
            if not is_new(conn, doc_id):
                continue

            # Försök extrahera bolagsnamn ur titeln
            company = title.split(":")[0].strip() if ":" in title else title[:60]

            log.info(f"Nasdaq RSS ({feed_name}): ny notering — {company}")
            new_docs.append({
                "id":         doc_id,
                "source":     f"Nasdaq/{feed_name}",
                "company":    company,
                "doc_type":   "rss_notice",
                "url":        link,
                "local_path": None,
            })

    return new_docs
