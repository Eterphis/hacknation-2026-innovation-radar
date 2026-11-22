"""Demo film in one command, from any folder:

    python scripts/film.py [http://localhost:8088]

1. installs what it needs if missing: the e2e Node packages (npm ci) and imageio-ffmpeg (pip),
2. measures the narration clips in docs/film/audio (docs/film/durations.json),
3. records the app scene by scene with Playwright (e2e/scripts/film.mjs, system Edge; FILM_CHANNEL=chrome for Chrome),
4. lays the voices on the picture (scripts/film_mix.py) -> docs/film/radar-innowacji-demo.mp4.
The app must be running at the given address.
"""

from __future__ import annotations

import importlib
import json
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8088").rstrip("/")
FILM = ROOT / "docs" / "film"


def run(cmd, cwd=ROOT):
    print("$", " ".join(map(str, cmd)))
    subprocess.run(cmd, cwd=cwd, check=True, shell=sys.platform == "win32" and cmd[0] in ("npm", "node"))


try:
    urllib.request.urlopen(BASE + "/healthz", timeout=5)
except OSError as e:
    sys.exit(f"Aplikacja nie odpowiada pod {BASE} ({e}). Uruchom ją: docker compose up -d")
if not shutil.which("node"):
    sys.exit("Brak Node.js (https://nodejs.org), potrzebny do Playwright.")
if not (ROOT / "e2e" / "node_modules" / "@playwright" / "test").exists():
    run(["npm", "ci", "--no-audit", "--no-fund"], cwd=ROOT / "e2e")
try:
    importlib.import_module("imageio_ffmpeg")
except ImportError:
    run([sys.executable, "-m", "pip", "install", "-q", "imageio-ffmpeg==0.6.0"])
import imageio_ffmpeg  # noqa: E402

FF = imageio_ffmpeg.get_ffmpeg_exe()


def duration(path) -> float:
    err = subprocess.run([FF, "-i", str(path)], capture_output=True, text=True).stderr
    h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err).groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


scenes = json.loads((FILM / "scenes.json").read_text(encoding="utf-8"))
d = {s["id"]: round(duration(FILM / "audio" / f"{s['id']}.mp3"), 2) for s in scenes}
(FILM / "durations.json").write_text(json.dumps({"ffmpeg": FF, "durations": d}, indent=1), encoding="utf-8")
print("lektor:", round(sum(d.values()), 1), "s w", len(d), "scenach")
run(["node", str(ROOT / "e2e" / "scripts" / "film.mjs"), BASE])
run([sys.executable, str(ROOT / "scripts" / "film_mix.py")])
