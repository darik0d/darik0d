#!/usr/bin/env python3
"""
make_neofetch.py - the terminal-style identity panel.

Replaces both the prose bio and the old stats card with a single neofetch-style
readout, which carries the same information in about a fifth of the vertical
space.

One implementation note that matters. The dotted leaders between a label and its
value are a dashed *line*, not a run of "." characters. Monospace advance widths
are not actually constant across the stack - DejaVu Sans Mono and Menlo sit near
0.60em, Consolas near 0.55em - so a leader built from text would be the right
length on the machine that generated it and visibly wrong on Windows. A dashed
line is immune to that, and the value is end-anchored so it lands on the right
margin whatever the font does.

    python tools/make_neofetch.py            # uses cached API data
    python tools/make_neofetch.py --refresh  # refetches
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_stats import THEMES, collect, human_bytes, top_languages  # noqa: E402
from make_sticker import (  # noqa: E402
    VINYL_BIG, VINYL_BORDER, VINYL_BOT, VINYL_H, VINYL_TOP, VINYL_W,
    vinyl_body, vinyl_defs,
)

# The sticker sits across the panel's bottom-right corner, half on and half off.
# GitHub strips `style` attributes from README HTML, so two separate images
# cannot be overlapped with CSS - the only way to get a real overlap is to draw
# the sticker inside this SVG.
STICKER_SCALE = 0.62
STICKER_ANGLE = -8.0
OVERHANG_X = 30     # how far past the panel's right edge it reaches
OVERHANG_Y = 26     # ... and past the bottom edge
STICKER_ROOM = 52   # blank band at the panel foot so no row is covered

MONO = ("ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, "
        "'DejaVu Sans Mono', monospace")

W = 780
PAD_L, PAD_R = 26, 26
ROW = 23           # baseline-to-baseline
SECTION_GAP = 16   # extra space above a section header
TOP = 44

USER = "darik0d"


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# Counted by the language stats but not what anyone means by "languages I
# program in". Makefile and CMake in particular rank high purely on volume from
# the coursework repos.
NOT_PROGRAMMING = {
    "Makefile", "CMake", "Dockerfile", "Shell", "Batchfile",
    "HTML", "CSS", "SCSS", "TeX", "YAML", "Other",
}


def build_rows(d: dict) -> list:
    """(kind, label, value) - kind is 'user', 'head', 'row' or 'gap'."""
    ranked = [n for n in d["languages"] if n not in NOT_PROGRAMMING]
    langs = ranked[:4]
    total = human_bytes(sum(d["languages"].values()))

    return [
        ("user", f"{USER}@github", ""),
        ("row", "Alias", "darik0d  ·  O'Daria"),
        ("row", "Host", "Whole world"),
        ("row", "Status", "Freelance, available from September"),

        ("gap", "", ""),
        ("head", "Languages", ""),
        ("row", "Programming", ", ".join(langs)),
        ("row", "Markup", "HTML, CSS, LaTeX, YAML"),
        ("row", "Human", "English, Esperanto, Russian, Ukrainian, Dutch & French"),

        ("gap", "", ""),
        ("head", "Building", ""),
        ("row", "Graphics", "Gaussian splats, CAD, Mechanical characters' rig"),
        ("row", "Research", "Photogrammetry, Spiking nets, Federated learning on microcontrollers"),
        ("row", "For fun", "Telegram bots, Three.js websites, hackathons, kiwi or potato classifier"),

        # ("gap", "", ""),
        # ("head", "Contact", ""),
        # ("row", "Email", "REPLACE_ME"),
        # ("row", "LinkedIn", "REPLACE_ME"),
        # ("row", "GitHub", USER),

        ("gap", "", ""),
        ("head", "GitHub", ""),
        ("row", "Contribution graph", "don't trust it"),
    ]


def build_svg(theme: str, d: dict, sticker: bool = True) -> str:
    c = THEMES[theme]
    rows = build_rows(d)

    # Lay out first, draw second. An earlier version computed the height with
    # one set of rules and positioned the rows with another, which left a block
    # of dead space at the bottom.
    placed: list[tuple[str, str, str, int]] = []
    y = TOP
    for kind, label, value in rows:
        if kind == "gap":
            y += SECTION_GAP
            continue
        placed.append((kind, label, value, y))
        y += ROW
    panel_h = y + 18 + (STICKER_ROOM if sticker else 0)

    # The canvas is bigger than the panel so the sticker has somewhere to hang
    # off into. Rotation grows its footprint, so the half-extents are computed
    # from the rotated box rather than the upright one.
    if sticker:
        import math
        hw = (VINYL_W / 2 + VINYL_BORDER) * STICKER_SCALE
        hh = (VINYL_H / 2 + VINYL_BORDER) * STICKER_SCALE
        rad = math.radians(abs(STICKER_ANGLE))
        rot_w = hw * math.cos(rad) + hh * math.sin(rad)
        rot_h = hw * math.sin(rad) + hh * math.cos(rad)
        cx = W + OVERHANG_X - rot_w
        cy = panel_h + OVERHANG_Y - rot_h
        canvas_w = math.ceil(max(W, cx + rot_w) + 2)
        canvas_h = math.ceil(max(panel_h, cy + rot_h) + 2)
    else:
        cx = cy = 0.0
        canvas_w, canvas_h = W, panel_h
    height = canvas_h

    p: list[str] = []
    add = p.append
    add(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {canvas_w} {height}" '
        f'width="{canvas_w}" height="{height}" fill="none" role="img" '
        f'aria-label="Profile readout for {USER}, also known as O\'Daria. '
        f'{VINYL_BIG} {VINYL_TOP}. Visit {VINYL_BOT}.">'
    )
    add(f"<title>{USER} - readout</title>")

    add("<defs>")
    add(
        f'<linearGradient id="nbg" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{c["bg0"]}"/>'
        f'<stop offset="1" stop-color="{c["bg1"]}"/></linearGradient>'
    )
    add(
        '<pattern id="ndots" width="26" height="26" patternUnits="userSpaceOnUse">'
        f'<circle cx="1.2" cy="1.2" r="1.2" fill="{c["grid"]}"/></pattern>'
    )
    css = f"""
    .m {{ font-family: {MONO}; }}
    .k {{ font-size: 14px; fill: {c['accent']}; font-weight: 600; }}
    .v {{ font-size: 14px; fill: {c['text']}; }}
    .h {{ font-size: 13px; fill: {c['accent2']}; font-weight: 700;
          letter-spacing: 2.2px; }}
    .u {{ font-size: 16px; fill: {c['text']}; font-weight: 700;
          letter-spacing: 0.4px; }}
    .lead {{ stroke: {c['muted']}; stroke-width: 1.6; stroke-linecap: round;
             stroke-dasharray: 0.5 5.5; opacity: .55; }}
    .rule {{ stroke: {c['rule']}; stroke-width: 1; }}
    """
    if sticker:
        sk_defs, sk_css = vinyl_defs(c)
        css += sk_css
    bad = {ch for ch in "<>&" if ch in css}
    if bad:
        raise ValueError(f"stylesheet has XML-significant characters {sorted(bad)}")
    add("<style>" + " ".join(l.strip() for l in css.splitlines() if l.strip()) + "</style>")
    if sticker:
        add(sk_defs)
    add("</defs>")

    add(f'<rect width="{W}" height="{panel_h}" rx="16" fill="url(#nbg)"/>')
    add(f'<rect width="{W}" height="{panel_h}" rx="16" fill="url(#ndots)" opacity="0.5"/>')

    right = W - PAD_R
    for kind, label, value, y in placed:
        if kind in ("head", "user"):
            # The user@host line keeps its own casing; section headings are set
            # in caps to separate them from it.
            text = label if kind == "user" else label.upper()
            cls = "u" if kind == "user" else "h"
            add(f'<text class="m {cls}" x="{PAD_L}" y="{y}">{esc(text)}</text>')
            start = PAD_L + len(text) * 9.4 + 14
            add(f'<line class="rule" x1="{start:.0f}" y1="{y - 5}" '
                f'x2="{right}" y2="{y - 5}"/>')
            continue

        add(f'<text class="m k" x="{PAD_L}" y="{y}">{esc(label)}:</text>')
        add(f'<text class="m v" x="{right}" y="{y}" text-anchor="end">'
            f"{esc(value)}</text>")
        # Leader between the two. Widths are estimated from character counts;
        # running a little short is invisible, overlapping the text would not be.
        x1 = PAD_L + (len(label) + 1) * 8.6 + 10
        x2 = right - len(value) * 8.6 - 10
        if x2 - x1 > 12:
            add(f'<line class="lead" x1="{x1:.0f}" y1="{y - 4}" '
                f'x2="{x2:.0f}" y2="{y - 4}"/>')

    add(
        f'<rect x="0.5" y="0.5" width="{W - 1}" height="{panel_h - 1}" rx="16" '
        f'stroke="{c["rule"]}" stroke-width="1"/>'
    )
    # Drawn last, so it sits over the panel and its border.
    if sticker:
        add(vinyl_body(c, cx, cy, STICKER_SCALE, STICKER_ANGLE))
    add("</svg>")
    return "\n".join(p) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    d = collect(args.refresh)
    out = Path(__file__).resolve().parent.parent / "assets"
    out.mkdir(parents=True, exist_ok=True)
    for theme in THEMES:
        path = out / f"readout-{theme}.svg"
        path.write_text(build_svg(theme, d), encoding="utf-8")
        print(f"wrote assets/{path.name}  ({path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
