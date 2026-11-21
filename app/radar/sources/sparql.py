"""SPARQL pull connector (EPO Linked Data, Wikidata, any SPARQL 1.1 endpoint).

options: endpoint, query (with {limit} and {offset} placeholders), page_size (100)
Bindings are flattened to {var: value}. Set id_path to the variable holding a stable id (e.g. "publication").
"""

from collections.abc import Iterator

from radar.config import get_settings
from radar.sources.base import Page, PullConnector, items_from_payload
from radar.sources.http import client, request


def flatten(bindings: list[dict]) -> list[dict]:
    return [{k: v.get("value") for k, v in b.items()} for b in bindings]


class SparqlConnector(PullConnector):
    def fetch(self, cursor: str | None) -> Iterator[Page]:
        endpoint = self.spec.opt("endpoint")
        template = self.spec.opt("query")
        size = int(self.spec.opt("page_size", 100))
        offset = int(cursor or 0) if self.spec.opt("resume_offset", False) else 0
        max_pages = int(self.spec.opt("max_pages", get_settings().max_pages_per_run))
        with client({"Accept": "application/sparql-results+json"}, self.spec.opt("timeout")) as c:
            for _ in range(max_pages):
                q = template.replace("{limit}", str(size)).replace("{offset}", str(offset))
                data = request(c, "POST", endpoint, data={"query": q}).json()
                rows = flatten(data.get("results", {}).get("bindings", []))
                items = items_from_payload(self.spec, rows, "pull")
                offset += len(rows)
                yield Page(items=items, next_cursor=str(offset))
                if len(rows) < size:
                    return
