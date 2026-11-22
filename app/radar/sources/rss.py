"""RSS / Atom connector: any platform that publishes a feed (gov.pl news, university and municipality sites,
WordPress, Blogger, YouTube channels, RSS bridges for social profiles…) becomes a source with config only.

Built to be polled often without burning rate limits:
- conditional GET per feed (If-None-Match / If-Modified-Since): an unchanged feed costs one 304 and no parsing
- per-host minimum interval (radar.sources.http.throttle) and the shared retry/backoff with Retry-After
- the cursor keeps ETag, Last-Modified and the last 500 entry ids per feed, so a re-run only ingests new entries;
  ingest is idempotent anyway (source, external_id, content hash)

options:
  feeds: list of URLs, and/or ${RADAR_RSS_FEEDS} (comma separated) so feeds can be added at deploy time
  min_interval_s: seconds between requests to the same host (default 2)
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from email.utils import parsedate_to_datetime

from radar.sources.base import Envelope, Page, PullConnector
from radar.sources.http import client, request, throttle

ATOM = "{http://www.w3.org/2005/Atom}"
TAG = re.compile(r"<[^>]+>")


def _text(el, *names) -> str:
    for n in names:
        x = el.find(n)
        if x is not None:
            if n.endswith("link") and x.get("href"):
                return x.get("href")
            if (x.text or "").strip():
                return x.text.strip()
    return ""


def parse_feed(body: bytes) -> list[dict]:
    root = ET.fromstring(body)
    items = root.findall(".//item") or root.findall(f".//{ATOM}entry")
    out = []
    for it in items:
        link = _text(it, "link", f"{ATOM}link")
        guid = _text(it, "guid", f"{ATOM}id") or link
        title = _text(it, "title", f"{ATOM}title")
        desc = _text(it, "{http://purl.org/rss/1.0/modules/content/}encoded", "description", f"{ATOM}content", f"{ATOM}summary")
        date = _text(it, "pubDate", f"{ATOM}published", f"{ATOM}updated")
        try:
            year = parsedate_to_datetime(date).year if date and not date[:4].isdigit() else int(date[:4]) if date else None
        except (TypeError, ValueError):
            year = None
        author = _text(it, "author", f"{ATOM}author/{ATOM}name", "{http://purl.org/dc/elements/1.1/}creator")
        cats = [c.text.strip() for c in it.findall("category") if (c.text or "").strip()] + [c.get("term") for c in it.findall(f"{ATOM}category") if c.get("term")]
        out.append({"id": guid, "title": TAG.sub(" ", title).strip(), "description": re.sub(r"\s+", " ", TAG.sub(" ", desc)).strip(),
                    "url": link, "published": date, "year": year, "author_org": author, "keywords": cats[:10]})
    return out


class RssConnector(PullConnector):
    def feeds(self) -> list[str]:
        feeds = list(self.spec.opt("feeds", []) or [])
        extra = self.spec.opt("feeds_env", "") or ""
        feeds += [u.strip() for u in str(extra).split(",") if u.strip()]
        return [f for f in dict.fromkeys(feeds) if f.startswith(("http://", "https://"))]

    def fetch(self, cursor: str | None) -> Iterator[Page]:
        state = json.loads(cursor) if cursor else {}
        gap = float(self.spec.opt("min_interval_s", 2))
        with client(self.spec.opt("headers", {})) as c:
            for url in self.feeds():
                st = state.get(url, {})
                headers = {}
                if st.get("etag"):
                    headers["If-None-Match"] = st["etag"]
                if st.get("modified"):
                    headers["If-Modified-Since"] = st["modified"]
                throttle(url, gap)
                try:
                    r = request(c, "GET", url, headers=headers)
                except Exception as e:  # one broken feed must not stop the others
                    state[url] = {**st, "error": f"{type(e).__name__}: {e}"[:200]}
                    yield Page(items=[], next_cursor=json.dumps(state), meta={"feed": url, "error": True})
                    continue
                if r.status_code == 304:
                    yield Page(items=[], next_cursor=json.dumps(state), meta={"feed": url, "not_modified": True})
                    continue
                seen = list(st.get("seen", []))
                new = []
                for it in parse_feed(r.content):
                    if it["id"] and it["id"] not in seen:
                        new.append(Envelope(source_id=self.spec.id, external_id=str(it["id"])[:500], payload={**it, "feed": url}))
                        seen.append(it["id"])
                state[url] = {"etag": r.headers.get("ETag"), "modified": r.headers.get("Last-Modified"), "seen": seen[-500:]}
                yield Page(items=new, next_cursor=json.dumps(state), meta={"feed": url, "new": len(new)})
