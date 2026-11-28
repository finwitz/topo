<h1>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="brand/logo/svg/topo-logo-dark.svg">
    <img alt="Topo" src="brand/logo/svg/topo-logo-light.svg" width="600">
  </picture>
</h1>

A zoomable map of a software system, read from its code. Topo shows a set of applications from the
whole system down to single functions, with every connection between them, and checks every claim on
the map against the code it cites.

![Topo in 16 seconds: from the whole system down to one function, the code it cites, what calls what, and the one command that starts a map](docs/topo-16s.gif)

The full tour, 48 seconds with sound:

https://github.com/user-attachments/assets/f2e601e3-e675-4e6e-b285-9ace4b36fec0

**What it costs.** Topo is free and open source. A map runs on your own Claude Code or Codex plan: about
4 US dollars for a small repository, and for werkzeug (about 180 code files) from 13 as an overview to
36 at full depth.

Codebases grow until nobody can draw the whole system, and the documents drift from what the code
does. Topo is a way to get the real picture back: agents read the code in parallel and write
structured claims with evidence, scripts check every claim they can, and a person decides what is
shared.

## See an example

**Open the example in your browser** from the website link under *About* on this repository's page
(GitHub Pages hosts it), or clone the repository and open `maps/saleor/dist/index.html`: Saleor, the
open-source commerce platform (its API, its Dashboard and four of its apps), mapped from source in
about 30 minutes by eleven agents. 2,120 boxes, 2,763 connections and four guided flows that cross all
three applications, with every one of its 835 function-level boxes citing a line that matches. Its
analysis is in [`maps/saleor/ANALYSIS.md`](maps/saleor/ANALYSIS.md).

The same website link opens the **gallery**: FastAPI, the MCP Python SDK and Hono, each mapped with
Topo at standard depth for 26 to 36 US dollars, with their sources in [`gallery/`](gallery/).

![The Saleor example map at its top level: three applications, the outside services they use, and the connections between them](docs/saleor-overview.jpg)

## Map your own repository

You need git, Python 3.10 or later (the standard library only) and a coding agent:
[Claude Code](https://docs.claude.com/en/docs/claude-code/overview) or Codex as a plugin, or any agent
that can read files and run commands (see [Other agents](#other-agents)), on macOS or Linux. On Windows, run
it inside [WSL](https://learn.microsoft.com/windows/wsl/install): the mapping scripts use only Python
and git, but the checks and the leak-guard hook are shell scripts, and Windows itself is untested.
Topo installs as a Claude Code plugin. Clone this repository once, then add it as a plugin
marketplace and install the plugin from it:

```bash
git clone <this repository's URL> topo
```

```bash
claude plugin marketplace add ./topo
```

```bash
claude plugin install topo@topo
```

Then, in any project, start Claude Code and map the code you're in:

```
/topo:map
```

or name a local path or a git URL: `/topo:map ~/code/your-app`. Several repositories that make up one
system go on one map, side by side: `/topo:map ~/code/api ~/code/web ~/code/worker`. To update the
plugin later, `git -C topo pull`, then `claude plugin marketplace update topo` and
`claude plugin update topo@topo`.

**How deep.** Choose how far down a map goes, in plain words or with `--depth`:

| Depth | What it maps | For |
|---|---|---|
| `overview` | applications, subsystems, modules and files; only the entry points at function level | a first look, a large codebase, a quick share |
| `standard` (default) | down to the functions and classes that carry the logic | most maps |
| `deep` | every public class, function and method | the code you own and work in every day |

`/topo:map --depth deep`, or "map this, just an overview". The first time you map without naming a
depth, Topo asks which you want and whether to keep it as your default; change it later with
`python3 -I topo/pipeline/settings.py --set-depth deep` (it lives in `~/.config/topo/config.json`).
Anything in between is a depth of your own, defined once in that file from one of the three:

```json
{"depths": {"review": {"based_on": "standard", "symbols": 0.4, "excerpts": 6,
                       "about": "the main functions only, for a quick review"}}}
```

Then "map this at review depth", or make it your default. `python3 -I topo/pipeline/depths.py` lists the
depths your machine knows with their floors, and its `--help` names every field. A map keeps its depth in
its own config, so its floors travel with it. Whatever the depth, every box cites real lines, and the
depth check holds the map to that depth's floors before you get it: no depth can turn the precision
checks off.

The `map` skill runs the whole method:

1. `pipeline/init.py` takes a snapshot of each repository's last commit, sets up the map folder at
   `~/topo-maps/<name>/` and writes an orientation: languages, the largest folders, manifests, entry
   points and how many mapping agents the code needs.
2. Claude reads the docs and entry points, draws the top levels (applications, subsystems and outside
   services) and splits the code into areas.
3. One mapping agent per area reads its code and writes its slice of the map, citing files and lines.
4. Scripts check every citation against the snapshot, merge the slices, write guided flows and an
   analysis, and Claude opens the finished page for you.

The map is one HTML file, `~/topo-maps/<name>/dist/index.html`. Open it locally, send it, or host it
anywhere static. `ANALYSIS.md` (coupling, the most depended-on parts, duplication, unfinished work) and
`BUILDOUT.md` (a draft plan) sit next to it.

**How long, and how much.** At standard depth, a small repository (up to about a hundred code files) is
one agent and takes 15 to 30 minutes. Larger code gets one agent per area of about 100 to 300 boxes, all running in
parallel, so the time stays about the same while usage grows: the Saleor example took eleven agents.
Each agent works through a full context of reading, so the skill tells you the plan and waits for your
yes before it launches more than four. In Claude Code the mapping agents run on Sonnet, which in our tests
mapped as deep as Opus for less, since the depth check holds every map to the same floors; ask for
another model when you start the map if you want one. A small repository cost about 4 US dollars this
way, against about 6 with Opus throughout. Depth and size move the cost most: werkzeug (about 180 code
files and 600 public definitions) cost about 31 US dollars at standard depth, split into eight areas,
with 346 function-level boxes; an overview of it cost about 13, with 199 boxes, split into six areas
where one would have done; deep cost about 36 and took 47 minutes, with 830 boxes and every one of its
623 public definitions boxed.

**What it touches.** Your repositories are read only: Topo maps committed files from `git archive`, so
uncommitted work never reaches the map and nothing in your clone changes. Topo runs no service of its
own; the agents read your code through Claude Code, and the map stays on your machine.

**Keeping it current.** `/topo:refresh` lists the boxes whose cited lines changed since the mapped
commit and re-runs only the agents for those areas.

Not using Claude Code? The method is plain: [`MAPPING_PLAYBOOK.md`](MAPPING_PLAYBOOK.md) describes it
for any agent that can read files and run commands, and the skills in `.claude/skills/` are the same
steps.

### Other agents

**Codex.** The same clone is a Codex plugin marketplace too:

```bash
codex plugin marketplace add ./topo
```

```bash
codex plugin add topo@topo
```

Then ask Codex to map the code you're in with Topo's map skill. Codex's sandbox can't start the
browser that the smoke test uses, so it ends by giving you that command to run yourself.

**Any other agent** that can read files and run shell commands (Gemini CLI, Cursor, opencode and
others): tell it to read `topo/.claude/skills/map/SKILL.md` and follow it. The skills say where Topo's
tools are relative to themselves, and every step is a Python command. These agents are untested.

The model doesn't change what a map has to pass. The checks that end every map, on whichever model
draws it, are the same: every citation exists in the snapshot, cited lines match their symbols, the
code's public definitions have boxes, and the page renders. A run that misses them is sent back, not
handed over. Each finding an agent reports is checked again in the code before it reaches you.

### Ask a map while you code

The plugin also starts Topo's map server (Model Context Protocol, MCP), so the agent you code with can
ask a finished map about the code in front of it, in Claude Code and in Codex alike:

- `topo_owner`: which box owns this file and line, and where it sits in the system
- `topo_box`: what a box is and does, its files and lines, what it calls and what calls it
- `topo_connections`: what depends on this and what it depends on, up to four hops (the impact of a change)
- `topo_find`, `topo_flow`, `topo_analysis`: search, walk a guided flow, read the analysis

Ask in plain words ("what depends on the function I'm changing?") and the agent picks the tools. The
server reads the maps in `~/topo-maps/` (and the folders listed in `$TOPO_MAPS`), never changes them,
and says when a clone has moved on since its map was made. It needs only Python. Any other MCP client
(Cursor, Gemini CLI and others) starts it with this in its MCP settings:

```json
{"mcpServers": {"topo": {"command": "python3", "args": ["-I", "/path/to/topo/pipeline/mcp_server.py"]}}}
```

## What the map does

- **Semantic zoom.** As many levels as the code has: from the whole ecosystem through applications,
  subsystems and modules down to classes and their methods (a deep map of werkzeug has eight). The level
  rail names each level on the path you're on. A box opens into its children once it is big enough on
  screen; at the deepest level a card shows what the code does, how it works and a verbatim excerpt.
- **Connections that roll up.** Calls, network requests, reads and writes, triggers and tests are
  drawn between whatever boxes are visible, bundled and counted as you zoom out.
- **Evidence.** Every box cites the files and lines it came from, linked into the code at the mapped
  commit when the repository is on GitHub, GitLab or Bitbucket. Boxes known only from documents are drawn dashed, inferred ones
  dotted.
- **Details.** Click a box for how it works, its files, what it uses and what uses it.
- **Guided flows.** Narrated walkthroughs that fly the camera along a real path through the system,
  step by step, with replay.
- **Features (optional).** What the product does for its users, as a tree of areas and features, each
  one citing the boxes that build it and marked built, partial or documents only. Give it a roadmap,
  a PRD or a competitor's feature list and it scores the list against the code: matched, not found
  (with the terms searched for, run again by a script), or to check by hand. One agent writes it from
  the finished map, for a few dollars (`pipeline/features.py`); click a feature to light it up on the map.
- **Insights.** The strongest coupling between subsystems, the most depended-on parts, unfinished work
  with the most dependents, and build status by subsystem.
- **Stack, search, boundaries and export.** Every outside service and technology, search with `/`,
  what the map covers and where its risk is, and PNG export of any view.
- **One file.** Each map is a single HTML page: d3 comes from cdnjs and fonts from Google Fonts,
  everything else is inline. Light and dark themes and a phone layout.

## How a map is made

[`MAPPING_PLAYBOOK.md`](MAPPING_PLAYBOOK.md) is the method, and the Claude Code skills in
`.claude/skills/` run it the same way every time:

1. **Check out** every repository from `git archive` at the commit you map, so uncommitted work never
   reaches the map and the clones are never touched (`pipeline/init.py` for a new map,
   `pipeline/checkout.py` after that).
2. **Draw the skeleton**: one box per application, its subsystems and the outside services.
3. **Split the code into areas** and write one brief per mapping agent (`pipeline/brief.py`), which
   catches files owned twice.
4. **Map in parallel**: one agent per area writes a slice of the map in the format
   [`pipeline/SCHEMA.md`](pipeline/SCHEMA.md) defines, and validates it against the code
   (`pipeline/validate.py --repo`).
5. **Merge and check**: `finish.py` copies the slices into the map and runs every check in one step:
   `validate.py` on the slices together, `refs.py` (references with no exact box), `build.py` (the
   page), `symcheck.py`, which checks that every symbol cites the line where it is defined, and
   `depthcheck.py`, which checks that the code's public definitions have boxes. Their floors are what
   keep a map's depth and precision the same whichever model draws it.
6. **Analyze**: `analyze.py` writes the connections between applications, coupling, the most
   depended-on parts, duplication, unfinished work and a draft build-out plan.

To keep a map current, `drift.py` lists the boxes whose cited lines changed since the mapped commit,
grouped by area, so only those agents run again. `contracts.py` checks every route a caller uses
against the routes its target serves.

**Maps of code you can't publish.** A map of a client's systems keeps its named sources in a private
folder outside this repository, set per machine with `$TOPO_PRIVATE` or `~/.config/topo/config.json`
(`~/.topo/private` by default; `python3 -I pipeline/settings.py` prints it). `anonymize.py` applies a private file of name rules and fails on any
name it misses, `generalize.py` turns business figures into qualitative statements through a reviewed
overlay, and `leakscan.py` blocks private files and names from every commit (install the hook with
`sh hooks/install.sh`). The `share` skill (`/topo:share`) runs the three in order.

## Build and check

```
python3 -I pipeline/validate.py maps/saleor
python3 -I pipeline/build.py maps/saleor
python3 -I pipeline/analyze.py maps/saleor
sh test/run.sh
```

`test/run.sh` runs the unit tests, the leak scan, a rebuild of the example map that must match what is
committed, and the browser smoke test. The smoke test needs Node and Playwright, installed once outside
the repository: `npm install --prefix ~/.topo-tools playwright` and
`~/.topo-tools/node_modules/.bin/playwright install chromium-headless-shell`, or point `NODE_PATH` at
another install. Without it the smoke test is skipped.

## Layout

```
MAPPING_PLAYBOOK.md          how to map a set of codebases with parallel agents
viewer/topo.template.html    the viewer; map data is injected at build time
viewer/shell.html            the shell every Topo page shares: theme, top bar and view switch
pipeline/SCHEMA.md           the slice format mapping agents write
pipeline/*.py                init, checkout, routes, brief, validate, build, refs, symcheck, depthcheck, finish,
                             analyze, stack_report, drift, contracts, skim, anonymize, generalize, leakscan,
                             settings, depths (depths.json: overview, standard, deep), mcp_server (the map
                             server for coding agents)
hooks/                       the leak guard as a pre-commit hook
test/                        unit tests, the browser smoke test and run.sh
maps/saleor/                 the example map: config, skeleton, slices, flows, page and analysis
.claude/skills/              map, refresh and share: the skills, for Claude Code, Codex or any agent
.claude-plugin/              the Claude Code plugin, and this repository as its own plugin marketplace
.codex-plugin/, .agents/     the same plugin, its map server and marketplace for Codex
```

## Contributing

Issues and pull requests are welcome; [`CONTRIBUTING.md`](CONTRIBUTING.md) says how to run the checks
and what a change needs. Report security problems privately, as [`SECURITY.md`](SECURITY.md) describes.

## License

Apache License 2.0; see `LICENSE` and `NOTICE`. The example map describes Saleor's BSD-licensed repositories
(saleor/saleor, saleor/saleor-dashboard and saleor/apps); Saleor is a trademark of its owners.
