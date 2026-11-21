"""Punkt wejścia kontenera Docker (napisany w Pythonie, żeby nie zależeć od końców linii skryptów sh).

    docker compose run --rm gui refresh [opcje radar.refresh]
    docker compose run --rm gui cards --stale
    docker compose run --rm gui store stats

Komendy:
  gui        przeglądarka danych na 0.0.0.0:$PORT (domyślnie 8765)
  scheduler  odświeżanie co $REFRESH_INTERVAL_HOURS godzin (domyślnie 24), pierwsze od razu
  refresh    jednorazowe odświeżenie (opcje jak w radar.refresh)
  cards      karty innowacji (opcje jak w radar.card, z bazą)
  store      operacje na bazie (opcje jak w radar.store)
  shell      powłoka w kontenerze
"""
from __future__ import annotations

import os
import signal
import sys
import time
from datetime import datetime


def _log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


def _stop(signum, frame):  # PID 1 in a container ignores SIGTERM without a handler
    _log("zatrzymuję")
    raise SystemExit(0)


def scheduler(extra: list[str]) -> int:
    from . import refresh

    hours = float(os.environ.get("REFRESH_INTERVAL_HOURS", "24"))
    extra = extra or os.environ.get("REFRESH_ARGS", "").split()
    _log(f"harmonogram: odświeżanie co {hours:g} h, opcje: {' '.join(extra) or '(brak)'}")
    while True:
        try:
            rc = refresh.main(list(extra))
            _log(f"odświeżanie zakończone, kod {rc}")
        except SystemExit as e:  # e.g. lock held by a manual run: try again next time
            if e.code not in (0, None):
                _log(f"odświeżanie przerwane: {e.code}")
        except Exception as e:  # keep the scheduler alive whatever happens in one run
            _log(f"odświeżanie nie powiodło się: {type(e).__name__}: {e}")
        time.sleep(hours * 3600)


def main(argv: list[str] | None = None) -> int:
    signal.signal(signal.SIGTERM, _stop)
    args = list(sys.argv[1:] if argv is None else argv)
    cmd, rest = (args[0], args[1:]) if args else ("gui", [])
    if cmd == "gui":
        from .gui.__main__ import main as gui
        return gui(["--host", "0.0.0.0", "--port", os.environ.get("PORT", "8765"), *rest])
    if cmd == "scheduler":
        return scheduler(rest)
    if cmd == "refresh":
        from .refresh import main as refresh
        return refresh(rest)
    if cmd == "cards":
        from .card import main as cards
        return cards(["--db", *rest] if "--db" not in rest else rest)
    if cmd == "store":
        from .store import main as store
        return store(rest)
    if cmd in ("shell", "sh", "bash"):
        os.execvp("bash", ["bash"])
    if cmd in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    print(f"nieznana komenda: {cmd}\n{__doc__}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
