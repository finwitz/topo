"""Merge the agents' slices and run every check on a map in one step.

usage: python3 -I pipeline/finish.py MAP_DIR [--merge] [--repo CHECKOUT] [--no-analyze]

--merge copies each slice from the slices folder (the areas file's "slices", else MAP_DIR/slices)
into MAP_DIR/parts/. A copy in parts/ edited since (the merge step edits those) is kept; a slice its
agent edited after the last merge (an agent sent back) replaces its copy, and the old copy goes to
MAP_DIR/.merge-backup/.

Then it runs, in order, and prints each one's report:

  validate.py   every slice together, against the checkout (stops here if it fails)
  refs.py       references with no exact box: the merge step's to-do list
  build.py      the page, dist/index.html
  symcheck.py   cited lines against their symbols (98% or more passes)
  depthcheck.py how deep the map goes: public definitions with a box, symbol boxes with a
                connection and code excerpts, each with a floor
  features.py   the feature tree, when the map has a features.json (rebuilds the page when the
                check updates the reference list's search results)
  analyze.py    ANALYSIS.md and BUILDOUT.md (skip with --no-analyze)

It exits 1 if validation, the build, the symbol check, the depth check or the feature check fails, and prints a one-line summary last.
Run it again after each round of edits in parts/ or flows.json.
"""
import argparse
import filecmp
import glob
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import depthcheck  # noqa: E402
SYMCHECK_FLOOR = 0.98


def run(tool, *args):
    r = subprocess.run([sys.executable, "-I", os.path.join(HERE, tool), *args], capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    print(f"\n== {tool[:-3]}\n{out}" if out else f"\n== {tool[:-3]}: no output")
    return r.returncode, out


def slices_folder(map_dir):
    areas = os.path.join(map_dir, "areas.json")
    if os.path.exists(areas):
        s = json.load(open(areas)).get("slices")
        if s:
            return os.path.expanduser(s)
    return os.path.join(map_dir, "slices")


def merge(map_dir):
    src = slices_folder(map_dir)
    found = sorted(glob.glob(os.path.join(src, "*.json")))
    if not found:
        sys.exit(f"finish: no slices in {src}")
    parts = os.path.join(map_dir, "parts")
    os.makedirs(parts, exist_ok=True)
    copied, updated, kept = [], [], []
    for f in found:
        name = os.path.basename(f)
        dest = os.path.join(parts, name)
        if not os.path.exists(dest):
            shutil.copyfile(f, dest)
            copied.append(name)
        elif filecmp.cmp(f, dest, shallow=False):
            continue
        elif os.path.getmtime(f) > os.path.getmtime(dest):
            # the agent edited its slice after the last merge (it was sent back): take it, keeping the old copy
            backup = os.path.join(map_dir, ".merge-backup")
            os.makedirs(backup, exist_ok=True)
            shutil.copyfile(dest, os.path.join(backup, name))
            shutil.copyfile(f, dest)
            updated.append(name)
        else:
            kept.append(name)
    print(f"== merge: {len(copied)} copied into parts/" + (f" ({', '.join(copied)})" if copied else ""))
    for u in updated:
        print(f"   updated parts/{u}: the slice is newer (the old copy is in .merge-backup/; redo any edits "
              f"made to it in the merge step)")
    for k in kept:
        print(f"   kept parts/{k}: edited since its slice; delete it to take the slice again")


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("map_dir")
    ap.add_argument("--merge", action="store_true")
    ap.add_argument("--repo", help="the checkout (default MAP_DIR/checkout)")
    ap.add_argument("--no-analyze", action="store_true")
    a = ap.parse_args()
    m = a.map_dir.rstrip("/")
    repo = a.repo or os.path.join(m, "checkout")
    if not os.path.isdir(repo):
        sys.exit(f"finish: no checkout at {repo}; pass --repo")
    if a.merge:
        merge(m)
    if not glob.glob(os.path.join(m, "parts", "*.json")):
        sys.exit(f"finish: no slices in {m}/parts; run with --merge")

    code, out = run("validate.py", m, "--repo", repo)
    if code:
        print("\nfinish: validation failed; fix the slices in parts/ and run again")
        sys.exit(1)
    warnings = re.search(r"OK \((\d+) warning", out)
    _, refs = run("refs.py", m)
    code, _ = run("build.py", m)
    if code:
        print("\nfinish: the build failed")
        sys.exit(1)
    _, sym = run("symcheck.py", m, "--repo", repo)
    ok, bad = (int(x) for x in re.search(r"(\d+) ok, (\d+) mismatched", sym).groups())
    share = ok / (ok + bad) if ok + bad else 1.0
    print("\n== depthcheck")
    deep_enough, depth = depthcheck.report(m, repo)
    covered, total = depth["covered"], depth["total"]
    features_ok = True
    if os.path.exists(os.path.join(m, "features.json")):
        print("\n== features")
        sys.path.insert(0, HERE)
        import features
        features_ok, changed = features.check(m, repo)
        if changed:
            run("build.py", m)
    if not a.no_analyze:
        run("analyze.py", m)
    unresolved = re.search(r"unresolved by family: (.*)", refs)
    print(f"\nfinish: validate OK ({warnings.group(1) if warnings else '?'} warnings); "
          f"unresolved references: {unresolved.group(1) if unresolved else '?'}; "
          f"symbols {ok}/{ok + bad} ({share:.0%}); public definitions with a box {covered}/{total}; "
          f"page {m}/dist/index.html")
    failed = False
    if share < SYMCHECK_FLOOR:
        print(f"finish: under {SYMCHECK_FLOOR:.0%} of cited lines match their symbols; fix or explain the mismatches")
        failed = True
    if not deep_enough:
        print("finish: the map is shallower than the depth check allows (see == depthcheck above); send the "
              "agent of each listed file's area back with that list, to box, connect and quote what it lists")
        failed = True
    if not features_ok:
        print("finish: the feature tree has errors or leaves entry points unclaimed (see == features above)")
        failed = True
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
