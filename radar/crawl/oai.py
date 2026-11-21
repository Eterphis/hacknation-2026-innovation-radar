"""Small OAI-PMH 2.0 client (harvester side), standard library only.

Covers what the radar needs from repositories such as Biblioteka Nauki, dLibra or PPM:
  * ListRecords with resumptionToken paging (``iter_pages`` / ``list_records``);
  * ListSets (set id -> name, e.g. journal names);
  * selective harvest by ``from`` / ``until`` (incremental refresh) and ``set``;
  * ``noRecordsMatch`` is an empty result, not an error; other OAI errors raise ``OAIError``;
  * deleted records (``<header status="deleted">``) come back with ``deleted=True``;
  * a pause between page requests (default 2 s, the project's per-host limit).

Metadata stays an ``xml.etree.ElementTree.Element``: mapping a format (oai_dc, oai_openaire, ...)
to a record is the connector's job. ``local()`` and ``children()`` help with namespaces.

Spec: https://www.openarchives.org/OAI/openarchivesprotocol.html
"""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Callable, Iterator
from urllib.parse import urlencode

from ..http import Response, fetch_bytes

OAI_NS = "http://www.openarchives.org/OAI/2.0/"
_O = "{" + OAI_NS + "}"
DEFAULT_DELAY = 2.0
EMPTY_LIST_CODES = {"noRecordsMatch", "noSetHierarchy"}


class OAIError(Exception):
    """An OAI-PMH <error> other than an empty list (badArgument, badResumptionToken, ...),
    or a response that is not OAI-PMH at all (HTML error page, bot challenge)."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code
        self.message = message


@dataclass
class Header:
    identifier: str
    datestamp: str | None
    sets: list[str] = field(default_factory=list)
    deleted: bool = False


@dataclass
class Record:
    header: Header
    metadata: ET.Element | None  # first child of <metadata> (e.g. oai_dc:dc); None for deleted records


@dataclass
class Page:
    """One OAI-PMH response."""

    url: str
    text: str
    fetched_at: str | None
    response_date: str | None = None
    records: list[Record] = field(default_factory=list)
    sets: list[tuple[str, str]] = field(default_factory=list)  # (setSpec, setName)
    token: str | None = None  # None or "" = last page
    complete_list_size: int | None = None
    cursor: int | None = None
    empty_reason: str | None = None  # e.g. "noRecordsMatch"


# --- helpers -------------------------------------------------------------------
def fetch_xml(url: str) -> Response:
    """GET an OAI response. ``radar.http.fetch`` asks for text/html, which some repositories answer
    with 406 (Biblioteka Nauki does), so this goes through ``fetch_bytes`` (same User-Agent, retries,
    ``Accept: */*``) and decodes as XML: UTF-8 unless the declaration says otherwise."""
    resp = fetch_bytes(url, timeout=60.0)
    raw = resp.content
    m = re.match(rb"<\?xml[^>]*encoding=[\"']([A-Za-z0-9._-]+)", raw.lstrip()[:200])
    encoding = m.group(1).decode() if m else "utf-8"
    try:
        text = raw.decode(encoding, errors="replace")
    except LookupError:
        text = raw.decode("utf-8", errors="replace")
    return Response(url=resp.url, status=resp.status, text=text.lstrip("\ufeff"), fetched_at=resp.fetched_at)


def local(tag: str) -> str:
    """'{http://purl.org/dc/elements/1.1/}title' -> 'title'."""
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def children(elem: ET.Element, name: str) -> list[ET.Element]:
    """All descendants with local name `name`, any namespace, in document order."""
    return [e for e in elem.iter() if local(e.tag) == name]


def text_of(elem: ET.Element | None) -> str:
    return " ".join("".join(elem.itertext()).split()) if elem is not None else ""


def oai_date(value: date | datetime | str | None) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def request_url(base: str, verb: str, *, resumption_token: str | None = None, metadata_prefix: str | None = None,
                set_spec: str | None = None, from_: date | str | None = None, until: date | str | None = None) -> str:
    """Build a request URL. With a resumptionToken the spec forbids every other argument."""
    if resumption_token:
        params = {"verb": verb, "resumptionToken": resumption_token}
    else:
        params = {"verb": verb, "metadataPrefix": metadata_prefix, "set": set_spec,
                  "from": oai_date(from_), "until": oai_date(until)}
    return base + ("&" if "?" in base else "?") + urlencode({k: v for k, v in params.items() if v})


# --- parsing -------------------------------------------------------------------
def _parse_header(h: ET.Element) -> Header:
    return Header(
        identifier=(h.findtext(_O + "identifier") or "").strip(),
        datestamp=(h.findtext(_O + "datestamp") or "").strip() or None,
        sets=[(s.text or "").strip() for s in h.findall(_O + "setSpec") if (s.text or "").strip()],
        deleted=h.get("status") == "deleted",
    )


def parse_response(text: str, *, url: str = "", fetched_at: str | None = None) -> Page:
    """Parse one OAI-PMH response body (ListRecords or ListSets)."""
    head = text[:2000]
    if "<!DOCTYPE" in head or "<!ENTITY" in head:
        # OAI-PMH responses never carry a DTD; refuse entity tricks and HTML error pages alike
        raise OAIError("notOAI", f"response with DOCTYPE from {url or 'repository'}")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise OAIError("notOAI", f"unparsable XML from {url or 'repository'}: {e}") from e
    if root.tag != _O + "OAI-PMH":
        raise OAIError("notOAI", f"root element {local(root.tag)!r}, expected OAI-PMH")

    page = Page(url=url, text=text, fetched_at=fetched_at,
                response_date=(root.findtext(_O + "responseDate") or "").strip() or None)
    errors = root.findall(_O + "error")
    if errors:
        codes = [e.get("code", "") for e in errors]
        if all(c in EMPTY_LIST_CODES for c in codes):
            page.empty_reason = codes[0]
            return page
        bad = next(e for e in errors if e.get("code", "") not in EMPTY_LIST_CODES)
        raise OAIError(bad.get("code", "unknown"), (bad.text or "").strip())

    body = root.find(_O + "ListRecords")
    if body is None:
        body = root.find(_O + "ListSets")
    if body is None:
        raise OAIError("notOAI", "no ListRecords/ListSets element")
    for rec in body.findall(_O + "record"):
        h = rec.find(_O + "header")
        if h is None:
            continue
        md = rec.find(_O + "metadata")
        meta = next(iter(md), None) if md is not None else None
        page.records.append(Record(header=_parse_header(h), metadata=meta))
    for s in body.findall(_O + "set"):
        spec = (s.findtext(_O + "setSpec") or "").strip()
        if spec:
            page.sets.append((spec, (s.findtext(_O + "setName") or "").strip()))
    tok = body.find(_O + "resumptionToken")
    if tok is not None:
        page.token = (tok.text or "").strip() or None
        size, cursor = tok.get("completeListSize"), tok.get("cursor")
        page.complete_list_size = int(size) if size and size.isdigit() else None
        page.cursor = int(cursor) if cursor and cursor.isdigit() else None
    return page


# --- harvesting ----------------------------------------------------------------
def iter_pages(
    base: str,
    verb: str = "ListRecords",
    *,
    metadata_prefix: str | None = "oai_dc",
    set_spec: str | None = None,
    from_: date | str | None = None,
    until: date | str | None = None,
    fetcher: Callable[[str], Response] = fetch_xml,
    delay: float = DEFAULT_DELAY,
    max_pages: int | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Iterator[Page]:
    """Yield response pages, following resumptionToken until the list ends.

    Lazy: the next page is requested only when the caller asks for it, so stopping early
    (``--limit``) costs no extra request. Network errors propagate as ``FetchError``."""
    if verb == "ListSets":
        metadata_prefix = None
    url = request_url(base, verb, metadata_prefix=metadata_prefix, set_spec=set_spec, from_=from_, until=until)
    seen_tokens: set[str] = set()
    n = 0
    while True:
        if n and delay:
            sleep(delay)
        resp = fetcher(url)
        page = parse_response(resp.text, url=url, fetched_at=resp.fetched_at)
        n += 1
        yield page
        if not page.token or (max_pages is not None and n >= max_pages):
            return
        if page.token in seen_tokens:
            raise OAIError("loop", f"repository repeated resumptionToken {page.token[:40]}...")
        seen_tokens.add(page.token)
        url = request_url(base, verb, resumption_token=page.token)


def list_records(base: str, **kwargs) -> Iterator[Record]:
    """Records from all pages (deleted ones included, see ``Header.deleted``)."""
    for page in iter_pages(base, "ListRecords", **kwargs):
        yield from page.records


def list_sets(base: str, **kwargs) -> dict[str, str]:
    """setSpec -> setName for the whole repository."""
    out: dict[str, str] = {}
    for page in iter_pages(base, "ListSets", **kwargs):
        out.update(page.sets)
    return out
