# Map slice schema

A Topo map is a zoomable map of one or more codebases. Zoomed out you see whole applications;
zooming in reveals subsystems, then modules and files, then the key functions, classes,
endpoints and code inside them. Connections are drawn between whatever boxes are visible
at the current zoom, so a connection declared between two functions automatically rolls up
to their files, subsystems and applications as you zoom out.

The map is assembled from **slices**: one JSON file per area of the code, usually written by
one mapping agent each (see `../MAPPING_PLAYBOOK.md`). This file is the contract every slice
follows. `validate.py` enforces it and `build.py` merges the slices.

---

## Map folder

```
maps/<name>/
  topo.config.json   title, region layout and colors, repos, fallbacks, featured flows
  skeleton.json       predefined top levels: applications, subsystems, external services
  parts/<area>.json   one or more slices per area (<area>.1.json, <area>.2.json, ...)
  flows.json          optional guided flows that cross areas, plus the featured list
  dist/index.html     the built page (output of build.py)
```

```
python3 -I pipeline/validate.py maps/<name> --repo /path/to/checkout   # agents run this
python3 -I pipeline/build.py maps/<name>                                # merge + build page
```

`topo.config.json` may list `decisions`, which the viewer's Boundaries rail shows under the map's own
facts: `[{"title", "detail"?, "node"?, "status"?}]`, where `node` is a box id the row flies to. They
are committed with the map, so the leak scan checks them: keep the wording generic, never a person's
name, and leave the list out of an example map unless it is clearly leak-safe.

## Slice file

```json
{ "area": "<area>", "nodes": [ <Node>, ... ], "edges": [ <Edge>, ... ], "flows": [ <Flow>, ... ] }
```

## Node

```json
{
  "id": "f:src/engine/workflow.py",
  "parent": "core.orchestration",
  "name": "Workflow engine",
  "kind": "module",
  "summary": "Loads a workflow definition, orders its phases by dependency and runs each step.",
  "detail": "How it works, 2 to 6 sentences: inputs, mechanism, outputs, decisions, fallbacks.",
  "paths": ["src/engine/workflow.py"],
  "status": "live",
  "tech": ["Python"],
  "facts": ["Phases marked parallel still run one after another"],
  "signature": "def run(self, inputs: dict) -> RunResult",
  "code": "verbatim excerpt, at most 15 lines",
  "source": "code"
}
```

| field | required | rules |
|---|---|---|
| `id` | yes | unique; see **Ids** |
| `parent` | yes | a node from the same slice or from `skeleton.json`; never another slice's node |
| `name` | yes | at most 48 characters. A role name for modules ("Workflow engine", not "workflow.py"; the viewer shows the file name under it). Symbols: `Workflow.run()`. Endpoints: `POST /v1/items/{key}/publish`. |
| `kind` | yes | `group` `service` `module` `component` `function` `class` `endpoint` `data` `config` `doc` `agent` `workflow` `job` `test` `external` (`app` is reserved for the skeleton) |
| `summary` | yes | one plain sentence, at most 200 characters |
| `detail` | groups, services, modules, key symbols | at most 1,200 characters on **how it works**. This is what a reader gets when they zoom in, so explain the mechanism rather than restating the name. |
| `paths` | anything file-backed | paths relative to the checkout, optionally with a line or range (`src/a.py:120`, `src/a.py:120-168`). The first one is the primary location and becomes a link when the config gives a repo URL. |
| `status` | only with evidence | `live` · `built` (code and tests, not live) · `partial` · `stub` · `planned` · `archived` · `unknown` |
| `tech` | optional | short tags: `Python`, `FastAPI`, `React`, `SQL`... They feed the viewer's Stack panel. |
| `facts` | optional | at most 5 specific, checkable bullets (numbers, limits, defaults, environment variables) |
| `signature` | optional | for function, class and endpoint nodes |
| `code` | optional | the 10 to 15 most important functions per area only; a verbatim excerpt of at most 15 lines |
| `source` | optional | `code` (default) · `docs` (known only from documents; drawn with a dashed outline) · `inferred` (dotted; say why in `detail`) |
| `phase` | optional | for actions in an engagement: the process step it belongs to, one of the `process` ids in `topo.config.json` |
| `date` | optional | when the action happened: `2026-08-15`, or `2026-08` when only the month is known |
| `capabilities` | optional | tags from the map's `capabilities` vocabulary in `topo.config.json`; `analyze.py` compares them across engagements to find gaps and shared work |
| `repo_key` | optional | on a group: the `repos` key its files belong to, when one region holds several repositories |
| `eyebrow` | optional | on a top-level skeleton node: the small label above its name (default: Application, or Outside world for groups) |
| `tag` | optional | the short label above a card's title, in place of its kind (for example a feature's phase, or how many engagements have a capability) |
| `abbrev` | optional | 1 to 3 characters for the badge on the box's card (default: the first letters of up to two words of its name) |
| `url`, `url_label` | optional | an outside link the detail panel offers (https only), such as the pull request a change landed in, with its label (`Pull request #74`) |

## Edge

```json
{ "from": "f:src/engine/workflow.py#Workflow.run",
  "to": "f:src/engine/agents.py#AgentCaller.call",
  "kind": "calls", "label": "routes each agent step",
  "detail": "optional", "evidence": "src/engine/workflow.py:212" }
```

| field | rules |
|---|---|
| `from`, `to` | node ids. Point at the most specific node that exists; the viewer rolls connections up as you zoom out. |
| `kind` | `calls` · `http` (any network call, including Model Context Protocol (MCP) calls) · `reads` · `writes` · `generates` (offline artifact) · `triggers` (cron, continuous integration, hooks, chaining) · `deploys` · `configures` · `tests` · `documents` |
| `label` | at most 60 characters, active voice |
| `evidence` | `path:line` where the connection is visible; required |
| `status` | optional, only `idea`: a connection someone proposed and nobody has accepted, with `evidence` pointing at the proposal. The viewer draws it dashed and faint, behind its own legend filter (off by default), never bundles it with real connections and leaves it out of every count. |
| `url` | optional `https://` link for the connection, such as the document that proposes an idea |

Aim for one to two edges per node: calls between modules, reads and writes of data, network
calls, links to other areas by their predictable ids, and links to external services.

## Flow

```json
{ "id": "flow.core.run", "name": "A workflow run, step by step", "summary": "one sentence",
  "steps": [ { "node": "<id>", "text": "1 to 3 sentences of narration" } ] }
```

`flows.json` may also hold `"feature": [["<flow id>", "short label"], ...]`: those flows are
listed first and offered on the start-up card.

## Features

`features.json` (optional, in the map folder) is the tree the viewer's Features view draws: what
the product does for its users, each feature citing the boxes that build it, and the gaps against a
reference list. It is written after the map, from the map, by one agent with
`pipeline/features.py brief`, and checked with `features.py check` (which `finish.py` runs).

```json
{ "features": [
    { "id": "feat.checkout", "name": "Checkout", "summary": "one sentence" },
    { "id": "feat.checkout.gift-cards", "parent": "feat.checkout", "name": "Gift cards",
      "summary": "one sentence", "entry": ["<box id>"], "boxes": ["<box id>"], "flows": ["<flow id>"] } ],
  "reference": { "name": "Roadmap", "items": [
    { "text": "Gift cards", "state": "matched", "feature": "feat.checkout.gift-cards" },
    { "text": "Saved carts", "state": "not found", "searched": ["saved cart", "persist checkout"] },
    { "text": "Marketplace", "state": "out of scope" } ] } }
```

- Three levels at most (area > feature > sub-feature); ids `feat.<area>[.<feature>[.<part>]]`.
- A feature with no sub-features cites at least one box: `entry` (where a user reaches it) and
  `boxes` (the rest that builds it). `flows` names guided flows that walk through it.
- Status is never written: the build works it out from the boxes (`built`, `partial` when a box or
  anything inside it is partial, a stub or planned, `docs` when every box is known only from
  documents).
- A reference item is `matched` (naming its feature), `not found` (listing the terms searched for)
  or `out of scope` (set only by the product's owner). The check runs a not-found item's terms over
  the checkout and the map and writes any hits into its `found`; such an item shows as "check by
  hand". Nothing is ever called missing.
- The check fails when fewer than 80% of the map's endpoints or 90% of its flows belong to a
  feature.

## Ids

Ids make references between slices resolvable without coordination. Follow them exactly.

| family | form | example |
|---|---|---|
| file | `f:<path>` | `f:src/engine/workflow.py` |
| folder (one node for a whole folder) | `d:<path>` | `d:web/public/icons` |
| symbol in a file | `f:<path>#<Symbol>` | `f:src/engine/workflow.py#Workflow.run` |
| HTTP endpoint | `ep:<service> <METHOD> <path>` | `ep:api POST /v1/items/{key}/publish` |
| MCP tool | `mcp:<server> <tool>` | `mcp:search search_docs` |
| agent of an agent platform | `<app>:agent/<name>` | `plat:agent/code-reviewer` |
| your groups | `<area prefix>.<slug>` | `core.orchestration.routing` |
| external service | `x:<slug>`, only those in `skeleton.json` | `x:bigquery` |

Endpoint service names are declared in `topo.config.json` (`endpoint_fallback` keys). Use the
path exactly as the route declares it, prefix included.

Each file belongs to exactly one area. Create `f:` nodes only for files you own; to connect to
another area's file, reference its predictable id. When that exact node doesn't exist, the build
falls back to the file, the folder or the owning group (`owners` in the config) and reports it.

## Depth and size

Levels: application → subsystem (skeleton) → your groups → files and modules → key symbols
and endpoints. Group by responsibility; 3 to 12 children per box reads best. Fold trivial files
into a parent's `paths`. Go to symbol level for the files that carry the core logic.

## Writing rules

- Read the code; never invent. Mark document-only knowledge `"source": "docs"` and your own
  reading `"source": "inferred"`.
- Spell out every domain acronym on first use in each `summary` and `detail`.
- Plain, specific language: numbers with units, environment variables, defaults and fallbacks.
- Never copy secrets, tokens or keys, even when a file contains them.
