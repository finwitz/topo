#!/bin/sh
# Every Topo check in one command: unit tests, the leak scan, a rebuild of the example map that must
# match what is committed, and the browser smoke test.
# usage: sh test/run.sh   (from anywhere in the clone)
#
# Needs Python 3.10+ and, for the smoke test, Node with Playwright, installed once outside the repo:
#   npm install --prefix ~/.topo-tools playwright
#   ~/.topo-tools/node_modules/.bin/playwright install chromium-headless-shell
# (or point NODE_PATH at another node_modules that has it).
set -u
cd "$(dirname "$0")/.." || exit 1
LOGS=$(mktemp -d)
fail=0
step() { printf '\n== %s\n' "$1"; }
run() { "$@" || { echo "FAILED: $*"; fail=1; }; }

step "unit tests"
run python3 -I -m unittest discover -s test -p 'test_*.py'

step "leak scan"
run python3 -I pipeline/leakscan.py

for map in maps/*/; do
  map=${map%/}
  step "$map rebuilds exactly as committed"
  run python3 -I pipeline/validate.py "$map"
  run python3 -I pipeline/build.py "$map"
  run python3 -I pipeline/analyze.py "$map"
  if [ -n "$(git status --porcelain -- "$map")" ]; then
    echo "FAILED: the rebuild changed $map (the sources changed and need a commit, or the build is no"
    echo "longer deterministic):"
    git status --short -- "$map"
    fail=1
  fi
done

step "the gallery rebuilds exactly as committed"
run python3 -I gallery/build.py
if [ -n "$(git status --porcelain -- gallery)" ]; then
  echo "FAILED: the rebuild changed gallery/ (its sources changed and need a commit, or the build is no"
  echo "longer deterministic):"
  git status --short -- gallery
  fail=1
fi

step "browser smoke test"
export NODE_PATH="${NODE_PATH:-$HOME/.topo-tools/node_modules}"
if node -e "require('playwright')" 2>/dev/null; then
  for page in maps/*/dist/index.html gallery/*/dist/index.html; do
    node test/smoke.cjs "$page" "$LOGS/$(basename "$(dirname "$(dirname "$page")")")"
    rc=$?
    if [ "$rc" -eq 77 ] && [ -z "${CI:-}" ]; then
      echo "smoke test skipped for $page (browser could not start in this environment)"
    elif [ "$rc" -ne 0 ]; then
      echo "FAILED: node test/smoke.cjs $page"
      fail=1
    fi
  done
else
  echo "no Playwright at $NODE_PATH: smoke test skipped (see the comment at the top of this file)"
fi

printf '\n'
if [ "$fail" -ne 0 ]; then echo "SOME CHECKS FAILED (logs and screenshots in $LOGS)"; exit 1; fi
echo "all checks passed (screenshots in $LOGS)"
