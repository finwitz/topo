"""Tests for the mapping tools (checkout, drift, routes, brief, contracts, the slice validator) on throwaway git repositories.
usage (from topo/): python3 -I -m unittest discover -s test -p 'test_*.py'
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PIPE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline")


def sh(cwd, *args):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True).stdout


def tool(name, *args):
    return subprocess.run([sys.executable, "-I", os.path.join(PIPE, name), *args], capture_output=True, text=True)


class Repo:
    def __init__(self, root):
        self.root = root
        os.makedirs(root)
        sh(root, "git", "init", "-q")
        sh(root, "git", "config", "user.email", "t@example.invalid")
        sh(root, "git", "config", "user.name", "t")

    def write(self, path, text):
        full = os.path.join(self.root, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        Path(full).write_text(text)

    def commit(self, msg="c"):
        sh(self.root, "git", "add", "-A")
        sh(self.root, "git", "commit", "-q", "-m", msg)
        return sh(self.root, "git", "rev-parse", "HEAD").strip()


class Tools(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.t = self.tmp.name
        self.repo = Repo(os.path.join(self.t, "app"))
        self.repo.write("src/a.py", "".join(f"line {i}\n" for i in range(1, 21)))
        self.repo.write("src/b.py", "x = 1\n")
        self.base = self.repo.commit()
        self.map = os.path.join(self.t, "map")
        os.makedirs(os.path.join(self.map, "parts"))
        Path(self.map, "topo.config.json").write_text(json.dumps(
            {"repos": [{"key": "app:x", "name": "X", "commit": self.base, "prefix": "app/"}]}))
        Path(self.map, "clones.json").write_text(json.dumps({"app:x": self.repo.root}))
        Path(self.map, "parts", "core.json").write_text(json.dumps({"area": "core", "nodes": [
            {"id": "f:app/src/a.py#early", "paths": ["app/src/a.py:2-4"]},
            {"id": "f:app/src/a.py#late", "paths": ["app/src/a.py:15-18"]},
            {"id": "f:app/src/b.py", "paths": ["app/src/b.py"]}], "edges": []}))

    def tearDown(self):
        self.tmp.cleanup()

    def test_checkout_is_the_mapped_commit_without_uncommitted_work(self):
        self.repo.write("src/b.py", "x = 2  # uncommitted\n")
        out = os.path.join(self.t, "checkout")
        r = tool("checkout.py", self.map, "--out", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(Path(out, "app", "src", "b.py").read_text(), "x = 1\n")

    def test_drift_tells_cited_lines_from_the_rest(self):
        text = Path(self.repo.root, "src/a.py").read_text().replace("line 3\n", "line three\n")
        self.repo.write("src/a.py", text)
        sh(self.repo.root, "git", "rm", "-q", "src/b.py")
        self.repo.write("src/new/c.py", "y = 1\n")
        self.repo.commit("change")
        out = os.path.join(self.t, "drift.json")
        r = tool("drift.py", self.map, "--out", out, "--fail-on-drift")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        rep = json.loads(Path(out).read_text())["repos"][0]
        reasons = {i["id"]: i["reason"] for i in rep["areas"]["core"]}
        self.assertEqual(reasons, {"f:app/src/a.py#early": "cited lines changed",
                                   "f:app/src/a.py#late": "file changed", "f:app/src/b.py": "gone"})
        self.assertEqual(rep["uncovered"], {"src/new": 1})

    def test_no_drift(self):
        r = tool("drift.py", self.map, "--fail-on-drift")
        self.assertEqual(r.returncode, 0)
        self.assertIn("no drift", r.stdout)

    def test_routes_with_router_prefixes(self):
        self.repo.write("api/main.py", "from fastapi import FastAPI\napp = FastAPI()\n"
                        "app.include_router(items.router, prefix='/v1')\n@app.get('/health')\ndef h(): ...\n")
        self.repo.write("api/items.py", "from fastapi import APIRouter\nrouter = APIRouter(prefix='/items')\n"
                        "@router.post('/{key}')\ndef put(key): ...\n")
        out = os.path.join(self.t, "routes.json")
        r = tool("routes.py", self.repo.root, "api", "--prefix", "app/", "--out", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = json.loads(Path(out).read_text())
        self.assertIn(["GET", "/health", "app/api/main.py:4"], rows)
        self.assertIn(["POST", "/v1/items/{key}", "app/api/items.py:3"], rows)

    def test_routes_go_servers(self):
        self.repo.write(
            "srv/nethttp.go",
            'package main\nfunc main() {\n'
            '\thttp.HandleFunc("/health", health)\n'
            '\thttp.HandleFunc("POST /webhooks", hook)\n'
            '}\n',
        )
        self.repo.write(
            "srv/gin_echo.go",
            'package main\nfunc mount(r *gin.Engine) {\n'
            '\tapi := r.Group("/api")\n'
            '\tv1 := api.Group("/v1")\n'
            '\tv1.GET("/orders", listOrders)\n'
            '\tv1.POST("/orders", createOrder)\n'
            '}\n',
        )
        self.repo.write(
            "srv/chi.go",
            'package main\nfunc routes(r chi.Router) {\n'
            '\tr.Route("/items", func(r chi.Router) {\n'
            '\t\tr.Get("/{id}", getItem)\n'
            '\t\tr.Delete("/{id}", deleteItem)\n'
            '\t})\n'
            '}\n',
        )
        self.repo.write(
            "srv/client.go",
            'package main\nfunc call(c *gin.Context, client *http.Client) {\n'
            '\thttp.Get("https://example.invalid/ping")\n'
            '\tclient.Post("https://example.invalid/events", "application/json", nil)\n'
            '\tc.Get("user")\n'
            '}\n',
        )
        self.repo.write(
            "srv/routes_test.go",
            'package main\nfunc TestX() { http.HandleFunc("/ignored", nil) }\n',
        )
        out = os.path.join(self.t, "go-routes.json")
        r = tool("routes.py", self.repo.root, "srv", "--out", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = json.loads(Path(out).read_text())
        self.assertIn(["GET", "/health", "srv/nethttp.go:3"], rows)
        self.assertIn(["POST", "/webhooks", "srv/nethttp.go:4"], rows)
        self.assertIn(["GET", "/api/v1/orders", "srv/gin_echo.go:5"], rows)
        self.assertIn(["POST", "/api/v1/orders", "srv/gin_echo.go:6"], rows)
        self.assertIn(["GET", "/items/{id}", "srv/chi.go:4"], rows)
        self.assertIn(["DELETE", "/items/{id}", "srv/chi.go:5"], rows)
        self.assertFalse(any(p == "/ignored" for _, p, _ in rows))
        self.assertFalse(any(loc.startswith("srv/client.go:") for _, _, loc in rows))

    def test_brief_catches_double_ownership(self):
        areas = {"map": self.map, "checkout": self.repo.root, "out": os.path.join(self.t, "briefs"),
                 "slices": os.path.join(self.t, "slices"), "areas": {
                     "one": {"app": "src/", "own": ["src/"]},
                     "two": {"app": "src/", "own": ["src/b.py"]}}}
        path = os.path.join(self.t, "areas.json")
        Path(path).write_text(json.dumps(areas))
        r = tool("brief.py", path)
        self.assertEqual(r.returncode, 1)
        self.assertIn("OWNED TWICE src/b.py", r.stdout)
        # two areas for two code files: more than the depth suggests, so it says so
        self.assertIn("MORE AREAS THAN SUGGESTED: 2 code areas where depth standard suggests 1", r.stdout)
        brief = Path(self.t, "briefs", "one.md").read_text()
        self.assertIn("pipeline/SCHEMA.md", brief)
        self.assertNotIn("MAPPING_PLAYBOOK", brief)   # the brief stands alone: agents don't read the playbook
        help_ = tool("brief.py", "--help")
        self.assertEqual(help_.returncode, 0)
        self.assertIn('"areas"', help_.stdout)



class DepthCheck(unittest.TestCase):
    """depthcheck.py: the public definitions a map is expected to box, in each language it reads."""

    def test_public_definitions_by_language(self):
        sys.path.insert(0, PIPE)
        import depthcheck
        with tempfile.TemporaryDirectory() as t:
            files = {
                "pkg/core.py": "import os\nclass Engine:\n    def run(self): ...\ndef start(): ...\ndef _private(): ...\n",
                "pkg/test_core.py": "def test_start(): ...\n",
                "web/api.ts": "export async function fetchOrders() {}\nexport class Cart {}\nconst hidden = 1\nexport default function App() {}\n",
                "svc/main.go": "package main\nfunc Serve() {}\nfunc helper() {}\ntype Order struct{}\nfunc (o *Order) Total() int { return 0 }\n",
                "lib/src/lib.rs": "pub fn parse() {}\nfn inner() {}\npub struct Token;\n",
                "tests/test_e2e.py": "def check(): ...\n",
                "docs/conf.py": "def setup(app): ...\n",
                "node_modules/x/index.js": "export function vendored() {}\n",
                "web/types.generated.ts": "export const generatedThing = 1\n",
                "web/generated/graphql.ts": "export function gql() {}\n",
                "web/schema.ts": "// Code generated by a tool. DO NOT EDIT.\nexport function made() {}\n",
                "web/model.ts": "export type Order = {id: string}\nexport interface Line {}\nexport function total() {}\n",
                "README.md": "# not code\n",
            }
            for rel, text in files.items():
                Path(t, rel).parent.mkdir(parents=True, exist_ok=True)
                Path(t, rel).write_text(text)
            self.assertEqual(depthcheck.public_defs(t), {
                "pkg/core.py": ["Engine", "Engine.run", "start"],
                "web/api.ts": ["fetchOrders", "Cart", "App"],
                "svc/main.go": ["Serve", "Order", "Order.Total"],
                "lib/src/lib.rs": ["parse", "Token"],
                "web/model.ts": ["total"]})   # generated files and TypeScript types don't count
            have = depthcheck.boxed(["f:pkg/core.py#Engine.run", "f:web/api.ts#Cart", "f:pkg/core.py", "f:svc/main.go#Total"])
            self.assertEqual(have, {"pkg/core.py": {"Engine", "Engine.run"}, "web/api.ts": {"Cart"},
                                    "svc/main.go": {"Total"}})
            self.assertTrue(depthcheck.has_box("Engine.run", have["pkg/core.py"]))
            self.assertTrue(depthcheck.has_box("Order.Total", have["svc/main.go"]))   # the class left out of the id
            self.assertFalse(depthcheck.has_box("start", have["pkg/core.py"]))
            # a file that defines one or two public names is mapped at symbol level by its own file box
            Path(t, "map").mkdir()
            Path(t, "map", "topo-data.json").write_text(json.dumps({"nodes": [
                {"id": "f:web/model.ts"}, {"id": "f:pkg/core.py"}], "edges": []}))
            c = depthcheck.check(os.path.join(t, "map"), t, "standard")
            self.assertNotIn("web/model.ts", c["missing"])        # one public name: its file box counts
            self.assertIn("pkg/core.py", c["missing"])            # three: they need boxes of their own
            self.assertEqual(c["per_area"][0][1], 1)
            # an area's symbol boxes: 65% of its public definitions, counting at most 75
            self.assertEqual((depthcheck.symbols_needed(54), depthcheck.symbols_needed(623)), (36, 49))
            # the three depths: an overview needs no symbol boxes, deep counts every public definition
            self.assertEqual([depthcheck.symbols_needed(623, lv) for lv in ("overview", "standard", "deep")], [0, 49, 405])
            self.assertEqual([depthcheck.full_depth(623, 3, lv) for lv in ("overview", "standard", "deep")],
                             [False, False, True])
            self.assertTrue(depthcheck.full_depth(54, 1, "standard"))


class Depths(unittest.TestCase):
    """depths.py: the built-in depths, a machine's own under "depths", and a map's depth kept in full."""

    def setUp(self):
        sys.path.insert(0, PIPE)
        import depths
        self.depths = depths
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = os.path.join(self.tmp.name, "config.json")
        self.old = os.environ.get("TOPO_CONFIG")
        os.environ["TOPO_CONFIG"] = self.cfg

    def tearDown(self):
        if self.old is None:
            os.environ.pop("TOPO_CONFIG", None)
        else:
            os.environ["TOPO_CONFIG"] = self.old
        self.tmp.cleanup()

    def config(self, data):
        Path(self.cfg).write_text(json.dumps(data))

    def test_a_machine_adds_its_own_depth(self):
        d = self.depths
        self.assertEqual(list(d.levels()), ["overview", "standard", "deep"])
        self.config({"depths": {"review": {"symbols": 0.4, "excerpts": 6, "about": "the main functions only"}}})
        review = d.resolve("review")
        # what it doesn't say comes from standard
        self.assertEqual((review["symbols"], review["cap"], review["excerpts"], review["connect"]), (0.4, 75, 6, "symbols"))
        self.config({"depths": {"skim": {"based_on": "overview", "excerpts": 1}}})
        self.assertEqual((d.resolve("skim")["connect"], d.resolve("skim")["symbols"]), ("files", 0.0))
        # a map keeps a depth of its own in full, so another machine still knows its floors
        stored = d.stored(d.resolve("skim"))
        self.assertEqual((stored["name"], stored["excerpts"], stored["connect"]), ("skim", 1, "files"))
        self.assertEqual(d.resolve(stored), d.resolve("skim"))
        self.assertEqual(d.stored(d.resolve("deep")), "deep")
        shown = subprocess.run([sys.executable, "-I", os.path.join(PIPE, "depths.py"), "--show", "skim"],
                               capture_output=True, text=True, env=dict(os.environ, TOPO_CONFIG=self.cfg))
        self.assertEqual(json.loads(shown.stdout), stored)
        import depthcheck
        self.assertEqual(depthcheck.symbols_needed(100, {**d.resolve("standard"), "symbols": 0.4}), 30)

    def test_a_depth_that_doesnt_make_sense_is_refused(self):
        d = self.depths
        for spec, words in (({"symbols": 2}, "share from 0 to 1"), ({"connect": "vibes"}, "symbols or files"),
                            ({"based_on": "bottomless"}, "is based on"), ({"precision": 0}, "unknown precision"),
                            ({"agents": ["dice"]}, "agents must be")):
            self.config({"depths": {"mine": spec}})
            with self.assertRaises(d.DepthError) as e:
                d.levels()
            self.assertIn(words, str(e.exception))
        self.config({"depths": {"deep": {"symbols": 0.1}}})
        with self.assertRaises(d.DepthError) as e:
            d.levels()
        self.assertIn("is built in", str(e.exception))


class Contracts(unittest.TestCase):
    """contracts.py on made-up repositories: a platform that serves routes, a shop that calls them."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.t = self.tmp.name
        self.platform = Repo(os.path.join(self.t, "platform"))
        self.platform.write("api/main.py", "from fastapi import FastAPI\napp = FastAPI()\n"
                            "app.include_router(items.router, prefix='/v1')\n@app.get('/health')\ndef h(): ...\n")
        self.platform.write("api/items.py", "from fastapi import APIRouter\nrouter = APIRouter(prefix='/items')\n"
                            "@router.get('/{key}')\ndef get(key): ...\n")
        self.old = self.platform.commit("items can be read")
        self.platform.write("api/items.py", "from fastapi import APIRouter\nrouter = APIRouter(prefix='/items')\n"
                            "@router.get('/{key}')\ndef get(key): ...\n@router.post('/{key}/hold')\ndef hold(key): ...\n")
        self.platform.commit("items can be held")
        self.platform.write("README.md", "platform\n")
        self.head = self.platform.commit("docs")
        self.shop = Repo(os.path.join(self.t, "shop"))
        self.contracts = os.path.join(self.t, "contracts.json")

    def tearDown(self):
        self.tmp.cleanup()

    def write_shop(self):
        """A caller with one call of every kind contracts.py reads."""
        self.shop.write("shop/client.py", "\n".join([
            "import os, httpx",
            "PLATFORM = os.getenv('PLATFORM_URL', 'https://api.platform.example')",
            "class Client:",
            "    def __init__(self, base=None):",
            "        self.base = (base or PLATFORM).rstrip('/')",
            "    def hold(self, key):",
            "        return httpx.post(f'{self.base}/v1/items/{key}/hold', json={})",
            "    def hold_quoted(self, key):",
            "        return httpx.post(f\"{self.base}/v1/items/{quote(key, safe='')}/hold\", json={})",
            "    def order(self):",
            "        url = f'{self.base}/v1/orders'",
            "        return httpx.post(url)",
            "    def read(self, key):",
            "        return httpx.put(f'{PLATFORM}/v1/items/{key}')",
            "    def health(self):",
            "        with httpx.Client(base_url=PLATFORM) as c:",
            "            return c.get('/health')",
            "def elsewhere():",
            "    base = 'https://other.example'",
            "    return httpx.get(f'{base}/not/the/platform')",
            ""]))
        self.shop.write("web/api.ts", "const baseUrl = process.env.PLATFORM_URL;\n"
                        "export const item = (k: string) => fetch(`${baseUrl}/v1/items/${k}`);\n")
        self.shop.write("ops/smoke.sh", 'curl -sS -X POST \\\n  "${PLATFORM_URL}/v1/items/x/hold"\n'
                        'curl -sS "https://api.platform.example/v2/status"\n')
        self.shop.write("shop/test_client.py", "httpx.get(f'{PLATFORM}/v1/fake')\n")
        return self.shop.commit()

    def run_check(self, callers, target=None):
        target = target or {"repo": self.platform.root, "folder": "api"}
        Path(self.contracts).write_text(json.dumps({"contracts": [{"name": "Platform", "target": target, "callers": callers}]}))
        out = os.path.join(self.t, "report.json")
        r = tool("contracts.py", self.contracts, "--out", out)
        report = json.loads(Path(out).read_text()) if os.path.exists(out) else None
        return r, report

    def caller(self, **extra):
        return {"name": "Shop", "repo": self.shop.root, "bases": ["PLATFORM_URL"],
                "patterns": [r"https://api\.platform\.example"], **extra}

    def test_unserved_routes_and_methods_fail(self):
        self.write_shop()
        self.shop.write("shop/late.py", "import os\nhttpx.get(f\"{os.getenv('PLATFORM_URL')}/uncommitted\")\n")
        r, rep = self.run_check([self.caller()])
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        calls = {(c["method"], c["path"]): c for c in rep["contracts"][0]["callers"][0]["calls"]}
        self.assertEqual(calls[("POST", "/v1/items/{key}/hold")]["target"], "served")
        self.assertEqual(calls[("POST", "/v1/items/{quote(key, safe='')}/hold")]["target"], "served")  # quotes in a placeholder
        self.assertEqual(calls[("POST", "/v1/items/x/hold")]["sites"], ["ops/smoke.sh:2"])   # curl -X POST
        self.assertEqual(calls[("POST", "/v1/orders")]["target"], "missing")                   # url = ...; post(url)
        self.assertEqual(calls[("PUT", "/v1/items/{key}")]["target"], "method")                # served as GET only
        self.assertEqual(calls[("GET", "/health")]["target"], "served")                        # client with base_url
        self.assertEqual(calls[("GET", "/v1/items/${k}")]["target"], "served")                 # fetch, template literal
        self.assertEqual(calls[("GET", "/v2/status")]["target"], "missing")                    # a literal URL
        paths = {p for _, p in calls}
        self.assertNotIn("/not/the/platform", paths)   # another service's base
        self.assertNotIn("/v1/fake", paths)            # tests are skipped
        self.assertNotIn("/uncommitted", paths)        # only committed files are read
        self.assertIn("not served at", r.stdout)

    def test_all_served_passes(self):
        self.shop.write("shop/client.py", "import os, httpx\nB = os.environ['PLATFORM_URL']\nhttpx.post(f'{B}/v1/items/a/hold')\n")
        self.shop.commit()
        r, rep = self.run_check([{"name": "Shop", "repo": self.shop.root, "bases": ["PLATFORM_URL"]}])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("all contracts hold", r.stdout)

    def test_submodule_pin_is_checked_at_its_commit(self):
        self.shop.write("shop/client.py", "import os, httpx\nB = os.environ['PLATFORM_URL']\nhttpx.post(f'{B}/v1/items/a/hold')\n")
        sh(self.shop.root, "git", "add", "-A")
        sh(self.shop.root, "git", "update-index", "--add", "--cacheinfo", f"160000,{self.old},vendor/platform")
        sh(self.shop.root, "git", "commit", "-q", "-m", "pin the platform")
        r, rep = self.run_check([{"name": "Shop", "repo": self.shop.root, "bases": ["PLATFORM_URL"],
                                  "pin": {"path": "vendor/platform", "max_behind": 1}}])
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        caller = rep["contracts"][0]["callers"][0]
        self.assertEqual(caller["pin"]["kind"], "submodule")
        self.assertEqual(caller["pin"]["behind"], 2)
        self.assertEqual(caller["calls"][0]["target"], "served")
        self.assertEqual(caller["calls"][0]["pin"], "missing")   # the hold route came after the pin
        self.assertIn("2 commit(s) behind", r.stdout)
        self.assertIn("more than the 1 allowed", r.stdout)

    def test_vendored_copy_pin(self):
        self.shop.write("shop/client.py", "import os, httpx\nB = os.environ['PLATFORM_URL']\nhttpx.get(f'{B}/v1/items/a')\n")
        for f in ("api/main.py", "api/items.py"):
            self.shop.write("vendor/platform/" + f, sh(self.platform.root, "git", "show", f"{self.old}:{f}"))
        self.shop.write("vendor/platform/VENDORED", f"platform from the platform repository, commit {self.old[:7]}, vendored 2026-01-01\n")
        self.shop.write("vendor/platform/api/self_call.py", "httpx.get(f'{PLATFORM_URL}/its/own/route')\n")
        self.shop.commit()
        r, rep = self.run_check([{"name": "Shop", "repo": self.shop.root, "bases": ["PLATFORM_URL"],
                                  "pin": {"path": "vendor/platform"}}])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        caller = rep["contracts"][0]["callers"][0]
        self.assertEqual((caller["pin"]["kind"], caller["pin"]["behind"]), ("vendored", 2))
        self.assertEqual([(c["path"], c["pin"]) for c in caller["calls"]], [("/v1/items/a", "served")])  # the copy is not a caller

    def test_openapi_target(self):
        self.platform.write("openapi.json", json.dumps({"paths": {"/v1/items/{id}": {"get": {}}}}))
        self.platform.commit("schema")
        self.shop.write("shop/client.py", "import os, httpx\nB = os.environ['PLATFORM_URL']\nhttpx.get(f'{B}/v1/items/a')\n"
                        "httpx.post(f'{B}/v1/items/a')\n")
        self.shop.commit()
        r, rep = self.run_check([{"name": "Shop", "repo": self.shop.root, "bases": ["PLATFORM_URL"]}],
                                target={"repo": self.platform.root, "openapi": "openapi.json"})
        statuses = {c["method"]: c["target"] for c in rep["contracts"][0]["callers"][0]["calls"]}
        self.assertEqual(statuses, {"GET": "served", "POST": "method"})
        self.assertEqual(r.returncode, 1)

    def test_known_failures_are_reported_but_pass_until_fixed(self):
        self.shop.write("shop/client.py", "import os, httpx\nB = os.environ['PLATFORM_URL']\nhttpx.get(f'{B}/v1/gone')\n")
        self.shop.commit()
        caller = {"name": "Shop", "repo": self.shop.root, "bases": ["PLATFORM_URL"],
                  "known": [{"route": "GET /v1/gone", "why": "reported to the platform team"}]}
        r, rep = self.run_check([caller])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("✗ known GET", r.stdout)
        self.assertIn("1 known failure", r.stdout)
        self.assertEqual(tool("contracts.py", self.contracts, "--strict").returncode, 1)
        self.shop.write("shop/client.py", "import os, httpx\nB = os.environ['PLATFORM_URL']\nhttpx.get(f'{B}/health')\n")
        self.shop.commit("fixed")
        r, _ = self.run_check([caller])
        self.assertEqual(r.returncode, 1)
        self.assertIn("no longer fails", r.stdout)

    def test_repositories_are_left_untouched(self):
        self.write_shop()
        before = [sh(repo.root, "git", "status", "--porcelain", "--ignored") + sh(repo.root, "git", "for-each-ref")
                  for repo in (self.platform, self.shop)]
        self.run_check([self.caller()])
        after = [sh(repo.root, "git", "status", "--porcelain", "--ignored") + sh(repo.root, "git", "for-each-ref")
                 for repo in (self.platform, self.shop)]
        self.assertEqual(before, after)

    def test_repositories_read_through_the_drift_watch_mirrors(self):
        self.write_shop()
        _, direct = self.run_check([self.caller()])
        private = os.path.join(self.t, "private")
        os.makedirs(os.path.join(private, "acme-map"))
        gone = {"app:platform": os.path.join(self.t, "gone", "platform"), "app:shop": os.path.join(self.t, "gone", "shop")}
        mirrors = {key: os.path.join(private, "mirrors", key[4:] + ".git") for key in gone}
        for key, repo in (("app:platform", self.platform), ("app:shop", self.shop)):
            sh(self.t, "git", "clone", "-q", "--mirror", repo.root, mirrors[key])
        Path(private, "acme-map", "clones.json").write_text(json.dumps(gone))          # clones this machine lacks
        Path(private, "mirrors", "acme-map.clones.json").write_text(json.dumps(mirrors))
        Path(self.contracts).write_text(json.dumps({"contracts": [{"name": "Platform",
            "target": {"repo": gone["app:platform"], "folder": "api"}, "callers": [{**self.caller(), "repo": gone["app:shop"]}]}]}))
        self.assertEqual(tool("contracts.py", self.contracts).returncode, 2)
        out = os.path.join(self.t, "mirrored.json")
        r = tool("contracts.py", self.contracts, "--mirrors", private, "--out", out)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(mirrors["app:platform"], r.stdout)
        calls = lambda rep: rep["contracts"][0]["callers"][0]["calls"]
        self.assertEqual(calls(json.loads(Path(out).read_text())), calls(direct))   # the same checks as from the clones

    def test_a_caller_without_bases_is_a_bad_contract(self):
        self.write_shop()
        r, _ = self.run_check([{"name": "Shop", "repo": self.shop.root}])
        self.assertEqual(r.returncode, 2)
        self.assertIn("bases", r.stderr)


class Abbrev(unittest.TestCase):
    """validate.py: a box's optional badge (abbrev) is 1 to 3 characters, on a part or the skeleton."""

    def setUp(self):
        import shutil
        self.tmp = tempfile.TemporaryDirectory()
        self.m = os.path.join(self.tmp.name, "m")
        src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "maps", "saleor")
        shutil.copytree(src, self.m, ignore=shutil.ignore_patterns("dist", "topo-data.json"))

    def tearDown(self):
        self.tmp.cleanup()

    def set_abbrev(self, file, value):
        p = Path(self.m, file)
        d = json.loads(p.read_text())
        d["nodes"][0]["abbrev"] = value
        p.write_text(json.dumps(d))

    def test_good_and_bad(self):
        part = os.path.join("parts", sorted(os.listdir(os.path.join(self.m, "parts")))[0])
        self.set_abbrev(part, "PB")
        self.set_abbrev("skeleton.json", "P")
        r = tool("validate.py", self.m)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for file, bad in ((part, "ABCD"), ("skeleton.json", " P"), (part, 7)):
            self.set_abbrev(part, "PB")
            self.set_abbrev("skeleton.json", "P")
            self.set_abbrev(file, bad)
            r = tool("validate.py", self.m)
            self.assertNotEqual(r.returncode, 0, f"{file} {bad!r} passed")
            self.assertIn("abbrev must be 1 to 3 characters", r.stdout)

    def test_decisions(self):
        cfg = Path(self.m, "topo.config.json")
        base = json.loads(cfg.read_text())
        node = json.loads(Path(self.m, "skeleton.json").read_text())["nodes"][0]["id"]
        cfg.write_text(json.dumps({**base, "decisions": [{"title": "Keep one gateway", "node": node, "status": "agreed"}]}))
        r = tool("validate.py", self.m)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for bad in ([{"detail": "no title"}], [{"title": "Unknown box", "node": "nowhere.at.all"}], {"title": "not a list"}):
            cfg.write_text(json.dumps({**base, "decisions": bad}))
            r = tool("validate.py", self.m)
            self.assertNotEqual(r.returncode, 0, f"{bad!r} passed")
            self.assertIn("decisions", r.stdout)


if __name__ == "__main__":
    unittest.main()
