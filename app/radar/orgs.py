"""Organisation registry and affiliation matching (T023), deterministic, no LLM.

Registry: RAD-on/POL-on institutions (universities and research institutes with REGON/NIP/KRS, kind, public or
not, voivodeship, city, former names). The team harvester writes them next to the projects as
`data/normalized/radon_institutions.jsonl` (`radar.sources.radon`); `ensure_registry()` loads that file into the
`organizations` table whenever it changes, so workers pick up a new registry without a restart.

Matching cascade for one affiliation (pipeline-design §4), first hit wins:
  1. id: RAD-on uuid, REGON, NIP or KRS carried by the record (harvester `organizations[]`) -> confidence 1.0
  2. alias: the normalized name equals a name, former name or name variant of exactly one entry -> 0.98
  3. contains: an unambiguous alias of 2+ words appears inside the affiliation, e.g. "Wydział Chemiczny,
     Politechnika Rzeszowska im. Ignacego Łukasiewicza" -> 0.93
  4. fuzzy: character similarity of the normalized names (+0.03 when the entry's city is named), accepted at
     >= 0.90, kept as an unconfirmed candidate at >= 0.70 (shown, not used for type and region).
Normalization folds Polish letters, drops patronage ("im. ...") and cuts words to 6 characters, so the
genitive in "Politechniki Rzeszowskiej" still meets "Politechnika Rzeszowska".
Out of scope here: ROR and Wikidata (ids fit in `Organization.ids`), schools (no RSPO access), companies.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

ACCEPT, REVIEW = 0.90, 0.70
STEM = 6
STOP = {"w", "we", "i", "im", "z", "ze", "na", "do", "oraz", "of", "the", "and", "in"}
TYPE_MAP = {"university": "uczelnia", "research_institute": "instytut"}
ID_FIELDS = (("radon", "radon_uuid"), ("regon", "regon"), ("nip", "nip"), ("krs", "krs"))
REGISTRY_FILE = "radon_institutions.jsonl"
CITY_RE = re.compile(r"\bwe?\s+([A-ZŁŚŻŹĆŃÓĘĄ][a-ząćęłńóśźż]+(?:[- ][A-ZŁŚŻŹĆŃÓĘĄ][a-ząćęłńóśźż]+)?)")


def fold(text: str | None) -> str:
    if not text:
        return ""
    t = unicodedata.normalize("NFKD", text.replace("ł", "l").replace("Ł", "L"))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def tokens(text: str | None) -> list[str]:
    return [w[:STEM] for w in fold(text).split() if w not in STOP]


def key(text: str | None) -> str:
    return " ".join(tokens(text))


CITY_ENDINGS = ("ach", "iu", "ie", "ej", "u", "y", "i", "e", "a")


def city_stem(city: str | None) -> str:
    """First word of a city name without its case ending: 'w Kielcach' and 'Kielce' -> 'kielc', 'w Łodzi' and
    'Łódź' -> 'lodz', while 'Tarnowie' (tarnow) and 'Tarnobrzeg' stay apart."""
    words = fold(city).split()
    if not words:
        return ""
    w = words[0]
    for end in CITY_ENDINGS:
        if w.endswith(end) and len(w) - len(end) >= 3:
            return w[: -len(end)][:8]
    return w[:8]


def name_variants(name: str) -> set[str]:
    """Official name plus the short forms people write: without patronage, without 'w <city>', the part after
    a dash ('Sieć Badawcza Łukasiewicz – Instytut ...'), without 'w likwidacji'."""
    base = re.sub(r"\s+w\s+likwidacji\b", "", name, flags=re.I).strip()
    out = {name, base}
    no_patron = re.sub(r"\s+im\.?\s+.+?(?=\s+w\s+[A-ZŁŚŻŹĆŃÓĘĄ]|$)", "", base).strip()
    out.add(no_patron)
    for v in list(out):
        m = re.match(r"(.+?)\s+w(?:e)?\s+[A-ZŁŚŻŹĆŃÓĘĄ][\w-]+(?:\s+[A-ZŁŚŻŹĆŃÓĘĄ][\w-]+)?$", v)
        if m:
            out.add(m.group(1))
        parts = re.split(r"\s+[-–—]\s+", v, maxsplit=1)
        if len(parts) == 2:
            out.add(parts[1])
    return {v for v in out if v}


def registry_row(inst: dict) -> dict:
    """radon_institutions.jsonl row -> Organization fields."""
    ids = {k: inst.get(src) for k, src in (("radon", "uuid"), ("regon", "regon"), ("nip", "nip"), ("krs", "krs"))
           if inst.get(src)}
    return {"key": f"radon:{inst['uuid']}", "name": inst.get("name") or "", "ids": ids,
            "institution_type": TYPE_MAP.get(inst.get("type_hint") or ""), "is_public": inst.get("is_public"),
            "voivodeship": inst.get("voivodeship"), "city": inst.get("city"), "status": inst.get("status"),
            "aliases": [n for n in inst.get("former_names") or [] if n], "source": "radon"}


@dataclass
class OrgInfo:
    id: int
    name: str
    ids: dict = field(default_factory=dict)
    institution_type: str | None = None
    is_public: bool | None = None
    voivodeship: str | None = None
    city: str | None = None

    def public(self) -> dict:
        return {"org_id": self.id, "org_name": self.name, "institution_type": self.institution_type,
                "is_public": self.is_public, "voivodeship": self.voivodeship, "city": self.city}


class Matcher:
    def __init__(self, orgs: Iterable[OrgInfo | dict], aliases: dict[int, list[str]] | None = None):
        self.orgs: dict[int, OrgInfo] = {}
        self.by_id: dict[tuple[str, str], int] = {}
        owners: dict[str, set[int]] = defaultdict(set)
        self.official: set[str] = set()  # keys of full official and former names: they carry their own city
        for o in orgs:
            o = o if isinstance(o, OrgInfo) else OrgInfo(**o)
            self.orgs[o.id] = o
            for kind, value in (o.ids or {}).items():
                self.by_id[(kind, re.sub(r"\D", "", str(value)) if kind != "radon" else str(value))] = o.id
            for name in [o.name, *(aliases or {}).get(o.id, [])]:
                self.official.add(key(name))
                for v in name_variants(name):
                    k = key(v)
                    if len(k) >= 4:
                        owners[k].add(o.id)
        # a short form shared by two entries ("Uniwersytet Medyczny") identifies neither
        self.exact = {k: next(iter(ids)) for k, ids in owners.items() if len(ids) == 1}
        self.by_first: dict[str, list[tuple[list[str], int]]] = defaultdict(list)
        for k, oid in self.exact.items():
            toks = k.split()
            if len(toks) >= 2:
                self.by_first[toks[0]].append((toks, oid))
        for lst in self.by_first.values():
            lst.sort(key=lambda x: -len(x[0]))
        self.city = {oid: city_stem(o.city) for oid, o in self.orgs.items() if fold(o.city)}
        acr: dict[str, set[int]] = defaultdict(set)
        for oid, o in self.orgs.items():
            for v in name_variants(o.name):
                letters = "".join(w[0] for w in fold(v).split() if w not in STOP and not w.isdigit()).upper()
                if len(letters) >= 3 and v != o.name:
                    acr[letters].add(oid)
        self.acronyms = {a: next(iter(ids)) for a, ids in acr.items() if len(ids) == 1}

    def _city_ok(self, name: str, oid: int) -> bool:
        """An affiliation that names a city ('... w Tarnowie') must agree with the registry entry's city."""
        named = {city_stem(c) for c in CITY_RE.findall(name)}
        return not named or oid not in self.city or self.city[oid] in named

    def _hit(self, name: str, oid: int, conf: float, method: str, **more) -> dict:
        return {"name": name, **self.orgs[oid].public(), "confidence": round(conf, 3), "method": method,
                "accepted": conf >= ACCEPT, **more}

    def match(self, name: str, refs: dict | None = None) -> dict:
        refs = refs or {}
        for kind, field_name in ID_FIELDS:
            v = refs.get(field_name)
            if v:
                oid = self.by_id.get((kind, str(v) if kind == "radon" else re.sub(r"\D", "", str(v))))
                if oid is not None:
                    return self._hit(name, oid, 1.0, "id")
        parts = [name, *[p for p in re.split(r"\s*[;,/]\s*", name) if p and p != name]]
        for p in parts:
            oid = self.exact.get(key(p))
            if oid is not None and (key(p) in self.official or self._city_ok(name, oid)):
                return self._hit(name, oid, 0.98, "alias")
        for word in re.findall(r"\b[A-ZŁŚŻŹĆŃÓĘĄ]{3,6}\b", name):
            oid = self.acronyms.get(fold(word).upper())
            if oid is not None and self._city_ok(name, oid):
                return self._hit(name, oid, 0.95, "acronym")
        toks = tokens(name)
        best: tuple[int, int] | None = None
        for i, t in enumerate(toks):
            for alias, oid in self.by_first.get(t, ()):
                if (toks[i:i + len(alias)] == alias and (best is None or len(alias) > best[0])
                        and self._city_ok(name, oid)):
                    best = (len(alias), oid)
                    break
        if best is not None:
            return self._hit(name, best[1], 0.93, "contains")
        name_toks = set(toks)
        top: tuple[float, int] | None = None
        for p in parts:
            pk = key(p)
            if len(pk) < 6:
                continue
            sm = SequenceMatcher(None, "", pk)  # b = the affiliation (cached), a = each alias
            for k, oid in self.exact.items():
                sm.set_seq1(k)
                if sm.real_quick_ratio() < REVIEW or sm.quick_ratio() < REVIEW:
                    continue
                if not self._city_ok(name, oid):
                    continue
                r = sm.ratio() + (0.03 if self.city.get(oid, "~")[:STEM] in name_toks else 0.0)
                if top is None or r > top[0]:
                    top = (r, oid)
        if top is not None and top[0] >= REVIEW:
            return self._hit(name, top[1], min(top[0], 0.97), "fuzzy" if top[0] >= ACCEPT else "candidate")
        return {"name": name, "org_id": None, "confidence": 0.0, "method": "none", "accepted": False}


def resolve(matcher: Matcher, affiliations: list[str], organizations: list[dict] | None) -> list[dict]:
    """One result per affiliation, in record order (beneficiary first). Harvester organisations give the ids."""
    refs = {(o.get("name") or "").strip(): o for o in organizations or [] if isinstance(o, dict)}
    seen, out = set(), []
    for a in affiliations or []:
        if not a or a in seen:
            continue
        seen.add(a)
        out.append(matcher.match(a, refs.get(a.strip())))
    return out


def summary(results: list[dict]) -> dict[str, Any]:
    """Record-level facts from the first accepted organisation: what Basal's gate gets as declared values."""
    first = next((r for r in results if r.get("accepted")), None)
    if not first:
        return {}
    return {k: first.get(k) for k in ("org_id", "institution_type", "is_public", "voivodeship") if first.get(k) is not None}


def read_registry_file(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            inst = json.loads(line)
            if inst.get("uuid"):
                rows.append(registry_row(inst))
    return rows


# ---------------------------------------------------------------- registry in the database
_cache: dict[str, Any] = {"version": None, "matcher": None}


def registry_path() -> Path:
    """RADAR_ORG_REGISTRY, else radon_institutions.jsonl in the harvester output directory."""
    import os

    from radar.sources.base import expand_env
    from radar.sources.snapshot import resolve_path

    return resolve_path(os.environ.get("RADAR_ORG_REGISTRY")
                        or expand_env("${RADAR_HARVEST_DIR:-../data/normalized}/" + REGISTRY_FILE))


def load_registry(s, rows: list[dict]) -> int:
    """Upsert registry rows by their stable key; entries are never deleted (records keep their org_id)."""
    from sqlalchemy import select

    from radar.models import Organization

    existing = {o.key: o for o in s.scalars(select(Organization))}
    for row in rows:
        org = existing.get(row["key"]) or Organization(key=row["key"])
        for k, v in row.items():
            setattr(org, k, v)
        s.add(org)
    s.flush()
    return len(rows)


def ensure_registry(s) -> Matcher | None:
    """Reload the registry file into the table when it changed (mtime, size), then return a cached matcher.
    No file and an empty table = no registry yet: resolve_org passes affiliations through."""
    from sqlalchemy import func, select

    from radar.models import Organization, Setting

    path = registry_path()
    st = s.get(Setting, "org_registry")
    if path.exists():
        stamp = {"path": str(path), "mtime": path.stat().st_mtime, "size": path.stat().st_size}
        if st is None or {k: st.value.get(k) for k in stamp} != stamp:
            n = load_registry(s, read_registry_file(path))
            st = st or Setting(key="org_registry")
            st.value = {**stamp, "count": n}
            s.add(st)
            s.flush()
    count, latest = s.execute(select(func.count(Organization.id), func.max(Organization.updated_at))).one()
    if not count:
        return None
    version = f"{count}:{latest}"
    if _cache["version"] != version:
        orgs = list(s.scalars(select(Organization)))
        _cache["matcher"] = Matcher([OrgInfo(id=o.id, name=o.name, ids=o.ids or {}, institution_type=o.institution_type,
                                             is_public=o.is_public, voivodeship=o.voivodeship, city=o.city) for o in orgs],
                                    {o.id: o.aliases or [] for o in orgs})
        _cache["version"] = version
    return _cache["matcher"]
