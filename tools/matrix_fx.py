#!/usr/bin/env python3
"""
matrix_fx.py - composites digital rain around the rendered splat turntable.

Runs over the frames splat_render.py produced and writes a new set. Kept as a
separate pass so the expensive part (the actual gaussian rasterisation, ~2.5s a
frame) does not have to be repeated every time the look is tweaked.

Two decisions worth stating:

* The glyphs are drawn from a bitmap set defined in this file rather than from a
  system font. Real katakana would mean depending on a CJK font being installed,
  which is true on Windows and generally false on a CI runner - the effect would
  silently degrade to tofu boxes. Hand-drawn 5x7 glyphs always render.

* The rain loops exactly. Each column falls a whole number of times over the
  frame count, so the last frame hands off seamlessly to the first. Rain that
  merely looks random produces a visible jump every cycle, which is the one
  thing people always notice.

    python tools/matrix_fx.py assets/statue_frames --out assets/statue_fx_frames
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import numpy as np
from PIL import Image

# ---------------------------------------------------------------------------
# Pseudo-katakana. Straight strokes on a 5x7 grid - close enough to read as
# Matrix rain at 12 pixels tall, and free of any font dependency.
# ---------------------------------------------------------------------------

GLYPHS = [
    ("#####", "....#", "...#.", "..##.", ".#.#.", "#..#.", "...#."),
    ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    (".....", "#####", "....#", "...#.", "..#..", ".#...", "#...."),
    ("#...#", "#...#", "#####", "....#", "....#", "...#.", "..#.."),
    ("..#..", "#####", "..#..", "..#..", "#####", "..#..", "..#.."),
    ("#####", "#...#", "#...#", "#####", "#....", "#....", "#...."),
    (".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."),
    ("#....", "#####", "#...#", "#...#", "#...#", "#...#", "#...#"),
    ("#####", "....#", "..###", ".#..#", "#...#", "....#", "....#"),
    ("..#..", "..#..", "#####", "..#..", "..#..", ".#.#.", "#...#"),
    ("#...#", ".#.#.", "..#..", "#####", "..#..", "..#..", "..#.."),
    ("#####", "#....", "#....", "####.", "....#", "....#", "####."),
    (".....", "####.", "....#", ".###.", "#....", "#....", "#####"),
    ("#...#", "#...#", "#...#", "#...#", "#...#", "#...#", "#####"),
    ("#####", "....#", "....#", "#####", "#....", "#....", "#####"),
    ("..#..", ".###.", "#.#.#", "..#..", "..#..", "..#..", "..#.."),
    ("#####", "#...#", "#####", "#...#", "#####", ".....", "....."),
    (".#...", ".#...", ".####", ".#..#", ".#..#", "##..#", "....#"),
    ("#####", "....#", "....#", "....#", "....#", "....#", "#####"),
    ("....#", "....#", "....#", "#####", "....#", "....#", "....#"),
    ("#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"),
    ("#####", ".....", "#####", ".....", "#####", ".....", "....."),
    ("..#..", "..#..", "..#..", "#####", "..#..", "..#..", "#####"),
    ("###..", "..#..", "..#..", "..#..", "..#..", "..#..", ".####"),
    (".....", "..#..", ".....", ".....", "..#..", ".....", "....."),
    ("#####", "#....", "#####", "....#", "#####", ".....", "....."),
    ("....#", "...#.", "..#..", ".#...", "#....", ".....", "....."),
    ("#####", "#...#", "#...#", "#...#", "#...#", "#...#", "#####"),
]

GW, GH = 5, 7


def glyph_masks(cell_w: int, cell_h: int) -> np.ndarray:
    """Rasterise every glyph once, at the cell size, as float coverage."""
    out = np.zeros((len(GLYPHS), cell_h, cell_w), np.float32)
    for gi, rows in enumerate(GLYPHS):
        small = np.array([[1.0 if ch == "#" else 0.0 for ch in r] for r in rows],
                         dtype=np.float32)
        img = Image.fromarray((small * 255).astype(np.uint8), mode="L")
        # Nearest keeps the strokes hard-edged; smoothing them turns the glyphs
        # into grey mush at this size.
        img = img.resize((max(1, cell_w - 2), max(1, cell_h - 3)), Image.NEAREST)
        pad = np.zeros((cell_h, cell_w), np.float32)
        a = np.asarray(img, dtype=np.float32) / 255.0
        pad[1:1 + a.shape[0], 1:1 + a.shape[1]] = a
        out[gi] = pad
    return out


# ---------------------------------------------------------------------------
# Rain
# ---------------------------------------------------------------------------


def build_rain(width: int, height: int, frames: int, cell_w: int, cell_h: int,
               seed: int, density: float, speed_lo: int, speed_hi: int,
               tail_lo: int, tail_hi: int) -> np.ndarray:
    """Per-frame brightness field for one rain layer, shape (frames, H, W).

    Brightness is 0..1 with the leading glyph at 1. Colour is applied later so
    the same field can drive both the background and foreground layers.
    """
    rng = np.random.default_rng(seed)
    cols = width // cell_w
    rows = height // cell_h
    period = rows + max(tail_hi, 1) + 4        # cells travelled per full cycle

    masks = glyph_masks(cell_w, cell_h)
    field = np.zeros((frames, height, width), np.float32)

    active = rng.random(cols) < density
    starts = rng.random(cols) * period
    # Integer falls-per-loop is what makes the animation seamless.
    laps = rng.integers(speed_lo, speed_hi + 1, cols)
    tails = rng.integers(tail_lo, tail_hi + 1, cols)
    # Each column gets its own glyph phase so they do not change in lockstep.
    phase = rng.integers(0, len(GLYPHS), cols)

    for c in range(cols):
        if not active[c]:
            continue
        x0 = c * cell_w
        for f in range(frames):
            head = (starts[c] + period * laps[c] * f / frames) % period
            for t in range(tails[c]):
                cell = int(head) - t
                if cell < 0 or cell >= rows:
                    continue
                # Bright head, exponential falloff down the tail.
                b = 1.0 if t == 0 else 0.62 * (1.0 - t / tails[c]) ** 1.5
                if b < 0.02:
                    continue
                gi = (phase[c] + cell * 7 + (f // 5) * (c % 3)) % len(GLYPHS)
                y0 = cell * cell_h
                field[f, y0:y0 + cell_h, x0:x0 + cell_w] = np.maximum(
                    field[f, y0:y0 + cell_h, x0:x0 + cell_w], masks[gi] * b
                )
    return field


# ---------------------------------------------------------------------------
# Compositing
# ---------------------------------------------------------------------------


def grade(rgb: np.ndarray, amount: float) -> np.ndarray:
    """Push the subject toward phosphor green without flattening it.

    Fully tinting it would throw away the photoreal detail that makes the splat
    worth showing, so this only blends part way and keeps the original
    luminance structure.
    """
    lum = (rgb * np.array([0.299, 0.587, 0.114])).sum(-1, keepdims=True)
    tint = lum * np.array([0.30, 1.00, 0.45])
    return np.clip(rgb * (1 - amount) + tint * amount, 0, 1)


def rounded_mask(h: int, w: int, r: int) -> np.ndarray:
    m = np.ones((h, w), np.float32)
    yy, xx = np.mgrid[0:r, 0:r].astype(np.float32)
    d = np.sqrt((r - 1 - yy) ** 2 + (r - 1 - xx) ** 2)
    corner = np.clip(r - d, 0, 1)
    m[:r, :r] = corner
    m[:r, -r:] = corner[:, ::-1]
    m[-r:, :r] = corner[::-1, :]
    m[-r:, -r:] = corner[::-1, ::-1]
    return m


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("frames", type=pathlib.Path)
    ap.add_argument("--out", type=pathlib.Path, required=True)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--cell", type=int, default=11, help="glyph cell width")
    ap.add_argument("--tint", type=float, default=0.34,
                    help="how far the subject is graded toward green, 0..1")
    ap.add_argument("--bg", default="#04070a")
    ap.add_argument("--radius", type=int, default=14)
    ap.add_argument("--scanlines", type=float, default=0.10)
    ap.add_argument("--rim", type=float, default=0.55, help="green edge light")
    args = ap.parse_args()

    paths = sorted(args.frames.glob("*.png"))
    if not paths:
        raise SystemExit(f"no frames in {args.frames}")
    src = [Image.open(p).convert("RGBA") for p in paths]
    W, H = src[0].size
    N = len(src)
    print(f"{N} frames at {W}x{H}")

    cw, ch = args.cell, args.cell + 3
    print("building rain ...")
    back = build_rain(W, H, N, cw, ch, args.seed, 0.78, 1, 3, 9, 18)
    # The near layer is sparser, faster and larger, which reads as depth.
    front = build_rain(W, H, N, cw + 6, ch + 8, args.seed + 101, 0.30, 2, 4, 4, 8)

    bg = np.array([int(args.bg[i:i + 2], 16) / 255 for i in (1, 3, 5)])
    mask = rounded_mask(H, W, args.radius)

    # Every third row darkened, CRT style. Shaped (H,1,1) to broadcast over
    # the (H,W,3) canvas.
    scan = (1.0 - args.scanlines
            * (np.arange(H) % 3 == 0).astype(np.float32))[:, None, None]

    args.out.mkdir(parents=True, exist_ok=True)
    for old in args.out.glob("*.png"):
        old.unlink()

    HEAD = np.array([0.72, 1.0, 0.78])      # near-white leading glyph
    BODY = np.array([0.10, 0.92, 0.34])     # phosphor green

    print("compositing ...")
    for i, im in enumerate(src):
        rgba = np.asarray(im, dtype=np.float32) / 255.0
        rgb, alpha = rgba[:, :, :3], rgba[:, :, 3:4]

        # Backdrop plus the far rain layer. The brightest cells shift toward
        # white so the leading glyph of each stream reads as the hot head.
        b = back[i][:, :, None]
        hot = np.clip((b - 0.85) / 0.15, 0, 1)
        canvas = bg + (BODY * (1 - hot) + HEAD * hot) * b

        # Subject over it, graded green and rim-lit.
        subject = grade(rgb, args.tint)
        canvas = canvas * (1 - alpha) + subject * alpha

        if args.rim > 0:
            a = alpha[:, :, 0]
            edge = np.clip(a - np.minimum.reduce([
                np.roll(a, 1, 0), np.roll(a, -1, 0),
                np.roll(a, 1, 1), np.roll(a, -1, 1),
            ]), 0, 1)
            canvas += (edge ** 0.7)[:, :, None] * BODY * args.rim

        # Near rain passes in front of the subject.
        f = front[i][:, :, None]
        canvas = canvas * (1 - 0.85 * f) + BODY * f * 0.85

        canvas = canvas * scan

        out = np.clip(canvas, 0, 1) * mask[:, :, None]
        rgba_out = np.dstack([out, mask])
        Image.fromarray((rgba_out * 255).astype(np.uint8)).save(
            args.out / f"{i:04d}.png")

        if (i + 1) % 10 == 0 or i == N - 1:
            sys.stdout.write(f"\r  {i + 1}/{N}")
            sys.stdout.flush()

    print(f"\nwrote {N} frames -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
