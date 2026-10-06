#!/usr/bin/env python3
"""banner.py — the hero: an i3 desktop running fastfetch.

Design notes that are easy to lose, so they live here:

* **Native, not decorated.** The panel is the owner's real setup: an i3bar
  with a live-looking status line, a focused terminal (Arch-blue border, i3's
  focused-title colours) and an unfocused second window, tiled. The terminal
  types `fastfetch`; the logo slot fastfetch would print holds the portrait,
  which rearranges itself into the official Arch logo and back, forever.

* **A real morph, cheaply.** A few hundred "traveller" dots, paired with logo
  dots by optimal assignment (`dither.travellers`), fly from the face to the
  logo while the two dense pictures cross-fade underneath. The motion is one
  shared CSS keyframe; each traveller only carries its own offset as two custom
  properties (`style="--x:4;--y:-9"`, ~45 bytes). The reference profile gives
  every one of its 900 travellers its own SMIL pair, ~350 bytes each.

* **Reduced motion is honoured** for the morph: CSS, unlike SMIL, can see
  `prefers-reduced-motion`, and then the portrait simply stays.

* **Text is outlines.** Every glyph comes from `glyphatlas.py`, which is why the
  document carries no `font-family` at all.

* **Drawn small, shown big.** GitHub scales README images to the column
  (~830 px). An 860 px canvas therefore renders nearly 1:1, so everything reads
  larger than the same layout on a 960 px canvas would.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from dither import logo, portrait, runs, save_grid, travellers
from glyphatlas import GlyphAtlas

ROOT = Path(__file__).resolve().parents[1]
# The photo never enters git: only its greyscale + alpha cell grid does, which
# is all the dither reads. Regenerate it with `banner.py --grid` after
# replacing the photo.
PORTRAIT_PHOTO = ROOT / "assets/source/portrait.png"       # local only, gitignored
PORTRAIT_GRID = ROOT / "assets/source/portrait-grid.png"   # committed
FONT_REGULAR = ROOT / "scripts/fonts/IBMPlexMono-Regular.woff2"
FONT_SEMIBOLD = ROOT / "scripts/fonts/IBMPlexMono-SemiBold.woff2"

# Official Arch Linux mark, from /usr/share/pixmaps/archlinux-logo.svg
# (package `filesystem`), viewBox 0 0 256 256, trademark glyphs dropped.
ARCH_LOGO = (
    "m127.98 12.07c-10.316 25.309-16.543 41.855-28.031 66.41 7.043 7.4609 15.691 "
    "16.156 29.734 25.977-15.098-6.207-25.395-12.445-33.094-18.918-14.703 30.68-37.742 "
    "74.391-84.492 158.39 36.746-21.219 65.23-34.293 91.773-39.289-1.1406-4.8945-1.7852-"
    "10.195-1.7422-15.734l0.042969-1.1719c0.58203-23.551 12.828-41.645 27.336-40.418 "
    "14.508 1.2266 25.781 21.316 25.199 44.867-0.10938 4.4219-0.60938 8.6914-1.4805 "
    "12.641 26.258 5.1328 54.438 18.18 90.684 39.105-7.1484-13.156-13.527-25.016-19.621-"
    "36.316-9.5938-7.4336-19.605-17.117-40.023-27.594 14.035 3.6406 24.082 7.8516 31.914 "
    "12.555-61.941-115.32-66.957-130.66-88.199-180.5z"
)
ARCH_VIEW = 256

W, H = 860, 456

# Layout ---------------------------------------------------------------------
BAR_H, BAR_BASE, BAR_FS = 28, 19, 12
WIN_Y, WIN_B = 36, H - 8
TITLE_H = 24
LEFT_X, LEFT_R = 8, 612          # focused terminal
RIGHT_X, RIGHT_R = 620, 852      # unfocused activity window

FS, LH = 13, 20                  # terminal font size and line height
TERM_X = 22
PROMPT_BASE = 84
SLOT = (22, 100, 200, 250)       # logo slot x, y, w, h in px
PITCH = 1.5                      # px per dot cell
DOT_PX = 1.1                     # drawn dot size; the rest of the cell is gap
GRID_W, GRID_H = round(SLOT[2] / PITCH), round(SLOT[3] / PITCH)
DOT = DOT_PX / PITCH             # in cell units, as the paths are drawn
LOGO_CELLS = round(GRID_W * 0.92)
TRAVELLERS = 400
INFO_X, INFO_BASE = 238, 112
BLOCKS_Y = 384
FINAL_BASE = 428

PANE_X, PANE_R = RIGHT_X + 16, RIGHT_R - 16
TRACE_BOX = (PANE_X, 94, PANE_R - PANE_X, 96)

# Timeline (seconds) ---------------------------------------------------------
CMD = "fastfetch"
T_CMD, CMD_CHAR = 0.5, 0.07      # `fastfetch` typed at this pace
T_OUT = round(T_CMD + len(CMD) * CMD_CHAR + 0.25, 2)   # output starts
LINE_GAP, LINE_CHAR = 0.06, 0.007
CYCLE = 12                       # face -> logo -> face

# Status line: (label, values). One value is static; several cycle, one step
# per STATUS_STEP seconds, so the bar looks alive without any of it being real.
STATUS = [("BRI", ["24%"]), ("VOL", ["0%"]),
          ("CPU", ["3%", "7%", "12%", "5%", "18%", "4%"]),
          ("RAM", ["23%", "24%", "26%", "24%"]), ("BAT", ["91%"])]
STATUS_STEP = 2.0


def _f(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def _s(v: float) -> str:
    return _f(v) + "s"


def load_numbers() -> dict:
    profile = json.loads((ROOT / "data/profile.json").read_text(encoding="utf-8"))
    contrib = json.loads((ROOT / "data/raw/contributions.json").read_text(encoding="utf-8"))
    user = json.loads((ROOT / "data/raw/user.json").read_text(encoding="utf-8"))
    langs = json.loads((ROOT / "data/raw/languages.json").read_text(encoding="utf-8"))

    coll = contrib["data"]["user"]["contributionsCollection"]
    cal = coll["contributionCalendar"]
    days = [d["contributionCount"] for w in cal["weeks"] for d in w["contributionDays"]]
    weeks = [sum(d["contributionCount"] for d in w["contributionDays"]) for w in cal["weeks"]]
    ranked = sorted(langs["totals"].items(), key=lambda kv: -kv[1])
    snapshot = json.loads((ROOT / "data/raw/snapshot.json").read_text(encoding="utf-8"))
    return {
        "profile": profile,
        "date": snapshot["date"],
        "contributions": cal["totalContributions"],
        "commits": coll["totalCommitContributions"],
        "days": days,
        "weeks": weeks,
        "repos": user["public_repos"],
        "source_bytes": sum(langs["totals"].values()),
        "peak": max(days),
        "top_langs": [name for name, _ in ranked[:3]],
    }


def _text(atlas: GlyphAtlas, s: str, x: float, y: float, fill: str,
          size: float = FS, anchor: str = "start") -> str:
    return f'<g fill="{fill}">' + atlas.run(s, size, x, y, anchor) + "</g>"


def _typed(cid: str, x: float, top: float, widths: list[float],
           begin: float, dur: float) -> str:
    """A clip rect that grows one step per character, then stays open."""
    vals = ";".join(_f(w) for w in [0.0, *widths])
    return (f'<clipPath id="{cid}"><rect x="{_f(x)}" y="{_f(top)}" width="0" '
            f'height="{LH}"><animate attributeName="width" values="{vals}" '
            f'calcMode="discrete" begin="{_s(begin)}" dur="{_s(dur)}" '
            f'fill="freeze"/></rect></clipPath>')


def _appear(at: float) -> str:
    return f'<set attributeName="opacity" to="1" begin="{_s(at)}" fill="freeze"/>'


def trace_path(days: list[int], box: tuple[float, float, float, float]) -> tuple[str, float, float]:
    """Closed area under the daily contribution series, in canvas coordinates."""
    x0, y0, w, h = box
    baseline = y0 + h - 4
    top = y0 + 6
    peak = max(max(days), 1)
    step = w / (len(days) - 1) if len(days) > 1 else w
    pts = [f"M{_f(x0)} {_f(baseline)}"]
    for i, v in enumerate(days):
        pts.append(f"L{_f(x0 + i * step)} {_f(baseline - (v / peak) * (baseline - top))}")
    pts.append(f"L{_f(x0 + w)} {_f(baseline)}Z")
    return "".join(pts), baseline, top


def _morph_css(t: dict) -> str:
    """Keyframes for the face <-> logo loop, as percentages of CYCLE.

    0-38 % face holds · 38-50 % travellers fly to the logo · 50-88 % logo holds
    · 88-100 % travellers fly back. The dense pictures cross-fade under the
    flight, so what the eye follows is the travellers.
    """
    to = "transform:translate(calc(var(--x)*1px),calc(var(--y)*1px))"
    ease = "animation-timing-function:cubic-bezier(.65,0,.35,1)"
    return (
        f".in{{animation:in .6s {_s(T_OUT)} backwards}}"
        f".pf,.lg,.t{{animation:{CYCLE}s linear {_s(T_OUT)} infinite both}}"
        ".pf{animation-name:pf}.lg{animation-name:lg}.t{animation-name:t}"
        "@keyframes in{from{opacity:0}}"
        "@keyframes pf{0%,37%{opacity:1}41%,97%{opacity:0}100%{opacity:1}}"
        "@keyframes lg{0%,47%{opacity:0}51%,86%{opacity:1}90%,100%{opacity:0}}"
        "@keyframes t{"
        f"0%,37%{{transform:none;opacity:0;stroke:{t['sky']}}}"
        f"38%{{transform:none;opacity:1;{ease}}}"
        f"50%{{{to};opacity:1;stroke:{t['arch']}}}"
        f"52%,86%{{{to};opacity:0}}"
        f"88%{{{to};opacity:1;{ease}}}"
        f"99%{{transform:none;opacity:1;stroke:{t['sky']}}}"
        "100%{transform:none;opacity:0}}"
        "@media (prefers-reduced-motion:reduce){.in,.pf{animation:none}.lg,.t{display:none}}"
    )


def render(theme: str, numbers: dict) -> tuple[str, dict]:
    profile = numbers["profile"]
    t = profile["design"][theme]
    ident, term = profile["identity"], profile["terminal"]

    reg = GlyphAtlas(str(FONT_REGULAR), prefix="a")
    sem = GlyphAtlas(str(FONT_SEMIBOLD), prefix="b")
    adv = reg.width("M", FS)

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" role="img" aria-labelledby="ttl dsc">',
        f'<title id="ttl">{ident["name"]}: fastfetch on Arch Linux with i3</title>',
        f'<desc id="dsc">An i3 desktop. A terminal runs fastfetch: a dot portrait '
        f"that rearranges itself into the Arch Linux logo and back, and system "
        f"lines for a {ident['role'].lower()} with {numbers['repos']} public "
        f"repositories and {numbers['contributions']} contributions. A second "
        f"window plots the last 52 weeks of activity.</desc>",
    ]
    defs_slot = len(parts)
    clips: list[str] = []

    # ---- desktop + i3bar ---------------------------------------------------
    parts.append(f'<rect width="{W}" height="{H}" rx="12" fill="{t["bg"]}"/>')
    parts.append(f'<rect width="{W}" height="{BAR_H}" rx="6" fill="{t["panel2"]}"/>')
    parts.append(f'<use href="#al" transform="translate(10 6) scale({_f(16 / ARCH_VIEW)})" '
                 f'fill="{t["arch"]}"/>')
    for i, ws in enumerate("1234"):
        x = 34 + i * 24
        if i == 0:
            parts.append(f'<rect x="{x}" y="4" width="22" height="20" rx="2" fill="{t["arch"]}"/>')
        parts.append(_text(sem if i == 0 else reg, ws, x + 11, BAR_BASE,
                           t["bg"] if i == 0 else t["muted"], BAR_FS, "middle"))
    parts.append(_text(reg, numbers["date"], W / 2, BAR_BASE, t["muted"], BAR_FS, "middle"))

    # status fields, laid out right to left; a cycling value is one <g> per
    # variant, each shown during its own STATUS_STEP slot
    bar_adv = reg.width("M", BAR_FS)
    x = W - 12
    for label, values in reversed(STATUS):
        if len(values) == 1:
            parts.append(_text(sem, values[0], x, BAR_BASE, t["bone"], BAR_FS, "end"))
        else:
            n = len(values)
            for k, v in enumerate(values):
                vis = ";".join("1" if j == k else "0" for j in range(n))
                parts.append(
                    f'<g opacity="{1 if k == 0 else 0}" fill="{t["bone"]}">'
                    f'<animate attributeName="opacity" values="{vis}" calcMode="discrete" '
                    f'dur="{_s(n * STATUS_STEP)}" repeatCount="indefinite"/>'
                    + sem.run(v, BAR_FS, x, BAR_BASE, "end") + "</g>"
                )
        x -= max(len(v) for v in values) * bar_adv + bar_adv * 0.6
        parts.append(_text(reg, label, x, BAR_BASE, t["arch"], BAR_FS, "end"))
        x -= reg.width(label, BAR_FS) + bar_adv * 1.6

    # ---- windows -----------------------------------------------------------
    def window(x0: float, x1: float, title: str, focused: bool) -> None:
        edge = t["arch"] if focused else t["line"]
        parts.append(f'<rect x="{_f(x0 + .5)}" y="{_f(WIN_Y + .5)}" width="{x1 - x0 - 1}" '
                     f'height="{WIN_B - WIN_Y - 1}" fill="{t["panel"]}" stroke="{edge}"/>')
        parts.append(f'<rect x="{x0}" y="{WIN_Y}" width="{x1 - x0}" height="{TITLE_H}" '
                     f'fill="{t["arch"] if focused else t["panel2"]}"/>')
        parts.append(_text(reg, title, x0 + 8, WIN_Y + 16,
                           t["bg"] if focused else t["muted"], BAR_FS))

    user_host = f"{term['user']}@{term['host']}"
    window(LEFT_X, LEFT_R, f"{user_host}: ~", True)
    window(RIGHT_X, RIGHT_R, "gh contributions --weeks 52", False)

    # ---- prompt + typed command --------------------------------------------
    def prompt(base: float) -> tuple[str, float]:
        x = TERM_X
        out = []
        for s, atlas, colour in (("[", reg, t["muted"]), (user_host, sem, t["arch"]),
                                 (" ~", reg, t["sky"]), ("]$ ", reg, t["muted"])):
            out.append(_text(atlas, s, x, base, colour))
            x += atlas.width(s, FS)
        return "".join(out), x

    first, cmd_x = prompt(PROMPT_BASE)
    parts.append(first)
    cmd_dur = len(CMD) * CMD_CHAR
    clips.append(_typed("cc", cmd_x, PROMPT_BASE - 14,
                        [adv * (i + 1) for i in range(len(CMD))], T_CMD, cmd_dur))
    parts.append('<g clip-path="url(#cc)">' + _text(reg, CMD, cmd_x, PROMPT_BASE, t["bone"]) + "</g>")
    xs = ";".join(_f(cmd_x + adv * i) for i in range(len(CMD) + 1))
    parts.append(
        f'<rect x="{_f(cmd_x)}" y="{PROMPT_BASE - 12}" width="{_f(adv)}" height="15" '
        f'fill="{t["bone"]}" opacity="1"><animate attributeName="x" values="{xs}" '
        f'calcMode="discrete" begin="{_s(T_CMD)}" dur="{_s(cmd_dur)}" fill="freeze"/>'
        f'<set attributeName="opacity" to="0" begin="{_s(T_OUT)}" fill="freeze"/></rect>'
    )

    # ---- logo slot: portrait <-> Arch logo ---------------------------------
    face = portrait(PORTRAIT_GRID)
    mark = logo(ARCH_LOGO, ARCH_VIEW, GRID_W, GRID_H, LOGO_CELLS)
    movers = travellers(face, mark, TRAVELLERS)
    parts.append(
        f'<g class="in" transform="translate({SLOT[0]} {SLOT[1]}) scale({_f(PITCH)})" '
        f'fill="none" stroke-width="{_f(DOT)}" stroke-dasharray="{_f(DOT)} {_f(1 - DOT)}">'
        f'<path class="pf" d="{runs(face)}" stroke="{t["sky"]}"/>'
        f'<path class="lg" d="{runs(mark)}" stroke="{t["arch"]}"/>'
        f'<g stroke="{t["sky"]}" stroke-width="1" stroke-dasharray="none">'
        + "".join(f'<path class="t" style="--x:{dx};--y:{dy}" d="M{x} {y}.5h1"/>'
                  for x, y, dx, dy in movers)
        + "</g></g>"
    )

    # ---- fastfetch lines ---------------------------------------------------
    mb = numbers["source_bytes"] / 1_000_000
    lines: list[tuple[str, str]] = [
        ("Name", ident["name"]),
        ("Role", f"{ident['role']} @ {ident['school_abbr']}"),
        ("Location", f"{ident['location']} ({ident['timezone']})"),
        ("OS", term["os"]),
        ("WM", term["wm"]),
        ("Shell", term["shell"]),
        ("Editor", term["editor"]),
        ("Stack", term["stack"]),
        ("Repos", f"{numbers['repos']} public · {numbers['contributions']} contributions"),
        ("Source", f"{mb:.2f} MB · {numbers['top_langs'][0]} leads"),
        ("Activity", ""),
        ("Now", term["now"]),
    ]
    clock = T_OUT + 0.15

    def typed_line(i: int, body: str, n_chars: int, extra: list[float] | None = None) -> None:
        nonlocal clock
        base = INFO_BASE + i * LH
        widths = [adv * (c + 1) for c in range(n_chars)] + (extra or [])
        dur = max(0.12, len(widths) * LINE_CHAR)
        clips.append(_typed(f"l{i}", INFO_X, base - 14, widths, clock, dur))
        parts.append(f'<g clip-path="url(#l{i})">{body}</g>')
        clock += dur + LINE_GAP

    host_x = INFO_X + adv * (len(term["user"]) + 1)
    title = (_text(sem, term["user"], INFO_X, INFO_BASE, t["arch"])
             + _text(reg, "@", INFO_X + adv * len(term["user"]), INFO_BASE, t["bone"])
             + _text(sem, term["host"], host_x, INFO_BASE, t["arch"]))
    typed_line(0, title, len(user_host))
    typed_line(1, _text(reg, "-" * len(user_host), INFO_X, INFO_BASE + LH, t["muted"]),
               len(user_host))

    weeks = numbers["weeks"]
    wpeak = max(max(weeks), 1)
    for j, (key, value) in enumerate(lines):
        i = j + 2
        base = INFO_BASE + i * LH
        head = f"{key}: "
        body = (_text(sem, key, INFO_X, base, t["arch"])
                + _text(reg, ":", INFO_X + adv * len(key), base, t["muted"]))
        extra: list[float] = []
        if key == "Activity":
            bx = INFO_X + adv * len(head)
            bars = "".join(f"M{_f(bx + w * 4 + 1.5)} {base}v-{_f(1 + 12 * v / wpeak)}"
                           for w, v in enumerate(weeks))
            body += f'<path d="{bars}" stroke="{t["cyan"]}" stroke-width="3"/>'
            extra = [bx - INFO_X + 4 * (w + 2) for w in range(0, len(weeks), 2)]
        else:
            body += _text(reg, value, INFO_X + adv * len(head), base, t["bone"])
        typed_line(i, body, len(head) + len(value), extra)

    t_end = clock + 0.2
    blocks = [t[c] for c in ("bg", "panel2", "line", "muted", "bone", "cyan", "sky", "arch")]
    parts.append(
        f'<g opacity="0" stroke="{t["line"]}" stroke-width=".5">{_appear(t_end)}'
        + "".join(f'<rect x="{INFO_X + i * 28}" y="{BLOCKS_Y}" width="26" height="13" fill="{c}"/>'
                  for i, c in enumerate(blocks))
        + "</g>"
    )
    final, cur_x = prompt(FINAL_BASE)
    parts.append(f'<g opacity="0">{_appear(t_end + 0.3)}{final}</g>')
    parts.append(
        f'<rect x="{_f(cur_x)}" y="{FINAL_BASE - 12}" width="{_f(adv)}" height="15" '
        f'fill="{t["bone"]}" opacity="0"><animate attributeName="opacity" values="1;0" '
        f'calcMode="discrete" begin="{_s(t_end + 0.3)}" dur="1.06s" repeatCount="indefinite"/></rect>'
    )

    # ---- activity window ---------------------------------------------------
    d, baseline, top = trace_path(numbers["days"], TRACE_BOX)
    tx, ty, tw, th = TRACE_BOX
    parts.append(_text(reg, "contributions · last 52 weeks", PANE_X, 84, t["muted"], 11))
    clips.append(
        f'<clipPath id="wp"><rect x="{tx}" y="{ty}" width="0" height="{th}">'
        f'<animate attributeName="width" values="0;{_f(tw)}" begin="{_s(T_OUT)}" dur="1.6s" '
        f'fill="freeze" calcMode="spline" keyTimes="0;1" keySplines="0.22 1 0.36 1"/>'
        f'</rect></clipPath>'
    )
    grid = "".join(
        f'<path d="M{_f(tx)} {_f(baseline - f * (baseline - top))}H{_f(tx + tw)}" '
        f'stroke="{t["line"]}" stroke-dasharray="2 5"/>' for f in (1 / 3, 2 / 3))
    parts.append(
        f'<g clip-path="url(#wp)">{grid}'
        f'<path d="M{_f(tx)} {_f(baseline)}H{_f(tx + tw)}" stroke="{t["cyan"]}" opacity=".7"/>'
        f'<path d="{d}" fill="{t["cyan"]}" fill-opacity=".16" stroke="{t["cyan"]}" '
        f'stroke-width="1.4" stroke-linejoin="round"/></g>'
    )
    parts.append(_text(reg, f"peak {numbers['peak']} / day", PANE_X, 206, t["muted"], 11))
    parts.append(f'<path d="M{RIGHT_X} 218H{RIGHT_R}M{RIGHT_X} 332H{RIGHT_R}" stroke="{t["line"]}"/>')
    cells = [
        (str(numbers["contributions"]), "contributions"),
        (str(numbers["commits"]), "commits"),
        (str(numbers["repos"]), "public repos"),
        (f"{mb:.2f} MB", "source"),
    ]
    col_w = (PANE_R - PANE_X) / 2
    for i, (value, label) in enumerate(cells):
        cx = PANE_X + (i % 2) * col_w
        vy = 250 + (i // 2) * 52
        parts.append(
            f'<g opacity="0">{_appear(T_OUT + 0.5 + i * 0.15)}'
            + _text(sem, value, cx, vy, t["sky"], 20)
            + _text(reg, label, cx, vy + 16, t["muted"], 11) + "</g>"
        )
    parts.append(_text(reg, "top languages", PANE_X, 358, t["muted"], 11))
    parts.append(_text(reg, " · ".join(numbers["top_langs"]), PANE_X, 376, t["bone"], 11))
    parts.append(_text(reg, f"updated {numbers['date']}", PANE_X, 400, t["muted"], 11))
    parts.append(_text(reg, "see README", PANE_R, FINAL_BASE, t["cyan"], 12, "end"))

    parts.insert(defs_slot, f"<style>{_morph_css(t)}</style>"
                 f'<defs><path id="al" d="{ARCH_LOGO}"/>'
                 + "".join(clips) + reg.defs() + sem.defs() + "</defs>")
    parts.append("</svg>")
    stats = {
        "portrait_dots": int(face.sum()),
        "logo_dots": int(mark.sum()),
        "travellers": len(movers),
        "typing_ends_s": round(t_end, 2),
        "glyphs_regular": reg.stats,
        "glyphs_semibold": sem.stats,
    }
    return "".join(parts), stats


def main() -> None:
    if sys.argv[1:] == ["--grid"]:
        save_grid(PORTRAIT_PHOTO, PORTRAIT_GRID, GRID_W, GRID_H)
        print(f"wrote {PORTRAIT_GRID.relative_to(ROOT)}")
        return
    numbers = load_numbers()
    out = ROOT / "assets"
    for theme in ("dark", "light"):
        svg, stats = render(theme, numbers)
        (out / f"banner-{theme}.svg").write_text(svg, encoding="utf-8")
        print(f"banner-{theme}.svg  {len(svg):,} B   {stats}")


if __name__ == "__main__":
    main()
