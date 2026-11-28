# Working on Topo

The mapping method is `MAPPING_PLAYBOOK.md` and the slice format is `pipeline/SCHEMA.md`. Run the
pipeline with `python3 -I`. Use the skills in `.claude/skills/` for each phase (`map`, `refresh`,
`share`; `/topo:map` and so on when Topo is installed as a plugin); they keep runs the same, and they
work from any folder.

A new map starts with `pipeline/init.py`, and its folder lives outside this repository
(`~/topo-maps/<name>/` by default). `maps/` holds only the committed example; never put a user's map
there. `gallery/` holds published maps of open-source projects, rebuilt by `gallery/build.py`;
never a user's or a client's map.

## Repositories you map

- Read only. Map from a snapshot (`git archive <commit>`, as `pipeline/checkout.py` does), never from
  a working tree with uncommitted changes, and never commit, branch or install anything in them.
- Report defects and committed secrets to the owner. Don't fix them in place from here.

## Private material

- Nothing that names a client or quotes its figures enters this repository. Named sources, name rules
  and the figures overlay live in a private folder outside it, set per machine (`$TOPO_PRIVATE` or
  `~/.config/topo/config.json`, else `~/.topo/private`; `python3 -I pipeline/settings.py` prints it).
- Never commit rules files, `generalized.json`, worklists or `topo-data.json`. The leak guard
  (`pipeline/leakscan.py`, installed by `sh hooks/install.sh`) backs this up.
- Change the private sources, then regenerate `maps/` with the `share` skill. Never hand-edit a
  shared map.

## Evidence

- Every box cites files. Knowledge from documents only is marked `"source": "docs"`.
- Verify every finding a mapping agent reports in the code before it goes anywhere.

## README

- A pull request that changes what Topo does (`pipeline/`, `viewer/`, `hooks/`, the skills, the plugin
  or `MAPPING_PLAYBOOK.md`) updates `README.md` in the same pull request, or its description has a line
  that starts `README: no change` and says why. The `readme` check fails otherwise.
- Before merging any pull request, a contributor's included, read the README against the change: the
  commands, what the map does, the layout and the costs it states. Fix what it misses first.

## Checks

`sh test/run.sh` runs the unit tests, the leak scan, a rebuild of the example map that must match
what is committed, and the browser smoke test.
