#!/usr/bin/env python3
"""stack.py — the toolbox panel: every stack item with its brand mark.

Same panel grammar as the chart (Arch mark, a command as the title) and the
same canvas width as the banner, so the three images stack without a seam.
Rows come from `profile.json` -> `stack`; marks from `icons.py`. Items with no
mark get a two-letter monogram chip so every row keeps its rhythm.
"""
from __future__ import annotations

import icons
from banner import ARCH_LOGO, ARCH_VIEW, FONT_REGULAR, FONT_SEMIBOLD, ROOT, W, _f, load_numbers
from glyphatlas import GlyphAtlas

HEAD_RULE_Y, HEAD_BASE = 60, 41
TOP = 88                 # first row baseline area
ROW_H = 34
LABEL_X = 28
ITEMS_X = 200
RIGHT = W - 28
ICON = 16
GAP = 20                 # between chips
FS = 13


def _text(atlas: GlyphAtlas, s: str, size: float, x: float, y: float,
          fill: str, anchor: str = "start") -> str:
    return f'<g fill="{fill}">' + atlas.run(s, size, x, y, anchor) + "</g>"


def render(theme: str, numbers: dict) -> tuple[str, dict]:
    profile = numbers["profile"]
    t = profile["design"][theme]
    reg = GlyphAtlas(str(FONT_REGULAR), prefix="a")
    sem = GlyphAtlas(str(FONT_SEMIBOLD), prefix="b")

    body: list[str] = []
    y = TOP
    marks = monos = 0
    for group in profile["stack"]:
        body.append(_text(reg, group["group"].lower(), 12, LABEL_X, y + 4, t["muted"]))
        x = ITEMS_X
        for name in group["items"]:
            chip = ICON + 7 + reg.width(name, FS)
            if x + chip > RIGHT:                  # wrap onto a continuation row
                x, y = ITEMS_X, y + ROW_H - 8
            top = y - ICON / 2
            mark = icons.path(name)
            if mark:
                marks += 1
                body.append(f'<path d="{mark}" fill="{t["sky"]}" transform="translate('
                            f'{_f(x)} {_f(top)}) scale({_f(ICON / icons.VIEW)})"/>')
            else:
                monos += 1
                body.append(f'<rect x="{_f(x + .5)}" y="{_f(top + .5)}" width="{ICON - 1}" '
                            f'height="{ICON - 1}" rx="3" fill="none" stroke="{t["sky"]}"/>')
                body.append(_text(sem, icons.monogram(name), 8, x + ICON / 2, top + 11,
                                  t["sky"], "middle"))
            body.append(_text(reg, name, FS, x + ICON + 7, y + 5, t["bone"]))
            x += chip + GAP
        y += ROW_H
    h = y - ROW_H + 40

    total = sum(len(g["items"]) for g in profile["stack"])
    names = "; ".join(f"{g['group']}: {', '.join(g['items'])}" for g in profile["stack"])
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}" '
        f'viewBox="0 0 {W} {h}" role="img" aria-labelledby="st sd">',
        '<title id="st">Toolbox</title>',
        f'<desc id="sd">{total} tools in {len(profile["stack"])} groups. {names}.</desc>',
    ]
    defs_slot = len(parts)
    parts += [
        f'<rect width="{W}" height="{h}" rx="14" fill="{t["bg"]}"/>',
        f'<rect x="12" y="12" width="{W - 24}" height="{h - 24}" rx="10" '
        f'fill="{t["panel"]}" stroke="{t["line"]}"/>',
        f'<path d="M12 {HEAD_RULE_Y}H{W - 12}" stroke="{t["line"]}"/>',
        f'<path d="{ARCH_LOGO}" transform="translate(25 25) scale({_f(18 / ARCH_VIEW)})" '
        f'fill="{t["arch"]}"/>',
        _text(sem, "$ ls ~/stack", 15, 51, HEAD_BASE, t["sky"]),
        _text(reg, f"{total} TOOLS · {len(profile['stack'])} GROUPS", 15, W - 32,
              HEAD_BASE, t["muted"], "end"),
        *body,
    ]
    parts.insert(defs_slot, "<defs>" + reg.defs() + sem.defs() + "</defs>")
    parts.append("</svg>")
    return "".join(parts), {"tools": total, "marks": marks, "monograms": monos}


def main() -> None:
    numbers = load_numbers()
    for theme in ("dark", "light"):
        svg, stats = render(theme, numbers)
        (ROOT / "assets" / f"stack-{theme}.svg").write_text(svg, encoding="utf-8")
        print(f"stack-{theme}.svg  {len(svg):,} B   {stats}")


if __name__ == "__main__":
    main()
