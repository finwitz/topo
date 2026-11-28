"""Build the gallery: every map in this folder from its sources, and the index page that lists them.

usage: python3 -I gallery/build.py      (from the repository root)

Each map here has its own folder with the sources a map needs (topo.config.json, skeleton.json,
parts/, flows.json) and a gallery.json that says where it came from:

  {"name": "FastAPI", "repository": "https://github.com/fastapi/fastapi", "license": "MIT",
   "about": "one line on the project", "depth": "standard", "minutes": 40, "mapped": "2026-11-24",
   "tokens": {"total": 36363674, "cache_read": 34375456, "output": 345989}}

"tokens" is what the run used, summed from its Claude Code transcripts (the session and its mapping
agents): every token read or written, the share of them read from the prompt cache, and the tokens
written.

The index also lists the example map in maps/saleor. Every number on the index is read from the
built maps, never typed in.
"""
import html
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EXAMPLE = os.path.join(ROOT, "maps", "saleor")


def build(folder):
    r = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "pipeline", "build.py"), folder],
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"gallery: {folder} doesn't build: {r.stderr.strip()[-400:]}")
    with open(os.path.join(folder, "topo-data.json"), encoding="utf-8") as f:
        return json.load(f)


def counts(data):
    symbols = sum(1 for n in data["nodes"] if n["id"].startswith("f:") and "#" in n["id"])
    return {"boxes": len(data["nodes"]), "connections": len(data["edges"]), "flows": len(data.get("flows", [])),
            "symbols": symbols, "apps": sum(1 for n in data["nodes"] if n.get("kind") == "app")}


def tokens(n):
    """36363674 -> "36 million", 4427250 -> "4.4 million", 345989 -> "350 thousand"."""
    if n >= 10_000_000:
        return f"{n / 1e6:.0f} million"
    if n >= 1_000_000:
        return f"{n / 1e6:.1f} million"
    return f"{round(n, -4) // 1000:,} thousand"


def card(entry, c, href):
    commit = (entry.get("commit") or "")[:7]
    facts = [f"{c['boxes']:,} boxes", f"{c['connections']:,} connections", f"{c['flows']} flows"]
    made = [f"{entry['depth']} depth"]
    t = entry.get("tokens")
    if t:
        made.append(f"about {tokens(t['total'])} tokens, {round(100 * t['cache_read'] / t['total'])}% from cache")
    if entry.get("minutes"):
        made.append(f"{entry['minutes']} minutes")
    src = html.escape(entry["repository"])
    return f"""
    <a class="card" href="{html.escape(href)}">
      <span class="name">{html.escape(entry['name'])}</span>
      <span class="about">{html.escape(entry['about'])}</span>
      <span class="facts">{' · '.join(facts)}</span>
      <span class="made">{' · '.join(made)}</span>
      <span class="src">{src.replace('https://', '')}{f' at {commit}' if commit else ''} · {html.escape(entry['license'])}</span>
    </a>"""


def main():
    entries = []
    for name in sorted(os.listdir(HERE)):
        folder = os.path.join(HERE, name)
        meta = os.path.join(folder, "gallery.json")
        if not os.path.isfile(meta):
            continue
        with open(meta, encoding="utf-8") as f:
            entry = json.load(f)
        data = build(folder)
        repos = data["meta"].get("repos") or [{}]
        entry.setdefault("commit", repos[0].get("commit"))
        entries.append((entry, counts(data), f"{name}/dist/index.html"))
        print(f"  {name}: {entries[-1][1]['boxes']} boxes")
    with open(os.path.join(EXAMPLE, "topo-data.json"), encoding="utf-8") as f:
        saleor = counts(json.load(f))
    example = {"name": "Saleor", "about": "The open-source commerce platform: its API, its Dashboard and four of its apps, "
               "mapped as one system.", "repository": "https://github.com/saleor", "license": "BSD 3-Clause",
               "depth": "standard", "minutes": 30}
    cards = card(example, saleor, "../maps/saleor/dist/index.html") + "".join(card(e, c, h) for e, c, h in entries)
    page = PAGE.replace("<!--CARDS-->", cards)
    with open(os.path.join(HERE, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    print(f"gallery: {len(entries) + 1} maps -> gallery/index.html")


PAGE = """<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Topo gallery</title>
<meta name="description" content="Open-source codebases mapped with Topo: zoom from the whole system to one function, every box citing its line.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&family=Sofia+Sans:wght@400;500;600;700&display=swap">
<style>
:root { --paper: #0a0e14; --panel: #131a1d; --panel-2: #192226; --ink: #e4e8e6; --ink-2: #a9b3b0; --ink-3: #7f8a87;
  --rule: #2a3438; --accent: #8ea4ff; color-scheme: dark; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--paper); color: var(--ink); font: 16px/1.5 "Sofia Sans", system-ui, sans-serif; }
main { max-width: 1080px; margin: 0 auto; padding: 24px max(16px, env(safe-area-inset-left)) 56px; }
header img { display: block; width: min(560px, 100%); height: auto; margin: 0 auto; }
header p { max-width: 62ch; margin: 0 auto 32px; text-align: center; color: var(--ink-2); font-size: 18px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }
.card { display: grid; gap: 6px; align-content: start; padding: 18px 20px; border: 1px solid var(--rule); border-radius: 12px;
  background: var(--panel); color: inherit; text-decoration: none; }
.card:hover, .card:focus-visible { border-color: var(--accent); background: var(--panel-2); outline: none; }
.name { font-size: 24px; font-weight: 700; }
.about { color: var(--ink-2); }
.facts { margin-top: 6px; font-weight: 600; }
.made, .src { font: 13px "JetBrains Mono", ui-monospace, monospace; color: var(--ink-3); }
footer { margin-top: 40px; text-align: center; color: var(--ink-3); font-size: 14px; }
footer a { color: var(--accent); }
</style>
<main>
  <header>
    <img src="../brand/logo/svg/topo-logo-dark.svg" alt="Topo" width="1200" height="520">
    <p>Open-source codebases mapped with Topo. Zoom from the whole system to one function: every box cites
    the file and line it came from, and a script checked each one before the map was published.</p>
  </header>
  <div class="grid"><!--CARDS--></div>
  <footer>Each map is one HTML file read from the project's code at the commit shown. The projects' own licenses
  are in Topo's NOTICE. <a id="repo" href="../README.md">Map your own code with Topo</a>.</footer>
</main>
<script>
// on GitHub Pages (<owner>.github.io/<repository>/), link to the repository itself
const [owner] = location.hostname.split('.'), repo = location.pathname.split('/')[1];
if (location.hostname.endsWith('.github.io') && repo) document.getElementById('repo').href = `https://github.com/${owner}/${repo}`;
</script>
</html>
"""

if __name__ == "__main__":
    main()
