#!/usr/bin/env python3
"""icons.py — brand marks from simple-icons (CC0), as single-colour paths.

Read straight from `node_modules/simple-icons/icons/<slug>.svg` (pinned in
package.json), so there is no copy of anybody's logo to keep in sync. Every
mark is drawn in one palette colour: brand colours would break the blue
palette that verify.py enforces, and a monochrome row reads calmer anyway.

Names without a mark in simple-icons (Microsoft withdrew Azure, Excel and Power
BI; SQL, OpenAQ and AppArmor never had one) get a two-letter monogram chip, so
a row never has a hole in it.
"""
from __future__ import annotations

import re
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ICONS = ROOT / "node_modules" / "simple-icons" / "icons"
VIEW = 24   # every simple-icons mark is drawn on a 24 x 24 box

SLUGS = {
    "Python": "python", "TypeScript": "typescript", "JavaScript": "javascript",
    "Dart": "dart", "C++": "cplusplus", "PHP": "php", "CSS": "css", "HTML": "html5",
    "FastAPI": "fastapi", "Flask": "flask", "React": "react", "Flutter": "flutter",
    "Tailwind CSS": "tailwindcss", "PostgreSQL": "postgresql",
    "BigQuery": "googlebigquery", "NumPy": "numpy", "NASA TEMPO": "nasa",
    "YOLOv26": "ultralytics", "ESP32": "espressif", "MicroPython": "micropython",
    "Arduino": "arduino", "GCP": "googlecloud", "Docker": "docker",
    "Kubernetes": "kubernetes", "Linux": "linux", "Arch Linux": "archlinux",
}


@cache
def path(name: str) -> str | None:
    """The mark's `d`, or None when `name` has no simple-icons entry."""
    slug = SLUGS.get(name)
    if slug is None:
        return None
    if not ICONS.is_dir():
        raise SystemExit(f"missing {ICONS.relative_to(ROOT)} — run `npm install` first")
    m = re.search(r'<path d="([^"]+)"', (ICONS / f"{slug}.svg").read_text(encoding="utf-8"))
    return m.group(1) if m else None


def monogram(name: str) -> str:
    """Two letters for a name with no mark: initials, else the first two letters."""
    words = re.findall(r"[A-Za-z0-9]+", name)
    letters = "".join(w[0] for w in words[:2]) if len(words) > 1 else words[0][:2]
    return letters.upper()
