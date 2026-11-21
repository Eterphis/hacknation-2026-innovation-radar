"""Generic REST/JSON pull connector, configured entirely in sources.yaml.

options:
  url, method (GET), params {}, headers {}, json_body {} (POST)
  pagination:
    type: none | page | offset | cursor | next_url
    param: page|offset param name; size_param / size: page size
    start: first page number (page) or offset (offset)
    cursor_param / cursor_path: request param and JMESPath to the next cursor in the response (cursor)
    next_url_path: JMESPath to the next page URL (next_url)
  since_param: request param for incremental pulls; since_path: JMESPath to an item's change date.
               The max change date seen becomes the cursor for the next run.
"""

from collections.abc import Iterator

from radar.config import get_settings
from radar.sources.base import Page, PullConnector, items_from_payload, search
from radar.sources.http import client, request


class RestConnector(PullConnector):
    def fetch(self, cursor: str | None) -> Iterator[Page]:
        url = self.spec.opt("url")
        method = self.spec.opt("method", "GET").upper()
        params = dict(self.spec.opt("params", {}) or {})
        body = self.spec.opt("json_body")
        pg = self.spec.opt("pagination", {}) or {}
        ptype = pg.get("type", "none")
        since_param, since_path = self.spec.opt("since_param"), self.spec.opt("since_path")
        if cursor and since_param:
            params[since_param] = cursor
        if pg.get("size_param"):
            params[pg["size_param"]] = pg.get("size", 50)

        max_pages = int(self.spec.opt("max_pages", get_settings().max_pages_per_run))
        page_no = int(pg.get("start", 1 if ptype == "page" else 0))
        newest = cursor
        with client(self.spec.opt("headers", {})) as c:
            for _ in range(max_pages):
                if ptype == "page":
                    params[pg.get("param", "page")] = page_no
                elif ptype == "offset":
                    params[pg.get("param", "offset")] = page_no
                r = request(c, method, url, params=params, json=body if method != "GET" else None)
                data = r.json()
                items = items_from_payload(self.spec, data, "pull")
                if since_path:
                    for env in items:
                        v = search(since_path, env.payload)
                        if v and (newest is None or str(v) > newest):
                            newest = str(v)

                next_url = None
                done = not items
                if ptype == "page":
                    page_no += 1
                elif ptype == "offset":
                    page_no += len(items)
                elif ptype == "cursor":
                    nxt = search(pg.get("cursor_path"), data)
                    done = done or not nxt
                    params[pg.get("cursor_param", "cursor")] = nxt
                elif ptype == "next_url":
                    next_url = search(pg.get("next_url_path"), data)
                    done = done or not next_url
                else:
                    done = True
                yield Page(items=items, next_cursor=newest if since_param else None)
                if done:
                    return
                if next_url:
                    url, params = next_url, {}
