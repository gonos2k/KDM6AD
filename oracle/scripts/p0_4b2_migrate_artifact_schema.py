#!/usr/bin/env python3
"""P0-4b.2 review fix — deterministic artifact schema migration (no re-run).

Owner review on PR #16: a per-column kg/m2 value summed over 65,988 columns is
a SUM OF COLUMN WATER-EQUIVALENTS, not a per-area domain mass — the previous
`*_domain_sum_kg_m2` names invited misreading. This migration renames those
keys, renames `code_sha` to `producer_code_sha` (the commit that GENERATED the
artifact, as opposed to later review-hardening commits on the same branch),
and stamps a migration block carrying the original artifact's sha256 so the
numeric lineage stays verifiable. Every numeric value is byte-identical.

Idempotent: artifacts already migrated (or produced by the post-migration
scripts) are left unchanged.
"""
import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
REPORTS = ROOT / "docs" / "reports"

REPLAY_FRAME_RENAMES = {
    "sink_domain_sum_kg_m2": "sink_sum_of_column_equivalents_kg_m2",
}
REPLAY_CUM_RENAMES = {
    "cum_1h_domain_sum_kg_m2": "cum_1h_sum_of_column_equivalents_kg_m2",
    "all_37_frame_replay_domain_sum_kg_m2":
        "all_37_frame_replay_sum_of_column_equivalents_kg_m2",
}
UNITS_NOTE = ("every *_sum field aggregates per-column kg/m2 water-equivalents "
              "over the column set (65,988 columns unless stated) — a SUM OF "
              "COLUMN EQUIVALENTS, not a per-area domain mass; a true domain "
              "mass in kg would require per-cell areas (WRF map factors)")


def _sha256_file(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def _rename(d, renames):
    changed = False
    for old, new in renames.items():
        if old in d:
            d[new] = d.pop(old)
            changed = True
    return changed


def _migration_block(original_sha):
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    return {
        "original_artifact_sha256": original_sha,
        "migration_script_sha256": _sha256_file(__file__),
        "migration_head_sha": head,
        "note": ("deterministic key/label migration (PR #16 review): numeric "
                 "values byte-identical to the original artifact"),
    }


def migrate_replay(path):
    original_sha = _sha256_file(path)
    art = json.loads(path.read_text())
    changed = False
    for fr in art.get("frames", []):
        changed |= _rename(fr, REPLAY_FRAME_RENAMES)
    cum = art.get("cumulative_replay", {})
    changed |= _rename(cum, REPLAY_CUM_RENAMES)
    c3 = cum.get("cumulative_3h", {})
    if "domain_sum_kg_m2" in c3:
        c3["sum_of_column_equivalents_kg_m2"] = c3.pop("domain_sum_kg_m2")
        changed = True
    ep = cum.get("endpoint_frame36", {})
    changed |= _rename(ep, REPLAY_FRAME_RENAMES)
    prov = art.get("provenance", {})
    if "code_sha" in prov:
        prov["producer_code_sha"] = prov.pop("code_sha")
        changed = True
    if "units_note" not in art:
        art["units_note"] = UNITS_NOTE
        changed = True
    if changed:
        art["migration"] = _migration_block(original_sha)
        path.write_text(json.dumps(art, indent=1))
    return changed


def migrate_impact(path):
    original_sha = _sha256_file(path)
    art = json.loads(path.read_text())
    prov = art.get("provenance", {})
    changed = False
    if "code_sha" in prov:
        prov["producer_code_sha"] = prov.pop("code_sha")
        changed = True
    if changed:
        art["migration"] = _migration_block(original_sha)
        path.write_text(json.dumps(art, indent=1))
    return changed


def main():
    r = REPORTS / "p0_4b1_lc05_replay_audit.json"
    i = REPORTS / "p0_4b1_impact_comparison.json"
    print(f"replay:  {'migrated' if migrate_replay(r) else 'already current'}  {r}")
    print(f"impact:  {'migrated' if migrate_impact(i) else 'already current'}  {i}")


if __name__ == "__main__":
    sys.exit(main())
