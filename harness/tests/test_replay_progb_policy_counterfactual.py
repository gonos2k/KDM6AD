from __future__ import annotations

from pathlib import Path
import sys
import struct
import hashlib
import json
from collections import Counter
import copy

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from replay_progb_validity import parse_event_lines  # noqa: E402
from replay_progb_policy_counterfactual import (  # noqa: E402
    NATIVE_CAPTURE_GOLDENS,
    _replay_event_rows,
    validate_capture_integrity,
)
from test_replay_progb_validity import _native_shape_event_lines  # noqa: E402


def _events(policy):
    def f32(value):
        return struct.unpack(">f", struct.pack(">f", value))[0]

    lines = _native_shape_event_lines()
    # Both policy arms make the current ProgB outputs defined. A records current
    # assignment separately; its INOUT values come from the explicit loop seed.
    adjusted = []
    for line in lines:
        fields = line.split()
        if fields[0] == "S10PB" and policy == "midpoint":
            fields[9:13] = ["1", "1", "1", "1"]
            line = " ".join(fields)
        elif fields[0] == "S10CMG" and policy == "midpoint":
            fields[8] = "1"
            line = " ".join(fields)
        elif fields[0] == "S10SLP" and policy == "midpoint":
            fields[8:12] = ["1", "1", "1", "1"]
            line = " ".join(fields)
        elif fields[0] == "S10DIAG" and policy == "midpoint":
            fields[5] = "1"
            line = " ".join(fields)
        adjusted.append(line)
    lines = adjusted
    base = parse_event_lines(lines)
    shape_rows = []
    volume_rows = []
    active_map = {tuple(row["values"][:7]): row["values"][7]
                  for row in base if row["tag"] == "S10PB"}
    for key, active in active_map.items():
        step, lat, site, loop, substep, i, k = key
        qg = f32(2.0e-9 if active else 5.0e-10)
        if key == (1, 73, 1, 0, 0, 115, 39):
            qg = f32(0.0)
        rhox = f32(400.0 if qg > 0.0 else 0.0)
        brs = f32(qg / f32(400.0)) if qg > 0.0 else f32(0.0)
        shape = (step, lat, site, loop, substep, i, k, int(qg > 1.0e-9),
                 qg, brs, rhox, 100.0 if qg else 0.0, 200.0 if qg else 0.0,
                 1.0 if qg else 0.0, 0.5 if qg else 0.0, 0.3 if qg else 0.0,
                 2.0 if qg else 0.0, 1.0 if qg else 0.0, 3.0 if qg else 0.0)
        shape_rows.append("S10SHAPE " + " ".join(map(str, shape)))
        if active:
            action = 0
            before = f32(brs + 1.0e-12)
            after = f32(brs)
        elif policy == "retention":
            action = 3
            before = f32(brs)
            after = f32(brs)
        elif qg > 0.0:
            action = 1
            before = f32(0.0)
            after = f32(qg / f32(400.0))
            brs = after
            # Keep the shape row's after state aligned with the fallback.
            shape = shape[:9] + (brs,) + shape[10:]
            shape_rows[-1] = "S10SHAPE " + " ".join(map(str, shape))
        else:
            action = 2
            before = f32(1.0e-16)
            after = f32(0.0)
        delta = f32(after - before)
        vol = (step, lat, site, loop, substep, i, k, action,
               qg, before, after, delta, rhox)
        volume_rows.append("S10VOL " + " ".join(map(str, vol)))
    scan_calls = {tuple(row["values"][:5]) for row in base
                  if row["tag"] == "S10SCAN" and row["values"][1] == 2}
    for step, lat, site, loop, substep in scan_calls:
        qg = f32(5.0e-10)
        brs = f32(qg / f32(400.0)) if policy == "midpoint" else f32(0.0)
        shape = (step, lat, site, loop, substep, 142, 17, 0,
                 qg, brs, f32(400.0), f32(100.0), f32(200.0), f32(1.0), f32(0.5), f32(0.3),
                 f32(2.0), f32(1.0), f32(3.0))
        shape_rows.append("S10SHAPE " + " ".join(map(str, shape)))
        action, before, after = ((1, f32(0.0), brs) if policy == "midpoint"
                                 else (3, brs, brs))
        volume_rows.append("S10VOL " + " ".join(map(str, (
            step, lat, site, loop, substep, 142, 17, action,
            qg, before, after, f32(after-before), f32(400.0)))))
    return lines + shape_rows + volume_rows


def test_retention_arm_keeps_defined_seed_without_changing_inactive_brs():
    result = _replay_event_rows(_events("retention"), "retention")
    assert result["policy_approved"] is False
    assert result["volume_actions"]["3"] > 0
    assert result["rhox_positive_denominator_checks_passed"]


def test_midpoint_arm_checks_positive_trace_projection_and_zero_qg_cleanup():
    result = _replay_event_rows(_events("midpoint"), "midpoint")
    assert result["volume_actions"]["1"] > 0
    assert result["volume_actions"]["2"] == 1
    assert result["rhox_positive_denominator_checks_passed"]


def test_midpoint_arm_fails_closed_on_qg_positive_zero_rhox_read():
    lines = _events("retention")
    out = []
    for line in lines:
        fields = line.split()
        if (fields[0] == "S10SHAPE" and fields[1:8] ==
                ["1", "73", "1", "0", "0", "115", "12"]):
            fields[11] = "0.0"  # rhox in the defined shape row
            line = " ".join(fields)
        if (fields[0] == "S10VOL" and fields[1:8] ==
                ["1", "73", "1", "0", "0", "115", "12"]):
            fields[13] = "0.0"
            line = " ".join(fields)
        out.append(line)
    out.append("S10RHO 1 73 1 0 0 115 12 1418 0 1")
    with pytest.raises(ValueError, match="no positive density"):
        _replay_event_rows(out, "retention")


def test_midpoint_reached_divider_requires_current_call_rhox_assignment():
    lines = _events("midpoint")
    lines.append("S10RHO 1 73 1 0 0 115 12 2915 1 1")
    assert _replay_event_rows(lines, "midpoint")["rhox_positive_denominator_checks_passed"]
    lines[-1] = "S10RHO 1 73 1 0 0 115 12 2915 0 1"
    with pytest.raises(ValueError, match="without a current-call producer"):
        _replay_event_rows(lines, "midpoint")


def _integrity_fixture(monkeypatch):
    rho = [f"S10RHO 1 73 3 1 0 113 {k} 1418 0 1" for k in range(1, 213)]
    rows = rho + ["S10PB 1 73 1 0 0 113 1 0 1 0 0"]

    def payload(lines):
        return ("\n".join(lines) + "\n").encode()

    raw = payload(rows)
    counts = dict(sorted(Counter(line.split()[0] for line in rows).items()))
    keys = sorted(tuple(map(int, line.split()[1:9])) for line in rho)
    rho_keys = "\n".join(" ".join(map(str, key)) for key in keys).encode() + b"\n"
    golden = {
        "payload_sha256": hashlib.sha256(raw).hexdigest(),
        "event_count": len(rows),
        "tag_counts": counts,
        "rho_key_sha256": hashlib.sha256(rho_keys).hexdigest(),
        "rho_row_count": len(rho),
    }
    monkeypatch.setitem(NATIVE_CAPTURE_GOLDENS, ("mp37", "midpoint"), golden)

    def manifest_for(candidate):
        candidate_lines = candidate.decode().splitlines()
        event_rows = [line for line in candidate_lines
                      if line.split() and line.split()[0].startswith("S10")]
        candidate_payload = ("\n".join(event_rows) + "\n").encode()
        candidate_counts = dict(sorted(Counter(
            line.split()[0] for line in event_rows).items()))
        candidate_rho = [line for line in event_rows if line.split()[0] == "S10RHO"]
        candidate_keys = sorted(tuple(map(int, line.split()[1:9]))
                                for line in candidate_rho)
        candidate_key_bytes = "\n".join(
            " ".join(map(str, key)) for key in candidate_keys).encode() + b"\n"
        receipt = {
            "sha256": hashlib.sha256(candidate).hexdigest(),
            "event_payload_sha256": hashlib.sha256(candidate_payload).hexdigest(),
            "event_record_count": len(event_rows),
            "event_record_counts": candidate_counts,
            "rho_key_sha256": hashlib.sha256(candidate_key_bytes).hexdigest(),
            "rho_row_count": len(candidate_rho),
        }
        return {"arms": [{"scheme": "mp37", "policy": "midpoint",
                           "event_stream": receipt}]}

    return rows, raw, manifest_for


def test_code_pinned_capture_rejects_rho_deletion_even_after_manifest_rehash(monkeypatch):
    rows, raw, manifest_for = _integrity_fixture(monkeypatch)
    assert validate_capture_integrity(raw, manifest_for(raw), "mp37", "midpoint")

    # Mirror the native attack: remove 110/212 RHO records and update every
    # mutable digest and count in the manifest to match the reduced payload.
    removed = 0
    mutated = []
    for line in rows:
        if line.startswith("S10RHO ") and removed < 110:
            removed += 1
            continue
        mutated.append(line)
    changed = ("\n".join(mutated) + "\n").encode()
    with pytest.raises(ValueError, match="code-pinned"):
        validate_capture_integrity(changed, manifest_for(changed), "mp37", "midpoint")


def test_code_pinned_capture_rejects_valid_id_remap_even_after_manifest_rehash(monkeypatch):
    rows, raw, manifest_for = _integrity_fixture(monkeypatch)
    assert validate_capture_integrity(raw, manifest_for(raw), "mp37", "midpoint")

    # 3027 is a valid non-dividing consumer ID, so syntax/semantic-ID checks
    # alone cannot detect this same-count relocation/remap attack.
    changed_rows = []
    remapped = 0
    for line in rows:
        fields = line.split()
        if fields[0] == "S10RHO" and remapped < 110:
            fields[8] = "3027"
            remapped += 1
            line = " ".join(fields)
        changed_rows.append(line)
    changed = ("\n".join(changed_rows) + "\n").encode()
    with pytest.raises(ValueError, match="code-pinned"):
        validate_capture_integrity(changed, manifest_for(changed), "mp37", "midpoint")


def test_replay_package_rejects_mutable_history_manifest_forgery():
    from replay_progb_policy_counterfactual import validate_replay_package

    repo = Path(__file__).resolve().parents[2]
    manifest = json.loads(
        (repo / "harness/evidence/s10_policy_counterfactual_native_results_2026-09-25.json")
        .read_text())
    plan = json.loads(
        (repo / "harness/evidence/s10_policy_counterfactual_run_plan_2026-09-25.json")
        .read_text())
    validate_replay_package(manifest, plan, "mp37", "midpoint", verify_artifacts=False)

    forged_manifest = copy.deepcopy(manifest)
    forged_plan = copy.deepcopy(plan)
    arm_key = "mp37/midpoint"
    fake_sha = "0" * 64
    for receipt in (forged_manifest, forged_plan):
        receipt["replay_package"]["arms"][arm_key]["runs"]["capture"]["history_sha256"] = fake_sha
    forged_manifest["arms"] = copy.deepcopy(forged_manifest["arms"])
    arm = next(x for x in forged_manifest["arms"]
               if x["scheme"] == "mp37" and x["policy"] == "midpoint")
    arm["capture"]["history_sha256"] = fake_sha
    # Even a self-consistent recomputation of the manifest's mutable package
    # digest cannot override the code-pinned expected package SHA.
    for receipt in (forged_manifest, forged_plan):
        receipt["replay_package_sha256"] = hashlib.sha256(
            json.dumps(receipt["replay_package"], sort_keys=True,
                       separators=(",", ":")).encode()).hexdigest()
    with pytest.raises(ValueError, match="code-pinned four-arm run receipt"):
        validate_replay_package(forged_manifest, forged_plan, "mp37", "midpoint",
                                verify_artifacts=False)


def test_replay_package_rejects_forged_redundant_flat_run_list():
    from replay_progb_policy_counterfactual import validate_replay_package

    repo = Path(__file__).resolve().parents[2]
    manifest = json.loads(
        (repo / "harness/evidence/s10_policy_counterfactual_native_results_2026-09-25.json")
        .read_text())
    plan = json.loads(
        (repo / "harness/evidence/s10_policy_counterfactual_run_plan_2026-09-25.json")
        .read_text())
    forged = copy.deepcopy(manifest)
    for row in forged["runs"]:
        row["run_id"] = "forged-" + row["run_id"]
        row["history_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="flat run list differs"):
        validate_replay_package(forged, plan, "mp37", "midpoint", verify_artifacts=False)


def test_public_replay_package_accepts_all_four_compact_event_payloads():
    from replay_progb_policy_counterfactual import validate_replay_package

    repo = Path(__file__).resolve().parents[2]
    manifest = json.loads(
        (repo / "harness/evidence/s10_policy_counterfactual_native_results_2026-09-25.json")
        .read_text())
    plan = json.loads(
        (repo / "harness/evidence/s10_policy_counterfactual_run_plan_2026-09-25.json")
        .read_text())
    for arm in manifest["arms"]:
        scheme, policy = arm["scheme"], arm["policy"]
        package, payload = validate_replay_package(
            manifest, plan, scheme, policy, verify_artifacts=False)
        assert payload
        lines = validate_capture_integrity(payload, manifest, scheme, policy)
        assert len(lines) == arm["event_stream"]["event_payload_count"]
        assert package["arms"][f"{scheme}/{policy}"]["event_stream"][
            "event_payload_sha256"] == arm["event_stream"]["event_payload_sha256"]
