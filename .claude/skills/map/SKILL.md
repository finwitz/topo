---
name: map
description: Map one or more repositories into a Topo map, a zoomable page of the whole system checked against its code, with parallel agents, from a repository path or git URL to a validated page. Use when asked to map, chart, draw or visualize a repository or a set of them, add a repository to a map, or run system discovery.
---

# Map repositories into Topo

`<topo>` below is the folder Topo is installed in, the one that holds `pipeline/`. In Claude Code it is
`${CLAUDE_PLUGIN_ROOT}`. If that still reads as a placeholder rather than a folder (in Codex, a clone of
Topo or any other tool), `<topo>` is three folders above this file, which sits at
`<topo>/.claude/skills/<skill>/SKILL.md`. Every command below runs from any folder.

Read `<topo>/CLAUDE.md` first: its rules (read-only repositories, evidence, private material) apply to
every step. The slice format is `<topo>/pipeline/SCHEMA.md`; read it before writing the skeleton. The
detail behind each step is in `<topo>/MAPPING_PLAYBOOK.md`: open the section for a step only if this
file leaves you unsure, since everything you read here is paid for again on every later turn.

The input is one or more repositories: local clones or git URLs. If the user gave none, map the
repository they are working in (the current folder) when it is one, and otherwise ask which
repositories to map, and what to call the map when there are several. The map folder is
`~/topo-maps/<name>/` unless the user names another (`--out`); it stays outside the mapped
repositories. Work that names a client goes in the private folder instead (`<private>/<map>/`, where
`python3 -I <topo>/pipeline/settings.py` says `<private>` is), so that a shareable copy can be made
later with the `share` skill.

**Depth.** A map goes to one of three depths: `overview` (applications, subsystems, modules and files,
with only the entry points at function level), `standard` (down to the functions that carry the logic)
or `deep` (every public class, function and method), or one the user defined for their machine
(`python3 -I <topo>/pipeline/depths.py` lists them all with their floors). Use the depth the user asks
for, in any words ("just an overview", "as deep as it goes", `--depth deep`, "use my review depth"). When they name none, run
`python3 -I <topo>/pipeline/settings.py`: if its last line says the depth is "not chosen yet", this is
their first map on this machine, so ask them once, before step 1, which depth they want. Offer the ones it lists
(in Claude Code, as a question with options; elsewhere, in plain words), say what each maps and that
deeper costs more (figures below), and ask whether to make it their default. If they say yes, run
`python3 -I <topo>/pipeline/settings.py --set-depth <depth>`, so they aren't asked again; either way pass
`--depth <depth>` to `init.py`. When the depth was chosen before, leave `--depth` out: `init.py` uses
the saved one. When nobody can answer (a scheduled or unattended run), use standard and say so. If the
user wants something in between ("standard, but lighter"), offer to define a depth of their own under
`"depths"` in Topo's config file, as `python3 -I <topo>/pipeline/depths.py --help` describes; no depth can
turn off the precision checks.

Most of a map's tokens are agents re-reading their own context, so the size of each area moves the
total more than depth does. On werkzeug (about 180 code files and 600 public definitions) an overview
used about 26 million tokens with one agent, standard 70 million with three and deep 54 million with
seven; a small repository at standard used about 4.4 million. Tell the user these figures when they
ask what a depth costs.

1. **Start the map.** `python3 -I <topo>/pipeline/init.py <repo> [<repo> ...] [--name <name>] [--out <folder>] [--depth <depth>]`
   writes `topo.config.json`, `skeleton.json`, `clones.json`, a read-only `checkout/` from `git archive`
   at each repository's HEAD, and `ORIENT.md`. Tell the user if it warns about uncommitted changes:
   only committed work is mapped. Never map from a working tree.
2. **Orient.** Read `ORIENT.md`, then the docs it lists, the manifests and deploy files, the entry points,
   and the outside services they name: enough to draw the subsystems and split the work, no more. Don't
   read the source files one by one: the mapping agents read every file they own, so reading them here
   pays for the same reading twice. A file listing and the first lines of a module are enough to place
   it. List every HTTP server's routes (skip this for code that serves none):
   `python3 -I <topo>/pipeline/routes.py <map>/checkout <server folder> --out <map>/routes-<service>.json`.
3. **Skeleton and config.** In `skeleton.json`, rewrite each `app:` summary from what you read, add 3 to 8
   level-1 subsystems (`kind: "group"`) under each application, and every outside service as an `x:` node
   under `ext` sub-groups (data, providers, hosting, people). In `topo.config.json`, add `owners`, a list
   of `["<path prefix>", "<group id>"]` pairs with specific prefixes first; an `endpoint_fallback` entry
   for every service with routes, `{"<service>": ["<box id>", ...]}` (leave it `{}` when there are none);
   and `area_names`, `{"<area>": "<display name>"}`. Mechanical parts (a generated client, a manifest of
   plugins) can come from a short script instead of an agent.
4. **Size the work.** `ORIENT.md` gives the depth and suggests how many mapping agents it needs: at
   standard, about one per 100 to 300 boxes; at deep, one per area of about 100 public definitions; an
   overview needs fewer. Use that many areas, not more: each area adds to what the depth check asks of
   the whole map, and to the cost. A small repository is one area and one agent. Before launching more
   than four agents, tell
   the user the plan (areas, agent count, about 15 to 35 minutes while they run in parallel) and wait for
   a yes, since each agent uses a full context of work.
5. **Split and brief.** Write `<map>/areas.json` (`python3 -I <topo>/pipeline/brief.py --help` prints the
   full format). For one repository at the checkout's root and one area:

   ```json
   {"map": "<map>", "checkout": "<map>/checkout", "out": "<map>/briefs", "slices": "<map>/slices",
    "routes": {"api": "<map>/routes-api.json"},
    "areas": {"core": {"app": "", "service": "api", "parents": ["<subsystem ids>"], "prefixes": ["core"],
                       "budget": 150, "own": ["src/", "README.md"], "start": "the docs to read first",
                       "must": ["what the agent has to cover"], "flows": ["2 or 3 paths worth narrating"]}}}
   ```

   With several repositories, `"app"` is the repository's folder in the checkout (its `prefix`, such as
   `"api/"`) and every `own` path starts with it. Set each `budget` to at least the area's public
   definitions plus its modules and groups. Run `python3 -I <topo>/pipeline/brief.py <map>/areas.json`.
   Fix every OWNED TWICE; give real code an owner. If it says MORE AREAS THAN SUGGESTED, merge areas,
   or tell the user why the extra areas are worth their cost before you launch them. Each brief lists the public definitions its agent has
   to box when the map can hold them all.
6. **Map in parallel.** One agent per area, all started at once (in Claude Code, Agent calls in one
   message; in Codex, its sub-agents), each told only to read its brief and follow it. The briefs give
   the schema and the validator as real paths. Keep agents off the browser and out of the repositories.
   If your tool can't run agents, map the areas yourself one after another, each from its brief alone.
   In Claude Code, launch mapping agents with `model: "sonnet"` unless the user asks for another model:
   in testing it mapped as deep as a larger model at lower cost, and the depth check in the next step sends an agent
   back when it falls short. Verifying findings (step 9) stays on your own model.
7. **Merge and check.** `python3 -I <topo>/pipeline/finish.py <map> --merge` copies the slices into
   `<map>/parts/` and runs every check in one step: it validates the slices together against the
   checkout, lists references with no exact box, builds the page, checks cited lines against their
   symbols (at least 98%; explain the rest), checks how deep the map goes (public definitions with
   boxes, symbol boxes per area, each citing its line and connected, code excerpts) and writes `ANALYSIS.md` and `BUILDOUT.md`. When the depth check
   fails, send the agent of each listed file's area back with the list, rather than drawing those boxes
   yourself from memory. Fix what it
   reports in the copies in `parts/`: make inferred boxes for routes no server declares, retarget group
   references, move flow steps to real boxes, add missing outside services. Run
   `python3 -I <topo>/pipeline/finish.py <map>` again until nothing is left to fix.
8. **Featured flows.** Pick 2 to 5: with several areas, write ones that cross them in `<map>/flows.json`,
   every sentence checked against the boxes; with one area, feature the agent's best flows. List them as
   `"feature": [["<flow id>", "short label"], ...]` in `flows.json`, and run `finish.py <map>` once more.
   **Features (optional).** When the user wants the Features view (what the product does, and its gaps
   against a roadmap, PRD or feature list they give you), run
   `python3 -I <topo>/pipeline/features.py brief <map> [--reference <their list>] --out <map>/features-brief.md`
   and give the brief to one agent (Sonnet in Claude Code) to write `<map>/features.json`; then run
   `finish.py <map>` once more. Keep the user's list in the map folder, never in the Topo repository.
9. **Verify findings.** Agents report defects and doc-versus-code mismatches in their replies. Re-read
   each one in the code (or have an agent do it and reply with the result) with a verdict, severity,
   evidence and the smallest fix, then write them to `<map>/FINDINGS.md` yourself: subagents reply, they
   don't write that file. Never file or fix them in the mapped repositories from here.
10. **Hand over.** If Playwright is installed (see `<topo>/README.md`), run
    `NODE_PATH=${NODE_PATH:-$HOME/.topo-tools/node_modules} node <topo>/test/smoke.cjs <map>/dist/index.html <map>/smoke`
    and look at the screenshots; fix what it reports before you hand over. If the browser can't start
    (a sandbox that blocks it, as Codex's does), say so in the hand-over and give the user that command
    to run; don't call the page tested. Open the page for the user
    (`open` on macOS, `xdg-open` on Linux, `explorer.exe` from WSL) and tell them where it is, its depth,
    what the map covers, the confirmed findings, and that `ANALYSIS.md` and `BUILDOUT.md` sit next to it.
    The page is one HTML file: it can be hosted anywhere static.
11. **Sharing a private map.** To publish an anonymized copy of a client's map, use the `share` skill.
    A map of the user's own repositories needs no copy.
