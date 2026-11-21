"""OAI-PMH 2.0 pull connector (Biblioteka Nauki, dLibra, any OAI repository).

options: base_url, metadata_prefix (oai_dc), set (optional), from (initial datestamp, optional)
Cursor = the newest `datestamp` seen; the next run asks `from=<cursor>` (incremental harvesting).
Within a run, pages follow `resumptionToken`. Records with header status="deleted" become deleted envelopes.

Each record becomes a flat dict: {oai_identifier, oai_datestamp, oai_setSpec, title: [...], creator: [...], ...}
with all Dublin Core elements as lists, so `mapping` in sources.yaml can use plain JMESPath.
"""

import xml.etree.ElementTree as ET
from collections.abc import Iterator

from radar.config import get_settings
from radar.sources.base import Envelope, Page, PullConnector
from radar.sources.http import client, request

NS = {"oai": "http://www.openarchives.org/OAI/2.0/"}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_record(rec: ET.Element) -> tuple[dict, bool]:
    header = rec.find("oai:header", NS)
    deleted = header is not None and header.get("status") == "deleted"
    out: dict = {
        "oai_identifier": header.findtext("oai:identifier", default="", namespaces=NS) if header is not None else "",
        "oai_datestamp": header.findtext("oai:datestamp", default="", namespaces=NS) if header is not None else "",
        "oai_setSpec": [e.text for e in header.findall("oai:setSpec", NS)] if header is not None else [],
    }
    md = rec.find("oai:metadata", NS)
    if md is not None:
        for el in md.iter():
            if el is md or len(el):
                continue
            text = (el.text or "").strip()
            if not text:
                continue
            key = _local(el.tag)
            lang = el.get("{http://www.w3.org/XML/1998/namespace}lang")
            out.setdefault(key, []).append(text)
            if lang:
                out.setdefault(f"{key}_{lang}", []).append(text)
    return out, deleted


def parse_page(xml_text: str | bytes) -> tuple[list[tuple[dict, bool]], str | None, str | None]:
    root = ET.fromstring(xml_text)
    err = root.find("oai:error", NS)
    if err is not None:
        if err.get("code") == "noRecordsMatch":
            return [], None, None
        raise RuntimeError(f"OAI-PMH error {err.get('code')}: {err.text}")
    lr = root.find("oai:ListRecords", NS)
    if lr is None:
        return [], None, None
    records = [parse_record(r) for r in lr.findall("oai:record", NS)]
    tok_el = lr.find("oai:resumptionToken", NS)
    token = (tok_el.text or "").strip() if tok_el is not None else None
    return records, token or None, None


class OaiPmhConnector(PullConnector):
    def fetch(self, cursor: str | None) -> Iterator[Page]:
        base = self.spec.opt("base_url")
        params = {"verb": "ListRecords", "metadataPrefix": self.spec.opt("metadata_prefix", "oai_dc")}
        if self.spec.opt("set"):
            params["set"] = self.spec.opt("set")
        since = cursor or self.spec.opt("from")
        if since:
            params["from"] = since[:10]
        newest = cursor
        max_pages = int(self.spec.opt("max_pages", get_settings().max_pages_per_run))
        with client() as c:
            for _ in range(max_pages):
                text = request(c, "GET", base, params=params).content
                records, token, _ = parse_page(text)
                items = []
                for data, deleted in records:
                    if data["oai_datestamp"] and (newest is None or data["oai_datestamp"] > newest):
                        newest = data["oai_datestamp"]
                    items.append(
                        Envelope(
                            source_id=self.spec.id,
                            external_id=data["oai_identifier"],
                            payload=data,
                            content_type="application/xml+oai",
                            deleted=deleted,
                        )
                    )
                yield Page(items=items, next_cursor=newest, meta={"resumptionToken": token})
                if not token:
                    return
                params = {"verb": "ListRecords", "resumptionToken": token}
