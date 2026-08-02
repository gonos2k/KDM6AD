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

    python harness/check_pr_landed.py 98 99 100      # exit 1 if any is stranded
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
        elif subprocess.run(("git", "merge-base", "--is-ancestor",
                             pr["headRefOid"], REF), capture_output=True).returncode == 0:
            print(f"PR #{n}: LANDED on {REF}  (base was {pr['baseRefName']})")
        else:
            stranded += 1
            print(f"PR #{n}: *** MERGED BUT NOT LANDED *** — merged into "
                  f"{pr['baseRefName']}, and {pr['headRefOid'][:12]} is not an "
                  f"ancestor of {REF}. Rebase onto {REF} and open a main-target PR.")
    return 1 if stranded else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
