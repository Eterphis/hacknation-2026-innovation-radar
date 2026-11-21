"""Shared helpers for connectors that read whole data files: open-data dumps and manual imports.

- `download_if_changed`: conditional GET (If-None-Match / If-Modified-Since from the saved meta file),
  streamed to disk, atomic replace, optional ZIP check; an unchanged file costs one small request.
- `import_files`: newest files of the given kinds in an import folder (`data/import/<source>/`).
- `read_table`: rows of a CSV (encoding and delimiter detected) or XLSX file as lists of strings.
- `HeaderMap`: header row detection by folded column-name prefixes.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..http import RETRY_STATUS, USER_AGENT, FetchError
from ..text import clean_text, fold
from ..xlsx import read_rows

CHUNK = 1 << 20


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _meta_path(dest: Path) -> Path:
    return dest.with_name(dest.name + ".meta.json")


def load_meta(dest: Path) -> dict | None:
    p = _meta_path(Path(dest))
    if not p.exists() or not Path(dest).exists():
        return None
    try:
        return json.loads(p.read_text("utf-8"))
    except json.JSONDecodeError:
        return None


def download_if_changed(url: str, dest: Path, *, timeout: float = 300.0, retries: int = 3, backoff: float = 5.0,
                        expect_zip: bool = False, force: bool = False,
                        opener: Callable[..., object] = urllib.request.urlopen) -> dict:
    """Download `url` to `dest` unless the server says the saved copy is current (HTTP 304).

    Returns the meta dict (url, final_url, status, fetched_at, etag, last_modified, bytes, sha256, path)
    with `changed` True when a new file was written."""
    dest = Path(dest)
    old = None if force else load_meta(dest)
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if old and old.get("url") == url:
        if old.get("etag"):
            headers["If-None-Match"] = old["etag"]
        if old.get("last_modified"):
            headers["If-Modified-Since"] = old["last_modified"]
    last: Exception | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers=headers)
        try:
            with opener(req, timeout=timeout) as resp:
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_name(dest.name + ".part")
                h = hashlib.sha256()
                size = 0
                with tmp.open("wb") as fh:
                    for chunk in iter(lambda: resp.read(CHUNK), b""):
                        fh.write(chunk)
                        h.update(chunk)
                        size += len(chunk)
                if expect_zip and not zipfile.is_zipfile(tmp):
                    tmp.unlink(missing_ok=True)
                    raise FetchError(f"{url}: odpowiedź nie jest archiwum ZIP/XLSX")
                tmp.replace(dest)
                meta = {"url": url, "final_url": resp.geturl(), "status": resp.status, "fetched_at": now_iso(),
                        "etag": resp.headers.get("ETag"), "last_modified": resp.headers.get("Last-Modified"),
                        "bytes": size, "sha256": h.hexdigest(), "path": dest.name}
                _meta_path(dest).write_text(json.dumps(meta, ensure_ascii=False, indent=1), "utf-8")
                return {**meta, "path": str(dest), "changed": True}
        except urllib.error.HTTPError as e:
            if e.code == 304 and old:
                old.update({"checked_at": now_iso()})
                _meta_path(dest).write_text(json.dumps(old, ensure_ascii=False, indent=1), "utf-8")
                return {**old, "path": str(dest), "changed": False}
            last = e
            if e.code not in RETRY_STATUS:
                raise FetchError(f"HTTP {e.code} for {url}") from e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
        if attempt < retries:
            time.sleep(backoff * (2**attempt))
    raise FetchError(f"giving up on {url}: {last}") from last


def saved_file(dest: Path) -> dict | None:
    """Meta of a previously downloaded file (for --offline), with an absolute path."""
    meta = load_meta(Path(dest))
    return {**meta, "path": str(dest), "changed": False} if meta else None


# --- import folders --------------------------------------------------------------------
def import_files(folder: Path, exts: tuple[str, ...] = (".csv", ".xlsx")) -> list[Path]:
    """Files with the given extensions in `folder`, newest first (lock/temp files of Excel skipped)."""
    folder = Path(folder)
    if not folder.is_dir():
        return []
    files = [p for p in folder.iterdir()
             if p.is_file() and p.suffix.lower() in exts and not p.name.startswith(("~$", "."))]
    return sorted(files, key=lambda p: (p.stat().st_mtime, p.name), reverse=True)


def file_meta(path: Path) -> dict:
    st = Path(path).stat()
    return {"url": None, "path": str(path), "bytes": st.st_size, "sha256": sha256_file(path),
            "fetched_at": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(timespec="seconds")}


# --- tables ------------------------------------------------------------------------------
def decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1250"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def read_csv_text(text: str, delimiter: str | None = None) -> list[list[str]]:
    if delimiter is None:
        sample = text[:20000]
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=";,\t|").delimiter
        except csv.Error:
            first = sample.splitlines()[0] if sample else ""
            delimiter = max(";,\t", key=first.count)
    return [row for row in csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)]


def read_table(path: Path, sheet: str | None = None) -> list[list[str]]:
    path = Path(path)
    data = path.read_bytes()
    if path.suffix.lower() == ".xlsx" or data[:2] == b"PK":
        return read_rows(data, sheet)
    return read_csv_text(decode(data))


@dataclass
class HeaderMap:
    """Field -> column index, found by folded header prefixes (first matching alias wins per column)."""

    columns: dict[str, int]
    header_row: int  # 0-based index of the header row

    @classmethod
    def find(cls, rows: list[list[str]], aliases: list[tuple[str, tuple[str, ...]]],
             required: tuple[str, ...] | list[tuple[str, ...]], scan: int = 30) -> "HeaderMap | None":
        """`aliases`: [(field, (prefix, ...))], longer/more specific prefixes first.
        `required`: fields that must all be present, or a list of alternatives (any one set suffices)."""
        alternatives = [required] if required and isinstance(required[0], str) else list(required)
        for i, row in enumerate(rows[:scan]):
            cols: dict[str, int] = {}
            for idx, cell in enumerate(row):
                f = re.sub(r"\s+", " ", fold(cell)).strip(" :*")
                if not f:
                    continue
                for key, prefixes in aliases:
                    if key not in cols and any(f.startswith(p) for p in prefixes):
                        cols[key] = idx
                        break
            if any(all(k in cols for k in alt) for alt in alternatives):
                return cls(cols, i)
        return None

    def records(self, rows: list[list[str]]) -> list[tuple[int, dict[str, str]]]:
        """[(1-based row number in the file, {field: cleaned value})], empty rows skipped."""
        out = []
        for j, row in enumerate(rows[self.header_row + 1:], start=self.header_row + 2):
            values = {k: clean_text(row[c]) if c < len(row) else "" for k, c in self.columns.items()}
            if any(values.values()):
                out.append((j, values))
        return out


def num(value: str | None) -> float | None:
    """'1 234 567,89' / '1234567.89' / '1,234,567.89' -> float."""
    if value is None:
        return None
    s = str(value).strip().replace("\xa0", "").replace(" ", "")
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", fold(value)).strip("-")
