"""Generic GraphQL pull connector (relay-style or any cursor pagination).

options:
  url, headers {}, query (string), variables {}
  cursor_var: name of the variable that carries the cursor (e.g. "after")
  end_cursor_path: JMESPath to the next cursor, e.g. "data.projects.pageInfo.endCursor"
  has_next_path: JMESPath to a boolean, e.g. "data.projects.pageInfo.hasNextPage"
record_path on the spec points at the list of nodes, e.g. "data.projects.edges[].node".
"""

from collections.abc import Iterator

from radar.config import get_settings
from radar.sources.base import Page, PullConnector, items_from_payload, search
from radar.sources.http import client, request


class GraphQLError(RuntimeError):
    pass


class GraphQLConnector(PullConnector):
    def fetch(self, cursor: str | None) -> Iterator[Page]:
        url = self.spec.opt("url")
        query = self.spec.opt("query")
        variables = dict(self.spec.opt("variables", {}) or {})
        cursor_var = self.spec.opt("cursor_var", "after")
        end_path = self.spec.opt("end_cursor_path")
        has_next_path = self.spec.opt("has_next_path")
        if cursor:
            variables[cursor_var] = cursor
        max_pages = int(self.spec.opt("max_pages", get_settings().max_pages_per_run))
        with client(self.spec.opt("headers", {})) as c:
            for _ in range(max_pages):
                data = request(c, "POST", url, json={"query": query, "variables": variables}).json()
                if data.get("errors"):
                    raise GraphQLError(str(data["errors"])[:500])
                items = items_from_payload(self.spec, data, "pull")
                nxt = search(end_path, data) if end_path else None
                has_next = bool(search(has_next_path, data)) if has_next_path else bool(nxt)
                # The cursor is checkpointed after every page, so a crash resumes mid-run.
                yield Page(items=items, next_cursor=nxt or cursor)
                if not has_next or not nxt or not items:
                    return
                variables[cursor_var] = cursor = nxt
