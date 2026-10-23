"""Independent numerical bookkeeping witnesses for the value-only factorial."""
import numpy as np
import pytest
import json
from pathlib import Path

from harness.run_ice_factorial import (MODES, contrast, state_equivalent_budget,
    ice_metrics, water_stages)
from harness.same_call_water_budget import read_response, ledger, sha
from harness.ice_factorial_batch import unpack_response


def test_bottom_arrival_is_distinct_from_bottom_departure_nonuniform_measure():
    before = np.array([3., 3., 2.])
    departure = np.array([1., .4, .25])
    arrival = np.array([0., 2/3, .24])
    weights = np.array([2., 3., 5.])
    after = before-departure+arrival
    out = state_equivalent_budget(before, after, departure, arrival, weights)
    assert out["actual_bottom_departure"] == 1.25
    assert out["bottom_arrival"] == 1.2
    assert abs(out["net_bottom_depletion"] - .05) < 2e-15
    assert abs(out["column_change"] + 1.25) < 2e-15
    assert abs(out["identity_residual"]) <= out["numerical_gate"]


def test_conservative_arrival_with_nonuniform_density_and_thickness():
    weights = np.array([100., 400.])
    before = np.array([1e-4, 0.])
    departure = np.array([2e-8, 0.])
    arrival = np.array([0., 5e-9])
    after = before-departure+arrival
    out = state_equivalent_budget(before, after, departure, arrival, weights)
    assert out["actual_bottom_departure"] == 0.
    assert out["bottom_arrival"] == 5e-9*400
    assert out["net_bottom_depletion"] == -out["bottom_arrival"]
    assert abs(out["state_plus_bottom"]) <= out["numerical_gate"]


def test_post_reservoir_cap_defect_is_retained_not_filled_with_a_sink():
    out = state_equivalent_budget([1., 0.], [.2, .2], [.8, 0.], [0., .2], [1., 1.])
    assert out["actual_bottom_departure"] == 0
    assert out["interface_gap_sum"] == .8-.2
    assert abs(out["column_change"] + .6) < 2e-16


@pytest.mark.parametrize("bad", ["arrival", "top_inflow", "negative", "nan"])
def test_bad_transfer_records_are_refused(bad):
    before = np.array([1., 0.])
    after = np.array([.2, .2])
    dep, arr = np.array([.8, 0.]), np.array([0., .2])
    if bad == "arrival":
        arr[1] = .3
    elif bad == "top_inflow":
        arr[0] = .1
    elif bad == "negative":
        dep[1] = -.1
    else:
        after[1] = np.nan
    with pytest.raises(ValueError):
        state_equivalent_budget(before, after, dep, arr, np.ones(2))


def test_two_factor_contrasts_keep_the_interaction():
    result = contrast({"raw_cap": 1., "norm_cap": 3., "raw_actual": 5., "norm_actual": 11.})
    assert result == {"normalization_at_cap": 2., "normalization_at_actual": 6.,
                      "actual_arrival_at_raw": 4., "actual_arrival_at_normalized": 8.,
                      "interaction": 4.}


def test_public_four_arm_capture_and_accounting_replay_without_kernel():
    directory = Path(__file__).parents[1]/"evidence/ice_factorial_2026-10-23"
    report = json.loads((directory/"native39_factorial.json").read_text())
    s, f = (np.asarray(report[k], dtype=np.float64) for k in ("state_in", "forcing_in"))
    all_stages = {}
    for mode in MODES:
        saved = report["modes"][mode]
        on = directory/"campaign"/(mode+"_on")
        off = directory/"campaign"/(mode+"_off")
        assert (on/"response.bin").read_bytes() == (off/"response.bin").read_bytes()
        assert sha(on/"response.bin") == saved["response_sha256"]
        _, _, raw, flux = read_response((on/"response.bin").read_bytes(), s, f)
        assert raw.tobytes() == np.asarray(saved["state_out"], dtype=np.float64).tobytes()
        assert ice_metrics(on/"ice.tsv", mode, s, f) == saved["ice"]
        stages = water_stages(on/"ice.tsv", mode, f)
        assert stages["post_micro"].tobytes() == raw[1:7].tobytes()
        all_stages[mode] = stages
        clean = raw.copy()
        clean[1] = np.maximum(raw[1], 0.)
        clean[2:7] = np.where(raw[2:7] < report["zero_out"]["threshold"], 0., raw[2:7])
        assert ledger(s, f, raw, clean, flux, 20.) == saved["accounting"]
        finish = np.asarray(saved["applied_finish"], dtype=np.float64)
        assert finish[2].tobytes() == ((clean[1]-s[1])/20.).tobytes()
        assert finish[3].tobytes() == ((clean[2]-s[2])/20.).tobytes()
    reference = all_stages["raw_cap"]
    for stages in all_stages.values():
        assert stages["pre_sed"].tobytes() == reference["pre_sed"].tobytes()
        assert stages["post_sed"][[0,1,2,4,5]].tobytes() == reference["post_sed"][[0,1,2,4,5]].tobytes()
    values = {mode:report["modes"][mode]["ice"]["QI"]["state_plus_bottom"] for mode in MODES}
    assert contrast(values) == report["contrasts"]["ice_QI_state_plus_bottom"]


def test_batch_sample_matches_each_single_column_treatment():
    root = Path(__file__).parents[1]/"evidence"
    report = json.loads((root/"ice_factorial_2026-10-23/native39_factorial.json").read_text())
    directory = root/"ice_factorial_batch_smoke_2026-10-23/final"
    for mode in MODES:
        a = unpack_response((directory/(mode+".B1.response.bin")).read_bytes())
        b = unpack_response((directory/(mode+".B2.response.bin")).read_bytes())
        assert a["state_out"][:, 0].tobytes() == np.asarray(report["modes"][mode]["state_out"], dtype=np.float64).tobytes()
        assert b["state_out"][:, 0].tobytes() == a["state_out"][:, 0].tobytes()
        assert b["state_out"][:, 1].tobytes() == a["state_out"][:, 0].tobytes()
        assert b["precip"][:, 0].tobytes() == a["precip"][:, 0].tobytes()
        assert b["precip"][:, 1].tobytes() == a["precip"][:, 0].tobytes()
