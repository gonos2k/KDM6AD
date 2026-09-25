"""Public-vector replay of one input-selected 39-level model profile."""

import copy
import json
import sys
from pathlib import Path

import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from phase_profile_case import (  # noqa: E402
    ALPHA, FRAME_SHA256, K, _state_forcing, replay_evidence, run_profile,
)
from kdm6.runtime import kdm6_fn, make_parameters  # noqa: E402
from kdm6.process_controls import ProcessControls  # noqa: E402
from kdm6.sensitivity_diagnostics import SensitivityTrace  # noqa: E402


DATA = Path(__file__).resolve().parents[2] / "harness/evidence/real_phase_profile_2026-09-24.json"


def _evidence():
    return json.loads(DATA.read_text())


def test_real_profile_input_and_both_cases_replay():
    data = _evidence()
    assert data["source"]["sha256"] == FRAME_SHA256
    assert len(data["input"]["raw_native_column"]["QCLOUD"]) == 39
    assert replay_evidence(data) == {
        "scope": "public_vector_oracle_replay_only", "case_count": 2,
        "native_host_executed": False,
    }
    base, controlled = data["cases"]["baseline"], data["cases"]["diagnostic_control"]
    assert base["producer_after_own_caps"] == controlled["producer_after_own_caps"]
    assert base["applied"]["pinuc"] > 0 and base["applied"]["pfrzdtc"] > 0
    assert controlled["applied"]["pinuc"] + controlled["applied"]["pfrzdtc"] == pytest.approx(
        controlled["phase_before"]["qc"], rel=1e-13)
    assert controlled["phase_after"]["qc"] == 0
    assert abs(base["heat_residual_j_per_kg"]) < 1e-8
    assert abs(controlled["heat_residual_j_per_kg"]) < 1e-8
    # Later cold-rate and saturation steps change the state; they are separate
    # from the isolated phase transfer and must not be folded into its ledger.
    assert base["later_stage_after"]["state_update"]["qi"] != base["phase_after"]["qi"]
    assert base["later_stage_after"]["satadj"]["t"] != base["phase_after"]["t"]


@pytest.mark.parametrize("edit", [
    lambda d: d["source"].update(sha256="0" * 64),
    lambda d: d.update(native_host_executed_for_this_capture=True),
    lambda d: d["input"]["raw_native_column"].pop("PHB"),
    lambda d: d["cases"]["baseline"]["applied"].update(pinuc=0.0),
    lambda d: d["cases"]["baseline"]["phase_after"].update(t=249.0),
    lambda d: d["cases"]["diagnostic_control"]["phase_after"].update(qi=0.0),
    lambda d: d["cases"]["baseline"]["later_stage_after"].pop("satadj"),
    lambda d: d["cases"]["baseline"]["producer_after_own_caps"].update(pinuc=float("nan")),
])
def test_public_replay_rejects_scope_and_value_mutations(edit):
    data = copy.deepcopy(_evidence())
    edit(data)
    with pytest.raises((ValueError, KeyError)):
        replay_evidence(data)


@pytest.mark.parametrize("controlled", [False, True])
def test_opt_in_phase_operands_do_not_change_oracle_output(controlled):
    raw = _evidence()["input"]["raw_native_column"]
    state, forcing = _state_forcing(raw)
    control = (ProcessControls(alpha_freeze=torch.tensor(ALPHA, dtype=torch.float64))
               if controlled else None)
    args = (state, forcing, make_parameters(), 20., torch.tensor([1.0]),
            100., 10., control)
    plain = kdm6_fn(*args)
    trace = SensitivityTrace()
    inspected = kdm6_fn(*args, diagnostic_trace=trace)
    for x, y in zip(plain, inspected):
        assert torch.equal(x, y)
    rec = trace.by_name("d2_d4_freeze")
    assert len(rec) == 1
    assert rec[0].operands["pre_control_pinuc"].shape == (1, 39)
    assert rec[0].operands["pre_control_pfrzdtc"][0, K] > 0
    assert run_profile(raw, controlled=controlled)["mass_residual_max"] < 1e-14
