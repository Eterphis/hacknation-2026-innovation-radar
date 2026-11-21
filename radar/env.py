"""Load `KEY=value` lines from a `.env` file into os.environ (no dependency on python-dotenv).

Variables already set in the environment win, so `OPENALEX_API_KEY=... python -m radar.refresh` and
Docker `env_file` keep working. Lines: `KEY=value`, `export KEY=value`, `# comment`; values may be
wrapped in single or double quotes. Values are never printed.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def load_env(path: str | os.PathLike = ".env", *, override: bool = False) -> list[str]:
    """Set variables from `path`; returns the names that were set. A missing file is not an error."""
    p = Path(path)
    if not p.is_file():
        return []
    names = []
    for line in p.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = _LINE.match(line)
        if not m:
            continue
        key, value = m.groups()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        if override or key not in os.environ:
            os.environ[key] = value
            names.append(key)
    return names
