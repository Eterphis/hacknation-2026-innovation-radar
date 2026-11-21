"""Minimal .xlsx reader (standard library only): first or named sheet -> rows of cell strings.

Enough for the government spreadsheets we harvest (shared strings, inline strings, numbers,
booleans). No formulas are evaluated: the cached value is read, which is what Excel shows.
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, timedelta

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "rel": "http://schemas.openxmlformats.org/package/2006/relationships"}


def _col_index(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref).group(0)
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _text(el) -> str:
    """Concatenate all <t> under an element (plain or rich-text runs)."""
    return "".join(t.text or "" for t in el.iter(f"{{{NS['m']}}}t"))


def _sheet_path(z: zipfile.ZipFile, sheet: str | None) -> str:
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    sheets = wb.findall("m:sheets/m:sheet", NS)
    chosen = next((s for s in sheets if sheet is None or s.get("name") == sheet), None)
    if chosen is None:
        raise KeyError(f"sheet {sheet!r} not found")
    rid = chosen.get(f"{{{NS['r']}}}id")
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    target = next(r.get("Target") for r in rels.findall("rel:Relationship", NS) if r.get("Id") == rid)
    target = target.lstrip("/")
    return target if target.startswith("xl/") else "xl/" + target


def read_rows(data: bytes, sheet: str | None = None) -> list[list[str]]:
    """All rows of a sheet as lists of strings (missing cells become "")."""
    z = zipfile.ZipFile(io.BytesIO(data))
    shared: list[str] = []
    if "xl/sharedStrings.xml" in z.namelist():
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        shared = [_text(si) for si in root.findall("m:si", NS)]
    root = ET.fromstring(z.read(_sheet_path(z, sheet)))
    rows: list[list[str]] = []
    for row in root.iter(f"{{{NS['m']}}}row"):
        cells: dict[int, str] = {}
        for c in row.findall("m:c", NS):
            t = c.get("t")
            v = c.find("m:v", NS)
            if t == "s" and v is not None:
                value = shared[int(v.text)]
            elif t == "inlineStr":
                is_ = c.find("m:is", NS)
                value = _text(is_) if is_ is not None else ""
            elif t == "b" and v is not None:
                value = "TRUE" if v.text == "1" else "FALSE"
            else:
                value = v.text if v is not None and v.text is not None else ""
            cells[_col_index(c.get("r"))] = value
        width = max(cells) + 1 if cells else 0
        rows.append([cells.get(i, "") for i in range(width)])
    return rows


def excel_date(value: str | float | None) -> date | None:
    """Excel serial day (1900 system) -> date; the time-of-day fraction is dropped."""
    try:
        serial = float(value)
    except (TypeError, ValueError):
        return None
    if not 1 <= serial < 100000:
        return None
    return date(1899, 12, 30) + timedelta(days=int(serial))
