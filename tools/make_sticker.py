#!/usr/bin/env python3
"""
make_sticker.py - the call to action.

Three styles, because the page has no other contact path now that the readout's
Contact block is commented out. Whichever you keep, wrap it in a link in the
README so the image is clickable:

    [![Available for freelance](assets/sticker-dark.svg)](mailto:you@example.com)

    python tools/make_sticker.py --style pill
    python tools/make_sticker.py --style vinyl
    python tools/make_sticker.py --style terminal
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_stats import THEMES  # noqa: E402

MONO = ("ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, "
        "'DejaVu Sans Mono', monospace")

HEAD = "AVAILABLE FOR FREELANCE"
SUB = "from September"
CTA = "let's build something odd"

# Vinyl carries the destination on its bottom line instead of a tagline. It is
# the only contact route on the page, so a visitor should be able to see where
# the click goes before making it. Swap VINYL_BOT back to CTA.upper() if you
# would rather have the tagline.
VINYL_TOP = "FROM SEPTEMBER"
VINYL_BIG = "OPEN FOR WORK"
VINYL_BOT = "O-DARIA.COM"


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def guard(css: str) -> str:
    bad = {ch for ch in "<>&" if ch in css}
    if bad:
        raise ValueError(f"stylesheet has XML-significant characters {sorted(bad)}")
    return " ".join(l.strip() for l in css.splitlines() if l.strip())


def open_svg(w: int, h: int, label: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
        f'width="{w}" height="{h}" fill="none" role="img" '
        f'aria-label="{esc(label)}">'
    )


# ---------------------------------------------------------------------------
# pill - a status indicator, like the green dot next to a name
# ---------------------------------------------------------------------------


def style_pill(c: dict) -> str:
    W, H = 620, 62
    p = [open_svg(W, H, f"{HEAD} {SUB}. {CTA}.")]
    css = f"""
    .m {{ font-family: {MONO}; }}
    .t {{ font-size: 15px; font-weight: 700; letter-spacing: 2.6px;
          fill: {c['text']}; }}
    .s {{ font-size: 13px; fill: {c['muted']}; letter-spacing: 1.2px; }}
    .dot {{ fill: {c['accent']}; animation: beat 4.8s ease-out infinite; }}
    .ring {{ fill: {c['accent']}; animation: ripple 4.8s ease-out infinite; }}
    @keyframes beat {{ 0%, 88% {{ opacity: .85; }} 94% {{ opacity: 1; }}
                       100% {{ opacity: .85; }} }}
    @keyframes ripple {{ 0% {{ opacity: .5; transform: scale(1); }}
                         55%, 100% {{ opacity: 0; transform: scale(3.2); }} }}
    .arrow {{ stroke: {c['accent']}; stroke-width: 2; stroke-linecap: round;
              stroke-linejoin: round; animation: nudge 4.8s ease-in-out infinite; }}
    @keyframes nudge {{ 0%, 70%, 100% {{ transform: translateX(0); }}
                        80% {{ transform: translateX(4px); }} }}
    @media (prefers-reduced-motion: reduce) {{
      .dot, .ring, .arrow {{ animation: none; }} .ring {{ opacity: 0; }}
    }}
    """
    p.append(f"<defs><style>{guard(css)}</style></defs>")
    p.append(
        f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="{(H - 2) / 2}" '
        f'fill="{c["bg1"]}" stroke="{c["accent"]}" stroke-width="1.5" '
        f'stroke-opacity="0.55"/>'
    )
    # The ripple scales about its own centre.
    p.append(
        f'<g transform="translate(34 {H / 2})">'
        f'<circle class="ring" r="5"/><circle class="dot" r="5"/></g>'
    )
    p.append(f'<text class="m t" x="58" y="{H / 2 + 5:.0f}">{esc(HEAD)}</text>')
    # Right-anchored rather than flowed after the heading: estimating the
    # heading's width from its character count put the two runs on top of each
    # other, because letter-spacing is not in the per-character estimate.
    p.append(
        f'<text class="m s" x="{W - 72}" y="{H / 2 + 5:.0f}" text-anchor="end">'
        f"{esc(SUB)}</text>"
    )
    # The translate lives on an outer group. A CSS transform in a keyframe
    # *replaces* the element's transform attribute rather than composing with
    # it, so animating this element directly threw the arrow into the corner.
    p.append(
        f'<g transform="translate({W - 44} {H / 2})"><g class="arrow">'
        f'<path d="M-6,0 H8"/><path d="M3,-5 L8,0 L3,5"/></g></g>'
    )
    p.append("</svg>")
    return "\n".join(p) + "\n"


# ---------------------------------------------------------------------------
# vinyl - a die-cut sticker, slapped on at an angle
# ---------------------------------------------------------------------------


# Base size of the sticker face, before rotation or scaling. Two lines, not
# three: the readout's Status row already says "available from September" a few
# centimetres above, and a third line only shrinks the other two.
VINYL_W, VINYL_H = 430, 104
VINYL_BORDER = 9


def vinyl_defs(c: dict) -> tuple[str, str]:
    """(defs markup, css) for the vinyl sticker, so a host SVG can embed it.

    Classes are prefixed `sk-` because the readout panel this gets pasted into
    already defines short class names of its own.
    """
    defs = (
        '<filter id="sk-drop" x="-30%" y="-30%" width="180%" height="180%">'
        '<feDropShadow dx="0" dy="6" stdDeviation="8" flood-color="#000" '
        'flood-opacity="0.45"/></filter>'
    )
    css = f"""
    .sk {{ font-family: {MONO}; }}
    .sk-big {{ font-size: 38px; font-weight: 700; letter-spacing: -1px;
               fill: {c['bg0']}; }}
    /* Large enough to survive being scaled twice: once into the readout panel,
       and again when GitHub fits that panel into its column. */
    .sk-sm {{ font-size: 21px; font-weight: 700; letter-spacing: 1.6px;
              fill: {c['bg0']}; opacity: .78; }}
    /* The placement transform lives on an outer group. A CSS transform in a
       keyframe replaces the element's transform attribute instead of composing
       with it, so animating the placed element directly would fling it to the
       origin. */
    .sk-peel {{ animation: wobble 6s ease-in-out infinite; }}
    @keyframes wobble {{ 0%, 100% {{ transform: rotate(-1deg); }}
                         50% {{ transform: rotate(0.8deg); }} }}
    @media (prefers-reduced-motion: reduce) {{ .sk-peel {{ animation: none; }} }}
    """
    return defs, css


def vinyl_body(c: dict, cx: float, cy: float, scale: float = 1.0,
               angle: float = -6.0) -> str:
    """The sticker art, centred on (cx, cy) in the host's coordinates."""
    hw, hh = VINYL_W / 2, VINYL_H / 2
    b = VINYL_BORDER
    return (
        f'<g transform="translate({cx:.1f} {cy:.1f}) rotate({angle}) '
        f'scale({scale})">'
        f'<g class="sk-peel" filter="url(#sk-drop)">'
        f'<rect x="{-hw - b}" y="{-hh - b}" width="{VINYL_W + 2 * b}" '
        f'height="{VINYL_H + 2 * b}" rx="26" fill="{c["text"]}"/>'
        f'<rect x="{-hw}" y="{-hh}" width="{VINYL_W}" height="{VINYL_H}" '
        f'rx="19" fill="{c["accent"]}"/>'
        f'<text class="sk sk-big" x="0" y="{-hh + 50}" text-anchor="middle">'
        f"{esc(VINYL_BIG)}</text>"
        f'<text class="sk sk-sm" x="0" y="{-hh + 82}" text-anchor="middle">'
        f"{esc(VINYL_BOT)}</text>"
        f"</g></g>"
    )


def style_vinyl(c: dict) -> str:
    W, H = 560, 210
    defs, css = vinyl_defs(c)
    p = [open_svg(W, H, f"{VINYL_BIG} {VINYL_TOP}. Visit {VINYL_BOT}.")]
    p.append(f"<defs><style>{guard(css)}</style>{defs}</defs>")
    p.append(vinyl_body(c, W / 2, H / 2, 1.0, -6.0))
    p.append("</svg>")
    return "\n".join(p) + "\n"


# ---------------------------------------------------------------------------
# terminal - a prompt, matching the readout panel
# ---------------------------------------------------------------------------


def style_terminal(c: dict) -> str:
    W, H = 620, 132
    p = [open_svg(W, H, f"{HEAD} {SUB}. {CTA}.")]
    css = f"""
    .m {{ font-family: {MONO}; }}
    .p {{ font-size: 15px; fill: {c['accent']}; font-weight: 700; }}
    .c {{ font-size: 15px; fill: {c['text']}; }}
    .o {{ font-size: 14px; fill: {c['muted']}; }}
    .ok {{ font-size: 14px; fill: {c['accent2']}; font-weight: 700; }}
    .car {{ fill: {c['accent']}; animation: blink 1.1s steps(1) infinite; }}
    @keyframes blink {{ 0%, 50% {{ opacity: 1; }} 50.01%, 100% {{ opacity: 0; }} }}
    @media (prefers-reduced-motion: reduce) {{ .car {{ animation: none; }} }}
    """
    p.append(f"<defs><style>{guard(css)}</style></defs>")
    p.append(
        f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="12" '
        f'fill="{c["bg0"]}" stroke="{c["rule"]}" stroke-width="1"/>'
    )
    p.append(
        f'<line x1="1" y1="34" x2="{W - 1}" y2="34" stroke="{c["rule"]}" '
        f'stroke-width="1"/>'
    )
    for i, col in enumerate((c["muted"], c["muted"], c["accent"])):
        p.append(f'<circle cx="{22 + i * 17}" cy="18" r="4.5" fill="{col}" '
                 f'opacity="{1 if i == 2 else 0.4}"/>')
    p.append(
        f'<text class="m o" x="{W - 20}" y="23" text-anchor="end">hire.sh</text>'
    )
    p.append(f'<text class="m p" x="22" y="66">$</text>')
    p.append(f'<text class="m c" x="40" y="66">contact --freelance --from september</text>')
    p.append(f'<text class="m ok" x="22" y="94">{esc(HEAD.capitalize())}.</text>')
    p.append(f'<text class="m o" x="22" y="116">{esc(CTA)} — click here.</text>')
    p.append(
        f'<rect class="car" x="{22 + len(CTA + " — click here.") * 8.4:.0f}" '
        f'y="105" width="9" height="15"/>'
    )
    p.append("</svg>")
    return "\n".join(p) + "\n"


STYLES = {"pill": style_pill, "vinyl": style_vinyl, "terminal": style_terminal}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--style", default="pill", choices=sorted(STYLES))
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--suffix", default="")
    args = ap.parse_args()

    out = args.out_dir or Path(__file__).resolve().parent.parent / "assets"
    out.mkdir(parents=True, exist_ok=True)
    for theme, c in THEMES.items():
        path = out / f"sticker-{theme}{args.suffix}.svg"
        path.write_text(STYLES[args.style](c), encoding="utf-8")
        print(f"wrote {path.name}  ({path.stat().st_size:,} bytes, {args.style})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
