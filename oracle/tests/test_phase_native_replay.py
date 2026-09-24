"""Replay the two actual mp37 phase events from published lossless tokens."""

import copy
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from replay_phase_native import parse_line, replay  # noqa: E402


DATA = Path(__file__).resolve().parents[2] / "harness/evidence/native_phase_event_2026-09-24.json"


def _evidence():
    return json.loads(DATA.read_text())


def _change_token(data, row, token, value):
    words = data["raw_records"][row].split()
    words[token] = value
    data["raw_records"][row] = " ".join(words)


def _change_output(data, command, target):
    argv = data["build"][command]
    argv[argv.index("-o") + 1] = target


def test_native_capture_has_two_complete_events_and_bitwise_history_identity():
    result = replay(_evidence())
    inactive, active = result["events"]
    assert not inactive["D2"]["number_valid"]
    assert inactive["D2"]["applied_mass"] == inactive["D3"]["applied_mass"] == 0
    assert active["D2"]["number_valid"] and active["D3"]["number_valid"]
    assert active["D2"]["applied_mass"] > 0
    assert active["D3"]["applied_mass"] > 0
    assert active["D2"]["requested_mass"] == active["D2"]["applied_mass"]
    assert active["D3"]["requested_mass"] == active["D3"]["applied_mass"]
    assert active["post_state_update"]["qi"] != active["phase_end"]["qi"]
    assert active["final"]["qc"] != active["post_state_update"]["qc"]
    assert result["full_energy_or_unit_approval"] is False


def test_native_latent_work_is_below_the_saved_f32_temperature_step():
    active = replay(_evidence())["events"][1]
    for stage in ("D2", "D3"):
        item = active[stage]
        assert item["thermal_step_before_f32_store_k"] > 0
        assert item["stored_temperature_change_k"] == 0
        # The source executed the heat expression, but a single stored f32 T
        # cannot resolve its tiny contribution in this selected native cell.
        assert item["thermal_step_before_f32_store_k"] < 0.5 * np.spacing(
            np.float32(active["phase_end"]["t"]))


@pytest.mark.parametrize("mutate", [
    lambda d: d["raw_records"].pop(0),
    lambda d: d["raw_records"].__setitem__(1, d["raw_records"][2]),
    lambda d: _change_token(d, 0, 6, "1"),  # inactive number flag
    lambda d: _change_token(d, 1, -1, "0000000000000001"),  # inactive output
    lambda d: _change_token(d, 8, -2, "3FF0000000000000"),  # applied mass
    lambda d: _change_token(d, 9, 7, "00000000"),  # post qc
    lambda d: _change_token(d, 9, 11, "43700000"),  # post T
    lambda d: _change_token(d, 10, 6, "00000000"),  # later qc
    lambda d: _change_token(d, 11, 6, "00000000"),  # final qc
    lambda d: d.update(raw_records_sha256="0" * 64),
    lambda d: d["build"].update(object_sha256="0" * 64),
    lambda d: d["build"].update(assemble_command=["/usr/bin/clang"]),
    lambda d: _change_output(d, "compile_command", "/tmp/unrelated.s"),
    lambda d: _change_output(d, "assemble_command", "/tmp/unrelated.o"),
    lambda d: _change_output(d, "link_command", "/tmp/unrelated.exe"),
    lambda d: d["build"]["compile_command"].append("-ffast-math"),
    lambda d: d["experiment_valid"][0].update(experiment_valid=False),
    lambda d: d.update(accepted_full_energy=True),
    lambda d: d.update(history_sha256=["0" * 64, "0" * 64]),
])
def test_native_replay_rejects_missing_mutated_or_overclaimed_evidence(mutate):
    data = copy.deepcopy(_evidence())
    mutate(data)
    with pytest.raises((ValueError, KeyError)):
        replay(data)


def test_native_parser_rejects_nonfinite_and_wrong_cell():
    line = _evidence()["raw_records"][6]
    with pytest.raises(ValueError, match="wrong loop or native cell"):
        parse_line(line.replace(" 97 173 22 ", " 98 173 22 "))
    with pytest.raises(ValueError, match="nonfinite"):
        parts = line.split()
        parts[7] = "7F800000"
        parse_line(" ".join(parts))
