#!/usr/bin/env python3
"""
splat_encode.py - packs rendered turntable frames into one animated image.

Format notes, since this is the part that decides whether the thing works on a
profile page at all:

  * APNG is the safe choice. The file extension is .png, which GitHub has always
    accepted, and every current browser animates it. Alpha is per-pixel.
  * Animated WebP is far smaller for photographic content and also supports
    alpha, but it is a less-travelled path through GitHub's image proxy.

Both are written so the size trade-off is visible, and the README can point at
whichever wins.

    python tools/splat_encode.py ../assets/statue_frames --out ../assets/statue
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import numpy as np
from PIL import Image


def load_frames(folder: pathlib.Path) -> list[Image.Image]:
    paths = sorted(folder.glob("*.png"))
    if not paths:
        raise SystemExit(f"no frames in {folder}")
    return [Image.open(p).convert("RGBA") for p in paths]


def common_crop(frames: list[Image.Image], pad: int = 2) -> tuple[int, int, int, int]:
    """Tightest box containing visible pixels in *any* frame.

    Cropping per frame would make the subject jitter, so the union is used. The
    renderer leaves slack around the figure for framing; that slack is pure
    transparent padding in the encoded file, and it is worth reclaiming.
    """
    box = None
    for f in frames:
        alpha = np.array(f)[:, :, 3]
        ys, xs = np.nonzero(alpha > 6)
        if not len(xs):
            continue
        b = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
        box = b if box is None else (
            min(box[0], b[0]), min(box[1], b[1]),
            max(box[2], b[2]), max(box[3], b[3]),
        )
    if box is None:
        raise SystemExit("every frame is fully transparent")

    w, h = frames[0].size
    return (max(0, box[0] - pad), max(0, box[1] - pad),
            min(w, box[2] + pad), min(h, box[3] + pad))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("frames", type=pathlib.Path)
    ap.add_argument("--out", type=pathlib.Path, required=True)
    ap.add_argument("--fps", type=float, default=20.0)
    ap.add_argument("--scale", type=float, default=1.0,
                    help="resize factor applied after cropping")
    ap.add_argument("--quality", type=int, default=78, help="WebP quality")
    ap.add_argument("--method", type=int, default=4,
                    help="WebP effort 0-6; 6 costs several minutes for well "
                         "under a percent of size, so 4 is the default")
    ap.add_argument("--apng", action="store_true",
                    help="also write an APNG; roughly 8x the size of the WebP, "
                         "so only worth it if animated WebP is a problem")
    ap.add_argument("--no-crop", action="store_true")
    args = ap.parse_args()

    frames = load_frames(args.frames)
    print(f"{len(frames)} frames at {frames[0].size[0]}x{frames[0].size[1]}")

    if not args.no_crop:
        box = common_crop(frames)
        frames = [f.crop(box) for f in frames]
        print(f"cropped to {frames[0].size[0]}x{frames[0].size[1]}")

    if args.scale != 1.0:
        w = round(frames[0].size[0] * args.scale)
        h = round(frames[0].size[1] * args.scale)
        frames = [f.resize((w, h), Image.LANCZOS) for f in frames]
        print(f"scaled to {w}x{h}")

    duration = round(1000 / args.fps)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    results = []

    webp = args.out.with_suffix(".webp")
    frames[0].save(
        webp, format="WEBP", save_all=True, append_images=frames[1:],
        duration=duration, loop=0, quality=args.quality, method=args.method,
        allow_mixed=True,
    )
    results.append(webp)

    if args.apng:
        apng = args.out.with_suffix(".png")
        frames[0].save(
            apng, format="PNG", save_all=True, append_images=frames[1:],
            duration=duration, loop=0, disposal=2, optimize=True,
        )
        results.append(apng)

    print()
    for p in results:
        size = p.stat().st_size
        flag = "" if size < 5_000_000 else "   <-- large for a README"
        print(f"  {p.name:<16} {size / 1e6:6.2f} MB{flag}")

    # A still, for the <picture> fallback and for anywhere animation is stripped.
    still = args.out.parent / f"{args.out.name}-still.png"
    frames[0].save(still, optimize=True)
    print(f"  {still.name:<16} {still.stat().st_size / 1e6:6.2f} MB (static)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
