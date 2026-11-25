"""List a server's HTTP routes (method, full path, file:line) before mapping it.

usage: python3 -I pipeline/routes.py CHECKOUT FOLDER [--prefix PATH_PREFIX] [--out routes.json]

Hand the list to every mapping agent: the area that owns a route creates its endpoint box, and
every other area, or another application, that calls it uses the same `ep:<service> <METHOD> <path>`
id. It also makes the routes that callers use but no server declares stand out at merge.

Reads FastAPI (APIRouter prefixes and include_router prefixes), Flask (@app.route with methods),
Express-style JavaScript or TypeScript (router.get('/path', ...)) and Go (net/http HandleFunc,
Gin/Echo groups, and chi Route blocks; http.Handle and chi Mount are not yet read, and Go Group
variables are tracked per file by name). Paths come out as declared, with the router prefix; tests
are skipped. Read the result: a route registered dynamically will not appear.
"""
import argparse
import json
import os
import re

PY_DECO = re.compile(r'@(\w+)\.(get|post|put|patch|delete)\(\s*[rf]?["\']([^"\']*)["\']')
PY_ROUTE = re.compile(r'@(\w+)\.route\(\s*[rf]?["\']([^"\']*)["\'](?:[^)]*methods\s*=\s*\[([^\]]*)\])?', re.S)
PY_ROUTER = re.compile(r'(\w+)\s*=\s*(?:APIRouter|Blueprint)\(([^)]*)\)', re.S)
PY_PREFIX = re.compile(r'(?:prefix|url_prefix)\s*=\s*["\']([^"\']*)["\']')
PY_INCLUDE = re.compile(r'include_router\(\s*([\w.]+)(?:\s*,[^)]*?prefix\s*=\s*["\']([^"\']*)["\'])?')
JS_ROUTE = re.compile(r'\b(?:router|app|server|api)\.(get|post|put|patch|delete)\(\s*[`"\']([^`"\']+)[`"\']')
GO_GROUP = re.compile(r'\b(\w+)\s*:?=\s*(\w+)\.Group\(\s*["`]([^"`]*)["`]')
GO_CHI_ROUTE = re.compile(r'\b(\w+)\.Route\(\s*["`]([^"`]*)["`]\s*,\s*func\(\s*(\w+)\b')
GO_HANDLE = re.compile(r'\b\w+\.HandleFunc\(\s*["`]([^"`]+)["`]')
GO_METHOD = re.compile(r'\b(\w+)\.(GET|POST|PUT|PATCH|DELETE|Get|Post|Put|Patch|Delete)\(\s*["`]([^"`]*)["`]')
SKIP_DIRS = {"node_modules", ".git", "__pycache__", "dist", "build", ".venv", "venv"}


def is_test(path):
    base = os.path.basename(path)
    return (
        "/tests/" in path
        or "/test/" in path
        or base.startswith("test_")
        or base.endswith("_test.go")
        or ".test." in base
        or ".spec." in base
    )


def _join_path(prefix, path):
    joined = (prefix.rstrip("/") + "/" + path.lstrip("/")) if (prefix and path) else (prefix or path or "/")
    return joined if joined.startswith("/") else "/" + joined


def _collect_go(text, rel):
    rows = []
    groups = {}
    route_stack = []  # [(brace_depth_after_open, inner_var, prefix)]
    depth = 0
    for lineno, line in enumerate(text.splitlines(), 1):
        code = line.split("//", 1)[0]
        gm = GO_GROUP.search(code)
        if gm:
            var, parent, prefix = gm.groups()
            groups[var] = _join_path(groups.get(parent, ""), prefix)
        rm = GO_CHI_ROUTE.search(code)
        if rm:
            parent, prefix, inner_var = rm.groups()
            base_prefix = next((p for _, v, p in reversed(route_stack) if v == parent), groups.get(parent, ""))
            route_stack.append((depth + code.count("{") - code.count("}"), inner_var, _join_path(base_prefix, prefix)))
        for hm in GO_HANDLE.finditer(code):
            raw = hm.group(1).strip()
            parts = raw.split(None, 1)
            if len(parts) == 2 and parts[0].upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                method, path = parts[0].upper(), parts[1]
            else:
                method, path = "GET", raw
            if path.startswith("/"):
                rows.append((method, path, f"{rel}:{lineno}"))
        for mm in GO_METHOD.finditer(code):
            var, method, path = mm.groups()
            if not path.startswith("/"):
                continue
            prefix = next((p for _, v, p in reversed(route_stack) if v == var), groups.get(var, ""))
            rows.append((method.upper(), _join_path(prefix, path), f"{rel}:{lineno}"))
        depth += code.count("{") - code.count("}")
        while route_stack and depth < route_stack[-1][0]:
            route_stack.pop()
    return rows


def walk(root, exts):
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        for f in files:
            p = os.path.join(d, f)
            if f.endswith(exts) and not is_test(p):
                yield p


def collect(checkout, folder="."):
    """[(METHOD, path, "file:line")] for every route declared under checkout/folder, sorted by path."""
    base = os.path.join(checkout, folder)
    py = list(walk(base, (".py",)))
    included = {}
    for f in py:
        for m in PY_INCLUDE.finditer(open(f, encoding="utf-8", errors="replace").read()):
            if m.group(2):
                included[m.group(1).split(".")[0]] = m.group(2)
    rows = []
    for f in sorted(py):
        text = open(f, encoding="utf-8", errors="replace").read()
        prefixes = {}
        for m in PY_ROUTER.finditer(text):
            pm = PY_PREFIX.search(m.group(2))
            prefixes[m.group(1)] = pm.group(1) if pm else ""
        module = os.path.splitext(os.path.basename(f))[0]
        rel = os.path.relpath(f, checkout)
        for m in PY_DECO.finditer(text):
            var, method, path = m.groups()
            if var not in prefixes and var != "app":
                continue
            line = text.count("\n", 0, m.start()) + 1
            rows.append((method.upper(), (included.get(module, "") + prefixes.get(var, "") + path) or "/", f"{rel}:{line}"))
        for m in PY_ROUTE.finditer(text):
            var, path, methods = m.groups()
            line = text.count("\n", 0, m.start()) + 1
            for method in re.findall(r'["\'](\w+)["\']', methods or "'GET'"):
                rows.append((method.upper(), (prefixes.get(var, "") + path) or "/", f"{rel}:{line}"))
    for f in sorted(walk(base, (".js", ".mjs", ".ts"))):
        text = open(f, encoding="utf-8", errors="replace").read()
        rel = os.path.relpath(f, checkout)
        for m in JS_ROUTE.finditer(text):
            if m.group(2).startswith("/"):
                rows.append((m.group(1).upper(), m.group(2), f"{rel}:{text.count(chr(10), 0, m.start()) + 1}"))
    for f in sorted(walk(base, (".go",))):
        text = open(f, encoding="utf-8", errors="replace").read()
        rows.extend(_collect_go(text, os.path.relpath(f, checkout)))
    return sorted(set(rows), key=lambda r: (r[1], r[0]))


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("checkout")
    ap.add_argument("folder")
    ap.add_argument("--prefix", default="", help="the repository's folder in the checkout, prepended to paths")
    ap.add_argument("--out")
    a = ap.parse_args()
    rows = collect(a.checkout, a.folder)
    if a.prefix:
        rows = [(m, p, a.prefix + loc if not loc.startswith(a.prefix) else loc) for m, p, loc in rows]
    print(f"{len(rows)} routes in {len({r[2].split(':')[0] for r in rows})} files")
    if a.out:
        json.dump(rows, open(a.out, "w"), indent=0)
    else:
        for m, p, loc in rows:
            print(f"  {m:6} {p:50} {loc}")


if __name__ == "__main__":
    main()
