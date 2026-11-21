"""Crawler stron z config/sites.json (bez LLM).

  python -X utf8 -m radar.crawl                          witryny, którym minął termin
  python -X utf8 -m radar.crawl --site prz_ctt --force   jedna witryna, niezależnie od terminu
  python -X utf8 -m radar.crawl --site prz_ctt --max-pages 20 --dry-run
                                                         przegląd bez zapisu (baza w pamięci)
  python -X utf8 -m radar.crawl sites                    stan witryn w bazie
"""
from __future__ import annotations

import argparse
import json
import sys
from contextlib import closing
from pathlib import Path

from .. import store
from .crawler import RAW_ROOT, crawl_due, totals
from .fetcher import Fetcher
from .sites import load_sites


def print_decisions(res: dict) -> None:
    print(f"\n== {res['site']} ({res['category']}): {res['status']}" + (f" ({res['error']})" if res["error"] else ""))
    for d in res["decisions"]:
        mark = "REKORD " if d["keep"] else "pomiń  "
        print(f"{mark} {d['title'][:90]}")
        print(f"        {d['url']}")
        extra = [f"typ={d['page_type']}", f"wynik={d['score']}", f"data={d['published'] or '-'}"]
        if d.get("organizations"):
            extra.append("org=" + "; ".join(d["organizations"][:4]))
        print(f"        {', '.join(extra)}")
        print(f"        powód: {d['reason']}")
    keys = ("fetched", "added", "skipped", "lists", "queued", "not_modified", "gone", "errors", "blocked", "robots")
    print("   " + ", ".join(f"{k}={res[k]}" for k in keys))


def sites_report(conn, config: str | None) -> list[dict]:
    configured = {s.id: s for s in load_sites(config, only_enabled=False)}
    rows = {r["site_id"]: dict(r) for r in conn.execute("SELECT * FROM crawl_sites")}
    out = []
    for sid in sorted(set(configured) | set(rows)):
        site, row = configured.get(sid), rows.get(sid, {})
        counts = {r["status"]: r["n"] for r in conn.execute(
            "SELECT status, COUNT(*) n FROM crawl_pages WHERE site_id=? GROUP BY status", (sid,))}
        records = conn.execute("SELECT COUNT(*) FROM records WHERE source=? AND removed_at IS NULL",
                               (f"web_{sid}",)).fetchone()[0]
        out.append({"site": sid, "name": site.name if site else None, "category": site.category if site else row.get("category"),
                    "enabled": site.enabled if site else False, "last_run": row.get("last_run"),
                    "status": row.get("status"), "error": row.get("error"), "pages": counts, "records": records})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=("run", "sites"), default="run")
    ap.add_argument("--site", action="append", default=[], help="id witryny (można powtórzyć)")
    ap.add_argument("--max-pages", type=int, default=None, help="limit stron na witrynę w tym przejściu")
    ap.add_argument("--dry-run", action="store_true", help="baza w pamięci, bez zapisu surowych plików")
    ap.add_argument("--force", action="store_true", help="uruchom witryny przed terminem")
    ap.add_argument("--db", default=None, help=f"plik bazy (domyślnie $RADAR_DB albo {store.DEFAULT_DB})")
    ap.add_argument("--config", default=None, help="plik witryn (domyślnie $RADAR_SITES albo config/sites.json)")
    ap.add_argument("--raw-dir", default=str(RAW_ROOT))
    ap.add_argument("--json", action="store_true", help="wynik jako JSON")
    args = ap.parse_args(argv)

    if args.cmd == "sites":
        with closing(store.connect(args.db)) as conn:
            report = sites_report(conn, args.config)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=1))
        else:
            for r in report:
                pages = ", ".join(f"{k}={v}" for k, v in sorted(r["pages"].items())) or "-"
                print(f"{r['site']:<28} {r['category'] or '-':<14} {'wł.' if r['enabled'] else 'wył.':<5} "
                      f"rekordy={r['records']:<5} {r['status'] or 'nigdy'} {r['last_run'] or ''}")
                print(f"    strony: {pages}" + (f"\n    błąd: {r['error']}" if r["error"] else ""))
        return 0

    sites = load_sites(args.config, only_enabled=not args.site)
    if args.site:
        wanted = set(args.site)
        unknown = wanted - {s.id for s in sites}
        if unknown:
            print(f"nieznane witryny: {', '.join(sorted(unknown))}", file=sys.stderr)
            return 2
        sites = [s for s in sites if s.id in wanted]
        for s in sites:
            s.enabled = True  # explicitly named: run even if disabled in the config
    if not sites:
        print("brak witryn do przejścia (sprawdź config/sites.json)", file=sys.stderr)
        return 0

    with closing(store.connect(":memory:" if args.dry_run else args.db)) as conn:
        results = crawl_due(conn, sites, Fetcher(), max_pages=args.max_pages, raw_root=Path(args.raw_dir),
                            dry_run=args.dry_run, force=args.force or args.dry_run or bool(args.site))
    if args.json:
        print(json.dumps({"sites": results, "totals": totals(results)}, ensure_ascii=False, indent=1))
    else:
        for res in results:
            if args.dry_run:
                print_decisions(res)
            else:
                keys = ("fetched", "added", "changed", "unchanged", "not_modified", "skipped", "removed", "errors")
                print(f"{res['site']}: {res['status']} " + ", ".join(f"{k}={res[k]}" for k in keys)
                      + (f" ({res['error']})" if res["error"] else ""), file=sys.stderr)
        t = totals(results)
        print(f"razem: witryny={t['sites']} pobrane={t['fetched']} nowe={t['added']} zmienione={t['changed']} "
              f"zablokowane={t['blocked_sites'] or '-'}", file=sys.stderr)
    return 1 if results and all(r["status"] == "error" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
