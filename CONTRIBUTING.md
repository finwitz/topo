# Contributing to Topo

Thanks for helping. Bug reports, maps that came out wrong, and pull requests are all welcome.

## Reporting a problem

Open an issue with what you ran, what you expected and what happened. For a map that came out wrong,
say which box or connection, and which file and line it should have cited. Never paste private code,
names or figures into an issue; describe the shape of the problem instead. Security problems go
through [`SECURITY.md`](SECURITY.md), not an issue.

## Making a change

1. Run every check before you open a pull request:

   ```bash
   sh test/run.sh
   ```

   It runs the unit tests, the leak scan, a rebuild of the example map that must match what is
   committed, and the browser smoke test (skipped without Playwright; `README.md` says how to install
   it). Continuous integration runs the same script on every pull request.

2. Keep to how the code is built:
   - **Python 3.10 or later, standard library only.** No packages to install is part of what makes
     Topo easy to run. Run scripts with `python3 -I` from the repository root.
   - **The build is deterministic.** The same sources must give the same page byte for byte, which
     is how `test/run.sh` catches unintended changes. A change to the viewer or the build that changes
     the example map's page needs the rebuilt `maps/saleor/` committed with it.
   - **Never hand-edit `maps/`.** The example map is regenerated from its sources.
   - **The viewer is one file.** `viewer/topo.template.html` holds the viewer's markup, style and
     script; outside it, a page loads only d3 from cdnjs and fonts from Google Fonts.
   - **Tests for tools.** A new or changed script under `pipeline/` comes with a test in `test/` that
     runs it on a throwaway git repository, like the ones already there.
3. Write plainly: specific words, numbers with units, acronyms spelled out on first use, no em
   dashes. That holds for code comments, docs and the text a map shows.
4. Keep `README.md` true. A change to the pipeline, the viewer, the hooks, the skills or the plugin
   updates the README in the same pull request. If the README needs nothing, add a line to the pull
   request's description that starts `README: no change` and says why, for example
   `README: no change, tests only`. The `readme` check fails until one of the two is there.
5. One change per pull request, with a commit message that says what it does in the area it touches,
   for example `Viewer: keep the selected box when the theme changes`.

## The leak guard

Topo can make anonymized copies of private maps, and `pipeline/leakscan.py` keeps private files and
names out of commits. With no private rules on your machine it still blocks rules files, worklists,
overlays and merged map data, and skips the name check. Maintainers who keep private maps install the
hook once per clone with `sh hooks/install.sh`.

## License

By contributing you agree that your contribution is licensed under the Apache License 2.0, the
license in `LICENSE`.
