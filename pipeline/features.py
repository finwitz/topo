"""The features view: a tree of what a product does, each feature citing the boxes that build it, and
the gaps against a reference list (a roadmap, a PRD, a competitor's feature list).

usage:
  python3 -I pipeline/features.py brief MAP_DIR [--reference LIST.md ...] [--out BRIEF.md]
  python3 -I pipeline/features.py check MAP_DIR [--repo CHECKOUT]

brief  writes the instructions and the map's material (areas, entry points, flows) for the agent that
       writes MAP_DIR/features.json. It reads the built map (topo-data.json), not the code.
check  checks features.json against the built map and prints the report: every cited box and flow
       exists, every leaf feature cites a box, the share of the map's entry points (endpoints and
       flows) some feature claims, and the reference list's score. For each reference item marked
       "not found" it runs the agent's search terms over the checkout and the map, and writes what
       they hit into the item's "found" (an item with hits shows as "check by hand"). Exits 1 on an
       error or when the entry-point coverage is under its floor.

features.json (in the map folder, beside flows.json):

  {"features": [
     {"id": "feat.checkout", "name": "Checkout", "summary": "..."},
     {"id": "feat.checkout.gift-cards", "parent": "feat.checkout", "name": "Gift cards",
      "summary": "...", "entry": ["<box id>"], "boxes": ["<box id>"], "flows": ["<flow id>"]}],
   "reference": {"name": "Roadmap 2027", "items": [
     {"text": "Gift cards", "state": "matched", "feature": "feat.checkout.gift-cards"},
     {"text": "Saved carts", "state": "not found", "searched": ["saved cart", "persist checkout"]},
     {"text": "Marketplace", "state": "out of scope"}]}}

A feature's status is worked out here from its boxes, never written by the agent: "docs" when every
box is known only from documents, "partial" when a box or anything inside it is partial, a stub or
planned, else "built".
"""
import argparse
import json
import os
import re
import sys

LEVELS = 3
NAME_MAX, SUMMARY_MAX = 48, 200
STATES = ("matched", "not found", "out of scope")
FLOOR = {"flows": 0.9, "endpoints": 0.8}      # share of the map's entry points some feature must claim
GAPPY = {"partial", "stub", "planned"}
CODE_EXT = (".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rb", ".java", ".kt", ".cs", ".php", ".rs",
            ".swift", ".graphql", ".gql", ".vue", ".svelte", ".html", ".sql", ".yml", ".yaml", ".json")
SKIP_DIRS = {"node_modules", ".git", "__pycache__", "dist", "build", ".venv", "venv", "vendor", ".next",
             "coverage", "locale", "locales", "translations"}
TEST_DIRS = {"test", "tests", "__tests__", "fixtures", "__fixtures__", "e2e", "cypress", "playwright"}
TEST_FILE = re.compile(r"(^test_|_test\.\w+$|\.(test|spec|stories)\.\w+$|^(fixtures?|mocks?)\.\w+$)")
ENTRY_HINT = re.compile(r"/(mutations?|queries|resolvers|commands|cli|pages|routes|views|screens|api)/|"
                        r"(Page|Screen|View|Mutation|Command)\b")


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------- the tree, its statuses and its coverage (build.py embeds this in topo-data.json)

def tree(nodes):
    kids = {}
    for n in nodes:
        if n.get("parent"):
            kids.setdefault(n["parent"], []).append(n["id"])
    return kids


def inside(ids, kids):
    """the boxes and everything inside them"""
    seen, stack = set(), list(ids)
    while stack:
        i = stack.pop()
        if i not in seen:
            seen.add(i)
            stack.extend(kids.get(i, []))
    return seen


def cited(f):
    return list(dict.fromkeys((f.get("entry") or []) + (f.get("boxes") or [])))


def embed(data, doc):
    """features.json + the built map -> the "features" block of topo-data.json"""
    nodes = {n["id"]: n for n in data["nodes"]}
    kids = tree(data["nodes"])
    feats = doc.get("features") or []
    children = {}
    for f in feats:
        children.setdefault(f.get("parent"), []).append(f["id"])
    out, by_id = [], {f["id"]: f for f in feats}

    def own(fid):
        f = by_id[fid]
        mine = [i for i in cited(f) if i in nodes]
        for c in children.get(fid, []):
            mine += own(c)
        return mine

    for f in feats:
        mine = own(f["id"])
        within = inside(mine, kids)
        boxes = [nodes[i] for i in within if i in nodes]
        if mine and all(nodes[i].get("source") == "docs" for i in mine):
            status = "docs"
        elif any(b.get("status") in GAPPY for b in boxes):
            status = "partial"
        else:
            status = "built" if mine else "docs"
        e = {k: f[k] for k in ("id", "parent", "name", "summary") if f.get(k)}
        e.update({"status": status, "count": len(within)})
        for k in ("entry", "boxes", "flows"):
            v = [i for i in (f.get(k) or []) if i in nodes] if k != "flows" else list(f.get(k) or [])
            if v:
                e[k] = v
        out.append(e)
    block = {"features": out}
    ref = doc.get("reference")
    if ref and ref.get("items"):
        items = []
        for it in ref["items"]:
            state = it.get("state", "not found")
            if state == "not found" and it.get("found"):
                state = "check"
            x = {"text": it.get("text", ""), "state": state}
            for k in ("feature", "searched", "found", "note"):
                if it.get(k):
                    x[k] = it[k]
            items.append(x)
        block["reference"] = {"name": ref.get("name", "Reference list"), "items": items}
    return block


def coverage(data, doc):
    nodes = {n["id"]: n for n in data["nodes"]}
    kids = tree(data["nodes"])
    claimed = inside([i for f in doc.get("features") or [] for i in cited(f) if i in nodes], kids)
    eps = [n["id"] for n in data["nodes"] if n.get("kind") == "endpoint"]
    flows = [f["id"] for f in data.get("flows", [])]
    claimed_flows = {i for f in doc.get("features") or [] for i in f.get("flows") or []}
    # a flow also counts when a feature claims most of its steps
    for fl in data.get("flows", []):
        steps = [s["node"] for s in fl.get("steps", [])]
        if steps and sum(s in claimed for s in steps) * 2 > len(steps):
            claimed_flows.add(fl["id"])
    return {"endpoints": (eps, [e for e in eps if e not in claimed]),
            "flows": (flows, [f for f in flows if f not in claimed_flows])}


# ---------- check

def errors_in(data, doc):
    nodes = {n["id"] for n in data["nodes"]}
    flows = {f["id"] for f in data.get("flows", [])}
    feats = doc.get("features")
    errs = []
    if not isinstance(feats, list) or not feats:
        return ["features.json has no \"features\" list"]
    by_id, parents = {}, set()
    for f in feats:
        fid = f.get("id", "")
        if not str(fid).startswith("feat."):
            errs.append(f"{fid!r}: a feature id starts with \"feat.\"")
        if fid in by_id:
            errs.append(f"{fid}: the id is used twice")
        by_id[fid] = f
        if f.get("parent"):
            parents.add(f["parent"])
    for fid, f in by_id.items():
        name, summary = f.get("name", ""), f.get("summary", "")
        if not name or len(name) > NAME_MAX:
            errs.append(f"{fid}: a name of 1 to {NAME_MAX} characters (has {len(name)})")
        if not summary or len(summary) > SUMMARY_MAX:
            errs.append(f"{fid}: a summary of 1 to {SUMMARY_MAX} characters (has {len(summary)})")
        depth, p, seen = 1, f.get("parent"), {fid}
        while p:
            if p not in by_id:
                errs.append(f"{fid}: its parent {p!r} isn't a feature")
                break
            if p in seen:
                errs.append(f"{fid}: its parents go round in a circle")
                break
            seen.add(p)
            depth += 1
            p = by_id[p].get("parent")
        if depth > LEVELS:
            errs.append(f"{fid}: {depth} levels deep; at most {LEVELS} (area > feature > sub-feature)")
        for i in cited(f):
            if i not in nodes:
                errs.append(f"{fid}: cites {i!r}, which isn't a box on the map")
        for i in f.get("flows") or []:
            if i not in flows:
                errs.append(f"{fid}: names flow {i!r}, which isn't on the map")
        if fid not in parents and not any(i in nodes for i in cited(f)):
            errs.append(f"{fid}: a feature with no sub-features cites at least one box (entry or boxes)")
    for n, it in enumerate((doc.get("reference") or {}).get("items") or [], 1):
        where = f"reference item {n} ({it.get('text', '')[:40]!r})"
        if not it.get("text"):
            errs.append(f"{where}: no text")
        state = it.get("state")
        if state not in STATES:
            errs.append(f"{where}: state is one of {', '.join(STATES)}")
        elif state == "matched" and it.get("feature") not in by_id:
            errs.append(f"{where}: matched, so it names the feature that covers it")
        elif state == "not found" and not it.get("searched"):
            errs.append(f"{where}: not found, so it lists the terms searched for")
    return errs


def term_re(term):
    words = [re.escape(w) for w in re.split(r"[\s_\-]+", term.strip()) if w]
    return re.compile(r"[\s_\-]*".join(words), re.I) if words else None


def roots(map_dir, repo):
    clones = os.path.join(map_dir, "clones.json")
    if os.path.exists(clones):
        return [os.path.expanduser(p) for p in load(clones).values()]
    return [repo] if repo and os.path.isdir(repo) else []


def search(items, data, folders, limit=3):
    """item index -> places its search terms hit, in the code and on the map"""
    pats = {n: [p for p in map(term_re, it.get("searched") or []) if p] for n, it in enumerate(items)
            if it.get("state") == "not found"}
    hits = {n: [] for n in pats}
    for n, ps in pats.items():
        for node in data["nodes"]:
            text = f"{node['id']} {node.get('name', '')} {node.get('summary', '')}"
            if any(p.search(text) for p in ps):
                hits[n].append(f"map: {node['id']}")
                if len(hits[n]) >= limit:
                    break
    for root in folders:
        base = os.path.basename(os.path.normpath(root))
        for d, dirs, files in os.walk(root):
            # tests and fixtures name things a product doesn't do; only the product's own code counts
            dirs[:] = [x for x in dirs if x not in SKIP_DIRS and x not in TEST_DIRS and not x.startswith(".")]
            for fn in files:
                if not fn.endswith(CODE_EXT) or ".generated." in fn or fn.endswith(".min.js") or TEST_FILE.search(fn):
                    continue
                path = os.path.join(d, fn)
                try:
                    if os.path.getsize(path) > 400_000:
                        continue
                    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
                except OSError:
                    continue
                rel = os.path.join(base, os.path.relpath(path, root))
                for n, ps in pats.items():
                    if len(hits[n]) >= limit:
                        continue
                    for ln, line in enumerate(lines, 1):
                        if any(p.search(line) for p in ps):
                            hits[n].append(f"{rel}:{ln}")
                            break
    return hits


def check(map_dir, repo=None):
    fp = os.path.join(map_dir, "features.json")
    data = load(os.path.join(map_dir, "topo-data.json"))
    doc = load(fp)
    errs = errors_in(data, doc)
    items = (doc.get("reference") or {}).get("items") or []
    folders = roots(map_dir, repo or os.path.join(map_dir, "checkout"))
    changed = False
    if items and folders:
        for n, found in search(items, data, folders).items():
            if items[n].get("found", []) != found:
                if found:
                    items[n]["found"] = found
                else:
                    items[n].pop("found", None)
                changed = True
        if changed:
            with open(fp, "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False, indent=1)
                f.write("\n")
    elif items and not folders:
        print("features: no checkout to search, so the not-found items keep their last search results")
    block = embed(data, doc)
    feats = block["features"]
    leaves = [f for f in feats if not any(g.get("parent") == f["id"] for g in feats)]
    status = {s: sum(f["status"] == s for f in leaves) for s in ("built", "partial", "docs")}
    areas = sum(1 for f in feats if not f.get("parent"))
    print(f"features: {len(feats)} in {areas} areas ({len(leaves)} without sub-features: "
          f"{status['built']} built, {status['partial']} partial, {status['docs']} docs only)")
    short = False
    for kind, (all_, left) in coverage(data, doc).items():
        if not all_:
            continue
        share = 1 - len(left) / len(all_)
        under = share < FLOOR[kind]
        short |= under
        print(f"{kind} claimed by a feature: {len(all_) - len(left)}/{len(all_)} ({share:.0%}; floor "
              f"{FLOOR[kind]:.0%}){' UNDER THE FLOOR' if under else ''}")
        for i in left[:25]:
            print(f"  unclaimed: {i}")
        if len(left) > 25:
            print(f"  ... and {len(left) - 25} more")
    if "reference" in block:
        ref = block["reference"]
        score = {s: sum(i["state"] == s for i in ref["items"]) for s in ("matched", "not found", "check", "out of scope")}
        print(f"reference {ref['name']!r}: {score['matched']} matched, {score['not found']} not found, "
              f"{score['check']} to check by hand, {score['out of scope']} out of scope")
        for i in ref["items"]:
            if i["state"] == "check":
                print(f"  check by hand: {i['text']!r}: the search hit {', '.join(i['found'])}")
    for e in errs:
        print(f"ERROR {e}")
    ok = not errs and not short
    print("features: OK" if ok else f"features: {len(errs)} error(s)" + (", entry points under the floor" if short else ""))
    return ok, changed


# ---------- brief

def reference_name(paths):
    for p in paths:
        for line in open(p, encoding="utf-8").read().splitlines():
            if line.startswith("#"):
                return line.lstrip("#").strip()
    return ", ".join(os.path.splitext(os.path.basename(p))[0].replace("-", " ").capitalize() for p in paths) or "Reference list"


def reference_items(paths):
    items = []
    for p in paths:
        for line in open(p, encoding="utf-8").read().splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            items.append(re.sub(r"^([-*+]|\d+[.)])\s+(\[[ xX]\]\s+)?", "", s))
    return items


def brief(map_dir, refs=()):
    data = load(os.path.join(map_dir, "topo-data.json"))
    nodes = data["nodes"]
    kids = tree(nodes)
    by_id = {n["id"]: n for n in nodes}
    lines = []

    def walk(i, depth):
        n = by_id[i]
        if n["kind"] in ("function", "class") or depth > 4:
            return
        extra = f" [{n['status']}]" if n.get("status") else ""
        extra += " [docs only]" if n.get("source") == "docs" else ""
        lines.append(f"{'  ' * depth}- {n['id']} ({n['kind']}) {n['name']}{extra}: {n.get('summary', '')}")
        for c in kids.get(i, []):
            walk(c, depth + 1)

    for n in nodes:
        if not n.get("parent"):
            walk(n["id"], 0)
    entries = [n for n in nodes if n["kind"] == "endpoint"]
    hinted = [n for n in nodes if n["kind"] in ("function", "class", "component", "module")
              and ENTRY_HINT.search(n["id"] + " " + n["name"])]
    flows = [f"- {f['id']}: {f['name']}. {f.get('summary', '')} Steps: {', '.join(s['node'] for s in f['steps'])}"
             for f in data.get("flows", [])]
    items = reference_items(refs)
    title = data["meta"].get("title", "this product")
    out = [f"""# Features of {title}: brief

Write `{os.path.join(map_dir, 'features.json')}`: the tree of what {title} does for its users, each
feature citing the boxes on the map that build it. Read the map below, not the code; open a file in
the checkout only to settle a doubt.

## What a feature is

Something a user can reach: a page or screen, an API operation (HTTP route, GraphQL query or
mutation), a command, a tool, or a job or webhook a user turns on. Name it for what the user gets
("Gift cards", "Refunds"), never for the code ("payment module").

- Three levels at most: area > feature > sub-feature. Areas group features the way a product page
  would (Checkout, Catalog, Accounts), not the way the code is split. 5 to 12 areas; a leaf is one
  thing a user can do or rely on. Use sub-features only where a feature really has parts.
- Every feature without sub-features cites boxes: `entry` (the boxes a user reaches it through:
  endpoints, mutations, pages, commands) and `boxes` (the rest that builds it: modules, data,
  jobs). Cite the most specific box that is the whole of it; 1 to 8 ids, all exactly as below.
- `flows`: the ids of the guided flows that walk through it.
- Every endpoint and every flow below belongs to some feature: the check counts the ones no
  feature claims (floors: {FLOOR['endpoints']:.0%} of endpoints, {FLOOR['flows']:.0%} of flows).
  Internal plumbing (logging, build tooling, shared helpers) is not a feature; leave it out.
- Names at most {NAME_MAX} characters, in sentence case with "and" rather than "&" ("Products and
  variants", "Sign-in and authentication"; product names keep their capitals: "Stripe payments").
  A summary is one plain sentence of at most {SUMMARY_MAX} characters on what the user can do, with
  no marketing words.
- Ids: `feat.<area>` and `feat.<area>.<feature>`, lowercase words joined by hyphens.
- Don't write a status: the check works it out from the boxes.
"""]
    if items:
        out.append(f"""## Reference list

Set `reference.name` to {json.dumps(reference_name(refs))}. Match each item below to the feature that
covers it. Write each one into `reference.items` with its text unchanged and a state:

- `"matched"` with `"feature"`: the id of the feature that covers it (add the feature if the map
  shows it and your tree missed it)
- `"not found"` with `"searched"`: 2 to 5 terms you looked for on the map and in the checkout,
  including the words the code would use (`saved cart`, `persist checkout`). Say "not found", never
  "missing": the check runs your terms again over the code, and any hit sends the item to be
  checked by hand.

Don't mark anything out of scope; only the product's owner does that.

""" + "\n".join(f"- {i}" for i in items) + "\n")
    out.append("## Entry points\n\nEndpoints:\n" + ("\n".join(f"- {n['id']}: {n['name']}" for n in entries) or "(none)"))
    if hinted:
        out.append("Other likely entry points (pages, mutations, commands; by their names):\n" +
                   "\n".join(f"- {n['id']} ({n['kind']}): {n['name']}" for n in hinted[:400]))
    out.append("## Guided flows\n\n" + ("\n".join(flows) or "(none)"))
    out.append("## The map (applications, groups and modules; symbols left out)\n\n" + "\n".join(lines))
    out.append(f"""## Then

Run `python3 -I {os.path.abspath(__file__)} check {map_dir}` and fix every ERROR; claim the
unclaimed entry points it lists, or leave them only if they are plumbing. Reply with the number of
areas and features, the coverage lines, and the reference score.""")
    return "\n\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("command", choices=("brief", "check"))
    ap.add_argument("map_dir")
    ap.add_argument("--reference", action="append", default=[])
    ap.add_argument("--out")
    ap.add_argument("--repo")
    a = ap.parse_args()
    m = a.map_dir.rstrip("/")
    if not os.path.exists(os.path.join(m, "topo-data.json")):
        sys.exit(f"features: no built map in {m}; run finish.py first")
    if a.command == "brief":
        text = brief(m, a.reference)
        if a.out:
            open(a.out, "w", encoding="utf-8").write(text)
            print(f"features: brief at {a.out} ({len(text) // 1024} KB)")
        else:
            sys.stdout.write(text)
        return
    if not os.path.exists(os.path.join(m, "features.json")):
        sys.exit(f"features: no features.json in {m}")
    ok, _ = check(m, a.repo)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
