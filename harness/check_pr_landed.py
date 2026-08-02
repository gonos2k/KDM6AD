#!/usr/bin/env python3
"""Did a merged PR actually reach main?

Owner review §1. GitHub reports `MERGED` for a PR merged into ANY base, so a PR
opened against a feature branch shows the same green state as one that landed on
main. PR #100 merged into `harness/g33-consumer-local-activity`; PR #91 had the
same shape earlier. Both read as done.

The state to trust is ancestry:

    git merge-base --is-ancestor <PR head sha> origin/main

A stacked PR is a reasonable thing to open -- it keeps a review focused on one
change. What is not reasonable is leaving it stacked once its base lands, because
at that point the parent branch stops moving and the child's commits are stranded
on a branch nothing merges again.

Exit 0 only if every PR checked is an ancestor of main.
"""
from __future__ import annotations

import json
import subprocess
import sys


def _run(*a) -> str:
    return subprocess.run(a, capture_output=True, text=True).stdout.strip()


def landed(sha: str, ref: str = "origin/main") -> bool:
    return subprocess.run(("git", "merge-base", "--is-ancestor", sha, ref),
                          capture_output=True).returncode == 0


def check(numbers, ref: str = "origin/main") -> list:
    out = []
    for n in numbers:
        raw = _run("gh", "pr", "view", str(n), "--json",
                   "number,state,baseRefName,headRefOid,title")
        if not raw:
            out.append({"pr": n, "error": "could not read PR"})
            continue
        d = json.loads(raw)
        out.append({
            "pr": d["number"], "state": d["state"], "base": d["baseRefName"],
            "head": d["headRefOid"], "title": d["title"],
            # A CLOSED-but-not-merged PR is not stranded, it was abandoned; only
            # MERGED carries the false assurance this exists to catch.
            "landed": landed(d["headRefOid"], ref) if d["state"] == "MERGED" else None,
        })
    return out


def main(argv) -> int:
    if not argv:
        print(__doc__)
        return 2
    ref = "origin/main"
    nums = [int(a) for a in argv if a.isdigit()]
    rows = check(nums, ref)
    bad = 0
    for r in rows:
        if "error" in r:
            print(f"PR #{r['pr']}: {r['error']}")
            bad += 1
            continue
        if r["state"] != "MERGED":
            print(f"PR #{r['pr']}: {r['state']} (not merged; nothing to check)")
            continue
        if r["landed"]:
            print(f"PR #{r['pr']}: LANDED on {ref}  (base was {r['base']})")
        else:
            bad += 1
            print(f"PR #{r['pr']}: *** MERGED BUT NOT LANDED *** "
                  f"-- merged into {r['base']}, and {r['head'][:12]} is not an "
                  f"ancestor of {ref}. Rebase onto {ref} and open a "
                  f"{ref.split('/')[-1]}-target PR.")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
