"""Fail a pull request that changes what Topo does without updating README.md.

usage: python3 -I .github/scripts/readme_check.py BASE_SHA    (the pull request's description in $PR_BODY)

A change under one of WATCHED needs README.md changed in the same pull request, or a line in the pull
request's description that starts "README: no change" and says why, for example
"README: no change, a refactor with the same commands and output".
"""
import os
import re
import subprocess
import sys

WATCHED = (
    "pipeline/", "viewer/", "hooks/", ".claude/skills/", ".claude-plugin/", ".codex-plugin/", ".agents/",
    "MAPPING_PLAYBOOK.md",
)
WAIVER = re.compile(r"^[ \t>*_-]*README:\s*no change\b(.*)", re.I | re.M)


def verdict(changed, body):
    """(ok, message) for a pull request that changes these files and has this description."""
    watched = sorted(f for f in changed if f.startswith(WATCHED))
    if not watched:
        return True, "readme: nothing here changes what Topo does"
    if "README.md" in changed:
        return True, "readme: README.md is updated with the change"
    for m in WAIVER.finditer(body or ""):
        reason = re.sub(r"^(needed\b)?[\W_]*", "", m.group(1).strip(), flags=re.I).strip()
        if len(re.sub(r"\W", "", reason)) >= 3:
            return True, f"readme: README.md unchanged, because: {reason}"
    listed = "\n".join(f"  {f}" for f in watched[:20]) + ("\n  ..." if len(watched) > 20 else "")
    return False, (
        "readme: this pull request changes what Topo does but not README.md:\n" + listed + "\n"
        "Update README.md in this pull request, or add a line to its description that starts\n"
        '"README: no change" and says why, for example "README: no change, tests only".'
    )


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    out = subprocess.run(["git", "diff", "--name-only", f"{sys.argv[1]}...HEAD"],
                         capture_output=True, text=True, check=True).stdout
    ok, message = verdict(set(out.split()), os.environ.get("PR_BODY", ""))
    print(message)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
