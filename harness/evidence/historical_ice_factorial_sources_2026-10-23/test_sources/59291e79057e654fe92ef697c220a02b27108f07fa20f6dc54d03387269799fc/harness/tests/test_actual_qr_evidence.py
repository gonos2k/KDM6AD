"""Replay the new candidate's public data; no private model or RTTOV dependency."""

from pathlib import Path
import hashlib
import json
import math

import numpy as np
import pytest

E = Path(__file__).parents[1] / "evidence/actual_qr_transport_2026-10-24"


def test_isolated_build_and_executed_map_identity():
    build = json.loads((E / "build_receipt.json").read_text())
    assert build["changed_object_members"] == ["sedimentation.cpp.o"]
    assert (
        build["unchanged_object_members"] == 13
        and not build["operational_install_changed"]
    )
    objects = [row for row in build["objects"] if row["name"].endswith(".o")]
    assert len(objects) == 14 and sum(row["identical"] for row in objects) == 13
    execution = json.loads((E / "block_execution.json").read_text())
    assert (
        execution["KDM_calls"] == 6
        and execution["host_steps"] == execution["RTTOV_calls"] == 0
    )
    for chunk in [34, 40]:
        rows = {
            row["condition"]: row
            for row in execution["receipts"]
            if row["chunk"] == chunk
        }
        assert set(rows) == {"legacy_off", "actual_off", "actual_on"}
        assert (
            rows["legacy_off"]["response_sha256"]
            == rows["legacy_off"]["prior_response_sha256"]
        )
        assert (
            rows["actual_off"]["response_sha256"]
            == rows["actual_on"]["response_sha256"]
        )
        assert all(
            row["tool_sha256"] == build["batch_tool_sha256"] for row in rows.values()
        )


@pytest.mark.parametrize("chunk", [34, 40])
def test_actual_transfers_and_surface_close_from_saved_operands(chunk):
    with np.load(E / f"chunk{chunk:03d}.npz", allow_pickle=False) as data:
        q, after, d, a = (
            data[name] for name in ["q_before", "q_after", "departure", "arrival"]
        )
        rho, dz, work, counts, gate = (
            data[name] for name in ["rho", "dz", "work", "mstep", "gate"]
        )
        assert q.shape == (5, 512, 39) and np.isfinite(q).all()
        attempted = rho * q * work / counts * gate * 20.0 / rho
        np.testing.assert_array_equal(d, np.minimum(attempted, q))
        np.testing.assert_array_equal(after, q - d + a)
        np.testing.assert_array_equal(a[:, :, 0], np.zeros((5, 512)))
        np.testing.assert_array_equal(
            a[:, :, 1:],
            d[:, :, :-1]
            * (rho[:, :, :-1] * dz[:, :, :-1])
            / (rho[:, :, 1:] * dz[:, :, 1:]),
        )
        np.testing.assert_array_equal(
            data["fall_after"], data["fall_before"] + d * rho / 20.0
        )
        assert (after >= 0).all() and (d >= 0).all() and (d <= q).all()
        mu = rho[0] * dz[0]
        delta = np.array(
            [
                math.fsum(
                    float(x) * float(w) for x, w in zip(after[-1, b] - q[0, b], mu[b])
                )
                for b in range(512)
            ]
        )
        reported = (
            np.maximum(data["fall_after"][-1, :, -1], 0)
            * dz[0, :, -1]
            / 1000.0
            * 20.0
            * 1000.0
        )
        np.testing.assert_array_equal(delta, data["qr_delta"])
        np.testing.assert_array_equal(reported, data["reported_QR"])
        assert np.all(abs(delta + reported) <= data["qr_gate"])
        # Arrival is not re-capped against an already depleted donor.
        assert np.any(a[:, :, 1:] > after[:, :, :-1])


@pytest.mark.parametrize("chunk", [34, 40])
def test_raw_water_cleanup_and_remaining_stage_budget_are_distinct(chunk):
    with np.load(E / f"chunk{chunk:03d}.npz", allow_pickle=False) as data:
        weights = data["rho"][0, :, ::-1] * data["dz"][0, :, ::-1]
        for mode in ["legacy", "actual"]:
            delta = data[mode + "_state_out"][1:7] - data[mode + "_state_in"][1:7]
            raw = np.array(
                [
                    math.fsum(
                        float(delta[s, b, k]) * float(weights[b, k])
                        for s in range(6)
                        for k in range(39)
                    )
                    + float(data[mode + "_precip"][0, b])
                    for b in range(512)
                ]
            )
            # Producer uses fsum for final (change,precip), so independent addition
            # can differ only by ordinary binary64 final rounding.
            np.testing.assert_allclose(
                raw, data[mode + "_raw_residual"], atol=1e-17, rtol=1e-13
            )
        reconstructed = (
            data["qr_residual"]
            + data["non_QR_sed_residual"]
            + data["micro_total_change"]
        )
        np.testing.assert_allclose(
            reconstructed, data["actual_raw_residual"], atol=1e-15, rtol=0
        )
        assert abs(data["micro_total_change"]).max() > 1e-8
        assert abs(data["non_QR_sed_residual"]).max() < 1e-14
        reference = json.loads(
            (
                E.parents[2]
                / "harness/evidence/applied_finish_ad_2026-10-21/native39_finish_ad.json"
            ).read_text()
        )
        after = data["actual_state_out"]
        clean = after.copy()
        clean[1] = np.maximum(clean[1], 0)
        clean[2:7] = np.where(
            clean[2:7] < reference["zero_out"]["threshold"], 0, clean[2:7]
        )
        change = clean[1:7] - after[1:7]
        cleanup = np.array(
            [
                math.fsum(
                    float(change[s, b, k]) * float(weights[b, k])
                    for s in range(6)
                    for k in range(39)
                )
                for b in range(512)
            ]
        )
        np.testing.assert_array_equal(cleanup, data["actual_cleanup"])


def test_selected_first_order_products_are_unchanged_by_candidate_trace():
    receipt = json.loads((E / "ad_noninterference.json").read_text())
    assert receipt["KDM_calls"] == 4
    for row in receipt["comparisons"]:
        assert all(row["products_bitwise_equal"].values())
        with (
            np.load(E / f"ad_chunk{row['chunk']:03d}_off.npz") as off,
            np.load(E / f"ad_chunk{row['chunk']:03d}_on.npz") as on,
        ):
            assert set(off.files) == set(on.files)
            for key in off.files:
                assert np.array_equal(off[key].view("u8"), on[key].view("u8"))


def test_current_source_and_artifact_manifest():
    manifest = json.loads((E / "manifest.json").read_text())
    root = E.parents[2]
    for name in ["source_sha256", "artifact_sha256"]:
        assert manifest[name]
        for path, digest in manifest[name].items():
            assert hashlib.sha256((root / path).read_bytes()).hexdigest() == digest, (
                path
            )


def test_repeated_controller_uses_one_scope_and_explicit_kernel_branch_limit():
    prepared = json.loads((E / "observation_prepared.json").read_text())
    result = json.loads((E / "observation_result.json").read_text())
    run = json.loads((E / "observation_run.json").read_text())
    assert prepared["experiment"] == result["experiment"] == run["experiment"]
    assert (
        prepared["scope"]
        == result["scope"]
        == run["scope"]
        == run["experiment"]["scope"]
    )
    assert "QR cap masks" in run["experiment"]["eligibility_scope"]
    assert (
        result["RTTOV_calls"]
        == result["KDM_forward_calls"]
        == run["RTTOV_calls"]
        == run["KDM_forward_calls"]
        == 19
    )
    assert (
        prepared["library"]["sha256"]
        == result["library"]["sha256"]
        == json.loads((E / "build_receipt.json").read_text())["library_sha256"]
    )
    assert (
        result["passed"]
        and np.all(np.array(result["quality"]) == 0)
        and np.all(np.array(result["mask"]) == 1)
    )


@pytest.mark.parametrize("name", ["theta_m", "qv", "mixed"])
def test_actual_candidate_cost_direction_and_endpoint_eligibility(name):
    d = json.loads((E / "observation_result.json").read_text())
    row = d["direction_checks"][name]
    keys = ["T", "Q", "P", "P_HALF", "HYDRO6", "HYDRO7", "HYDRO_DEFF6", "HYDRO_DEFF7"]
    observation = np.array(d["observation_BT_KMA"])
    residual = np.array(d["BT_KMA"]) - observation
    seed = np.clip(residual, -1, 1) * np.array(d["mask"])
    np.testing.assert_array_equal(seed, np.array(d["cost_BT_seed"]))

    def cost(bt, mask):
        error = np.asarray(bt) - observation
        return math.fsum(
            (
                np.where(abs(error) <= 1, 0.5 * error * error, abs(error) - 0.5)
                * np.asarray(mask)
            ).reshape(-1)
        )

    assert abs(cost(d["BT_KMA"], d["mask"]) - d["cost"]) < 1e-12
    products = (
        np.array(d["native_x_cost_gradient"]) * np.array(row["direction_x"])
    ).reshape(-1)
    rhs = math.fsum(float(x) for x in products)
    assert abs(rhs - row["cost_directional_derivative"]) <= 8 * np.finfo(
        float
    ).eps * max(1, math.fsum(abs(float(x)) for x in products))
    bt_jvp = np.array(
        [
            [
                math.fsum(
                    float(np.array(d["profile_K"][key])[0, channel, level])
                    * float(np.array(row["profile_tangent"][key])[level])
                    for key in keys
                    for level in range(len(row["profile_tangent"][key]))
                )
                for channel in range(7)
            ]
        ]
    )
    np.testing.assert_allclose(bt_jvp, np.array(row["BT_JVP"]), rtol=2e-13, atol=2e-13)
    lhs = math.fsum(
        float(x) * float(y) for x, y in zip(bt_jvp.reshape(-1), seed.reshape(-1))
    )
    assert abs(lhs - rhs) / max(abs(lhs), abs(rhs), 1e-12) <= 1e-10
    for trial in row["trials"]:
        for sign in ["plus", "minus"]:
            assert (
                abs(
                    cost(trial[sign + "_BT"], trial[sign + "_mask"])
                    - trial[sign + "_cost"]
                )
                < 1e-12
            )
            for key, basekey in [
                ("quality", "quality"),
                ("mask", "mask"),
                ("endpoint_cfrac", "endpoint_cfrac"),
                ("endpoint_signature", "endpoint_signature"),
            ]:
                assert np.array_equal(
                    np.array(trial[sign + "_" + key]), np.array(d[basekey])
                )
            assert all(trial[sign + "_endpoint_eligibility"].values())
        eps = trial["epsilon"]
        fd = (np.array(trial["plus_BT"]) - np.array(trial["minus_BT"])) / (2 * eps)
        cfd = (trial["plus_cost"] - trial["minus_cost"]) / (2 * eps)
        np.testing.assert_array_equal(fd, np.array(trial["BT_FD"]))
        assert cfd == trial["cost_FD"]
        jv = np.array(row["BT_JVP"])
        rhs_stored = row["cost_directional_derivative"]
        bt_ratio = float(
            np.max(abs(fd - jv) / (1e-8 + 3e-5 * np.maximum(abs(fd), abs(jv))))
        )
        cost_ratio = abs(cfd - rhs_stored) / (
            1e-8 + 3e-5 * max(abs(cfd), abs(rhs_stored))
        )
        assert (
            bt_ratio == trial["max_BT_tolerance_ratio"]
            and cost_ratio == trial["cost_tolerance_ratio"]
        )
        assert trial["eligible"] and trial["passed"] and max(bt_ratio, cost_ratio) <= 1
