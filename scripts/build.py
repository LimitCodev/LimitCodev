#!/usr/bin/env python3
"""build.py — the whole pipeline behind one command.

    python scripts/build.py

1. **Assets.** Every generator (banner, chart, stack, verified button) renders
   both themes; each raw SVG goes through svgo into `assets/`.
2. **README** is emitted after the assets exist, so the colophon quotes real
   byte counts and the real request count instead of placeholders.
3. **verify.py** runs last and can fail the build. A build that quietly ships a
   200 KB banner or a dropped animation is worse than no build.

svgo must be installed (`npm install`); if it is missing this exits with the
instruction rather than silently skipping optimisation.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))  # the generators import each other as siblings

import banner as banner_mod  # noqa: E402
import charts as charts_mod  # noqa: E402
import stack as stack_mod  # noqa: E402
import verified as verified_mod  # noqa: E402
from verify import count_requests  # noqa: E402

ASSETS = ROOT / "assets"
BUILD = ROOT / ".build"
TEMPLATE = ROOT / "templates" / "README.md.tmpl"
README = ROOT / "README.md"
SVGO = ROOT / "node_modules" / ".bin" / "svgo"
LANGUAGES = ROOT / "data" / "raw" / "languages.json"

# asset name -> generator module with render(theme, numbers) -> (svg, stats)
GENERATORS = {"banner": banner_mod, "chart": charts_mod,
              "stack": stack_mod, "verified": verified_mod}


def _svgo(src: Path, dst: Path) -> int:
    if not SVGO.exists():
        raise SystemExit(f"missing {SVGO.relative_to(ROOT)} — run `npm install` first")
    res = subprocess.run(
        [str(SVGO), str(src), "-o", str(dst), "--multipass"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if res.returncode != 0:
        raise SystemExit(f"svgo failed on {src.name}:\n{res.stdout}\n{res.stderr}")
    return dst.stat().st_size


def build_assets(numbers: dict) -> dict[str, int]:
    """Render and shrink every asset; return the heavier theme's bytes per asset."""
    sizes: dict[str, int] = {}
    for name, mod in GENERATORS.items():
        for theme in ("dark", "light"):
            svg, _stats = mod.render(theme, numbers)
            raw = BUILD / f"raw-{name}-{theme}.svg"
            raw.write_text(svg, encoding="utf-8")
            size = _svgo(raw, ASSETS / f"{name}-{theme}.svg")
            sizes[name] = max(sizes.get(name, 0), size)
            print(f"  {name}-{theme}.svg  {size:,} B")
    return sizes


# --- README blocks ----------------------------------------------------------

def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def _picture(name: str, alt: str, width: int | None = None, height: int | None = None) -> str:
    """A themed image: GitHub swaps the source on the reader's colour scheme."""
    size = (f' width="{width}"' if width else "") + (f' height="{height}"' if height else "")
    return (f'<picture><source media="(prefers-color-scheme: dark)" '
            f'srcset="assets/{name}-dark.svg">'
            f'<img src="assets/{name}-light.svg"{size} alt="{_esc(alt)}"></picture>')


def _alt_banner(p: dict, n: dict) -> str:
    ident = p["identity"]
    return (
        f"{ident['name']}, {ident['role'].lower()} at {ident['school']}. An i3 desktop "
        f"on Arch Linux runs fastfetch: a dot portrait that turns into the Arch logo, "
        f"{n['contributions']} contributions and {n['commits']} commits in the past "
        f"year, {n['repos']} public repositories and {n['source_bytes']:,} bytes of "
        f"source led by {', '.join(n['top_langs'])}."
    )


def _alt_chart(rows: list[tuple[str, int]], total: int, repos: int) -> str:
    body = ", ".join(f"{name} {v:,}" for name, v in rows)
    return (f"Bar chart of source bytes by language across {repos} public repositories: "
            f"{body}. Total {total:,} bytes.")


def _certificates(p: dict) -> dict[str, str]:
    return {pr["name"]: pr["certificate"] for pr in p["projects"] if pr.get("certificate")}


def _badges(p: dict) -> str:
    """One HTML line. Markdown and HTML mix badly on the same line in GitHub's
    renderer, and a single line keeps the images in one block. A badge tied to a
    project links to that project's certificate."""
    certs = _certificates(p)
    parts = [f'<img src="{_esc(p["counter"]["url"])}" alt="Profile views">']
    for b in p["badges"]:
        img = f'<img src="{_esc(b["url"])}" alt="{_esc(b["alt"])}">'
        link = certs.get(b.get("project", ""))
        parts.append(f'<a href="{_esc(link)}">{img}</a>' if link else img)
    return " ".join(parts)


def _projects(p: dict) -> str:
    blocks = []
    for pr in p["projects"]:
        facts = "\n".join(f"- {f}" for f in pr["facts"])
        stack = " ".join(f"`{s}`" for s in pr["stack"])
        cert = ""
        if pr.get("certificate"):
            button = _picture("verified", f"Verified: open the {pr['name']} certificate",
                              height=28)
            cert = f'\n\n<a href="{_esc(pr["certificate"])}">{button}</a>'
        blocks.append(
            f"### [{pr['name']}](https://github.com/{pr['repo']})\n"
            f"**{pr['subtitle']}** · {pr['role']}\n\n"
            f"{pr['summary']}\n\n"
            f"{facts}\n\n"
            f"{stack}\n\n"
            f"**Outcome:** {pr['outcome']}{cert}"
        )
    creds = " · ".join(
        f"{a['title']} — {a['issuer']} ({a['date']})"
        for a in p["achievements"]
        # anything already printed as a project Outcome would just repeat
        if a["title"] not in " ".join(pr["outcome"] + pr["subtitle"] for pr in p["projects"])
    )
    if creds:
        blocks.append(f"**Other credentials:** {creds}")
    return "\n\n".join(blocks)


def _stack(p: dict) -> str:
    alt = "Toolbox. " + "; ".join(f"{g['group']}: {', '.join(g['items'])}" for g in p["stack"])
    return _picture("stack", alt + ".", width=860)


def _links(p: dict) -> str:
    items = [("LinkedIn", p["contact"]["primary_url"])]
    items += [(s["label"], s["url"]) for s in p["social"]]
    # No email on purpose: a public README is scraped by spam bots.
    return " · ".join(f"[{lab}]({url})" for lab, url in items)


def _colophon(date: str, sizes: dict[str, int], requests: int) -> str:
    each = " + ".join(f"{name} {b / 1024:.1f} KB" for name, b in sizes.items())
    return (
        f"Generated by <code>scripts/build.py</code> from <code>data/profile.json</code> · "
        f"{each} = {sum(sizes.values()) / 1024:.1f} KB · {requests} image requests · "
        f"outlined text, no web fonts, no JavaScript · "
        f"surfaces are GitHub Primer tokens so the panels have no edge to fade into · "
        f"data from {date}, refreshed daily by GitHub Actions"
    )


def make_readme(p: dict, numbers: dict, sizes: dict[str, int]) -> str:
    """Pure: assemble the README text. The colophon quotes its own request
    count, which depends only on structure, so a first pass measures it."""
    rows = charts_mod.language_rows(json.loads(LANGUAGES.read_text(encoding="utf-8")))
    total = sum(v for _, v in rows)

    def fill(requests: int) -> str:
        tokens = {
            "ALT_BANNER": _alt_banner(p, numbers),
            "ALT_CHART": _alt_chart(rows, total, numbers["repos"]),
            "LEDE": (
                f"{p['identity']['role']} at **{p['identity']['school']}** "
                f"({p['identity']['school_abbr']}), {p['identity']['location']} · "
                f"{p['identity']['period']}.\n\n"
                f"{p['identity']['summary']}\n\n"
                f"**Currently:** {p['identity']['currently']}"
            ),
            "BADGES": _badges(p),
            "PROJECTS": _projects(p),
            "STACK": _stack(p),
            "LINKS": _links(p),
            "COLOPHON": _colophon(numbers["date"], sizes, requests),
        }
        out = TEMPLATE.read_text(encoding="utf-8")
        for key, value in tokens.items():
            out = out.replace("{{" + key + "}}", value)
        leftover = re.findall(r"\{\{(\w+)\}\}", out)
        if leftover:
            raise SystemExit(f"README template has unsubstituted tokens: {leftover}")
        return out

    return fill(count_requests(fill(0))[2])


def main() -> int:
    print("build")
    ASSETS.mkdir(exist_ok=True)
    BUILD.mkdir(exist_ok=True)

    numbers = banner_mod.load_numbers()
    p = numbers["profile"]

    print("\n1. assets")
    sizes = build_assets(numbers)

    print("\n2. readme")
    readme_text = make_readme(p, numbers, sizes)
    README.write_text(readme_text, encoding="utf-8")
    print(f"  README.md  {len(readme_text.encode('utf-8')):,} B")

    print("\n3. gate")
    res = subprocess.run([sys.executable, str(HERE / "verify.py")], cwd=ROOT, text=True)
    return res.returncode


if __name__ == "__main__":
    sys.exit(main())
