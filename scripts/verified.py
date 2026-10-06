#!/usr/bin/env python3
"""verified.py — the "VERIFIED · certificate" button placed under each project.

One small SVG per theme, reused by every project: the README wraps it in a link
to that project's certificate, so the browser fetches it once and caches it.
"""
from __future__ import annotations

from banner import FONT_REGULAR, FONT_SEMIBOLD, ROOT, _f, load_numbers
from glyphatlas import GlyphAtlas

H, PAD, FS = 28, 10, 12
CHECK = "M5 9.5l3 3 6.5-7"          # inside an 18 x 18 circle box


def render(theme: str, numbers: dict) -> tuple[str, dict]:
    t = numbers["profile"]["design"][theme]
    reg = GlyphAtlas(str(FONT_REGULAR), prefix="a")
    sem = GlyphAtlas(str(FONT_SEMIBOLD), prefix="b")
    word, tail = "VERIFIED", "certificate ↗"
    x_word = PAD + 18 + 8
    x_tail = x_word + sem.width(word, FS) + 8
    w = round(x_tail + reg.width(tail, FS) + PAD)
    base = 18.5

    body = (
        f'<rect x=".5" y=".5" width="{w - 1}" height="{H - 1}" rx="6" '
        f'fill="{t["panel"]}" stroke="{t["arch"]}"/>'
        f'<g transform="translate({PAD} 5)"><circle cx="9" cy="9" r="9" fill="{t["arch"]}"/>'
        f'<path d="{CHECK}" fill="none" stroke="{t["bg"]}" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round"/></g>'
        f'<g fill="{t["sky"]}">{sem.run(word, FS, x_word, base)}</g>'
        f'<g fill="{t["muted"]}">{reg.run(tail, FS, x_tail, base)}</g>'
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{H}" '
        f'viewBox="0 0 {w} {H}" role="img" aria-labelledby="vt vd">'
        '<title id="vt">Verified certificate</title>'
        '<desc id="vd">Button: opens the certificate for this project.</desc>'
        f"<defs>{reg.defs()}{sem.defs()}</defs>{body}</svg>"
    )
    return svg, {"width": w}


def main() -> None:
    numbers = load_numbers()
    for theme in ("dark", "light"):
        svg, stats = render(theme, numbers)
        (ROOT / "assets" / f"verified-{theme}.svg").write_text(svg, encoding="utf-8")
        print(f"verified-{theme}.svg  {len(svg):,} B   {stats}")


if __name__ == "__main__":
    main()
