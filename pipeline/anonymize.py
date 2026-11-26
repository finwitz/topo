"""Anonymize a map's sources with a private substitution map, then scan for leaks.

usage:
  python3 -I anonymize.py --rules PRIVATE_RULES.json --src SRC_DIR --out OUT_DIR

SRC_DIR holds skeleton.json, parts/*.json and (optionally) flows.json, features.json and topo.config.json.
Every string is rewritten (ids, paths and JSON keys included) so references stay consistent. The rules file is a list of [pattern, replacement] or
[pattern, replacement, "case"] entries applied in order. "case" entries match
case-insensitively and copy the source's casing (ACME -> NORTHWIND, acme -> northwind).

After rewriting, the output is scanned with leakscan.py: every `leak_scan` pattern from the
rules file (case-insensitive, also against identifiers split into words, so `acme` is found in
`extract_acme_frames.py` and `ShardsAcme`) and every rule's source pattern. Any hit fails the
run, so nothing that names the client can slip into a shared repository.

Repo URLs and commits in topo.config.json are cleared, so shared copies never link into
private repositories.

Keep the rules file OUT of any shared repository: it is the key that undoes the anonymization.
"""
import argparse
import glob
import importlib.util
import json
import os
import re
import shutil
import sys

# loaded by path: python3 -I keeps the script's folder off sys.path
_spec = importlib.util.spec_from_file_location("leakscan", os.path.join(os.path.dirname(os.path.abspath(__file__)), "leakscan.py"))
leakscan = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(leakscan)


def load_rules(path):
    raw = json.load(open(path))
    rules = []
    for entry in raw["rules"]:
        pat, rep = entry[0], entry[1]
        case = len(entry) > 2 and entry[2] == "case"
        rules.append((re.compile(pat, re.IGNORECASE if case else 0), rep, case))
    leaks = leakscan.compile_patterns(raw)
    return rules, leaks


def match_case(src, rep):
    if src.isupper() and len(src) > 1:
        return rep.upper()
    if src[:1].isupper():
        return rep[:1].upper() + rep[1:]
    return rep.lower()


def rewrite(s, rules):
    for rx, rep, case in rules:
        if case:
            s = rx.sub(lambda m, r=rep: match_case(m.group(0), r), s)
        else:
            s = rx.sub(rep, s)
    return s


def walk(v, rules):
    if isinstance(v, str):
        return rewrite(v, rules)
    if isinstance(v, list):
        return [walk(x, rules) for x in v]
    if isinstance(v, dict):
        # keys are rewritten too: configs key things by name (e.g. endpoint services)
        return {rewrite(k, rules): walk(x, rules) for k, x in v.items()}
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rules", required=True)
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rules, leaks = load_rules(a.rules)

    files = [os.path.join(a.src, "skeleton.json")] + sorted(glob.glob(os.path.join(a.src, "parts", "*.json")))
    for extra in ("flows.json", "features.json", "topo.config.json"):
        if os.path.exists(os.path.join(a.src, extra)):
            files.append(os.path.join(a.src, extra))

    if os.path.isdir(os.path.join(a.out, "parts")):
        shutil.rmtree(os.path.join(a.out, "parts"))
    os.makedirs(os.path.join(a.out, "parts"), exist_ok=True)

    seen_ids, before_ids, written = {}, set(), []
    for f in files:
        doc = json.load(open(f))
        for n in doc.get("nodes", []):
            before_ids.add(n["id"])
        out = walk(doc, rules)
        if os.path.basename(f) == "topo.config.json":
            # shared copies never link into private repositories
            for r in out.get("repos", []):
                r["url"], r["commit"] = None, None
        for n in out.get("nodes", []):
            if n["id"] in seen_ids:
                sys.exit(f"anonymize: id collision after rewriting: {n['id']} ({seen_ids[n['id']]} and {os.path.basename(f)})")
            seen_ids[n["id"]] = os.path.basename(f)
        rel = os.path.relpath(f, a.src)
        dest = os.path.join(a.out, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        json.dump(out, open(dest, "w"), ensure_ascii=False, indent=1)
        written.append(dest)

    if len(seen_ids) != len(before_ids):
        sys.exit(f"anonymize: {len(before_ids)} ids became {len(seen_ids)}; two ids collapsed into one")

    hits = 0
    for dest in written:
        text = open(dest).read()
        for i, line, start, end in leakscan.find(text, leaks):
            hits += 1
            if hits <= 25:
                ctx = text[max(0, start - 50): end + 50].replace("\n", " ") if start is not None else "(after splitting identifiers into words)"
                print(f"LEAK {os.path.basename(dest)}:{line} /{leaks[i][0].pattern}/: ...{ctx}...")
    print(f"anonymize: {len(written)} files, {len(seen_ids)} ids rewritten, {hits} leak(s)")
    if hits:
        sys.exit(1)


if __name__ == "__main__":
    main()
