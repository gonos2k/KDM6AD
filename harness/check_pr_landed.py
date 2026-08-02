#!/usr/bin/env python3
"""Did a merged PR actually reach main?

Owner review §1. GitHub reports `MERGED` for a PR merged into ANY base, so a PR
opened against a feature branch shows the same green state as one that landed on
main. PR #100 merged into `harness/g33-consumer-local-activity`; PR #91 had the
same shape earlier. Both read as done.

The state to trust is ancestry:

    git merge-base --is-ancestor <PR head sha> origin/main

A stacked PR is a reasonable thing to open — it keeps a review focused on one
change. What is not reasonable is leaving it stacked once its base lands, because
at that point the parent branch stops moving and the child's commits are stranded.

Ancestry alone is not enough, though: rebasing rewrites SHAs, so a PR whose content
reached main via a rebased branch fails the ancestor test while being perfectly
landed. PR #100 is exactly that — merged into a feature branch, rebased, then landed
inside #101. `git cherry` answers the real question by patch-id, so the check
distinguishes CONTENT LANDED from genuinely STRANDED and only fails on the latter.

    python harness/check_pr_landed.py 98 99 100      # exit 1 only if truly stranded
"""
import json
import subprocess
import sys

REF = "origin/main"


def main(argv) -> int:
    if not argv:
        print(__doc__)
        return 2
    stranded = 0
    for n in (a for a in argv if a.isdigit()):
        raw = subprocess.run(
            ("gh", "pr", "view", n, "--json", "number,state,baseRefName,headRefOid"),
            capture_output=True, text=True).stdout.strip()
        if not raw:
            print(f"PR #{n}: could not read PR")
            stranded += 1
            continue
        pr = json.loads(raw)
        # A CLOSED-but-not-merged PR is not stranded, it was abandoned. Only MERGED
        # carries the false assurance this exists to catch.
        if pr["state"] != "MERGED":
            print(f"PR #{n}: {pr['state']} (not merged; nothing to check)")
            continue
        head = pr["headRefOid"]
        if subprocess.run(("git", "merge-base", "--is-ancestor", head, REF),
                          capture_output=True).returncode == 0:
            print(f"PR #{n}: LANDED on {REF}  (base was {pr['baseRefName']})")
            continue
        # Not an ancestor. Either the content is in main under different SHAs
        # (rebase), or it really is stranded. `git cherry` decides, by patch-id.
        subprocess.run(("git", "fetch", "-q", "origin",
                        f"refs/pull/{n}/head:refs/tmp/pr{n}"), capture_output=True)
        cherry = subprocess.run(("git", "cherry", REF, f"refs/tmp/pr{n}"),
                                capture_output=True, text=True).stdout.split()
        absent = [c for c in cherry if c == "+"]
        if cherry and not absent:
            print(f"PR #{n}: CONTENT LANDED on {REF} under rewritten SHAs "
                  f"(merged into {pr['baseRefName']}, then rebased)")
        else:
            stranded += 1
            print(f"PR #{n}: *** MERGED BUT NOT LANDED *** — merged into "
                  f"{pr['baseRefName']}, {head[:12]} is not an ancestor of {REF}, "
                  f"and {len(absent) or 'all'} of its commits are absent by "
                  f"patch-id. Rebase onto {REF} and open a main-target PR.")
    return 1 if stranded else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
