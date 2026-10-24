"""Public scalar/profile-K replay, not a new private model or RTTOV run."""

from pathlib import Path
import hashlib
import json
import math
import numpy as np
import pytest

E = Path(__file__).parents[1] / "evidence/norm_actual_observation_2026-10-24"
KEYS = ("T", "Q", "P", "P_HALF", "HYDRO6", "HYDRO7", "HYDRO_DEFF6", "HYDRO_DEFF7")


def test_valid_native_target_cost_and_seed_match_observed_seven_channels():
    d = json.loads((E / "native13188_cost.json").read_text())
    assert (d["i"], d["j"], d["chunk"], d["local_row"], d["B"], d["L"]) == (
        131,
        88,
        40,
        8,
        512,
        39,
    )
    assert d["passed"] and d["RTTOV_calls"] == d["KDM_forward_calls"] == 19
    r = np.array(d["BT_KMA"]) - np.array(d["observation_BT_KMA"])
    mask = np.array(d["mask"])
    assert (
        mask.shape == (1, 7)
        and np.all(mask == 1)
        and np.all(np.array(d["quality"]) == 0)
    )
    terms = np.where(abs(r) <= 1.0, 0.5 * r * r, abs(r) - 0.5) * mask
    expected = math.fsum(terms.reshape(-1))
    assert abs(d["cost"] - expected) <= 8 * np.finfo(float).eps * max(
        1.0, abs(expected)
    )
    np.testing.assert_array_equal(
        np.array(d["cost_BT_seed"]), np.clip(r, -1.0, 1.0) * mask
    )


@pytest.mark.parametrize("name", ["theta_m", "qv", "mixed"])
def test_actual_pressure_aware_cost_jvp_and_finite_differences(name):
    d = json.loads((E / "native13188_cost.json").read_text())
    row = d["direction_checks"][name]
    gradient = np.array(d["native_X_cost_gradient"])
    direction = np.array(row["direction_x"])
    products = (gradient * direction).reshape(-1)
    rhs_independent = math.fsum(float(x) for x in products)
    rhs = row["cost_directional_derivative"]
    # Independent rounded-product reduction; producer NumPy sum is not a bit contract.
    rhs_roundoff = (
        8 * np.finfo(float).eps * max(1.0, math.fsum(abs(float(x)) for x in products))
    )
    assert abs(rhs_independent - rhs) <= rhs_roundoff
    K = {k: np.array(d["profile_K"][k]) for k in KEYS}
    v = {k: np.array(row["profile_tangent"][k]) for k in KEYS}
    reconstructed = np.zeros((1, 7))
    for channel in range(7):
        reconstructed[0, channel] = math.fsum(
            float(K[k][0, channel, level] * v[k][level])
            for k in KEYS
            for level in range(v[k].size)
        )
    # The stored producer uses einsum reductions; compare independent rounded products+fsum.
    np.testing.assert_allclose(
        reconstructed, np.array(row["BT_JVP"]), atol=2e-13, rtol=2e-13
    )
    lhs_products = (np.array(row["BT_JVP"]) * np.array(d["cost_BT_seed"])).reshape(-1)
    lhs = math.fsum(float(x) for x in lhs_products)
    lhs_roundoff = (
        8
        * np.finfo(float).eps
        * max(1.0, math.fsum(abs(float(x)) for x in lhs_products))
    )
    assert abs(lhs - row["dot_lhs"]) <= lhs_roundoff
    independent_dot_error = abs(lhs - rhs_independent) / max(
        abs(lhs), abs(rhs_independent), 1e-30
    )
    assert (
        independent_dot_error <= 1e-10
        and row["dot_relative_error"] <= 1e-10
        and row["passed"]
    )
    for trial in row["trials"]:
        epsilon = trial["epsilon"]
        fd = (np.array(trial["plus_BT"]) - np.array(trial["minus_BT"])) / (2 * epsilon)
        cost_fd = (trial["plus_cost"] - trial["minus_cost"]) / (2 * epsilon)
        np.testing.assert_array_equal(fd, np.array(trial["BT_FD"]))
        assert cost_fd == trial["cost_FD"]
        jv = np.array(row["BT_JVP"])
        bt_ratio = float(
            np.max(abs(fd - jv) / (1e-8 + 3e-5 * np.maximum(abs(fd), abs(jv))))
        )
        cost_ratio = abs(cost_fd - rhs) / (1e-8 + 3e-5 * max(abs(cost_fd), abs(rhs)))
        assert (
            bt_ratio == trial["max_BT_tolerance_ratio"]
            and cost_ratio == trial["cost_tolerance_ratio"]
        )
        assert (
            trial["eligible"] and trial["passed"] and max(bt_ratio, cost_ratio) <= 1.0
        )


def test_rejected_column_masked_zero_is_never_a_fit():
    d = json.loads((E / "rejected11376.json").read_text())
    assert d["target"] == [113, 76] and d["simulated_usable_channels"] == 0
    assert d["do_not_interpret_zero_masked_cost_as_fit"] and np.all(
        np.array(d["RTTOV_quality"]) != 0
    )
    assert d["reported_humidity_ppmv"] > d["reported_upper_limit_ppmv"]
    assert "exceeds upper coef limit" in (E / "rejected11376_rttov.log").read_text()


def test_derived_number_receipt_keeps_payload_and_source_scope_explicit():
    d = json.loads((E / "number_qualification.json").read_text())
    assert (
        d["original_host_payload_basis"] == "unknown_not_migrated"
        and not d["original_host_basis_certified"]
    )
    assert d["source_bindings"]["source_artifact_kind"].startswith(
        "captured original B512"
    )
    assert (d["source_bindings"]["i"], d["source_bindings"]["j"]) == (131, 88)
    assert all(v["max_ulp"] <= 2 for v in d["roundtrip_volume_coordinate"].values())


def test_source_and_artifact_hashes():
    manifest = json.loads((E / "manifest.json").read_text())
    root = E.parents[2]
    for group in ("source_sha256", "artifact_sha256"):
        assert manifest[group]
        for path, expected in manifest[group].items():
            assert hashlib.sha256((root / path).read_bytes()).hexdigest() == expected, (
                path
            )
