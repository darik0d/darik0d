#!/usr/bin/env python3
"""
preview.py - see the profile page locally, before pushing anything.

    python tools/preview.py

Builds `.preview.html` in the repo root and opens it in your browser. Run it
again after any change; just reload the tab.

Two things it does that opening README.md in an editor cannot:

  * It renders the Markdown through GitHub's own API, so tables, <details>
    blocks and the HTML layout come out exactly as they will on the profile.
  * It rewrites the raw.githubusercontent URLs to local paths. Those URLs point
    at a repository that does not exist yet, so in any other preview every
    image is a broken icon.

The theme switch swaps the dark and light asset variants the same way GitHub
does, so both can be checked without changing your OS setting.

Offline is fine - the asset gallery still works, and the page says the Markdown
could not be fetched rather than pretending.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import urllib.error
import urllib.request
import webbrowser

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = "https://raw.githubusercontent.com/darik0d/darik0d/main/"
OUT = ROOT / ".preview.html"

SHELL = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>preview - darik0d</title>
<style>
  :root {{
    --bg:#0d1117; --panel:#0d1117; --line:#30363d; --soft:#21262d;
    --text:#e6edf3; --muted:#9198a1; --link:#4493f8; --code:#151b23;
  }}
  body.light {{
    --bg:#ffffff; --panel:#ffffff; --line:#d1d9e0; --soft:#d1d9e0;
    --text:#1f2328; --muted:#59636e; --link:#0969da; --code:#f6f8fa;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--text);
         font:16px/1.6 -apple-system,"Segoe UI",Helvetica,Arial,sans-serif; }}
  .bar {{ position:sticky; top:0; z-index:9; display:flex; gap:14px; align-items:center;
          padding:10px 20px; background:var(--panel); border-bottom:1px solid var(--line);
          font:12px ui-monospace,monospace; color:var(--muted); }}
  .bar button {{ font:inherit; padding:6px 12px; border-radius:20px; cursor:pointer;
                 border:1px solid var(--line); background:transparent; color:var(--text); }}
  .wrap {{ max-width:1012px; margin:0 auto; padding:24px 20px 80px; }}
  h2.sec {{ font:600 12px ui-monospace,monospace; letter-spacing:2.4px;
            text-transform:uppercase; color:var(--muted);
            margin:34px 0 10px; padding-bottom:6px; border-bottom:1px solid var(--soft); }}
  .card {{ border:1px solid var(--line); border-radius:6px; padding:32px; }}
  .asset {{ margin:14px 0; }}
  .asset img {{ max-width:100%; border-radius:8px; display:block; }}
  .cap {{ font:11px ui-monospace,monospace; color:var(--muted); margin-bottom:6px; }}
  .warn {{ border:1px solid #9e6a03; background:rgba(187,128,9,.12);
           padding:12px 16px; border-radius:6px; font-size:14px; }}
  /* GitHub-ish markdown */
  .md h1,.md h2,.md h3 {{ margin:24px 0 12px; line-height:1.25; }}
  .md h2 {{ font-size:24px; padding-bottom:.3em; border-bottom:1px solid var(--soft); }}
  .md h3 {{ font-size:18px; }}
  .md a {{ color:var(--link); text-decoration:none; }}
  .md hr {{ border:0; border-top:1px solid var(--soft); margin:24px 0; }}
  .md img {{ max-width:100%; }}
  .md table {{ border-collapse:collapse; }}
  .md td,.md th {{ border:1px solid var(--line); padding:6px 13px; vertical-align:top; }}
  .md code {{ background:var(--code); padding:.2em .4em; border-radius:6px; font-size:85%; }}
  .md pre {{ background:var(--code); padding:16px; border-radius:6px; overflow:auto; }}
  .md pre code {{ background:none; padding:0; }}
  .md blockquote {{ border-left:.25em solid var(--line); padding:0 1em;
                    color:var(--muted); margin:0 0 16px; }}
  .md sub {{ color:var(--muted); }}
  .md summary {{ cursor:pointer; }}
</style></head>
<body>
<div class="bar">
  <button id="theme">Switch to light</button>
  <span>{note}</span>
</div>
<div class="wrap">
  <h2 class="sec">Assets</h2>
  {gallery}
  <h2 class="sec">README, as GitHub renders it</h2>
  {readme}
</div>
<script>
  var dark = true;
  document.getElementById("theme").addEventListener("click", function () {{
    dark = !dark;
    document.body.classList.toggle("light", !dark);
    this.textContent = dark ? "Switch to light" : "Switch to dark";
    // Swap every themed asset the way GitHub's <picture> would.
    document.querySelectorAll("img").forEach(function (img) {{
      var s = img.getAttribute("src");
      if (!s) return;
      if (dark && s.indexOf("-light.svg") > -1)
        img.setAttribute("src", s.replace("-light.svg", "-dark.svg"));
      else if (!dark && s.indexOf("-dark.svg") > -1)
        img.setAttribute("src", s.replace("-dark.svg", "-light.svg"));
    }});
  }});
</script>
</body></html>
"""


def gallery() -> str:
    """Every generated asset, at the width GitHub actually shows it."""
    items = [
        ("banner-dark.svg", "BANNER - animated SVG, theme-swapped by the button above"),
        ("readout-dark.svg", "READOUT - identity panel with the CTA sticker across its corner"),
        ("graph-dark.svg", "GRAPH - the pattern the marquee is drawing"),
        ("statue.webp", "SPLAT TURNTABLE - 60 frames, 3s loop"),
    ]
    out = []
    for name, cap in items:
        path = ROOT / "assets" / name
        if not path.exists():
            out.append(
                f'<div class="asset"><div class="cap">{cap}</div>'
                f'<div class="warn">assets/{name} is missing. '
                f"Generate it first - see SETUP.md.</div></div>"
            )
            continue
        width = "320" if name.endswith(".webp") else "100%"
        size = path.stat().st_size
        out.append(
            f'<div class="asset"><div class="cap">{cap} &middot; '
            f"{size / 1024:.0f} KB</div>"
            f'<img src="assets/{name}" width="{width}" alt="{name}"></div>'
        )
    return "\n".join(out)


def render_markdown(md: str) -> tuple[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "darik0d-local-preview",
    }
    # Unauthenticated the Markdown API allows 60 calls an hour, which a few
    # preview-and-tweak rounds will exhaust. A token raises it to 5000; any
    # token works, since this endpoint reads nothing from your account.
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(
        "https://api.github.com/markdown",
        data=json.dumps({"text": md, "mode": "gfm",
                         "context": "darik0d/darik0d"}).encode(),
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            html = resp.read().decode()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        hint = ""
        if "403" in str(exc) or "rate limit" in str(exc).lower():
            hint = (" You have used up the 60 anonymous calls an hour. Set "
                    "GITHUB_TOKEN to raise it to 5000, or wait.")
        return (
            '<div class="warn">Could not reach GitHub to render the Markdown '
            f"({exc}).{hint} The asset gallery above is still accurate.</div>",
            "markdown unavailable - assets only",
        )
    # Point the images at the working copy instead of a repo that does not exist.
    html = html.replace(RAW + "assets/", "assets/")
    return f'<div class="card md">{html}</div>', "rendered by GitHub's markdown API"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-open", action="store_true", help="write the file only")
    args = ap.parse_args()

    readme = ROOT / "README.md"
    if not readme.exists():
        raise SystemExit(f"no README.md in {ROOT}")

    body, note = render_markdown(readme.read_text(encoding="utf-8"))
    OUT.write_text(
        SHELL.format(gallery=gallery(), readme=body, note=note), encoding="utf-8"
    )
    print(f"wrote {OUT}")
    print(f"  {note}")

    if not args.no_open:
        webbrowser.open(OUT.as_uri())
        print("  opened in your browser - reload the tab after each change")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
