#!/usr/bin/env python3
"""verify.py — the gate. Exits non-zero if anything about the payload drifted.

Run by `build.py` on every local build and by `.github/workflows` on every push.
It checks four independent things, because they fail for different reasons:

1. **Structure.** viewBox, <title>/<desc>, every href="#..." resolving to a real
   id, no font-family, no <text>. A dangling href renders as a missing glyph,
   which looks like a font bug rather than a build bug.
2. **Motion.** The banner's SMIL node count must stay inside its range. svgo's
   default preset deletes animated elements (they start at opacity="0", so they
   look hidden); without this check that regression is invisible in a still.
3. **Palette.** Every hex in every asset must be a token declared in
   data/profile.json. This is what keeps the background welded to GitHub's
   canvas — one stray #071C24 and the seam comes back.
4. **Budget.** Bytes, request counts, badge count. Failing here is the whole
   point of having a budget.

Usage:  python scripts/verify.py [--readme README.md]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SVG_NS = "{http://www.w3.org/2000/svg}"

HEX = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![0-9a-fA-F])")
LOCAL_SRC = re.compile(r'(?:src|srcset)="((?!https?://)[^"]+?\.(?:svg|png))"')
ANY_SRC = re.compile(r'(?:src|srcset)="([^"]+)"')
BADGE = re.compile(r"https?://(?:img|shields)\.shields\.io/[^\"'\s]+")

SMIL_TAGS = {"animate", "animateTransform", "animateMotion", "set"}

# Hit counters increment on every GET, so fetching one to weigh it would add a
# fake view on every local build and every CI run. Budget them with the size
# measured once by hand with a throwaway page_id (see data/profile.json counter).
COUNTER_BYTES = {"visitor-badge.laobi.icu": 1310, "komarev.com": 889}

# Motion contract as (min, max) SMIL nodes. The banner needs its typing and
# status line; the ceiling is a budget, because node count is what made the
# reference profile cost ~2,100 animations. The face <-> logo morph is CSS and
# is not counted here.
ASSETS = ("banner", "chart", "stack", "verified")
EXPECTED_SMIL = {"banner": (10, 250)}     # anything not listed must be static

BUDGETS = {
    "banner_kb": 150,          # hard ceiling for the hero
    "banner_target_kb": 80,    # aggressive target — reported, not fatal
    "assets_kb_total": 300,    # every local image, heavier theme of each pair
    "readme_first_load_kb": 800,
    "readme_requests": 8,
    "badges": 6,
}


class Gate:
    """Collects failures instead of dying on the first one, so a single run
    reports every way the build is wrong."""

    def __init__(self) -> None:
        self.errors: list[str] = []

    def check(self, ok: bool, msg: str) -> None:
        print(("  ok   " if ok else "  FAIL ") + msg)
        if not ok:
            self.errors.append(msg)

    @property
    def failed(self) -> bool:
        return bool(self.errors)


def _norm(hex_str: str) -> str:
    """svgo's convertColors shortens #FFFFFF to #fff, so compare after
    expanding the shorthand. Without this every light asset reports a stray."""
    h = hex_str.lower()
    if re.fullmatch(r"#[0-9a-f]{3}", h):
        h = "#" + "".join(c * 2 for c in h[1:])
    return h


def palette() -> set[str]:
    """Every colour the design is allowed to use, from the single source of truth."""
    profile = json.loads((ROOT / "data/profile.json").read_text(encoding="utf-8"))
    out: set[str] = set()
    for theme in ("dark", "light"):
        for key, val in profile["design"][theme].items():
            if not key.startswith("_"):
                out.add(_norm(val))
    return out


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def check_svg(path: Path, g: Gate, allowed: set[str]) -> dict:
    """Validate one SVG and return its measurements."""
    raw = path.read_bytes()
    rel = path.relative_to(ROOT)
    print(f"\n{rel}  {len(raw):,} B")

    # --- parse -------------------------------------------------------------
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        g.check(False, f"{rel.name}: XML parse error: {exc}")
        return {"bytes": len(raw), "smil": -1, "uses": 0}

    # --- structure ---------------------------------------------------------
    g.check(root.get("viewBox") is not None, f"{rel.name}: has viewBox")
    g.check(root.get("width") is not None and root.get("height") is not None,
            f"{rel.name}: has explicit width/height (no layout reflow on load)")

    counts: dict[str, int] = {}
    smil = 0
    uses = 0
    ids: set[str] = set()
    hrefs: set[str] = set()
    text_elems = 0

    # Two passes: an id may legally follow the <use> that points at it, so a
    # single forward-only pass would report every reference as dangling.
    for el in root.iter():
        tag = _local(el.tag)
        counts[tag] = counts.get(tag, 0) + 1
        if tag in SMIL_TAGS:
            smil += 1
        if tag == "text":
            text_elems += 1
        eid = el.get("id")
        if eid:
            ids.add(eid)

    for el in root.iter():
        if _local(el.tag) == "use":
            href = el.get("href") or el.get("{http://www.w3.org/1999/xlink}href") or ""
            if href.startswith("#"):
                hrefs.add(href[1:])
                uses += 1
    dangling = sorted(h for h in hrefs if h not in ids)

    g.check(not dangling, f"{rel.name}: every use href resolves ({len(hrefs)} refs)")
    if dangling:
        print(f"         dangling: {dangling[:8]}")

    g.check(text_elems == 0, f"{rel.name}: no <text> — all type is outlined ({text_elems})")

    blob = raw.decode("utf-8", "replace")
    g.check("font-family" not in blob and "@font-face" not in blob,
            f"{rel.name}: no font dependency")
    g.check("<title" in blob and "<desc" in blob,
            f"{rel.name}: keeps <title> and <desc> for screen readers")

    # --- motion ------------------------------------------------------------
    lo, hi = EXPECTED_SMIL.get(path.name.rsplit("-", 1)[0], (0, 0))
    g.check(lo <= smil <= hi, f"{rel.name}: {smil} SMIL nodes (allowed {lo}-{hi})")

    # Counting nodes is not enough: an animation can exist and drive nothing.
    # svgo's convertShapeToPath rewrote the clip <rect width="0"> as a <path>,
    # after which attributeName="width" targets an attribute paths do not have.
    # The count stayed at 4, the screenshot still looked composed, and only the
    # "now" marker - which sits outside the clip - survived. So verify ownership.
    orphans = []
    for el in root.iter():
        for child in el:
            if _local(child.tag) != "animate":
                continue
            if (child.get("attributeType") or "").upper() == "CSS":
                continue          # CSS properties are not XML attributes
            attr = child.get("attributeName")
            if attr in (None, "transform"):
                continue          # transform is driven by <animateTransform>
            # svgo drops opacity="1" as a default, and opacity applies to every
            # element, so a missing opacity still animates something real
            if attr not in el.attrib and attr != "opacity":
                orphans.append(f"<{_local(el.tag)} {attr=}>")
    g.check(not orphans,
            f"{rel.name}: every <animate> drives an attribute its element owns")
    if orphans:
        print(f"         animating nothing: {orphans}")

    # --- palette -----------------------------------------------------------
    # Scan only real colour attributes. A raw hex regex would also catch id
    # references — href="#b1a", clip-path="url(#n)" — and every glyph id looks
    # exactly like a 3-digit colour, which is why those showed up as "stray".
    scan = raw.decode("utf-8", "replace")
    scan = re.sub(r'(?:xlink:)?href="#[^"]*"', "", scan)
    scan = re.sub(r'url\(#[^)]*\)', "", scan)
    scan = re.sub(r'\bid="[^"]*"', "", scan)
    found = {_norm(m.group(0)) for m in HEX.finditer(scan)}
    stray = sorted(c for c in found if c not in allowed)
    g.check(not stray, f"{rel.name}: all {len(found)} colours are declared tokens")
    if stray:
        print(f"         stray: {stray}")

    return {"bytes": len(raw), "smil": smil, "uses": uses, "colours": len(found)}


def count_requests(blob: str) -> tuple[int, int, int]:
    """(picture blocks, standalone <img>, distinct fetches).

    A <picture> costs exactly one request: the browser picks one source, so
    counting raw URLs would double every image. The same image used twice (the
    VERIFIED button under each project) is fetched once and cached, so fetches
    are counted by distinct URL, a <picture> keyed by its fallback <img>.
    """
    blocks = len(re.findall(r"<picture\b", blob, re.I))
    rest = re.sub(r"<picture\b.*?</picture>", "", blob, flags=re.I | re.S)
    standalone = len(re.findall(r"<img\b", rest, re.I))
    urls = set(re.findall(r'<img\b[^>]*\bsrc="([^"]+)"', blob, re.I))
    return blocks, standalone, len(urls)


def _fetch_size(url: str, timeout: float = 6.0) -> int | None:
    """Bytes of an external badge, or None if it cannot be reached right now.

    Deliberately forgiving: the gate's job is to catch *our* regressions, not to
    inherit the availability of a third-party CDN. Absence is reported, never
    raised.
    """
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (limitcodev-build)"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return len(resp.read())
    except Exception:
        return None


def check_readme(path: Path, g: Gate) -> None:
    """The README is the only thing the browser actually downloads."""
    print(f"\n{path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")
    blob = path.read_text(encoding="utf-8")

    # A <picture> costs exactly one request: the browser picks one source.
    # Counting raw URLs instead would double every image, and counting both
    # themes as bytes would double the payload the reader never downloads.
    blocks = re.findall(r"<picture\b.*?</picture>", blob, re.I | re.S)
    rest = re.sub(r"<picture\b.*?</picture>", "", blob, flags=re.I | re.S)

    bytes_total = 0
    local_hits: list[str] = []

    seen: set[tuple[str, ...]] = set()
    for blk in blocks:
        files = tuple(sorted({m.group(1) for m in LOCAL_SRC.finditer(blk)}))
        if not files or files in seen:      # a repeated image is fetched once
            continue
        seen.add(files)
        sizes = []
        for rel in files:
            p = ROOT / rel
            if p.exists():
                sizes.append(p.stat().st_size)
                local_hits.append(rel)
            else:
                g.check(False, f"README references missing file: {rel}")
        if sizes:
            # budget the heavier of the two themes: a dark reader must not be
            # the case that busts the ceiling
            bytes_total += max(sizes)

    for m in LOCAL_SRC.finditer(rest):
        rel = m.group(1)
        p = ROOT / rel
        if p.exists():
            bytes_total += p.stat().st_size
            local_hits.append(rel)
        else:
            g.check(False, f"README references missing file: {rel}")

    _blocks_n, standalone, requests = count_requests(blob)

    external = sorted({m.group(1) for m in ANY_SRC.finditer(blob)
                       if m.group(1).startswith("http")})
    badges = [u for u in external if BADGE.match(u)]

    print(f"  <picture>      : {len(blocks)}  (one fetch each)")
    print(f"  standalone img : {standalone}")
    print(f"  local bytes    : {bytes_total:,}  (heavier theme of each pair)")
    print(f"  external URLs  : {len(external)}  ({len(badges)} badges)")

    # External badges are real payload too. Measured when the network is up,
    # skipped when it is not — a CDN being down must not fail a build that is
    # otherwise correct, so this is reported and only counted when it lands.
    ext_bytes, ext_measured = 0, 0
    for url in external:
        host = urllib.parse.urlsplit(url).hostname or ""
        size = COUNTER_BYTES.get(host)
        if size is None:
            size = _fetch_size(url)
        if size is None:
            print(f"  note           : could not measure {url[:64]}")
        else:
            ext_bytes += size
            ext_measured += 1
    print(f"  external bytes : {ext_bytes:,}  ({ext_measured}/{len(external)} measured)")

    first_load = bytes_total + ext_bytes
    print(f"  est. requests  : {requests}")
    print(f"  first load     : {first_load:,}")

    g.check(first_load <= BUDGETS["readme_first_load_kb"] * 1024,
            f"README first load {first_load/1024:.1f} KB "
            f"<= {BUDGETS['readme_first_load_kb']} KB")
    g.check(requests <= BUDGETS["readme_requests"],
            f"README requests {requests} <= {BUDGETS['readme_requests']}")
    g.check(len(badges) <= BUDGETS["badges"],
            f"badges {len(badges)} <= {BUDGETS['badges']}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--readme", default=str(ROOT / "README.md"))
    args = ap.parse_args()

    g = Gate()
    allowed = palette()
    print(f"palette: {len(allowed)} declared tokens")
    print("allowed:", " ".join(sorted(allowed)))

    assets = ROOT / "assets"
    results = {}
    for name in (f"{a}-{t}.svg" for a in ASSETS for t in ("dark", "light")):
        p = assets / name
        if not p.exists():
            g.check(False, f"{name} missing — did the build run?")
            continue
        results[name] = check_svg(p, g, allowed)

    # --- budgets -----------------------------------------------------------
    print("\nbudgets")
    # a reader downloads one theme of each pair, so budget the heavier one
    total = sum(max(results.get(f"{a}-{t}.svg", {"bytes": 0})["bytes"]
                    for t in ("dark", "light")) for a in ASSETS)
    for name in ("banner-dark.svg", "banner-light.svg"):
        if name not in results:
            continue
        kb = results[name]["bytes"] / 1024
        g.check(kb <= BUDGETS["banner_kb"],
                f"{name} {kb:.1f} KB <= {BUDGETS['banner_kb']} KB")
        if kb > BUDGETS["banner_target_kb"]:
            print(f"  note {name} is above the {BUDGETS['banner_target_kb']} KB "
                  f"stretch target (still inside the ceiling)")
    g.check(total <= BUDGETS["assets_kb_total"] * 1024,
            f"all assets {total/1024:.1f} KB <= {BUDGETS['assets_kb_total']} KB")

    readme = Path(args.readme)
    if readme.exists():
        check_readme(readme, g)
    else:
        g.check(False, f"{readme} not found")

    print()
    if g.failed:
        print(f"GATE FAILED — {len(g.errors)} problem(s)")
        for e in g.errors:
            print(f"  - {e}")
        return 1
    print("GATE PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
