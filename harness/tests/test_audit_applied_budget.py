"""Independent small inventories for the value-only saved-array diagnostic."""
from __future__ import annotations

import json

import numpy as np
import pytest

from harness import audit_applied_budget as audit


def test_split_separates_physics_sink_cleanup_removal_and_negative_repair():
    before = np.zeros((6, 2))
    before[0] = [.1, .2]
    before[3] = [.04, .08]
    raw = before.copy()
    raw[0] = [.08, -.01]
    raw[3] = [.03, .001]
    clean = raw.copy()
    clean[0, 1] = 0.
    clean[3, 1] = 0.
    result = audit.split_changes(before, raw, clean, 2., np.array([2., 3.]))
    assert result["algebraic_split_verified"]
    qv, qi = result["fields"]["QV"], result["fields"]["QI"]
    assert qv["cleanup_added_kg_m2"] == pytest.approx(.03)
    assert qv["cleanup_removed_kg_m2"] == 0
    assert qi["cleanup_removed_kg_m2"] == pytest.approx(.003)
    assert qi["cleanup_changed_levels_1based"] == [2]
    assert qi["kernel_change_kg_m2"] == pytest.approx(-.257)
    assert qi["applied_change_kg_m2"] == pytest.approx(-.26)
    np.testing.assert_allclose(qi["applied_mean_rate_ratio_per_s"], [-.005, -.04])


@pytest.mark.parametrize("dt", [0., -1., np.nan, np.inf, True])
def test_refuse_invalid_time_interval(dt):
    state = np.ones((6, 2))
    with pytest.raises(ValueError, match="dt"):
        audit.split_changes(state, state, state, dt, np.ones(2))


def test_refuse_nonfinite_and_nonpositive_measure_without_repair():
    state = np.ones((6, 2))
    with pytest.raises(ValueError, match="weights must be positive"):
        audit.split_changes(state, state, state, 1., np.array([1., 0.]))
    changed = state.copy()
    changed[0, 0] = np.nan
    with pytest.raises(ValueError, match="raw must be finite"):
        audit.split_changes(state, changed, state, 1., np.ones(2))
    assert np.isnan(changed[0, 0])


def synthetic_report():
    levels = 2
    before = np.zeros((12, levels))
    before[1] = [.01, .02]
    before[4] = [.001, .002]
    raw = before.copy()
    raw[1] -= 1e-4
    raw[4] = [1e-9, 1e-6]
    raw[9] = [10., 20.]
    clean = raw.copy()
    clean[4, 0] = 0.
    x = np.r_[np.array([1., 2.]), before[1], 1., [0., 1., 2.]]
    return {"schema": "kdm6.microphysics_observation_ad.v1", "passed": True,
            "kernel_contract": {"physics_variant": 0, "dry_number": 0, "dt_seconds": 20.},
            "native_prep_phase": {"namelist_options": {"mp_physics": 137, "use_theta_m": 1,
                "no_mp_heating": 0, "use_q_diabatic": 0, "mp_zero_out": 2, "mp_zero_out_all": 0}},
            "kernel_after": raw.tolist(), "clean_after": clean.tolist(),
            "native_X": x.tolist(), "native_rest": before[2:].tolist(), "native_snapshot": {},
            "native_f32_replay": {"captured_f32": {"DEN": [1., 2.], "DELZ": [3., 4.]}},
            "applied_finish": {"QV_RATE": ((clean[1]-before[1])/20).tolist(),
                               "QC_RATE": ((clean[2]-before[2])/20).tolist(),
                               "H_RATE": [.01, .02], "T_NEW_AFTER": [1.2, 2.4]}}


def test_saved_layout_checks_tendencies_and_keeps_number_basis_conditional():
    source = synthetic_report()
    result = audit.audit(source)
    assert result["passed"]
    assert result["finish_checks"]["QV_RATE_maxabs_error"] == 0.
    assert result["number"]["NI"]["cleanup_exact_identity"]
    assert result["number"]["NI"]["kernel_change_raw"] == [10., 20.]
    pair = result["mass_number_pairs"]["QI_NI"]
    assert pair["newly_zero_mass_after_cleanup_levels_1based"] == [1]
    assert pair["raw_number_at_newly_zero_mass_levels"] == [10.]
    assert result["water"]["fields"]["QI"]["cleanup_removed_kg_m2"] == pytest.approx(3e-9)
    assert not result["closed_water_budget_certified"]
    assert not result["closed_energy_budget_certified"]
    assert not result["closed_number_budget_certified"]
    assert not result["number_basis_certified"]
    assert not result["cleanup_rule_recomputed"]
    assert not result["surface_exports_available_for_this_fp64_call"]
    assert source == synthetic_report()  # read-only audit
    source["applied_finish"]["QV_RATE"][0] += 1e-5
    assert not audit.audit(source)["passed"]


def test_cli_refuses_alias_and_preserves_source(tmp_path):
    source = tmp_path/"input.json"
    source.write_text(json.dumps(synthetic_report()))
    original = source.read_bytes()
    with pytest.raises(ValueError, match="output must be new"):
        audit.run(source, source)
    alias = tmp_path/"alias.json"
    alias.symlink_to(source)
    with pytest.raises(ValueError, match="output must be new"):
        audit.run(source, alias)
    assert source.read_bytes() == original


def test_refuse_unlabelled_schema_or_a_different_kernel_basis():
    source = synthetic_report()
    source["schema"] = "unknown"
    with pytest.raises(ValueError, match="saved microphysics"):
        audit.audit(source)
    source = synthetic_report()
    source["kernel_contract"]["dry_number"] = 1
    with pytest.raises(ValueError, match="legacy/raw"):
        audit.audit(source)


@pytest.mark.parametrize(("name", "value"), [("mp_zero_out_all", 1), ("no_mp_heating", 1)])
def test_refuse_different_physics_contract(name, value):
    source = synthetic_report()
    source["native_prep_phase"]["namelist_options"][name] = value
    with pytest.raises(ValueError, match="namelist contract"):
        audit.audit(source)
