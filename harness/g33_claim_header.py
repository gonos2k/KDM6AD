#!/usr/bin/env python3
"""Stamp each finding with the registry's verdict on the claims it carries.

Owner §10. Declaring "CLAIMS.yaml is the authority" does not stop a reader
copying a table out of a finding whose surrounding prose was written before the
claim was withdrawn — `FINDING_column_water_orders_v1` carried
"turnover is roundoff — confirmed" in a grade table for two commits after the
registry had withdrawn exactly that.

So the verdict is written INTO each finding, mechanically, as a block the tool
owns:

    <!-- claim-status: generated from CLAIMS.yaml, do not edit -->
    | claim | status |
    |---|---|
    | G33-TURNOVER-001 | withdrawn -> G33-TURNOVER-002 |
    <!-- /claim-status -->

    python g33_claim_header.py           # rewrite every finding's block
    python g33_claim_header.py --check   # exit 1 if any block is stale

`--check` is what the test runs, so a claim whose status changes without the
findings being restamped fails rather than drifting.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

EVIDENCE = Path(__file__).resolve().parent / "evidence"
REGISTRY = EVIDENCE / "CLAIMS.yaml"
OPEN, CLOSE = ("<!-- claim-status: generated from CLAIMS.yaml, do not edit -->",
               "<!-- /claim-status -->")
BLOCK = re.compile(re.escape(OPEN) + r".*?" + re.escape(CLOSE), re.S)


def claims() -> list[dict]:
    """[{id, status, superseded_by?, evidence[]}] — the same flat shape the
    registry test parses, kept minimal on purpose."""
    out, cur, pending = [], None, None
    for line in REGISTRY.read_text().splitlines():
        if re.match(r"^  - id: ", line):
            cur = {"id": line.split("id:", 1)[1].strip(), "evidence": []}
            out.append(cur)
            pending = None
        elif cur is not None and (m := re.match(r"^    (\w+): (.*)$", line)):
            key, val = m.group(1), m.group(2).strip()
            pending = None
            if key == "evidence":
                cur["evidence"] = re.findall(r"[\w.]+\.md", val)
            elif val in (">", "|"):
                # Folded values were DROPPED here, which is why the header could
                # not show `scope` -- the claims whose scope needs the most words
                # are exactly the ones that fold.
                cur[key], pending = "", key
            else:
                cur[key] = val
        elif cur is not None and re.match(r"^      \S", line):
            if pending:
                cur[pending] = (cur[pending] + " " + line.strip()).strip()
            else:
                cur["evidence"] += re.findall(r"[\w.]+\.md", line)
    return out


def block_for(doc: str, cs: list[dict]) -> str:
    rows = [c for c in cs if doc in c["evidence"]]
    if not rows:
        return ""
    # grade and scope too (owner §7.5): `active` alone read identically for
    # `confirmed`, `conditional` and `strong-candidate`, and a fixture-scoped
    # result quoted as a general one is the recurring defect the registry exists
    # for -- so the scope travels with the status instead of living one file away.
    lines = [OPEN, "", "| claim | status | grade | scope |", "|---|---|---|---|"]
    for c in sorted(rows, key=lambda c: c["id"]):
        st = c.get("status", "?")
        if c.get("superseded_by"):
            st += f" → {c['superseded_by']}"
        scope = " ".join(c.get("scope", "—").split()).replace("|", "\\|")
        lines += [f"| `{c['id']}` | **{st}** | {c.get('grade', '—')} | {scope} |"]
    lines += ["",
              "Statuses above are the authority; prose below may predate them.",
              CLOSE]
    return "\n".join(lines)


def stamp(check: bool = False) -> int:
    cs, stale = claims(), []
    for doc in sorted({d for c in cs for d in c["evidence"]}):
        path = EVIDENCE / doc
        if not path.exists():
            continue
        want, text = block_for(doc, cs), path.read_text()
        if BLOCK.search(text):
            new = BLOCK.sub(lambda _: want, text, count=1)
        else:
            # after the H1 title, so the verdict is the first thing under it
            head, _, rest = text.partition("\n")
            new = f"{head}\n\n{want}\n{rest}"
        if new != text:
            stale.append(doc)
            if not check:
                path.write_text(new)
    if check and stale:
        print("stale claim-status blocks (run g33_claim_header.py):")
        for d in stale:
            print(f"  {d}")
        return 1
    if not check:
        print(f"  stamped {len(stale)} finding(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(stamp(check="--check" in sys.argv[1:]))
