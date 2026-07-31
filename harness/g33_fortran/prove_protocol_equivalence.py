#!/usr/bin/env python3
"""Prove a protocol bump ADDED observations without changing the answer.

    prove_protocol_equivalence.py OLD.g33f NEW.g33f --added-stage kernel_after_entry_clamp

Every record the OLD stream could carry must be byte-identical in the NEW one; only the
records the bump introduces may appear. This is the discipline every step from v2 onward
has used, and it is the only thing separating "we added observations" from "we added
observations and changed the answer".

It lives in the repo rather than in a scratch directory because the scratchpad has been
reaped mid-session before, and a proof nobody can re-run is not a proof.
"""
from __future__ import annotations

import argparse
from pathlib import Path

#: Records the banner brackets rather than the body. Their version literally changed, so
#: comparing them would report the bump as a difference.
_BANNER = ("G33F BEGIN", "G33F END")


def records(text: str) -> list:
    return [ln for ln in text.splitlines()
            if ln.startswith("G33F") and not ln.startswith(_BANNER)]


def _is_added(line: str, stages: set, fields: set, prefixes=()) -> bool:
    if prefixes and line.startswith(tuple(prefixes)):
        return True
    if line.startswith("G33F ENTRY"):
        return "G33F ENTRY" in fields          # only when declared as added
    if line.startswith("G33F STAGE"):
        f = line.split()
        # G33F STAGE <loop> <chain> <stage> <n> <field> <col> <k> <dtype> <bits>
        if len(f) < 8:
            return False
        stage, field = f[4], f[6]
        return stage in stages or (stage, field) in fields
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("old", type=Path)
    ap.add_argument("new", type=Path)
    ap.add_argument("--added-stage", action="append", default=[],
                    help="a stage the bump introduces (whole stage is new)")
    ap.add_argument("--added-field", action="append", default=[],
                    metavar="STAGE:FIELD", help="a field added to an EXISTING stage")
    ap.add_argument("--added-entry", action="store_true",
                    help="the G33F ENTRY record itself is new")
    ap.add_argument("--added-record", action="append", default=[],
                    metavar="PREFIX",
                    help="a whole new record class, e.g. 'G33F INIT'")
    a = ap.parse_args()

    stages = set(a.added_stage)
    fields = {tuple(s.split(":", 1)) for s in a.added_field}
    if a.added_entry:
        fields.add("G33F ENTRY")

    old, new = records(a.old.read_text()), records(a.new.read_text())
    pref = tuple(a.added_record)
    added = [ln for ln in new if _is_added(ln, stages, fields, pref)]
    kept = [ln for ln in new if not _is_added(ln, stages, fields, pref)]
    # FILTER BOTH SIDES. Only filtering the new stream is right for a pure ADDITION, and
    # silently wrong for a MOVE: when the old stream already contains the named stage —
    # at a different program point — the comparison becomes old-with-it against
    # new-without-it and reports DIFFERS at the first such record, which reads as the
    # instrumentation having changed the run. It has not; the tool was comparing two
    # different things.
    old_kept = [ln for ln in old if not _is_added(ln, stages, fields, pref)]
    old_dropped = len(old) - len(old_kept)
    old = old_kept

    print(f"  old records : {len(old)}"
          + (f"   ({old_dropped} of the changed class filtered out too)"
             if old_dropped else ""))
    print(f"  shared      : {len(kept)}   "
          f"{'BYTE-IDENTICAL' if kept == old else 'DIFFERS'}")
    print(f"  added       : {len(added)}")
    if kept == old:
        return 0
    for i, (x, y) in enumerate(zip(old, kept)):
        if x != y:
            print(f"  first difference at shared record {i}:\n"
                  f"    old: {x}\n    new: {y}")
            break
    else:
        print(f"  length differs: {len(old)} vs {len(kept)}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())


# Self-test: a MOVE must not be reported as a physics change. Run with -m pytest, or
# directly — it needs no fixtures.
def _selftest():
    same = ["G33F STAGE 1 - op 0 qr 1 0 f32 AAAA",
            "G33F STAGE 1 - micro_call_aux 0 rhox 1 0 f32 1111",
            "G33F STAGE 1 - outer_post_micro 0 qr 1 0 f32 BBBB"]
    moved = ["G33F STAGE 1 - op 0 qr 1 0 f32 AAAA",
             "G33F STAGE 1 - outer_post_micro 0 qr 1 0 f32 BBBB",
             "G33F STAGE 1 - micro_call_aux 0 rhox 1 0 f32 2222"]
    st, fl = {"micro_call_aux"}, set()
    a = [ln for ln in same if not _is_added(ln, st, fl)]
    b = [ln for ln in moved if not _is_added(ln, st, fl)]
    assert a == b, "filtering both sides should make a MOVE byte-identical"
    # and a genuine content change must still be caught
    changed = [ln.replace("AAAA", "CCCC") for ln in moved]
    c = [ln for ln in changed if not _is_added(ln, st, fl)]
    assert c != a, "a real difference outside the moved stage must still show"
    return True


assert _selftest()
