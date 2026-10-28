"""Build RSS 2.0 feeds for news sites without an official 港聞 feed.

Sources:
    hk01: 香港01 港聞 zone (web-data.api.hk01.com JSON API)
    oncc: 東網 港聞 (hk.on.cc news index HTML)
    pulse: Pulse HK (pulsehknews.com WordPress REST API)

Standard library only. Writes one XML file per source into the output folder.

Usage:
    python3 make_feeds.py --out docs
"""

import argparse
import html
import json
import logging
import re
import sys
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from typing import Callable, Dict, List
from urllib.error import URLError
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
)
HKT = timezone(timedelta(hours=8))
HK01_API = "https://web-data.api.hk01.com/v2/feed/zone/1?bucketId=00000&offset={offset}"
HK01_FIRST_OFFSET = 99999999990
HK01_PAGES = 4
ONCC_INDEX = "https://hk.on.cc/hk/news/index.html"
ONCC_BASE = "https://hk.on.cc/hk/bkn"
# The site's HTML and /feed/ sit behind a bot check; the public WordPress REST API does not.
PULSE_API = (
    "https://pulsehknews.com/wp-json/wp/v2/posts"
    "?per_page=30&_fields=date_gmt,link,title,excerpt"
)
DESCRIPTION_CHARS = 200

Item = Dict[str, object]


def fetch_text(url: str) -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def hk01_items() -> List[Item]:
    """Return the latest articles of the 香港01 港聞 zone."""
    items: List[Item] = []
    offset = HK01_FIRST_OFFSET
    for _ in range(HK01_PAGES):
        page = json.loads(fetch_text(HK01_API.format(offset=offset)))
        for entry in page.get("items", []):
            data = entry.get("data", {})
            if not data.get("title") or not data.get("publishTime"):
                continue
            items.append({
                "title": data["title"],
                "link": data.get("canonicalUrl") or data.get("publishUrl"),
                "date": datetime.fromtimestamp(data["publishTime"], tz=timezone.utc),
                "description": (data.get("description") or "")[:DESCRIPTION_CHARS],
            })
        offset = page.get("nextOffset")
        if not offset:
            break
    return items


def oncc_items() -> List[Item]:
    """Return the Hong Kong articles listed on the 東網 news index page.

    The index also lists 中國/台灣/澳門 stories; only district="香港" is kept.
    """
    page = fetch_text(ONCC_INDEX)
    items: List[Item] = []
    pattern = re.compile(
        r'<div class="focus[^"]*"[^>]*district="([^"]*)"[^>]*pubdate="(\d{14})"[^>]*url="([^"]+)"[^>]*>'
    )
    for match in pattern.finditer(page):
        district, pubdate, path = match.groups()
        if district != "香港":
            continue
        following = page[match.end():match.end() + 2000]
        title = re.search(r'(?:title|alt)="([^"]+)"', following)
        if not title:
            continue
        items.append({
            "title": html.unescape(title.group(1)).replace("　", " "),
            "link": ONCC_BASE + path,
            "date": datetime.strptime(pubdate, "%Y%m%d%H%M%S").replace(tzinfo=HKT),
            "description": "",
        })
    return items


def _strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(text or ""))).strip()


def pulse_items() -> List[Item]:
    """Return the latest posts of Pulse HK (all categories)."""
    items: List[Item] = []
    for post in json.loads(fetch_text(PULSE_API)):
        items.append({
            "title": _strip_html(post["title"]["rendered"]),
            "link": post["link"],
            "date": datetime.fromisoformat(post["date_gmt"]).replace(tzinfo=timezone.utc),
            "description": _strip_html(post["excerpt"]["rendered"])[:DESCRIPTION_CHARS],
        })
    return items


def to_rss(title: str, site: str, items: List[Item]) -> str:
    """Serialize items as an RSS 2.0 document, newest first, without duplicate links."""
    seen, rows = set(), []
    for item in sorted(items, key=lambda i: i["date"], reverse=True):
        if item["link"] in seen:
            continue
        seen.add(item["link"])
        rows.append(
            "<item>"
            f"<title>{escape(str(item['title']))}</title>"
            f"<link>{escape(str(item['link']))}</link>"
            f"<guid isPermaLink=\"true\">{escape(str(item['link']))}</guid>"
            f"<pubDate>{format_datetime(item['date'])}</pubDate>"
            f"<description>{escape(str(item['description']))}</description>"
            "</item>"
        )
    now = format_datetime(datetime.now(timezone.utc))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
        f"<title>{escape(title)}</title><link>{escape(site)}</link>"
        f"<description>{escape(title)}（非公式フィード）</description>"
        f"<language>zh-HK</language><lastBuildDate>{now}</lastBuildDate>\n"
        + "\n".join(rows)
        + "\n</channel></rss>\n"
    )


SOURCES: Dict[str, Dict[str, object]] = {
    "hk01-news.xml": {"title": "香港01 港聞", "site": "https://www.hk01.com/zone/1/港聞", "fetch": hk01_items},
    "oncc-news.xml": {"title": "東網 港聞", "site": ONCC_INDEX, "fetch": oncc_items},
    "pulsehk.xml": {"title": "Pulse HK", "site": "https://pulsehknews.com/", "fetch": pulse_items},
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("docs"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args.out.mkdir(parents=True, exist_ok=True)

    failures = 0
    for filename, source in SOURCES.items():
        fetch: Callable[[], List[Item]] = source["fetch"]  # type: ignore[assignment]
        try:
            items = fetch()
        except (URLError, TimeoutError, ValueError, KeyError) as e:
            # Keep the previous XML so readers do not see an empty feed.
            logger.error("%s failed: %s", filename, e)
            failures += 1
            continue
        if not items:
            logger.error("%s: no items parsed; page layout may have changed", filename)
            failures += 1
            continue
        xml = to_rss(str(source["title"]), str(source["site"]), items)
        (args.out / filename).write_text(xml, encoding="utf-8")
        logger.info("%s: %d items", filename, len(items))
    return 1 if failures == len(SOURCES) else 0


if __name__ == "__main__":
    sys.exit(main())
