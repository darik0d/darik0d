#!/usr/bin/env python3
"""
make_graph.py - draws the contribution graph the marquee is currently spelling.

GitHub renders the real graph below the README, so it is only visible after a
scroll. This puts the same thing inside the page, at the point where it is
being talked about.

The pattern logic here mirrors `marquee.py` in the stats-lie repository, which
is the source of truth: same 5x5 font, same EPOCH, same 53x7 geometry. If the
marquee text or spacing changes there, change it here too - they are separate
repositories on purpose, so nothing enforces it automatically.

    python tools/make_graph.py
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

ROWS, WINDOW_COLS = 7, 53
EPOCH = dt.date(2020, 1, 5)   # a Sunday; must match marquee.py
TOP_ROW = 1                   # letters occupy Mon..Fri
GLYPH_W, GLYPH_H = 5, 5

# Must stay identical to FONT in marquee.py, or this illustration will show
# something the real graph does not.
FONT = {
    " ": (".....", ".....", ".....", ".....", "....."),
    "A": (".###.", "#...#", "#####", "#...#", "#...#"),
    "E": ("#####", "#....", "####.", "#....", "#####"),
    "I": ("#####", "..#..", "..#..", "..#..", "#####"),
    "L": ("#....", "#....", "#....", "#....", "#####"),
    "S": (".####", "#....", ".###.", "....#", "####."),
    "T": ("#####", "..#..", "..#..", "..#..", "..#.."),
}

CELL, GAP = 11, 3
PITCH = CELL + GAP
LABEL_W, TOP_PAD, BOT_PAD = 30, 22, 8

THEMES = {
    "dark": {
        "bg": "none", "empty": "#161b22", "lit": "#39d353", "dim": "#0e4429",
        "text": "#8b96ad", "ring": "rgba(255,255,255,0.04)",
    },
    "light": {
        "bg": "none", "empty": "#ebedf0", "lit": "#216e39", "dim": "#9be9a8",
        "text": "#5a6478", "ring": "rgba(27,31,35,0.06)",
    },
}

MONO = ("ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, "
        "'DejaVu Sans Mono', monospace")


def build_strip(text: str, gap: int) -> list[list[int]]:
    cols: list[list[int]] = []
    for ch in text.upper():
        glyph = FONT[ch]
        for x in range(GLYPH_W):
            col = [0] * ROWS
            for y in range(GLYPH_H):
                if glyph[y][x] == "#":
                    col[TOP_ROW + y] = 1
            cols.append(col)
        cols.append([0] * ROWS)
    cols.extend([0] * ROWS for _ in range(gap))
    return cols


def week_index(day: dt.date) -> int:
    sunday = day - dt.timedelta(days=(day.weekday() + 1) % 7)
    return (sunday - EPOCH).days // 7


def build_svg(theme: str, text: str, gap: int, today: dt.date) -> str:
    c = THEMES[theme]
    strip = build_strip(text, gap)

    width = LABEL_W + WINDOW_COLS * PITCH
    height = TOP_PAD + ROWS * PITCH + BOT_PAD

    last_sunday = today - dt.timedelta(days=(today.weekday() + 1) % 7)
    first_sunday = last_sunday - dt.timedelta(weeks=WINDOW_COLS - 1)

    p: list[str] = []
    add = p.append
    add(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" fill="none" role="img" '
        f'aria-label="A GitHub contribution graph spelling {text}.">'
    )
    add(f"<title>Contribution graph spelling {text}</title>")
    add(
        f'<style>.lbl {{ font-family: {MONO}; font-size: 10px; '
        f'fill: {c["text"]}; }}</style>'
    )

    # Weekday labels, the three GitHub itself shows.
    for row, name in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        y = TOP_PAD + row * PITCH + CELL - 1
        add(f'<text class="lbl" x="0" y="{y}">{name}</text>')

    # Month labels above the first column of each new month.
    seen = set()
    for col in range(WINDOW_COLS):
        day = first_sunday + dt.timedelta(weeks=col)
        if day.month not in seen and day.day <= 7:
            seen.add(day.month)
            x = LABEL_W + col * PITCH
            add(f'<text class="lbl" x="{x}" y="12">{day.strftime("%b")}</text>')

    for col in range(WINDOW_COLS):
        for row in range(ROWS):
            day = first_sunday + dt.timedelta(weeks=col, days=row)
            x = LABEL_W + col * PITCH
            y = TOP_PAD + row * PITCH
            if day > today:
                continue          # the current week is not full yet
            on = strip[week_index(day) % len(strip)][row]
            fill = c["lit"] if on else c["empty"]
            add(
                f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2" '
                f'fill="{fill}" stroke="{c["ring"]}" stroke-width="1"/>'
            )

    add("</svg>")
    return "\n".join(p) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", default="STATS LIE")
    ap.add_argument("--gap", type=int, default=2,
                    help="must match --gap in marquee.py")
    ap.add_argument("--date", default=None,
                    help="render the window as of this YYYY-MM-DD instead of today")
    args = ap.parse_args()

    today = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
    out = Path(__file__).resolve().parent.parent / "assets"
    out.mkdir(parents=True, exist_ok=True)
    for theme in THEMES:
        path = out / f"graph-{theme}.svg"
        path.write_text(build_svg(theme, args.text, args.gap, today),
                        encoding="utf-8")
        print(f"wrote assets/{path.name}  ({path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
