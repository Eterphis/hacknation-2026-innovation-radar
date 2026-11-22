"""Lay the narration on the recorded picture: docs/film/raw/*.webm + docs/film/audio/*.mp3 -> docs/film/radar-innowacji-demo.mp4

    python scripts/film_mix.py

Uses docs/film/timeline.json (scene start times written by e2e/scripts/film.mjs) and the ffmpeg binary named in
docs/film/durations.json (imageio-ffmpeg). The recording starts a little before the first scene (browser start,
cache warm-up); that lead is cut off so the first frame is the page and the first word starts with it.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILM = ROOT / "docs" / "film"
meta = json.loads((FILM / "durations.json").read_text(encoding="utf-8"))
tl = json.loads((FILM / "timeline.json").read_text(encoding="utf-8"))
FF = meta["ffmpeg"]
ADA = ROOT / "app" / "radar" / "api" / "static" / "audio" / "1019-ada.mp3"


def duration(path) -> float:
    err = subprocess.run([FF, "-i", str(path)], capture_output=True, text=True).stderr
    h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err).groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


scenes = tl["timeline"]
end = max(s["at"] + s["len"] for s in scenes)
video = Path(tl["video"])
lead = max(0.0, duration(video) - end - 0.3)  # the context closes ~0.3 s after the last scene
inputs, filters, labels = ["-ss", f"{lead:.2f}", "-i", str(video)], [], []
for n, s in enumerate(scenes, start=1):
    src = ADA if s["id"] == "ada" else FILM / "audio" / f"{s['id']}.mp3"
    inputs += ["-i", str(src)]
    delay = int((s["at"] + (0.15 if s["id"] != "ada" else 0)) * 1000)
    trim = f"atrim=0:{s['len']},afade=t=out:st={s['len'] - 1.2}:d=1.2," if s["id"] == "ada" else ""
    filters.append(f"[{n}:a]{trim}aresample=44100,adelay={delay}|{delay}[a{n}]")
    labels.append(f"[a{n}]")
filters.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0,afade=t=out:st={end - 1.5:.2f}:d=1.5[aout]")
filters.append(f"[0:v]fade=t=in:st=0:d=0.6,fade=t=out:st={end - 1.0:.2f}:d=1.0,format=yuv420p[vout]")
out = FILM / "radar-innowacji-demo.mp4"
cmd = [FF, "-y", *inputs, "-filter_complex", ";".join(filters), "-map", "[vout]", "-map", "[aout]", "-t", f"{end:.2f}",
       "-c:v", "libx264", "-preset", "medium", "-crf", "22", "-r", "30", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)]
r = subprocess.run(cmd, capture_output=True, text=True)
if r.returncode:
    raise SystemExit(r.stderr[-2000:])
print(f"{out} · {duration(out):.1f} s · {out.stat().st_size / 1e6:.1f} MB · obcięty wstęp {lead:.2f} s")
