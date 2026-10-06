#!/usr/bin/env python3
"""dither.py — photo and logo to 1-bit dots, plus the dots that travel between them.

Decisions that carry this file:

**Cut the subject out first.** The source is an ID-style photo on a white wall.
Dithered as-is, the wall is the largest tone in the frame and prints as a solid
block around a face-shaped hole. A flood fill from the border over near-white
pixels removes the wall, so only the person is ever inked.

**Ink the shadows, on both themes.** Hair, brows, eyes and the jaw line are
what make a face recognisable at 100 x 125 cells. Inking highlights instead
(the obvious choice on a dark page) loses the hair entirely and leaves a pale
mask. Tones are rank-equalised inside the subject only, so exposure does not
matter, then a gamma pulls the overall density down to about a third.

**Atkinson error diffusion.** It diffuses only 6/8 of the error, which keeps
contrast in the features and leaves flat areas clean — it reads as a drawing
rather than a halftone. Bayer was smaller but printed a visible grid.

**Travellers.** The transition between pictures is a few hundred dots that
really move: `travellers` samples them from the source picture and pairs each
with a destination dot by minimum total squared distance (Hungarian method),
so they fly the shortest overall routes and no two land on the same cell.
The dense pictures only fade; the travellers carry the motion.
"""
from __future__ import annotations

import re
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps
from scipy.optimize import linear_sum_assignment

WALL_MIN = 205       # a pixel is wall when all of R, G, B are above this
GAMMA = 1.6          # >1 thins the ink; 1.6 lands near 35 % of the subject


def _subject_mask(im: Image.Image) -> Image.Image:
    """Alpha: 0 on wall connected to the border, 255 on the person."""
    a = np.asarray(im.convert("RGB")).astype(np.int16)
    h, w, _ = a.shape
    wall_like = a.min(axis=2) > WALL_MIN
    wall = np.zeros((h, w), bool)
    todo = deque([(y, x) for y in range(h) for x in (0, w - 1)]
                 + [(0, x) for x in range(w)])
    while todo:
        y, x = todo.popleft()
        if 0 <= y < h and 0 <= x < w and wall_like[y, x] and not wall[y, x]:
            wall[y, x] = True
            todo.extend(((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)))
    alpha = np.where(wall, 0, 255).astype(np.uint8)
    return Image.fromarray(alpha).filter(ImageFilter.MedianFilter(5))


def _crop_to_aspect(im: Image.Image, aspect: float) -> Image.Image:
    w, h = im.size
    if w / h > aspect:
        new_w = int(round(h * aspect))
        left = (w - new_w) // 2
        return im.crop((left, 0, left + new_w, h))
    new_h = int(round(w / aspect))
    return im.crop((0, 0, w, new_h))      # keep the top: that is where the face is


def save_grid(source: Path, dest: Path, grid_w: int, grid_h: int) -> None:
    """Write the one-pixel-per-cell greyscale + alpha grid that gets committed.

    The photo itself never enters git; this thumbnail at the banner's own
    resolution is everything `portrait` reads.
    """
    im = Image.open(source).convert("RGB")
    alpha = _subject_mask(im)
    aspect = grid_w / grid_h
    size = (grid_w, grid_h)
    gray = ImageOps.grayscale(_crop_to_aspect(im, aspect).resize(size, Image.Resampling.LANCZOS))
    gray = gray.filter(ImageFilter.UnsharpMask(2, 120, 2))
    mask = _crop_to_aspect(alpha, aspect).resize(size, Image.Resampling.LANCZOS)
    Image.merge("LA", (gray, mask)).save(dest, optimize=True)


def _atkinson(tone: np.ndarray) -> np.ndarray:
    t = tone.astype(np.float64).copy()
    h, w = t.shape
    out = np.zeros((h, w), bool)
    for y in range(h):
        for x in range(w):
            on = t[y, x] >= 0.5
            out[y, x] = on
            err = (t[y, x] - on) / 8
            for dy, dx in ((0, 1), (0, 2), (1, -1), (1, 0), (1, 1), (2, 0)):
                yy, xx = y + dy, x + dx
                if yy < h and 0 <= xx < w:
                    t[yy, xx] += err
    return out


def runs(lit: np.ndarray) -> str:
    """Run-length encode `lit` as `M x y.5h n` per horizontal run.

    The result is *stroked* one cell wide, centred on the row, so a zero-area
    run still paints its cells.
    """
    out: list[str] = []
    for y, row in enumerate(lit.tolist()):
        x = 0
        while x < len(row):
            if not row[x]:
                x += 1
                continue
            start = x
            while x < len(row) and row[x]:
                x += 1
            out.append(f"M{start} {y + 0.5:g}h{x - start}")
    return "".join(out)


def travellers(src: np.ndarray, dst: np.ndarray, n: int,
               seed: int = 13) -> list[tuple[int, int, int, int]]:
    """(x, y, dx, dy) for `n` dots of `src` paired with dots of `dst`.

    Pairing minimises the summed squared distance, which is what makes the
    morph read as one picture rearranging itself rather than two cross-fading.
    """
    rng = np.random.default_rng(seed)
    a = np.argwhere(src)[:, ::-1]
    b = np.argwhere(dst)[:, ::-1]
    a = a[rng.choice(len(a), min(n, len(a)), replace=False)]
    b = b[rng.choice(len(b), min(n, len(b)), replace=False)]
    cost = ((a[:, None, :] - b[None, :, :]) ** 2).sum(axis=2)
    rows, cols = linear_sum_assignment(cost)
    return [(int(a[r][0]), int(a[r][1]), int(b[c][0] - a[r][0]), int(b[c][1] - a[r][1]))
            for r, c in zip(rows, cols)]


def portrait(grid: Path) -> np.ndarray:
    """Inked cells of the committed portrait grid."""
    la = Image.open(grid).convert("LA")
    gray = np.asarray(la.getchannel("L")).astype(np.float64) / 255
    subject = np.asarray(la.getchannel("A")) > 127

    rank = np.empty(subject.sum())
    rank[np.argsort(gray[subject], kind="stable")] = np.linspace(0, 1, rank.size)
    tone = np.zeros_like(gray)
    tone[subject] = (1 - rank) ** GAMMA * 0.95       # shadows carry the ink
    return _atkinson(tone) & subject


# --- logo ---------------------------------------------------------------------

_NUM = re.compile(r"-?(?:\d+\.?\d*|\.\d+)(?:e-?\d+)?")


def _flatten(d: str, steps: int = 12) -> list[tuple[float, float]]:
    """Polygon for a path made of m/c/l/z commands (absolute or relative)."""
    pts: list[tuple[float, float]] = []
    x = y = 0.0
    for cmd, args in re.findall(r"([mMcClLzZ])([^mMcClLzZ]*)", d):
        nums = [float(n) for n in _NUM.findall(args)]
        rel = cmd.islower()
        c = cmd.lower()
        if c in ("m", "l"):
            for i in range(0, len(nums), 2):
                x, y = (x + nums[i], y + nums[i + 1]) if rel else (nums[i], nums[i + 1])
                pts.append((x, y))
        elif c == "c":
            for i in range(0, len(nums), 6):
                a = nums[i:i + 6]
                if rel:
                    a = [a[0] + x, a[1] + y, a[2] + x, a[3] + y, a[4] + x, a[5] + y]
                p0 = np.array([x, y])
                p1, p2, p3 = np.array(a[0:2]), np.array(a[2:4]), np.array(a[4:6])
                for s in range(1, steps + 1):
                    t = s / steps
                    p = ((1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1
                         + 3 * (1 - t) * t ** 2 * p2 + t ** 3 * p3)
                    pts.append((float(p[0]), float(p[1])))
                x, y = a[4], a[5]
    return pts


def logo(path_d: str, view: float, grid_w: int, grid_h: int, size: int) -> np.ndarray:
    """The logo filled with a top-lit gradient, dithered on the portrait's grid.

    `view` is the logo's square viewBox side; `size` is how many cells wide it
    is drawn, centred in the grid. Same dots, same pitch, so the dissolve from
    face to logo is dot for dot.
    """
    ss = 4                                   # supersample the edge
    scale = size * ss / view
    ox = (grid_w - size) / 2 * ss
    oy = (grid_h - size) / 2 * ss
    canvas = Image.new("L", (grid_w * ss, grid_h * ss), 0)
    poly = [(ox + px * scale, oy + py * scale) for px, py in _flatten(path_d)]
    ImageDraw.Draw(canvas).polygon(poly, fill=255)
    inside = np.asarray(canvas.resize((grid_w, grid_h), Image.Resampling.BOX)) > 127

    ramp = np.linspace(0.92, 0.55, grid_h)[:, None] * np.ones((1, grid_w))
    return _atkinson(np.where(inside, ramp, 0)) & inside
