import copy
import hashlib
import json
from pathlib import Path

import pytest

from harness.replay_s2_number_trace import TraceError, parse_capture, replay


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence/native_s2_number_trace_2026-09-25.json"
CAPTURE = ROOT / "evidence/native_s2_number_trace_2026-09-25.txt"


@pytest.fixture(scope="module")
def bundle():
    return json.loads(EVIDENCE.read_text()), CAPTURE.read_text()


def test_retained_mp37_number_trace_replays_and_keeps_basis_open(bundle):
    evidence, text = bundle
    result = replay(evidence, text)

    assert result["capture_records"] == 1257
    assert result["physical_number_basis_resolved"] is False
    assert result["host_kernel_boundary"] == {
        "steps": 2, "host_entry_layers": 78, "host_return_layers": 78}
    assert result["rain_applied_transport"]["mstep_values"] == [1]
    assert result["rain_applied_transport"]["nonzero_departures"] == 4
    assert result["rain_applied_transport"]["first_nonzero_departure"] == [
        2, 13, 19.540470123291016]
    assert result["measured_rain_number_sources"]["positive_source_or_sink_counts"] == {
        "snow_melt": 5, "graupel_melt": 1, "rain_freeze_sink": 1}
    focus = result["focus_path"]
    assert focus["step1_snow_melt_number_increment"] == pytest.approx(
        238.7642059326172, rel=0, abs=0)
    assert focus["step2_face_k14_to_k13"]["number_departure"] == pytest.approx(
        35.04592514038086, rel=0, abs=0)
    assert focus["step2_face_k14_to_k13"]["number_arrival"] == pytest.approx(
        38.00294876098633, rel=0, abs=0)
    assert focus["step2_face_k13_to_k12"]["number_departure"] == pytest.approx(
        19.540470123291016, rel=0, abs=0)
    assert focus["step2_face_k13_to_k12"]["number_arrival"] == pytest.approx(
        21.470430374145508, rel=0, abs=0)
    assert result["focus_path"]["step1_snow_melt_number_increment"] == pytest.approx(
        238.7642059326172, rel=0, abs=0)
    face = result["focus_path"]["step2_face_k14_to_k13"]
    assert face["number_departure"] == pytest.approx(35.04592514038086, rel=0, abs=0)
    assert face["number_arrival"] == pytest.approx(38.00294876098633, rel=0, abs=0)
    measures = result["conditional_column_measures"][1]["number_measures"]
    assert measures["dz_volume"]["interface_mismatch"] == pytest.approx(
        0.002348708254430676, rel=0, abs=1e-15)
    assert measures["rho_m_operator"]["interface_mismatch"] == pytest.approx(
        2043.6810873946965, rel=0, abs=1e-9)
    assert measures["rho_d_conditional"]["interface_mismatch"] == pytest.approx(
        1988.2700102827903, rel=0, abs=1e-9)
    assert len(result["conditional_threshold_maps"]) == 2
    assert all(x["basis_choice"].startswith("conditional diagnostic only")
               for x in result["conditional_threshold_maps"])
    assert result["conditional_threshold_maps"][1][
        "nrmin_volume_threshold_if_host_is_dry_kg"] == pytest.approx(
            0.008314188203507553, rel=0, abs=1e-15)


def _flip_first_face_departure(text: str, evidence: dict) -> str:
    schema = evidence["capture_source"]["tags"]["NR_FACE_PRE"]
    order = schema["value_order"]
    offset = 8 + len(schema["flags"])
    index = next(i for i, x in enumerate(order) if x["expr"] == "dnr(i,k)")
    lines = text.splitlines()
    row = next(i for i, x in enumerate(lines) if x.startswith("S2NR NR_FACE_PRE "))
    parts = lines[row].split()
    old = int(parts[offset + index], 16)
    parts[offset + index] = f"{old ^ 1:08X}"
    lines[row] = " ".join(parts)
    return "\n".join(lines) + "\n"


def _delete_events(text: str, predicate) -> str:
    return "".join(line for line in text.splitlines(keepends=True)
                   if not predicate(line.split()))


def _with_updated_capture_hash(evidence: dict, changed: str) -> dict:
    altered = copy.deepcopy(evidence)
    altered["capture_sha256"] = hashlib.sha256(changed.encode()).hexdigest()
    return altered


def test_applied_transfer_bit_mutation_is_rejected(bundle):
    evidence, text = bundle
    changed = _flip_first_face_departure(text, evidence)
    altered = copy.deepcopy(evidence)
    altered["capture_sha256"] = hashlib.sha256(changed.encode()).hexdigest()

    with pytest.raises(TraceError, match="applied number cap|applied state"):
        replay(altered, changed)


def test_missing_or_failing_noninterference_frame_is_rejected(bundle):
    evidence, text = bundle
    altered = copy.deepcopy(evidence)
    altered["noninterference"]["frames"][1]["bitwise_match"] = 252

    with pytest.raises(TraceError, match="noninterference frame"):
        replay(altered, text)


def test_basis_approval_cannot_be_inferred_from_a_small_residual(bundle):
    evidence, text = bundle
    altered = copy.deepcopy(evidence)
    altered["physical_number_basis_resolved"] = True

    with pytest.raises(TraceError, match="unresolved physical number basis"):
        replay(altered, text)


def test_changed_canonical_source_or_retained_input_identity_is_rejected(bundle):
    evidence, text = bundle
    bad_source = copy.deepcopy(evidence)
    bad_source["source"]["canonical_source_sha256"] = "0" * 64
    with pytest.raises(TraceError, match="canonical mp37 source SHA256"):
        replay(bad_source, text)

    bad_input = copy.deepcopy(evidence)
    bad_input["input_identity"]["wrfinput_sha256"] = "0" * 64
    with pytest.raises(TraceError, match="retained input SHA256"):
        replay(bad_input, text)


@pytest.mark.parametrize("removed_levels", [(14,), tuple(range(1, 7))])
def test_missing_one_or_low_level_transport_face_is_rejected(bundle, removed_levels):
    evidence, text = bundle
    removed = set(removed_levels)
    changed = _delete_events(
        text,
        lambda parts: (len(parts) > 7 and parts[0] == "S2NR"
                       and parts[1] in {"NR_FACE_PRE", "NR_FACE_POST"}
                       and int(parts[2]) in (1, 2) and int(parts[7]) in removed))
    altered = _with_updated_capture_hash(evidence, changed)

    with pytest.raises(TraceError, match="capture record census"):
        replay(altered, changed)


def test_missing_rain_number_source_event_is_rejected(bundle):
    evidence, text = bundle
    changed = _delete_events(
        text,
        lambda parts: (len(parts) > 7 and parts[0] == "S2NR"
                       and parts[1] in {"NR_SNOW_MELT_PRE", "NR_SNOW_MELT_POST"}
                       and int(parts[2]) == 2 and int(parts[7]) == 14))
    altered = _with_updated_capture_hash(evidence, changed)

    with pytest.raises(TraceError, match="capture record census"):
        replay(altered, changed)


def test_transport_face_key_census_is_code_fixed(bundle):
    evidence, text = bundle
    lines = text.splitlines()
    row = next(i for i, line in enumerate(lines)
               if (line.startswith("S2NR NR_FACE_PRE 2 ")
                   and int(line.split()[7]) == 14))
    parts = lines[row].split()
    parts[7] = "39"
    lines[row] = " ".join(parts)
    changed = "\n".join(lines) + "\n"
    altered = _with_updated_capture_hash(evidence, changed)

    with pytest.raises(TraceError, match="NR_FACE_PRE event-key census"):
        replay(altered, changed)


def test_source_event_census_rejects_same_count_displaced_rows(bundle):
    evidence, text = bundle
    lines = text.splitlines()
    for index, line in enumerate(lines):
        parts = line.split()
        if (len(parts) > 7 and parts[0] == "S2NR"
                and parts[1] in {"NR_SNOW_MELT_PRE", "NR_SNOW_MELT_POST"}
                and int(parts[2]) == 2 and int(parts[7]) == 14):
            parts[2] = "3"
            lines[index] = " ".join(parts)
    changed = "\n".join(lines) + "\n"
    altered = _with_updated_capture_hash(evidence, changed)

    with pytest.raises(TraceError, match="invalid step/loop/level"):
        replay(altered, changed)


def test_dsd_gate_rejects_same_count_event_outside_pinned_steps(bundle):
    evidence, text = bundle
    lines = text.splitlines()
    row = next(i for i, line in enumerate(lines)
               if (line.startswith("S2NR DSD_PRE_GATE 2 ")
                   and int(line.split()[7]) == 14))
    parts = lines[row].split()
    parts[2] = "3"
    lines[row] = " ".join(parts)
    changed = "\n".join(lines) + "\n"
    altered = _with_updated_capture_hash(evidence, changed)

    with pytest.raises(TraceError, match="invalid step/loop/level"):
        replay(altered, changed)


def test_nrmax_branch_flag_is_recomputed_from_k13_operands(bundle):
    evidence, text = bundle
    lines = text.splitlines()
    row = next(i for i, line in enumerate(lines)
               if (line.startswith("S2NR NR_MAX_GATE 1 ")
                   and int(line.split()[7]) == 13))
    parts = lines[row].split()
    assert parts[8] == "0"
    parts[8] = "1"
    lines[row] = " ".join(parts)
    changed = "\n".join(lines) + "\n"
    altered = _with_updated_capture_hash(evidence, changed)

    with pytest.raises(TraceError, match="K13 nrmax threshold branch"):
        replay(altered, changed)


def test_warm_number_update_and_cap_keys_cannot_move_into_cold_levels(bundle):
    evidence, text = bundle
    warm_tags = {
        "NR_LIMIT_PRE", "NR_LIMIT_POST",
        "NR_UPDATE_WARM_PRE", "NR_UPDATE_WARM_POST",
    }
    lines = text.splitlines()
    for index, line in enumerate(lines):
        parts = line.split()
        if (len(parts) > 7 and parts[0] == "S2NR" and parts[1] in warm_tags
                and int(parts[2]) == 1 and int(parts[7]) == 16):
            parts[7] = "15"
            lines[index] = " ".join(parts)
    changed = "\n".join(lines) + "\n"
    altered = _with_updated_capture_hash(evidence, changed)

    with pytest.raises(TraceError, match="NR_LIMIT_POST event-key census"):
        replay(altered, changed)


def test_parser_allows_only_explicitly_predeclared_extended_step_domain(bundle):
    evidence, text = bundle
    lines = text.splitlines()
    row = next(i for i, line in enumerate(lines)
               if line.startswith("S2NR HOST_ENTRY 2 "))
    parts = lines[row].split()
    parts[2] = "3"
    lines[row] = " ".join(parts)
    changed = "\n".join(lines) + "\n"
    tags = evidence["capture_source"]["tags"]

    with pytest.raises(TraceError, match="invalid step/loop/level"):
        parse_capture(changed, tags)
    rows = parse_capture(changed, tags, allowed_steps=range(1, 31))
    assert any(row["tag"] == "HOST_ENTRY" and row["step"] == 3 for row in rows)
