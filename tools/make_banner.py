#!/usr/bin/env python3
"""
make_banner.py - generates the animated banner at the top of the profile README.

Emits two files, one per GitHub theme, which the README selects between with a
<picture> element. They are byte-identical apart from the palette.

Everything is inline: no scripts, no external fonts, no network requests.
GitHub serves README images through its camo proxy, which renders them as
ordinary <img> documents. CSS animations run there; JavaScript and remote
resources do not. So the motion is pure CSS keyframes, and the type uses the
system monospace stack.

    python tools/make_banner.py

Layout is deterministic - the seeded RNG means re-running produces the exact
same file, so regenerating never shows up as a spurious diff.
"""

from __future__ import annotations

import random
from pathlib import Path

W, H = 1200, 212

# The card sits just inside the canvas edge.
CARD_L, CARD_R = 16, W - 16
CARD_T, CARD_B = 16, H - 16

# Left half is type, right half is the network.
NET_MID = 106

# One heartbeat for the whole banner: the border pulse and the signal wave
# through the network share it, so the piece reads as a single rhythm rather
# than two effects running at unrelated speeds.
CYCLE = 4.8
LAYER_STEP = 0.45   # seconds between one layer firing and the next
TRAVEL = 0.85       # seconds a spike takes to cross a gap
# The wave itself lasts about 1.9s; the rest of the cycle is deliberate quiet,
# with the border pulse carrying the banner in between.

THEMES = {
    "dark": {
        "bg0": "#080a12",
        "bg1": "#0d1020",
        "grid": "#161a2e",
        "edge": "#232c4a",
        "node": "#38456b",
        "accent": "#22d3ee",
        "accent2": "#a78bfa",
        "spark": "#fde68a",
        "text": "#e8eef7",
        "muted": "#8b96ad",
        "rule": "#1c2338",
    },
    "light": {
        "bg0": "#fbfcfe",
        "bg1": "#eef2f9",
        "grid": "#d7dfee",
        "edge": "#a9b8d6",
        "node": "#7184ad",
        "accent": "#0b7f96",
        "accent2": "#6d4aca",
        "spark": "#b7791f",
        "text": "#111827",
        "muted": "#5a6478",
        "rule": "#d3dbe9",
    },
}

MONO = ("ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, "
        "'DejaVu Sans Mono', monospace")

# The eyebrow has to clear the network art, which starts at x=690. At 15px with
# 4.2px tracking that works out to roughly 45 characters.
EYEBROW = "CHASING DREAMS UNTIL THEY COMPILE"
NAME = "darik0d"


# ---------------------------------------------------------------------------
# Network topology
# ---------------------------------------------------------------------------


def build_network(rng: random.Random):
    """Four layers, each node wired to a couple of plausible successors.

    Fully connecting the layers turns the whole thing into grey mush at this
    size, so each node gets 2-3 edges biased toward vertically nearby targets -
    which also happens to look more like a real sparse network.
    """
    sizes = [5, 7, 5, 3]
    spreads = [56, 72, 56, 34]  # must keep the outermost nodes inside the card
    xs = [690, 838, 986, 1116]

    layers = []
    for size, spread, x in zip(sizes, spreads, xs):
        if size == 1:
            ys = [NET_MID]
        else:
            step = (spread * 2) / (size - 1)
            ys = [NET_MID - spread + i * step for i in range(size)]
        layers.append([(x, y) for y in ys])

    edges = []
    for li in range(len(layers) - 1):
        src, dst = layers[li], layers[li + 1]
        for si, (x0, y0) in enumerate(src):
            # Aim at the vertically closest node, then take neighbours of it.
            centre = min(range(len(dst)), key=lambda di: abs(dst[di][1] - y0))
            options = sorted(
                range(len(dst)), key=lambda di: (abs(di - centre), di)
            )
            for di in options[: rng.choice([2, 2, 3])]:
                edges.append((li, si, di, (x0, y0), dst[di]))
    return layers, edges


def esc(s: str) -> str:
    """XML-escape copy before it goes into a text node.

    An ampersand in a tagline would otherwise produce a file that parses as
    broken XML and renders as an empty box on the profile.
    """
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def edge_path(a: tuple[float, float], b: tuple[float, float]) -> str:
    """Gentle S-curve. Straight lines read as a circuit diagram, not a brain."""
    (x0, y0), (x1, y1) = a, b
    dx = (x1 - x0) * 0.45
    return f"M{x0:.1f},{y0:.1f} C{x0 + dx:.1f},{y0:.1f} {x1 - dx:.1f},{y1:.1f} {x1:.1f},{y1:.1f}"


# ---------------------------------------------------------------------------
# SVG
# ---------------------------------------------------------------------------


def build_svg(theme: str, frame: str = "plain") -> str:
    c = THEMES[theme]
    rng = random.Random(20260806)  # fixed: regenerating must not churn the diff
    layers, edges = build_network(rng)

    # Nothing structurally stops a tall layer from growing past the card edge.
    # Catch it here rather than by noticing it in a screenshot.
    lowest = max(y for layer in layers for _, y in layer)
    highest = min(y for layer in layers for _, y in layer)
    if lowest + 14 > CARD_B or highest - 14 < CARD_T:
        raise ValueError(
            f"network spans y={highest:.0f}..{lowest:.0f}, which does not fit "
            f"inside the card ({CARD_T}..{CARD_B}); reduce the layer spreads"
        )

    # Copy runs left to right into the same space the network occupies. These
    # are approximate advance widths for the monospace stack at each size;
    # generous enough to catch a real overrun without crying wolf.
    leftmost = min(x for layer in layers for x, _ in layer)
    for label, text, per_char in (("EYEBROW", EYEBROW, 13.2),):
        end = 64 + len(text) * per_char
        if end > leftmost - 20:
            raise ValueError(
                f"{label} is {len(text)} characters, reaching x={end:.0f}, which "
                f"runs into the network art at x={leftmost:.0f}. Shorten it to "
                f"about {int((leftmost - 84) / per_char)} characters."
            )

    parts: list[str] = []
    add = parts.append

    # Derived from the copy above rather than written out again, so the
    # accessible name cannot drift out of sync with the visible text.
    label = f"{NAME} - {EYEBROW.title()}."
    add(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}" fill="none" role="img" '
        f'aria-label="{esc(label)}">'
    )
    add(f"<title>{esc(NAME)}</title>")

    # -- defs ---------------------------------------------------------------
    add("<defs>")
    add(
        f'<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{c["bg0"]}"/>'
        f'<stop offset="1" stop-color="{c["bg1"]}"/></linearGradient>'
    )
    add(
        f'<radialGradient id="halo" cx="0.78" cy="0.5" r="0.55">'
        f'<stop offset="0" stop-color="{c["accent"]}" stop-opacity="0.16"/>'
        f'<stop offset="1" stop-color="{c["accent"]}" stop-opacity="0"/>'
        f"</radialGradient>"
    )
    add(
        '<pattern id="dots" width="26" height="26" patternUnits="userSpaceOnUse">'
        f'<circle cx="1.2" cy="1.2" r="1.2" fill="{c["grid"]}"/></pattern>'
    )
    add(
        f'<clipPath id="frame"><rect x="{CARD_L}" y="{CARD_T}" '
        f'width="{CARD_R - CARD_L}" height="{CARD_B - CARD_T}" rx="18"/></clipPath>'
    )
    # Soft bloom under the travelling border segment.
    add(
        '<filter id="glow" x="-120%" y="-120%" width="340%" height="340%">'
        '<feGaussianBlur stdDeviation="3" result="b"/>'
        "<feMerge><feMergeNode in=\"b\"/><feMergeNode in=\"SourceGraphic\"/>"
        "</feMerge></filter>"
    )
    # The same bloom in absolute coordinates, for the spikes. Filter regions
    # sized in percentages are measured against the bounding box, and an edge
    # running flat between two layers at the same height has a box of zero
    # height - which would resolve to a zero-area region and paint nothing.
    add(
        f'<filter id="glowline" filterUnits="userSpaceOnUse" x="0" y="0" '
        f'width="{W}" height="{H}">'
        '<feGaussianBlur stdDeviation="2.4" result="b"/>'
        "<feMerge><feMergeNode in=\"b\"/><feMergeNode in=\"SourceGraphic\"/>"
        "</feMerge></filter>"
    )
    # A spike is brightest mid-flight and fades at both ends, so it reads as
    # something moving rather than a dash sliding along a wire.
    add(
        f'<linearGradient id="fade" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="{c["accent"]}" stop-opacity="0"/>'
        f'<stop offset="0.5" stop-color="{c["accent"]}" stop-opacity="0.95"/>'
        f'<stop offset="1" stop-color="{c["accent2"]}" stop-opacity="0"/>'
        f"</linearGradient>"
    )

    # -- styles -------------------------------------------------------------
    css = f"""
    .mono {{ font-family: {MONO}; }}
    .eyebrow {{ font-size: 15px; letter-spacing: 4.2px; fill: {c['accent']};
                font-weight: 600; }}
    .name    {{ font-size: 84px; letter-spacing: -2px; fill: {c['text']};
                font-weight: 700; }}

    .edge  {{ stroke: {c['edge']}; stroke-width: 1.15; }}

    /* A spike crossing one gap. Each edge carries one per cycle, delayed by
       its layer, so activity sweeps left to right and only about a quarter of
       the edges are lit at any instant - lighting them all at once is what made
       the first version look busy. */
    .spark {{ stroke: url(#fade); stroke-width: 2.4; stroke-linecap: round;
              stroke-dasharray: 14 86; stroke-dashoffset: 100; opacity: 0;
              animation: travel {CYCLE}s linear infinite; }}
    @keyframes travel {{
      0%   {{ stroke-dashoffset: 100; opacity: 0; }}
      3%   {{ opacity: 1; }}
      {TRAVEL / CYCLE * 100:.1f}% {{ stroke-dashoffset: 0; opacity: 1; }}
      {TRAVEL / CYCLE * 100 + 3:.1f}%, 100% {{ stroke-dashoffset: 0; opacity: 0; }}
    }}

    /* Only the fill is animated, not the radius: Firefox gained CSS geometry
       properties (r, cx, cy) only recently, and a node that never lights up for
       a chunk of visitors is worse than one that lights without growing. */
    .node {{ fill: {c['node']}; animation: fire {CYCLE}s ease-out infinite; }}
    @keyframes fire {{
      0%   {{ fill: {c['node']}; }}
      4%   {{ fill: {c['accent']}; }}
      22%  {{ fill: {c['node']}; }}
      100% {{ fill: {c['node']}; }}
    }}

    .cursor {{ fill: {c['accent']}; animation: blink 1.15s steps(1) infinite; }}
    @keyframes blink {{ 0%, 50% {{ opacity: 1; }} 50.01%, 100% {{ opacity: 0; }} }}

    @media (prefers-reduced-motion: reduce) {{
      .cursor, .pulse, .spark, .node {{ animation: none; }}
      .spark {{ opacity: 0; }}
    }}
    """

    # Only the selected frame's rules are emitted; shipping the other style's
    # keyframes would be dead weight in a file that goes on a profile page.
    if frame == "pulse":
        css += f"""
    /* A short lit segment chased around the card's own outline. pathLength
       normalises the perimeter to 100 so the dash numbers stay readable. */
    .pulse {{ stroke: {c['accent']}; stroke-width: 2.2; stroke-linecap: round;
              stroke-dasharray: 11 89; stroke-dashoffset: 100;
              animation: chase {CYCLE}s linear infinite; }}
    @keyframes chase {{ to {{ stroke-dashoffset: 0; }} }}
    """
    # The stylesheet is not wrapped in CDATA, so a stray angle bracket or
    # ampersand would silently produce a broken SVG that GitHub renders as a
    # blank box. Cheaper to fail here than to debug it in a README.
    flat = " ".join(line.strip() for line in css.splitlines() if line.strip())
    bad = {ch for ch in "<>&" if ch in flat}
    if bad:
        raise ValueError(
            f"stylesheet contains XML-significant character(s) {sorted(bad)}; "
            f"rewrite the CSS to avoid them"
        )
    add("<style>" + flat + "</style>")
    add("</defs>")

    # -- background ---------------------------------------------------------
    add('<g clip-path="url(#frame)">')
    add(f'<rect width="{W}" height="{H}" fill="url(#bg)"/>')
    add(f'<rect width="{W}" height="{H}" fill="url(#dots)" opacity="0.55"/>')
    add(f'<rect width="{W}" height="{H}" fill="url(#halo)"/>')

    # -- network ------------------------------------------------------------
    add('<g stroke-linecap="round">')
    for li, si, di, a, b in edges:
        add(f'<path class="edge" d="{edge_path(a, b)}"/>')
    add("</g>")

    # Spikes ride the same curves as the edges beneath them.
    add('<g filter="url(#glowline)">')
    for li, si, di, a, b in edges:
        # Jitter within the layer so the wave has a soft leading edge instead
        # of every edge in a column firing on the same frame.
        delay = li * LAYER_STEP + (si % 3) * 0.07
        add(
            f'<path class="spark" pathLength="100" d="{edge_path(a, b)}" '
            f'style="animation-delay:{delay:.2f}s"/>'
        )
    add("</g>")

    for li, layer in enumerate(layers):
        # A layer lights as the spikes launched at it land.
        arrive = max(0.0, li * LAYER_STEP + TRAVEL - LAYER_STEP)
        for si, (x, y) in enumerate(layer):
            delay = arrive + (si % 3) * 0.07
            add(
                f'<circle class="node" cx="{x}" cy="{y:.1f}" r="4" '
                f'style="animation-delay:{delay:.2f}s"/>'
            )

    # -- type ---------------------------------------------------------------
    # Two lines, centred in the card by hand.
    add(f'<text class="mono eyebrow" x="64" y="62">{esc(EYEBROW)}</text>')
    add(f'<text class="mono name" x="60" y="142">{esc(NAME)}</text>')
    # Blinking terminal caret parked after the name.
    add(f'<rect class="cursor" x="{60 + len(NAME) * 50.4:.0f}" y="106" width="30" height="44" rx="2"/>')

    add("</g>")  # end of the clipped card

    # -- frame ---------------------------------------------------------------
    # Drawn after the clip group closes, so anything here may cross the border
    # and land in the transparent margin outside the card.
    bx, by = CARD_L + 0.5, CARD_T + 0.5
    bw, bh = (CARD_R - CARD_L) - 1, (CARD_B - CARD_T) - 1
    add(
        f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="18" '
        f'stroke="{c["rule"]}" stroke-width="1"/>'
    )

    if frame == "pulse":
        add(
            f'<rect class="pulse" x="{bx}" y="{by}" width="{bw}" height="{bh}" '
            f'rx="18" pathLength="100" filter="url(#glow)"/>'
        )
    elif frame != "plain":
        raise ValueError(f"unknown frame style {frame!r}")

    add("</svg>")
    return "\n".join(parts) + "\n"


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--frame", default="pulse", choices=["plain", "pulse"],
        help="plain: static border. pulse: a lit segment chased around the "
             "card outline.",
    )
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--suffix", default="", help="appended to the filename")
    args = ap.parse_args()

    out = args.out_dir or Path(__file__).resolve().parent.parent / "assets"
    out.mkdir(parents=True, exist_ok=True)
    for theme in THEMES:
        path = out / f"banner-{theme}{args.suffix}.svg"
        path.write_text(build_svg(theme, args.frame), encoding="utf-8")
        print(f"wrote {path.name}  ({path.stat().st_size:,} bytes, frame={args.frame})")


if __name__ == "__main__":
    main()
