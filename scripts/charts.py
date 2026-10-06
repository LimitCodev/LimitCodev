#!/usr/bin/env python3
"""charts.py — the language readout: bytes by language, as a gauge.

Same panel language as `banner.py` (12 px bezel, rule at y = 60, 960 px wide) so
the two assets sit together in the README without a seam. Labels come from the
same glyph atlas, so this file adds no font either.

Two choices worth stating:

**Bytes, not GitHub's percentage.** GitHub's per-repo language percentages are
linguist estimates over *that* repo; summing them across repos double-counts and
ignores vendored trees. `data/raw/languages.json` holds byte counts per repo, so
the totals here are exact and reproducible from the daily snapshot.

**Top 7 plus an aggregated tail.** Eleven languages sit under 3.2 % combined;
drawing them would cost rows and bytes to show noise. The tail is merged into one
bar in the muted colour, which reads as "not the headline" without hiding it.
"""
from __future__ import annotations

import json

import icons
from banner import ARCH_LOGO, ARCH_VIEW, FONT_REGULAR, FONT_SEMIBOLD, ROOT, W, _f, load_numbers
from glyphatlas import GlyphAtlas

H = 296
HEAD_RULE_Y = 60
HEAD_BASE = 41

LABEL_X = 158           # labels are right-aligned so they hug the bars
ICON_SIZE, ICON_GAP = 14, 8    # brand mark, hugging the label on its left
TRACK_X0, TRACK_X1 = 170, W - 110
VALUE_X = W - 36
ROWS_TOP, ROW_PITCH, BAR_H = 84, 21, 11
TOP_N = 7
RULE_Y = 264
FOOT_BASE = 284


def _text(atlas: GlyphAtlas, s: str, size: float, x: float, y: float,
          fill: str, anchor: str = "start") -> str:
    return f'<g fill="{fill}">' + atlas.run(s, size, x, y, anchor) + "</g>"


def _rule(y: float, x1: float = 12, x2: float = W - 12, stroke: str = "",
          opacity: float = 1.0) -> str:
    op = f' opacity="{opacity}"' if opacity < 1 else ""
    return f'<path d="M{_f(x1)} {_f(y)}H{_f(x2)}" stroke="{stroke}"{op}/>'


def language_rows(langs: dict) -> list[tuple[str, int]]:
    """Top N languages by bytes, plus one aggregated `Other` bar."""
    totals: dict[str, int] = langs["totals"]
    ordered = sorted(totals.items(), key=lambda kv: -kv[1])
    head = ordered[:TOP_N]
    tail = ordered[TOP_N:]
    rows = list(head)
    if tail:
        rows.append(("Other", sum(v for _, v in tail)))
    return rows


def render(theme: str, numbers: dict) -> tuple[str, dict]:
    t = numbers["profile"]["design"][theme]
    profile = numbers["profile"]
    langs = json.loads((ROOT / "data/raw/languages.json").read_text(encoding="utf-8"))

    reg = GlyphAtlas(str(FONT_REGULAR), prefix="a")
    sem = GlyphAtlas(str(FONT_SEMIBOLD), prefix="b")

    rows = language_rows(langs)
    total = sum(langs["totals"].values())
    peak = max(v for _, v in rows)

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" role="img" aria-labelledby="ct cd">',
        '<title id="ct">Source bytes by language</title>',
        f'<desc id="cd">Horizontal bar chart of {total:,} bytes of indexed '
        f"source across {len(langs['totals'])} languages, led by "
        f"{rows[0][0]} at {rows[0][1] / total:.0%}.</desc>",
    ]
    defs_slot = len(parts)

    parts.append(f'<rect width="{W}" height="{H}" rx="14" fill="{t["bg"]}"/>')
    parts.append(
        f'<rect x="12" y="12" width="{W - 24}" height="{H - 24}" rx="10" '
        f'fill="{t["panel"]}" stroke="{t["line"]}"/>'
    )
    parts.append(_rule(HEAD_RULE_Y, stroke=t["line"]))

    # same grammar as the banner: the Arch mark, then a command instead of a
    # label — `wc -c` is literally what produced these numbers.
    parts.append(f'<path d="{ARCH_LOGO}" transform="translate(25 25) scale({_f(18 / ARCH_VIEW)})" '
                 f'fill="{t["arch"]}"/>')
    parts.append(_text(sem, "$ wc -c", 15, 51, HEAD_BASE, t["sky"]))
    parts.append(
        _text(reg, f"BYTES BY LANGUAGE · {len(langs['totals'])} LANGUAGES · "
                   f"{total:,} B", 15, W - 32, HEAD_BASE, t["muted"], "end")
    )

    for i, (name, value) in enumerate(rows):
        y = ROWS_TOP + i * ROW_PITCH
        share = value / total
        fill = t["muted"] if name == "Other" else t["sky"]
        w = max(2.0, (TRACK_X1 - TRACK_X0) * value / peak)

        parts.append(
            f'<rect x="{TRACK_X0}" y="{y}" width="{TRACK_X1 - TRACK_X0}" '
            f'height="{BAR_H}" rx="1" fill="{t["panel2"]}"/>'
        )
        parts.append(
            f'<rect x="{TRACK_X0}" y="{y}" width="{_f(round(w, 1))}" '
            f'height="{BAR_H}" rx="1" fill="{fill}"/>'
        )
        baseline = y + BAR_H - 2
        parts.append(_text(reg, name, 12, LABEL_X, baseline, t["bone"], "end"))
        mark = icons.path(name)
        if mark:
            k = ICON_SIZE / icons.VIEW
            icon_x = LABEL_X - reg.width(name, 12) - ICON_GAP - ICON_SIZE
            parts.append(f'<path d="{mark}" fill="{t["sky"]}" '
                         f'transform="translate({_f(icon_x)} {_f(y + BAR_H / 2 - ICON_SIZE / 2)}) scale({_f(k)})"/>')
        parts.append(_text(sem, f"{share:.1%}", 12, VALUE_X, baseline, t["muted"], "end"))

    parts.append(_rule(RULE_Y, 24, W - 24, t["line"], 0.9))
    parts.append(
        _text(reg, f"byte counts from {numbers['repos']} public repositories · snapshot {numbers['date']}",
              11, 24, FOOT_BASE, t["muted"])
    )
    parts.append(_text(reg, "see README", 11, W - 24, FOOT_BASE, t["cyan"], "end"))

    parts.insert(defs_slot, "<defs>" + reg.defs() + sem.defs() + "</defs>")
    parts.append("</svg>")

    stats = {
        "rows": len(rows),
        "total_bytes": total,
        "peak_language": rows[0][0],
        "glyphs_regular": reg.stats,
        "glyphs_semibold": sem.stats,
    }
    return "".join(parts), stats


def main() -> None:
    numbers = load_numbers()
    out = ROOT / "assets"
    for theme in ("dark", "light"):
        svg, stats = render(theme, numbers)
        (out / f"chart-{theme}.svg").write_text(svg, encoding="utf-8")
        print(f"chart-{theme}.svg  {len(svg):,} B   {stats}")


if __name__ == "__main__":
    main()
