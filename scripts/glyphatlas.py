#!/usr/bin/env python3
"""glyphatlas.py — real typography for SVGs that GitHub serves as an <img>.

Why this exists
---------------
A README image is loaded in the browser's *secure static mode*: no scripts, no
external resources and — measured on Chromium 123 in this repo — **no @font-face
either**, even when the font is a `data:` URI (pixel diff: 0 changed pixels in
the glyph area; `docs/03-optimizacion-y-carga.md` §1). So `font-family` in a
README SVG is a promise nobody can keep: the reader gets Consolas on Windows,
SF Mono on macOS, DejaVu Sans Mono on Linux — never the face you designed with.

This module turns text into outlines instead, which is both honest and, with the
right structure, *cheaper than shipping the font*.

How the bytes stay down
-----------------------
Measured the naive way first — one path per (character, **size**) — the banner
text cost 95 883 B of `<defs>` for 4 sizes. Three structural choices fix that:

1. **One outline per character, ever.** Glyphs are stored in font units (integers
   from the source, no re-rounding) and every size is applied by a single
   `transform="scale(k)"` on a parent `<g>`.
2. **Em-grid coordinates for placement.** `<use x y>` lands on integer font
   units, so at 26 px the rounding error is 0.5 × 26/1000 ≈ 0.013 px — well under
   a device pixel on a retina screen.
3. **Monospace advances come from `hmtx`**, so a run is a flat loop with no
   per-character measurement beyond a table lookup.

Text never appears in a `<text>` element, so the readable string goes in the
root `<title>`/`aria-label` for screen readers.

Usage
-----
    atlas = GlyphAtlas("scripts/fonts/IBMPlexMono-Regular.woff2")
    body = atlas.run("157 commits", size=26, x=24, y=80)   # registers glyphs
    ...
    defs = atlas.defs()      # after every run(), dropped inside <defs>
"""
from __future__ import annotations

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

_B36 = "0123456789abcdefghijklmnopqrstuvwxyz"


class GlyphAtlas:
    """Glyph atlas: one outline per character in <defs>, `<g scale>` per size."""

    def __init__(self, font_path: str, prefix: str = "a"):
        """`prefix` disambiguates several weights in one document: a SemiBold
        atlas drawn next to a Regular one must not reuse the same ids."""
        self.prefix = prefix
        self.font = TTFont(font_path, fontNumber=0)
        self.upem = self.font["head"].unitsPerEm
        self.cmap = self.font.getBestCmap()
        self.hmtx = self.font["hmtx"]
        self.glyphset = self.font.getGlyphSet()
        self._paths: dict[str, str] = {}
        self._raw: dict[str, str] = {}
        self._order: list[str] = []
        self._missing: set[str] = set()
        self._uses = 0

    # ---------------------------------------------------------------- glyphs
    def _id(self, char: str) -> str:
        """Short id from the code point: 'A' with prefix 'a' -> 'a1t'."""
        n, out = ord(char), ""
        while True:
            out = _B36[n % 36] + out
            n //= 36
            if n == 0:
                return self.prefix + out

    def _glyph(self, char: str) -> str:
        """Id of `char`'s outline, registering it the first time. '' if unknown."""
        hit = self._paths.get(char)
        if hit is not None:
            return hit

        gname = self.cmap.get(ord(char))
        if gname is None:
            # Not in the font: keep the run's rhythm with a space, and remember
            # the character so the build can report it.
            self._missing.add(char)
            gname = self.cmap.get(ord(" "))
            if gname is None:
                self._paths[char] = ""
                return ""

        pen = SVGPathPen(self.glyphset)
        self.glyphset[gname].draw(pen)
        d = _flip_y(pen.getCommands())
        gid = self._id(char) if d else ""
        if gid:
            self._paths[char] = gid
            self._order.append(char)
            self._raw[char] = d
        else:
            self._paths[char] = ""
        return gid

    # ------------------------------------------------------------------ text
    def run(self, text: str, size: float, x: float, y: float,
            anchor: str = "start") -> str:
        """One baseline-aligned run of text, scaled by its parent `<g>`."""
        k = size / self.upem
        advances = [self._advance(ch) for ch in text]
        total = sum(advances) * k
        if anchor == "middle":
            x -= total / 2
        elif anchor == "end":
            x -= total

        cursor = round(x / k)
        base = round(y / k)
        uses: list[str] = []
        for ch, adv in zip(text, advances):
            gid = self._glyph(ch)
            if gid:
                uses.append(f'<use href="#{gid}" x="{cursor}" y="{base}"/>')
                self._uses += 1
            cursor += adv
        return f'<g transform="scale({_f(k)})">' + "".join(uses) + "</g>"

    def width(self, text: str, size: float) -> float:
        """Advance width of `text` at `size`, in px — for layout before emitting."""
        return sum(self._advance(ch) for ch in text) * size / self.upem

    def _advance(self, char: str) -> int:
        gname = self.cmap.get(ord(char)) or self.cmap.get(ord(" "))
        if gname is None:
            return round(self.upem * 0.6)
        return self.hmtx[gname][0]

    def ensure(self, chars: str) -> None:
        """Register `chars` before any run is emitted.

        Needed wherever a document reports its own size. Glyph outlines land in
        `<defs>` on first use, so a payload printed as `41.6` pulls in the `6`
        while a payload printed as `42.0` does not — one is 618 bytes larger
        than the other, which flips the very number being reported and sends the
        convergence loop into a permanent two-cycle (measured: 41.6 -> 42.0 ->
        41.6 -> 42.0). Fixing the set up front makes the byte count a function
        of the layout alone, so the label can settle.
        """
        for ch in chars:
            self._glyph(ch)

    # ------------------------------------------------------------------ defs
    def defs(self) -> str:
        """Every unique outline, ready to drop inside <defs>."""
        return "".join(
            f'<path id="{self._paths[c]}" d="{self._raw[c]}"/>'
            for c in self._order
        )

    @property
    def stats(self) -> dict:
        return {
            "unique_glyphs": len(self._order),
            "uses": self._uses,
            "missing": sorted(self._missing),
        }


def _flip_y(d: str) -> str:
    """Negate every y so the baseline sits at 0 and 'up' is negative (SVG y-down).

    SVGPathPen emits M/L/H/V/C/Q/T/S/Z. H and V carry a *single* value that is
    respectively an x and a y, so the naive "flip every odd index" rule silently
    corrupts them — that bug produced truncated glyphs on the first render.
    Repeated argument sets are unwrapped explicitly: a second set after M means
    lineto, not moveto.
    """
    if not d:
        return ""
    # command -> values per argument set; None marks a passthrough
    arity = {"M": 2, "L": 2, "T": 2, "C": 6, "S": 4, "Q": 4, "H": 1, "V": 1, "A": 7, "Z": 0}

    out: list[str] = []
    cmd = ""
    floats: list[float] = []

    def emit(command: str, args: list[float]) -> None:
        if command == "H":
            out.append("H" + _f(args[0]))
        elif command == "V":
            out.append("V" + _f(-args[0]))
        elif command == "A":
            # rx ry rot large-arc sweep x y → flags 3 and 4 are booleans
            parts = [
                _f(v) if i in (3, 4) else _f(-v if i in (5, 6) else v)
                for i, v in enumerate(args)
            ]
            out.append("A" + " ".join(parts))
        elif command in ("Z", "z"):
            out.append("Z")
        else:
            parts = [_f(-v if i % 2 == 1 else v) for i, v in enumerate(args)]
            out.append(command + " ".join(parts))

    def flush() -> None:
        if not cmd:
            return
        n = arity.get(cmd)
        if n is None:
            out.append(cmd + " ".join(_f(v) for v in floats))
        elif n == 0:
            emit(cmd, [])
        else:
            for i in range(0, len(floats), n):
                chunk = floats[i:i + n]
                if len(chunk) < n:
                    continue
                # extra sets after an initial M are line-tos by SVG's own rules
                sub = "L" if (cmd == "M" and i > 0) else cmd
                emit(sub, chunk)

    buf = ""
    for ch in d:
        if ch.isalpha():
            if buf:
                floats.append(float(buf))
                buf = ""
            flush()
            cmd, floats = ch.upper() if ch != "z" else "Z", []
        elif ch in " ,\n\t\r":
            if buf:
                floats.append(float(buf))
                buf = ""
        else:
            buf += ch
    if buf:
        floats.append(float(buf))
    flush()
    return "".join(out)


def _f(v: float) -> str:
    """Compact number: no trailing zeros, no '-0'."""
    if v == int(v):
        return str(int(v))
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s
