#!/usr/bin/env python3
"""
make_stats.py - generates the stats card, without depending on anyone else's server.

The usual way to put stats on a profile is to hotlink a third-party renderer.
That service was returning 503 DEPLOYMENT_PAUSED at the time this was written,
which on a profile page means a broken-image icon where the numbers should be.
A card you render yourself cannot be paused, rate-limited, or quietly restyled.

Reads only public data from the GitHub REST API and writes two SVGs matching the
banner's palette.

    python tools/make_stats.py                 # unauthenticated, 60 req/hour
    GITHUB_TOKEN=... python tools/make_stats.py  # 5000 req/hour

Rerunning without a token risks the rate limit, so responses are cached to
.stats-cache.json; pass --refresh to ignore it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

USER = "darik0d"
API = "https://api.github.com"

W, H = 1200, 320

# Right-hand column geometry, kept here so the bar and its clip path cannot
# drift apart.
BAR_X, BAR_Y, BAR_W, BAR_H = 656, 108, 480, 18
ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "tools" / ".stats-cache.json"

# Same palette as the banner, so the two cards read as one system.
THEMES = {
    "dark": {
        "bg0": "#080a12", "bg1": "#0d1020", "grid": "#161a2e",
        "accent": "#22d3ee", "accent2": "#a78bfa",
        "text": "#e8eef7", "muted": "#8b96ad", "rule": "#1c2338",
        "track": "#1a2136",
    },
    "light": {
        "bg0": "#fbfcfe", "bg1": "#eef2f9", "grid": "#d7dfee",
        "accent": "#0b7f96", "accent2": "#6d4aca",
        "text": "#111827", "muted": "#5a6478", "rule": "#d3dbe9",
        "track": "#dde4f0",
    },
}

MONO = ("ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, "
        "'DejaVu Sans Mono', monospace")

# GitHub's own linguist colours, so the bar matches what people expect.
LANG_COLOURS = {
    "Python": "#3572A5", "TypeScript": "#3178c6", "JavaScript": "#f1e05a",
    "C++": "#f34b7d", "C": "#555555", "Jupyter Notebook": "#DA5B0B",
    "Makefile": "#427819", "HTML": "#e34c26", "CSS": "#563d7c",
    "Java": "#b07219", "Shell": "#89e051", "CMake": "#DA3434",
    "Assembly": "#6E4C13", "TeX": "#3D6117", "Rust": "#dea584",
    "Go": "#00ADD8", "SCSS": "#c6538c", "Dockerfile": "#384d54",
}
OTHER = "#8b96ad"


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------


def get(url: str) -> object:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{USER}-profile-stats",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def collect(refresh: bool) -> dict:
    if CACHE.exists() and not refresh:
        print(f"using cached data ({CACHE.name}); pass --refresh to refetch")
        return json.loads(CACHE.read_text(encoding="utf-8"))

    print(f"fetching {USER} ...")
    user = get(f"{API}/users/{USER}")

    repos, page = [], 1
    while True:
        batch = get(f"{API}/users/{USER}/repos?per_page=100&page={page}")
        if not batch:
            break
        repos.extend(batch)
        page += 1

    own = [r for r in repos if not r["fork"]]
    print(f"  {len(repos)} repos, {len(own)} not forks")

    # Language bytes, counted only over repos actually written here. Including
    # forks would credit someone else's codebase to this profile.
    langs: dict[str, int] = {}
    for r in own:
        try:
            for name, count in get(r["languages_url"]).items():
                langs[name] = langs.get(name, 0) + count
        except urllib.error.HTTPError as exc:
            # A rate limit partway through would silently skew the chart, so
            # stop rather than publish a breakdown built from half the repos.
            if exc.code in (403, 429):
                raise SystemExit(
                    "rate limited by the GitHub API partway through the language "
                    "scan. Set GITHUB_TOKEN and rerun with --refresh."
                ) from exc
            raise

    data = {
        "fetched": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "public_repos": user["public_repos"],
        "followers": user["followers"],
        "created_at": user["created_at"],
        "stars": sum(r["stargazers_count"] for r in own),
        "own_repos": len(own),
        "languages": dict(sorted(langs.items(), key=lambda kv: -kv[1])),
    }
    CACHE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def human_bytes(n: int) -> str:
    for unit, size in (("MB", 1024**2), ("kB", 1024)):
        if n >= size:
            value = n / size
            return f"{value:.1f}{unit}" if value < 10 else f"{value:.0f}{unit}"
    return f"{n}B"


def top_languages(langs: dict[str, int], n: int = 6) -> list[tuple[str, float, str]]:
    total = sum(langs.values())
    if not total:
        return []
    items = list(langs.items())[:n]
    out = [
        (name, count / total * 100, LANG_COLOURS.get(name, OTHER))
        for name, count in items
    ]
    rest = total - sum(c for _, c in items)
    if rest > 0:
        out.append(("Other", rest / total * 100, OTHER))
    return out


def build_svg(theme: str, d: dict) -> str:
    c = THEMES[theme]
    langs = top_languages(d["languages"])
    years = round(
        (date.today() - datetime.fromisoformat(
            d["created_at"].replace("Z", "+00:00")).date()).days / 365.25, 1
    )

    p: list[str] = []
    add = p.append

    add(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}" fill="none" role="img" '
        f'aria-label="GitHub statistics for {USER}: {d["own_repos"]} own '
        f'repositories, {d["stars"]} stars, {d["followers"]} followers.">'
    )
    add(f"<title>{USER} - statistics</title>")

    add("<defs>")
    add(
        f'<linearGradient id="sbg" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{c["bg0"]}"/>'
        f'<stop offset="1" stop-color="{c["bg1"]}"/></linearGradient>'
    )
    add(
        '<pattern id="sdots" width="26" height="26" patternUnits="userSpaceOnUse">'
        f'<circle cx="1.2" cy="1.2" r="1.2" fill="{c["grid"]}"/></pattern>'
    )
    add(f'<clipPath id="sframe"><rect width="{W}" height="{H}" rx="18"/></clipPath>')
    add(
        f'<clipPath id="barclip"><rect x="{BAR_X}" y="{BAR_Y}" width="{BAR_W}" '
        f'height="{BAR_H}" rx="{BAR_H / 2}"/></clipPath>'
    )

    css = f"""
    .m {{ font-family: {MONO}; }}
    .eye {{ font-size: 13px; letter-spacing: 3.4px; fill: {c['accent']}; font-weight: 600; }}
    .big {{ font-size: 46px; font-weight: 700; fill: {c['text']}; letter-spacing: -1.5px; }}
    .cap {{ font-size: 11.5px; letter-spacing: 2px; fill: {c['muted']}; }}
    .lab {{ font-size: 13px; fill: {c['text']}; }}
    .pct {{ font-size: 13px; fill: {c['muted']}; }}
    .foot {{ font-size: 11px; letter-spacing: 1.4px; fill: {c['muted']}; opacity: .8; }}
    """
    # Note: the bar is deliberately NOT animated in. An earlier version grew it
    # from scaleX(0), which meant any renderer that rasterises at t=0 - an image
    # proxy, a thumbnailer, a screenshot - captured an empty chart. A data
    # visualisation has to be readable in a single static frame.
    bad = {ch for ch in "<>&" if ch in css}
    if bad:
        raise ValueError(f"stylesheet contains XML-significant characters {sorted(bad)}")
    add("<style>" + " ".join(l.strip() for l in css.splitlines() if l.strip()) + "</style>")
    add("</defs>")

    add('<g clip-path="url(#sframe)">')
    add(f'<rect width="{W}" height="{H}" fill="url(#sbg)"/>')
    add(f'<rect width="{W}" height="{H}" fill="url(#sdots)" opacity="0.55"/>')

    add(f'<text class="m eye" x="64" y="56">TELEMETRY</text>')

    # -- the four numbers ---------------------------------------------------
    # Deliberately not stars and followers. On a page whose entire argument is
    # that these numbers measure activity rather than worth, leading with two
    # popularity metrics would be both weak and off-message. Volume, breadth
    # and tenure at least describe the work. Both are in `d` if you disagree.
    total_bytes = sum(d["languages"].values())
    tiles = [
        (str(d["own_repos"]), "REPOSITORIES"),
        (str(len(d["languages"])), "LANGUAGES"),
        (f"{years:g}", "YEARS HERE"),
        (human_bytes(total_bytes), "OF CODE"),
    ]
    for i, (value, caption) in enumerate(tiles):
        x = 64 + (i % 2) * 250
        y = 132 + (i // 2) * 84
        add(f'<text class="m big" x="{x}" y="{y}">{esc(value)}</text>')
        add(f'<text class="m cap" x="{x}" y="{y + 22}">{caption}</text>')

    # -- language bar -------------------------------------------------------
    add(f'<line x1="600" y1="40" x2="600" y2="{H - 40}" stroke="{c["rule"]}" stroke-width="1"/>')
    add(f'<text class="m eye" x="{BAR_X}" y="56">LANGUAGE MIX</text>')

    add(
        f'<rect x="{BAR_X}" y="{BAR_Y}" width="{BAR_W}" height="{BAR_H}" '
        f'rx="{BAR_H / 2}" fill="{c["track"]}"/>'
    )
    add('<g clip-path="url(#barclip)">')
    cursor = float(BAR_X)
    for name, pct, colour in langs:
        width = BAR_W * pct / 100
        add(
            f'<rect x="{cursor:.1f}" y="{BAR_Y}" width="{width:.1f}" '
            f'height="{BAR_H}" fill="{colour}"/>'
        )
        cursor += width
    add("</g>")

    # Legend: two columns beneath the bar.
    legend_top = BAR_Y + 54
    for i, (name, pct, colour) in enumerate(langs):
        x = BAR_X + (i % 2) * 246
        y = legend_top + (i // 2) * 26
        add(f'<circle cx="{x + 5}" cy="{y - 4}" r="5" fill="{colour}"/>')
        add(f'<text class="m lab" x="{x + 18}" y="{y}">{esc(name)}</text>')
        add(f'<text class="m pct" x="{x + 224}" y="{y}" text-anchor="end">{pct:.1f}%</text>')

    # The legend grows with the language count; make sure it has not walked
    # into the footer instead of finding out from a screenshot.
    legend_bottom = legend_top + ((len(langs) - 1) // 2) * 26
    if legend_bottom > H - 44:
        raise ValueError(
            f"legend reaches y={legend_bottom} but the card is only {H} tall; "
            f"raise H or lower the language count"
        )

    add(
        f'<text class="m foot" x="64" y="{H - 26}">'
        f'SELF-HOSTED  /  NO THIRD-PARTY RENDERER  /  {d["fetched"]}</text>'
    )
    add("</g>")
    add(
        f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="18" '
        f'stroke="{c["rule"]}" stroke-width="1"/>'
    )
    add("</svg>")
    return "\n".join(p) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="ignore the cache")
    args = ap.parse_args()

    d = collect(args.refresh)
    out = ROOT / "assets"
    out.mkdir(parents=True, exist_ok=True)
    for theme in THEMES:
        path = out / f"stats-{theme}.svg"
        path.write_text(build_svg(theme, d), encoding="utf-8")
        print(f"wrote assets/{path.name}  ({path.stat().st_size:,} bytes)")

    top = list(d["languages"])[:5]
    print(f"  {d['own_repos']} repos / {d['stars']} stars / {d['followers']} followers")
    print(f"  top languages: {', '.join(top)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
