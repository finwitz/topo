"""Merge a map's slices into one dataset and inject it into the viewer page.

usage:
  python3 -I pipeline/build.py MAP_DIR [--template viewer/topo.template.html] [--out PATH] [--views FILE]

MAP_DIR holds:
  topo.config.json   title, region layout and colors, repos, fallbacks, featured flows
  skeleton.json       the predefined top levels (regions, subsystems, external services)
  parts/*.json        slices written by mapping agents (see pipeline/SCHEMA.md)
  flows.json          optional cross-area guided flows
  features.json       optional feature tree for the Features view (see features.py)

Writes MAP_DIR/topo-data.json and the page (default MAP_DIR/dist/index.html), with the Topo shell
(viewer/shell.html: the theme and top bar every Topo page shares) in it.
Views (the config's "views", or --views FILE: a config or a JSON list) link sibling pages of the same
work, such as what we did and what we should be doing; the one whose href is this page's file name
is marked current.
References between slices are resolved by id; when an exact node doesn't exist the
reference falls back to the file, folder or owning group, and the run reports it.
"""
import argparse
import glob
import html
import json
import os
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import features as feature_tree  # noqa: E402
KEEP = ["id", "parent", "name", "kind", "summary", "detail", "paths", "status", "tech", "facts",
        "signature", "code", "source", "repo", "provenance", "message", "phase", "date", "capabilities", "repo_key", "eyebrow", "tag",
        "url", "url_label", "abbrev"]


def strip_line(p):
    return re.sub(r":\d+(?:-\d+)?$", "", p)


def fill_shell(page):
    """The page with the Topo shell (viewer/shell.html: the theme, the top bar's brand and view switch, and the
    script that remembers where you were) in place of its markers."""
    with open(os.path.join(HERE, "..", "viewer", "shell.html"), encoding="utf-8") as f:
        src = f.read()
    parts = dict(re.findall(r"<!--shell:(\w+)-->\n(.*?)(?=<!--shell:|\Z)", src, re.S))
    return (page.replace("/*__SHELL_STYLE__*/", parts["style"].rstrip()).replace("<!--__SHELL_BAR__-->", parts["bar"].rstrip())
            .replace("<!--__SHELL_SCRIPT__-->", parts["script"].rstrip()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("map_dir")
    ap.add_argument("--template", default=os.path.join(HERE, "..", "viewer", "topo.template.html"))
    ap.add_argument("--out")
    ap.add_argument("--views", help="a JSON list of {label, href}, or a config holding one under 'views'")
    a = ap.parse_args()
    adir = a.map_dir
    out_page = a.out or os.path.join(adir, "dist", "index.html")
    cfg = json.load(open(os.path.join(adir, "topo.config.json")))
    log, notes = Counter(), defaultdict(list)

    skel = json.load(open(os.path.join(adir, "skeleton.json")))
    parts = sorted(glob.glob(os.path.join(adir, "parts", "*.json")))
    docs = [("skeleton", skel)] + [(os.path.basename(p), json.load(open(p))) for p in parts]

    nodes, order = {}, []
    for name, doc in docs:
        for n in doc.get("nodes", []):
            nid = n.get("id")
            if not nid:
                continue
            if nid in nodes:
                log["dup_nodes"] += 1
                notes["dup_nodes"].append(f"{nid} ({name})")
                continue
            nodes[nid] = {k: n[k] for k in KEEP if k in n and n[k] not in (None, "", [])}
            order.append(nid)

    # Only nodes that REPRESENT a file stand in for it: a node's `paths` are often just
    # evidence, so endpoint/agent/external nodes never do, and only primary paths count.
    file_level, sym_level = {}, {}
    for nid in order:
        if nid.startswith(("f:", "d:")):
            base = nid[2:].split("#")[0].rstrip("/")
            (sym_level.setdefault(base, nid) if "#" in nid else file_level.__setitem__(base, nid))
    for nid in order:
        if nid.startswith(("ep:", "mcp:", "x:", "app:", "f:", "d:")) or any(nid.startswith(p) for p in cfg.get("prefix_fallback", {})):
            continue
        ps = nodes[nid].get("paths") or []
        if ps and strip_line(ps[0]) == ps[0]:
            file_level.setdefault(ps[0].rstrip("/"), nid)
    ep_index = {re.sub(r"\{[^}]*\}", "{}", nid).rstrip("/"): nid for nid in order if nid.startswith("ep:")}

    owners = [(p, g) for p, g in cfg.get("owners", [])]
    root_default = cfg.get("default_parent", next((n for n in order if nodes[n].get("kind") == "app"), order[0]))

    def owner(path):
        for prefix, gid in owners:
            if path.startswith(prefix) and gid in nodes:
                return gid
        return root_default

    def resolve(ref):
        if ref in nodes:
            return ref, "exact"
        if ref.startswith(("f:", "d:")):
            path = ref[2:].split("#")[0].rstrip("/")
            for cand in ("f:" + path, "d:" + path, "d:" + path + "/"):
                if cand in nodes:
                    return cand, "file"
            if path in file_level:
                return file_level[path], "path"
            if path in sym_level:
                return sym_level[path], "symbol"
            p = path
            while "/" in p:
                p = p.rsplit("/", 1)[0]
                for cand in ("d:" + p, "d:" + p + "/"):
                    if cand in nodes:
                        return cand, "dir"
                if p in file_level:
                    return file_level[p], "dir"
            return owner(path), "owner"
        if ref.startswith("ep:"):
            norm = re.sub(r"\{[^}]*\}", "{}", ref).rstrip("/")
            if norm in ep_index:
                return ep_index[norm], "ep-norm"
            service = ref[3:].split(" ")[0]
            for c in cfg.get("endpoint_fallback", {}).get(service, []):
                if c in nodes:
                    return c, "ep-fallback"
            return None, "none"
        for prefix, target in cfg.get("prefix_fallback", {}).items():
            if ref.startswith(prefix) and target in nodes:
                return target, "prefix-fallback"
        return None, "none"

    for nid in order:
        n = nodes[nid]
        par = n.get("parent")
        if par is None or par in nodes:
            continue
        r, _ = resolve(par)
        if not r and nid.startswith(("f:", "d:")):
            r = owner(nid[2:].split("#")[0])
        n["parent"] = r or root_default
        log["reparented"] += 1
        notes["reparented"].append(f"{nid}: {par} -> {n['parent']}")
    for nid in order:
        seen, cur = set(), nid
        while cur:
            if cur in seen:
                nodes[nid]["parent"] = root_default
                log["cycle_fixed"] += 1
                break
            seen.add(cur)
            cur = nodes.get(cur, {}).get("parent")

    edges, seen_edges = [], {}
    for name, doc in docs:
        for e in doc.get("edges", []):
            src, hs = resolve(e.get("from", ""))
            dst, hd = resolve(e.get("to", ""))
            log["edge_" + hs] += 1
            log["edge_" + hd] += 1
            if not src or not dst:
                log["edges_dropped_unresolved"] += 1
                notes["unresolved"].append(f"{e.get('from')} -> {e.get('to')} ({name})")
                continue
            if src == dst:
                log["edges_dropped_self"] += 1
                continue
            # an idea (status "idea": proposed, not accepted) never merges into a real connection or another idea
            key = (src, dst, e.get("kind")) + ((e["status"], e.get("label")) if e.get("status") else ())
            if key in seen_edges:
                log["edges_merged"] += 1
                continue
            ed = {"from": src, "to": dst, "kind": e.get("kind", "calls"), "label": e.get("label", "")[:80]}
            for f in ("detail", "evidence", "status"):
                if e.get(f):
                    ed[f] = e[f]
            if str(e.get("url", "")).startswith("https://"):
                ed["url"] = e["url"]
            seen_edges[key] = ed
            edges.append(ed)

    flow_docs = list(docs)
    fp = os.path.join(adir, "flows.json")
    if os.path.exists(fp):
        flow_docs.append(("flows.json", json.load(open(fp))))
    feature = cfg.get("featured_flows") or []
    if os.path.exists(fp):
        feature = feature or json.load(open(fp)).get("feature", [])
    feat = {fid: (i, short) for i, (fid, short) in enumerate(feature)}
    area_names = cfg.get("area_names", {})
    flows = []
    for name, doc in flow_docs:
        for f in doc.get("flows", []) or []:
            steps = []
            for s in f.get("steps", []):
                r, _ = resolve(s.get("node", ""))
                if r:
                    steps.append({"node": r, "text": s.get("text", "")})
                else:
                    log["flow_steps_dropped"] += 1
            if len(steps) < 2:
                continue
            fl = {"id": f["id"], "name": f["name"], "summary": f.get("summary", ""), "steps": steps}
            if f.get("short"):
                fl["short"] = f["short"]
            if f["id"] in feat:
                fl["featured"] = True
                fl.setdefault("short", feat[f["id"]][1])
            area = doc.get("area")
            if area and area not in ("skeleton", "flows"):
                fl["area"] = area_names.get(area, area)
            flows.append(fl)
    flows.sort(key=lambda f: (0, feat[f["id"]][0]) if f["id"] in feat else (1, 0))

    for app_id, fields in cfg.get("apps", {}).items():
        if app_id in nodes:
            nodes[app_id].update({k: v for k, v in fields.items() if v})

    meta = {
        "title": cfg.get("title", "Topo map"),
        "generated": cfg.get("generated", ""),
        "regions": cfg.get("regions", []),
        "repos": cfg.get("repos", []),
        "process": cfg.get("process", []),
    }
    if cfg.get("decisions"):  # optional: decisions the Boundaries rail lists, each may name a box
        meta["decisions"] = cfg["decisions"]
    views = cfg.get("views") or []
    if a.views:
        v = json.load(open(a.views))
        views = v.get("views", []) if isinstance(v, dict) else v
    if views:
        here = os.path.basename(out_page)
        meta["views"] = [{**{k: x[k] for k in ("label", "short", "href") if k in x}, **({"current": True} if x["href"] == here else {})} for x in views]
    data = {"meta": meta, "nodes": [nodes[i] for i in order], "edges": edges, "flows": flows}
    ftp = os.path.join(adir, "features.json")
    if os.path.exists(ftp):
        data.update(feature_tree.embed(data, json.load(open(ftp))))
    json.dump(data, open(os.path.join(adir, "topo-data.json"), "w"), ensure_ascii=False, indent=1)

    tpl = fill_shell(open(a.template).read())
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    page = tpl.replace("__TOPO_TITLE__", html.escape(meta["title"])).replace("/*__TOPO_DATA__*/", blob)
    os.makedirs(os.path.dirname(out_page), exist_ok=True)
    open(out_page, "w").write(page)

    print(f"parts: {len(parts)}  nodes: {len(order)}  edges: {len(edges)}  flows: {len(flows)} "
          f"({sum(1 for f in flows if f.get('featured'))} featured)")
    if data.get("features"):
        print(f"features: {len(data['features'])}" + (f", reference items: {len(data['reference']['items'])}" if data.get("reference") else ""))
    print("kinds:", dict(Counter(nodes[i]["kind"] for i in order).most_common()))
    print("resolution:", dict(sorted(log.items())))
    for k in ("dup_nodes", "reparented", "unresolved"):
        if notes[k]:
            print(f"{k} ({len(notes[k])}):", *notes[k][:12], sep="\n  ")
    print(f"page: {out_page} ({len(page) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
