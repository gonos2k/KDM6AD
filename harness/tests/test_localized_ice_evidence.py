"""Independent public-array replay; never loads the diagnostic model library."""

from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pytest

from harness.analyze_domain_ice_factorial import columns
from harness.verify_localized_ice_ad import fd_metrics

EVIDENCE = Path(__file__).parents[1] / "evidence/localized_ice_budget_ad_2026-10-24"
DOMAIN = EVIDENCE.parent / "domain_ice_factorial_2026-10-23"


def test_call_counts_and_unique_selected_profiles_preserve_both_modes():
    validation = json.loads((EVIDENCE / "validation.json").read_text())
    assert validation["KDM_forward_calls_total"] == 512
    assert sum(validation["KDM_forward_calls_by_task"].values()) == 512
    assert (
        validation["whole_domain_repeats"]
        == validation["native_host_steps"]
        == validation["RTTOV_calls"]
        == 0
    )
    stage = json.loads((EVIDENCE / "stage_analysis.json").read_text())
    expected = {
        f"{mode}_chunk{i:03d}"
        for mode in ("norm_actual", "raw_actual")
        for i in (34, 40)
    }
    assert set(stage["selected_by_case"]) == expected
    for case, profiles in stage["selected_by_case"].items():
        assert len(profiles) == 1
        profile = next(iter(profiles.values()))
        assert profile["mode"] == case.split("_chunk")[0]
        assert profile["i_fortran"] in (113, 131) and profile["j_fortran"] in (76, 88)


@pytest.mark.parametrize("mode", ["norm_actual", "raw_actual"])
@pytest.mark.parametrize("index", [34, 40])
def test_full_block_water_residuals_match_original_domain_archive(mode, index):
    with np.load(
        EVIDENCE / f"stage_{mode}_chunk{index:03d}.npz", allow_pickle=False
    ) as z:
        stages = z["water_stage_state_bottomfirst"]
        w = z["measure_DENxDELZ_kg_m2"]
        assert stages.shape == (3, 6, 512, 39)
        for key, delta in [
            ("pre_to_post_sed_delta_kg_m2", stages[1] - stages[0]),
            ("post_sed_to_post_micro_delta_kg_m2", stages[2] - stages[1]),
        ]:
            expected = np.stack([columns(field, w) for field in delta])
            np.testing.assert_array_equal(z[key], expected)
        raw_change = columns(stages[2] - stages[0], w)
        residual = np.array(
            [
                math.fsum((a, p))
                for a, p in zip(raw_change, z["precip_total_snowice_graupel_mm"][0])
            ]
        )
        np.testing.assert_array_equal(z["six_species_residual_kg_m2"], residual)
        with np.load(DOMAIN / f"{mode}.columns.npz", allow_pickle=False) as original:
            np.testing.assert_array_equal(
                residual,
                original["raw_plus_reported_precip_residual"][
                    index * 512 : (index + 1) * 512
                ],
            )
        row = 254 if index == 34 else 8
        exact = float(
            sum(
                (
                    Fraction.from_float(
                        float(stages[2, f, row, k] - stages[0, f, row, k])
                        * float(w[row, k])
                    )
                    for f in range(6)
                    for k in range(39)
                ),
                Fraction(),
            )
        )
        assert exact == raw_change[row]


@pytest.mark.parametrize("family", ["raw", "pairs"])
@pytest.mark.parametrize("index", [34, 40])
def test_ad_products_reproduce_dots_and_all_field_fd_decisions(family, index):
    report = json.loads((EVIDENCE / f"{family}_{index:03d}.report.json").read_text())
    path = EVIDENCE / f"{family}_{index:03d}.products.npz"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == report["products_sha256"]
    with np.load(path, allow_pickle=False) as z:
        if family == "raw":
            target = report["target_row"]
            at_floor = z["state"][7, target] == 1e8
            assert np.any(z["number_ds"][7, target, at_floor] != 0.0)
            assert not np.any(z["cloud_mass_ds"][11])
            assert np.any(z["cloud_mass_ds"][6, target])
        for name, item in report["directions"].items():
            ds, df = z[name + "_ds"], z[name + "_df"]
            jv = z[name + "_jvp"]
            lhs = math.fsum((z["cotangent"] * jv).reshape(-1))
            rhs = math.fsum(
                np.r_[
                    (z["state_vjp"] * ds).reshape(-1),
                    (z["forcing_vjp"] * df).reshape(-1),
                ]
            )
            assert lhs == item["dot_lhs"] and rhs == item["dot_rhs"]
            passed = []
            for trial in item["trials"]:
                fd = z[name + f"_fd_{trial['epsilon']}"]
                metrics = fd_metrics(fd, jv)
                assert metrics["max_tolerance_ratio"] == trial["max_tolerance_ratio"]
                assert (
                    metrics["per_field_tolerance_ratio"]
                    == trial["per_field_tolerance_ratio"]
                )
                passed.append(
                    trial["thermo_branches_preserved"]
                    and metrics["max_tolerance_ratio"] <= 1
                )
            assert (
                bool(item["dot_relative_error"] <= 1e-10 and any(passed))
                == item["passed"]
            )
        assert report["passed"] == (family == "pairs")


def test_nn_one_sided_values_demonstrate_boundary_and_probe_provenance():
    probe = json.loads((EVIDENCE / "nn_one_sided.json").read_text())
    provenance = json.loads((EVIDENCE / "nn_probe_provenance.json").read_text())
    assert len(provenance["cases"]) == len(probe["results"]) == 2
    for row in probe["results"]:
        assert row["NN_before"] == row["NN_base"] == 1e8
        assert row["JVP"] == row["forward_sided_FD"] == 1e6
        assert row["backward_sided_FD"] == 0.0
        assert row["central_FD"] == 5e5
        assert (row["NN_plus"] - row["NN_minus"]) / (2 * row["epsilon"]) == row[
            "central_FD"
        ]


def test_within_variant_trace_products_match_bitwise():
    receipt = json.loads((EVIDENCE / "noninterference.json").read_text())
    assert receipt["KDM_forward_calls"] == 8 and len(receipt["cases"]) == 4
    for case in receipt["cases"]:
        stem = f"noninterference_{case['mode']}_{case['chunk']:03d}"
        with (
            np.load(EVIDENCE / (stem + ".off.npz"), allow_pickle=False) as off,
            np.load(EVIDENCE / (stem + ".on.npz"), allow_pickle=False) as on,
        ):
            assert set(off.files) == set(on.files) == set(case["products"])
            for name, expected in case["products"].items():
                assert expected["raw_bitwise_equal"]
                assert off[name].size == expected["values"]
                assert (
                    hashlib.sha256(off[name].tobytes()).hexdigest()
                    == expected["off_raw_sha256"]
                )
                assert (
                    hashlib.sha256(on[name].tobytes()).hexdigest()
                    == expected["on_raw_sha256"]
                )
                np.testing.assert_array_equal(off[name].view("u8"), on[name].view("u8"))


def test_source_and_evidence_inventory():
    manifest = json.loads((EVIDENCE / "manifest.json").read_text())
    root = EVIDENCE.parents[2]
    for group in ("source_sha256", "artifact_sha256"):
        assert manifest[group]
        for path, digest in manifest[group].items():
            assert hashlib.sha256((root / path).read_bytes()).hexdigest() == digest, (
                path
            )
    # The failed v1 tests retain their original executed source, not current helper bytes.
    snapshot = EVIDENCE / "execution_sources/ad_verifier_v1.py.txt"
    assert (
        hashlib.sha256(snapshot.read_bytes()).hexdigest()
        == manifest["raw_v1_executed_source_sha256"]
    )
