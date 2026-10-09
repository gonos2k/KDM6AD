"""Synthetic storage-boundary checks; these tests never open native inputs."""
from __future__ import annotations

import json
import hashlib
import stat
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import torch

import capture_tq_state as capture
from kdm6.da_cvt import CVT_LINEAR, cvt_apply
from kdm6.da_dual import default_param_prior, params_from_vtheta
from kdm6.state import Forcing, State


def _synthetic_state_and_forcing():
    state = State(*(torch.ones((1, 39), dtype=torch.float64) for _ in State._fields))
    forcing = Forcing(*(torch.ones((1, 39), dtype=torch.float64) for _ in Forcing._fields))
    return state, forcing


def _tagged_state(tag: int) -> State:
    return State(*(torch.full((1, 39), tag * 100 + index + 1, dtype=torch.float64)
                   for index, _ in enumerate(State._fields)))


def _tagged_forcing(tag: int) -> Forcing:
    return Forcing(*(torch.full((1, 39), tag * 10 + index + 1, dtype=torch.float64)
                     for index, _ in enumerate(Forcing._fields)))


def test_private_npz_is_atomic_private_and_refuses_replacement(tmp_path: Path):
    directory = tmp_path / "private"
    checkpoint = directory / "accepted.npz"
    digest = capture.write_private_npz_atomic(
        checkpoint, {"synthetic": np.arange(3, dtype=np.float64)})

    assert len(digest) == 64
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(checkpoint.stat().st_mode) == 0o600
    with np.load(checkpoint, allow_pickle=False) as archive:
        np.testing.assert_array_equal(archive["synthetic"], np.arange(3))

    try:
        capture.write_private_npz_atomic(checkpoint, {"synthetic": np.zeros(1)})
    except FileExistsError:
        pass
    else:
        raise AssertionError("private checkpoint writer replaced a prior checkpoint")
    assert list(directory.iterdir()) == [checkpoint]


def test_private_npz_digest_is_computed_before_no_clobber_publication(tmp_path: Path, monkeypatch):
    checkpoint = tmp_path / "private" / "prehashed.npz"
    original_hash = capture.sha256_file
    hashed_paths = []

    def record_hash(path):
        path = Path(path)
        assert path != checkpoint
        hashed_paths.append(path)
        return original_hash(path)

    monkeypatch.setattr(capture, "sha256_file", record_hash)
    digest = capture.write_private_npz_atomic(checkpoint, {"state": np.arange(5)})
    assert len(hashed_paths) == 1
    assert hashed_paths[0].parent == checkpoint.parent
    assert not hashed_paths[0].exists()
    assert hashlib.sha256(checkpoint.read_bytes()).hexdigest() == digest


def test_post_link_receipt_temp_cleanup_error_keeps_referenced_checkpoint(tmp_path: Path, monkeypatch):
    checkpoint = tmp_path / "private" / "accepted.npz"
    checkpoint_sha = capture.write_private_npz_atomic(
        checkpoint, {"synthetic_state": np.arange(4, dtype=np.float64)})
    receipt = tmp_path / "public" / "RESULT.json"
    original_unlink = Path.unlink

    def fail_receipt_temp_unlink(path, *args, **kwargs):
        if path.name.startswith(".RESULT.json."):
            raise OSError("synthetic temp cleanup failure after receipt link")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_receipt_temp_unlink)
    receipt_sha = capture._write_receipt_exclusive(
        receipt, {"status": "RETURNED_DIAGNOSTIC_ONLY",
                  "private_checkpoint": str(checkpoint),
                  "private_checkpoint_sha256": checkpoint_sha})
    record = json.loads(receipt.read_text())
    assert len(receipt_sha) == 64
    assert record["status"] == "RETURNED_DIAGNOSTIC_ONLY"
    assert Path(record["private_checkpoint"]).is_file()
    assert hashlib.sha256(Path(record["private_checkpoint"]).read_bytes()).hexdigest() == record[
        "private_checkpoint_sha256"]
    # Cleanup is best-effort after the receipt hard link commits. A leftover
    # 0600 temp name does not turn a committed receipt into a failed call.
    assert any(path.name.startswith(".RESULT.json.") for path in receipt.parent.iterdir())


def test_public_receipt_is_exclusive_and_failure_does_not_publish_state(tmp_path: Path):
    receipt_path = tmp_path / "public" / "RESULT.json"
    receipt_hash = capture._write_receipt_exclusive(receipt_path, {"status": "SYNTHETIC"})
    assert len(receipt_hash) == 64
    assert stat.S_IMODE(receipt_path.stat().st_mode) == 0o600
    assert json.loads(receipt_path.read_text())["status"] == "SYNTHETIC"
    try:
        capture._write_receipt_exclusive(receipt_path, {"status": "REPLACED"})
    except FileExistsError:
        pass
    else:
        raise AssertionError("public receipt writer replaced a prior receipt")

    xb, forcing = _synthetic_state_and_forcing()
    checkpoint = tmp_path / "failure-case" / "private" / "state.npz"
    failed_receipt = tmp_path / "failure-case" / "RESULT.json"
    calls = []
    result = capture.run_capture(
        xb=xb,
        forcings=(forcing,),
        y_bt=np.zeros((1, 7)),
        y_rq=np.zeros((1, 7)),
        xland=np.ones(1),
        clear_cfg=object(),
        rttov_cfg={},
        window_config=SimpleNamespace(dt=20.0, normalized_dry=True),
        obs_time=1,
        pool=object(),
        private_checkpoint=checkpoint,
        public_receipt=failed_receipt,
        case_root=tmp_path / "failure-case" / "H",
        native_intake_context_path=tmp_path / "never-opened.json",
        native_intake_context_sha256="unused",
        native_intake_npz_path=tmp_path / "never-opened.npz",
        native_intake_npz_sha256="unused",
        run_manifest={},
        analysis_runner=lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    assert result["status"] == "ANALYSIS_EXCEPTION"
    assert result["input_validity"]["status"] == "NOT_VALIDATED"
    assert result["numerical_return"]["minimizer_returned_state"] is False
    assert result["numerical_return"]["status"] == "FAILED_BEFORE_RETURN"
    assert result["failure_stage"] == "PRE_ANALYSIS"
    assert result["physical_matchup_and_science_acceptance"]["status"] == "NOT_ASSESSED"
    assert not checkpoint.exists()
    assert json.loads(failed_receipt.read_text())["status"] == "ANALYSIS_EXCEPTION"
    assert calls == []
    assert not checkpoint.parent.exists()
    returned = capture._numerical_return_failure_summary(
        True, {"result": SimpleNamespace()})
    assert returned == {
        "status": "RETURNED_BUT_CAPTURE_FAILED",
        "analysis_runner_returned": True,
        "minimizer_returned_state": True,
    }


def test_private_npz_roundtrips_four_distinct_full_states_and_forcings(tmp_path: Path):
    states = {
        "background_initial_state": _tagged_state(1),
        "returned_analysis_initial_state": _tagged_state(2),
        "background_slot_state": _tagged_state(3),
        "final_slot_state": _tagged_state(4),
    }
    forcing_window = (_tagged_forcing(1),)
    final_forcing = _tagged_forcing(2)
    host_mass = np.linspace(1.0, 39.0, 39, dtype=np.float32)
    payload = capture._private_payload(
        xb=states["background_initial_state"],
        accepted_initial_state=states["returned_analysis_initial_state"],
        background_slot_state=states["background_slot_state"],
        final_slot_state=states["final_slot_state"],
        forcings=forcing_window,
        final_slot_forcing=final_forcing,
        rho_d=torch.full((1, 39), 0.75, dtype=torch.float64),
        y_bt=np.arange(7, dtype=np.float64).reshape(1, 7),
        y_rq=np.zeros((1, 7), dtype=np.float64),
        rttov_cfg={"p_lay": np.arange(39), "p_half": np.arange(40),
                   "t_ref": np.arange(39), "q_ref": np.arange(39)},
        native_coordinates={"centers": {"values": np.arange(39)}},
        slot_calls=[{"mask": np.ones((1, 7)), "rad_quality": np.zeros((1, 7)),
                     "bt": np.full((1, 7), 240.0)}],
        receipt_metadata={"synthetic_fixture": True},
        host_dry_mass_background_kg_m2=host_mass,
        extra_private_arrays={
            **{f"b_sigma__{field}": getattr(_tagged_state(5), field).numpy()
               for field in State._fields},
            "optimizer_v_state_control": np.full((12, 1, 39), 6.0),
            "optimizer_v_theta_control": np.full(4, 7.0),
            "optimizer_final_gradient_v_state": np.full((12, 1, 39), 8.0),
            "optimizer_final_gradient_v_theta": np.full(4, 9.0),
            "optimizer_final_gradient_combined": np.full(12 * 39 + 4, 10.0),
            "optimizer_state__d": np.arange(12, dtype=np.float64),
            "fixed_eta_present": np.asarray([False]),
            "fixed_eta": np.empty(0),
        },
    )
    checkpoint = tmp_path / "private" / "roundtrip.npz"
    capture.write_private_npz_atomic(checkpoint, payload)

    expected_prefixes = tuple(states)
    expected_state_keys = {f"{prefix}__{field}"
                           for prefix in expected_prefixes for field in State._fields}
    with np.load(checkpoint, allow_pickle=False) as archive:
        assert expected_state_keys <= set(archive.files)
        assert len(expected_state_keys) == 4 * 12
        for prefix, state in states.items():
            for field in State._fields:
                np.testing.assert_array_equal(
                    archive[f"{prefix}__{field}"], getattr(state, field).numpy())
        for field in Forcing._fields:
            np.testing.assert_array_equal(
                archive[f"forcing_window_0__{field}"],
                getattr(forcing_window[0], field).numpy())
            np.testing.assert_array_equal(
                archive[f"final_slot_forcing__{field}"],
                getattr(final_forcing, field).numpy())
        np.testing.assert_array_equal(archive["final_slot_frozen_mask"], np.ones((1, 7)))
        np.testing.assert_array_equal(archive["final_slot_rad_quality"], np.zeros((1, 7)))
        np.testing.assert_array_equal(archive["final_slot_bt_K"], np.full((1, 7), 240.0))
        for field in State._fields:
            np.testing.assert_array_equal(
                archive[f"control__b_sigma__{field}"], getattr(_tagged_state(5), field).numpy())
        np.testing.assert_array_equal(
            archive["control__optimizer_v_state_control"], np.full((12, 1, 39), 6.0))
        np.testing.assert_array_equal(
            archive["control__optimizer_final_gradient_v_state"], np.full((12, 1, 39), 8.0))
        np.testing.assert_array_equal(archive["control__fixed_eta_present"], np.asarray([False]))
        assert archive["control__fixed_eta"].shape == (0,)
        np.testing.assert_array_equal(archive["optimizer_state__d"], np.arange(12))
        assert archive["host_dry_mass_background_kg_m2"].dtype == np.float32
        np.testing.assert_array_equal(archive["host_dry_mass_background_kg_m2"], host_mass)


def test_lbfgs_observer_preserves_original_quadratic_step_and_gradient():
    original_factory = torch.optim.LBFGS
    kwargs = {"lr": 0.7, "max_iter": 4, "history_size": 8,
              "line_search_fn": "strong_wolfe", "tolerance_grad": 1e-12}
    x_plain = torch.tensor([4.0, -2.0], dtype=torch.float64, requires_grad=True)
    x_observed = x_plain.detach().clone().requires_grad_(True)
    plain_calls = []
    observed_calls = []

    def closure_for(value, calls):
        def closure():
            calls.append(1)
            value.grad = None
            loss = ((value - torch.tensor([1.5, 0.25], dtype=torch.float64)) ** 2).sum()
            loss.backward()
            return loss
        return closure

    plain_optimizer = original_factory([x_plain], **kwargs)
    plain_loss = plain_optimizer.step(closure_for(x_plain, plain_calls))
    observation = {"constructor_calls": 0, "step_calls": 0, "step_returned": False}
    observed_factory = capture._observe_existing_lbfgs(original_factory, observation)
    observed_optimizer = observed_factory([x_observed], **kwargs)
    observed_loss = observed_optimizer.step(closure_for(x_observed, observed_calls))

    assert type(observed_optimizer) is type(plain_optimizer)
    torch.testing.assert_close(x_observed, x_plain, rtol=0.0, atol=0.0)
    torch.testing.assert_close(x_observed.grad, x_plain.grad, rtol=0.0, atol=0.0)
    torch.testing.assert_close(observed_loss, plain_loss, rtol=0.0, atol=0.0)
    assert len(observed_calls) == len(plain_calls)
    assert observation["constructor_calls"] == 1
    assert observation["step_calls"] == 1
    assert observation["step_returned"] is True
    assert observation["termination_status"] == "UNKNOWN"
    assert observation["termination_reason"] == "NOT_EXPOSED_BY_PYTORCH_LBFGS"
    assert observation["step_state"]["n_iter"] == plain_optimizer.state[x_plain]["n_iter"]
    assert observation["step_state"]["func_evals"] == plain_optimizer.state[x_plain]["func_evals"]
    assert observation["step_state"]["step_t"] == plain_optimizer.state[x_plain]["t"]
    failure_summary = capture._public_optimizer_failure_summary(observation)
    assert "optimizer" not in failure_summary
    assert "optimizer_state_arrays" not in failure_summary


def test_final_audit_signature_is_bound_to_frozen_mask_and_stable_trace():
    signature = "a" * 64
    result = SimpleNamespace(j_trace=[
        {"n_valid": {1: 7}, "signature": {1: signature}},
        {"n_valid": {1: 7}, "signature": {1: signature}},
    ])
    mask = torch.ones((1, 7), dtype=torch.float64)
    record = capture._final_audit_signature(result, obs_time=1, final_mask=mask)
    assert record["sha256"] == signature
    assert record["trace_entry_count"] == 2
    assert record["final_trace_index"] == 1
    assert record["all_trace_signatures_match"] is True
    assert record["final_frozen_mask"]["shape"] == [1, 7]
    assert record["final_frozen_mask"]["sha256_f64"] == capture.array_sha256(mask)

    result.j_trace[-1]["signature"][1] = "b" * 64
    with pytest.raises(RuntimeError, match="signature changed"):
        capture._final_audit_signature(result, obs_time=1, final_mask=mask)


def test_initial_zero_control_cost_is_separate_from_zero_mask_probe_cost():
    signature = "c" * 64
    mask = np.ones((1, 7), dtype=np.float64)
    zero_mask = np.zeros((1, 7), dtype=np.float64)
    result = SimpleNamespace(j_trace=[{
        "j_state": 0.0, "j_theta": 0.0, "j_obs": 12.75, "total": 12.75,
        "n_valid": {1: 7}, "signature": {1: signature},
    }, {
        "j_state": 1.0, "j_theta": 0.0, "j_obs": 8.0, "total": 9.0,
        "n_valid": {1: 7}, "signature": {1: signature},
    }])
    events = [
        {"call_index": 1, "grad": False, "returned": True,
         "J_huber": 0.0, "frozen_mask": zero_mask.tolist(),
         "fixed_mask": zero_mask.tolist(), "target_BT_K": np.full((1, 7), 240.0).tolist(),
         "BT_K": np.full((1, 7), 245.0).tolist(), "rad_quality": zero_mask.tolist()},
        {"call_index": 2, "grad": True, "returned": True,
         "J_huber": 12.75, "frozen_mask": mask.tolist(),
         "fixed_mask": mask.tolist()},
    ]
    accepted_signature = {"sha256": signature}
    initial = capture._initial_zero_control_closure(
        result, events, obs_time=1, final_audit_signature=accepted_signature,
        final_mask=torch.as_tensor(mask))
    probe = capture._background_quality_probe(events)

    assert initial["trace_index"] == 0
    assert initial["Jb_state"] == initial["Jtheta"] == 0.0
    assert initial["Jo"] == initial["Jtotal"] == 12.75
    assert initial["operator_signature_sha256"] == signature
    assert initial["frozen_mask"]["sha256_f64"] == capture.array_sha256(mask)
    assert probe["raw_J_huber"] == 0.0
    assert probe["cost_semantics"].startswith("non-grad background quality probe")
    assert probe["mask"]["sha256_f64"] == capture.array_sha256(zero_mask)
    assert probe["raw_J_huber"] != initial["Jo"]


def test_final_control_snapshot_reads_full_gradient_and_private_controls(tmp_path: Path):
    original_factory = torch.optim.LBFGS
    prior = default_param_prior(active=())
    v_state = torch.zeros((12, 1, 39), dtype=torch.float64, requires_grad=True)
    v_theta = torch.zeros((4,), dtype=torch.float64, requires_grad=True)
    observation = {"constructor_calls": 0, "step_calls": 0, "step_returned": False}
    optimizer = capture._observe_existing_lbfgs(original_factory, observation)(
        [v_state, v_theta], max_iter=2)

    def closure():
        v_state.grad = None
        v_theta.grad = None
        loss = ((v_state - 0.2) ** 2).sum() + ((v_theta - 0.1) ** 2).sum()
        loss.backward()
        return loss

    optimizer.step(closure)
    # Emulate the gradients assigned by run_dual_minimizer's existing final
    # accepted-state audit; the helper must read them without another closure.
    v_state.grad = torch.full_like(v_state, 0.01)
    v_theta.grad = torch.full_like(v_theta, -0.05)
    grad_state_l2 = float(torch.linalg.vector_norm(v_state.grad))
    grad_theta_l2 = float(torch.linalg.vector_norm(v_theta.grad))
    xb = _tagged_state(0)
    b_sigma = _tagged_state(5)
    x_analysis, _ = cvt_apply(xb, b_sigma, v_state, CVT_LINEAR)
    result = SimpleNamespace(
        v_state=v_state.detach().clone(), v_theta=v_theta.detach().clone(),
        grad_norm_final=grad_state_l2, grad_theta_norm_final=grad_theta_l2,
        x_analysis=x_analysis,
        theta_analysis=params_from_vtheta(prior, v_theta.detach(), live=False),
        n_window_evals=3, n_audit_evals=1)
    package = {"b_sigma": b_sigma, "param_prior": prior, "cvt": CVT_LINEAR}

    private, public, metadata = capture._final_control_snapshot(
        observation, result, package, SimpleNamespace(eta=None, eta_pre=None), xb)

    assert private["optimizer_v_state_control"].shape == (12, 1, 39)
    assert private["optimizer_final_gradient_v_state"].shape == (12, 1, 39)
    np.testing.assert_array_equal(private["optimizer_final_gradient_v_state"], 0.01)
    np.testing.assert_array_equal(private["optimizer_final_gradient_v_theta"], -0.05)
    for field in State._fields:
        np.testing.assert_array_equal(private[f"b_sigma__{field}"],
                                      getattr(b_sigma, field).numpy())
    assert private["fixed_eta"].shape == (0,)
    assert private["fixed_eta_pre"].shape == (0,)
    assert public["optimizer"]["termination_reason"] == "NOT_EXPOSED_BY_PYTORCH_LBFGS"
    assert public["optimizer"]["termination_status"] == "UNKNOWN"
    assert public["final_control_gradient"]["state_l2_norm"] == grad_state_l2
    assert public["final_control_gradient"]["theta_l2_norm"] == grad_theta_l2
    assert public["final_control_gradient"]["x_analysis_rederived_exactly_from_v_state_and_b_sigma"] is True
    assert public["final_control_gradient"]["theta_analysis_rederived_exactly_from_v_theta_and_prior"] is True
    assert public["control_background"]["fixed_eta"]["present"] is False
    assert "optimizer_v_state_control" not in public
    assert metadata["control_capture"]["fixed_eta_pre_present"] is False
    state_array_refs = public["optimizer"]["state_arrays"]
    assert state_array_refs
    assert set(state_array_refs) <= set(private)
    for array_key, item in state_array_refs.items():
        assert item["private_npz_key"] == array_key

    all_states = {
        "background_initial_state": xb,
        "returned_analysis_initial_state": x_analysis,
        "background_slot_state": _tagged_state(1),
        "final_slot_state": _tagged_state(2),
    }
    forcing = _tagged_forcing(1)
    checkpoint_payload = capture._private_payload(
        xb=xb, accepted_initial_state=x_analysis,
        background_slot_state=all_states["background_slot_state"],
        final_slot_state=all_states["final_slot_state"],
        forcings=(forcing,), final_slot_forcing=forcing,
        rho_d=torch.ones((1, 39), dtype=torch.float64),
        y_bt=np.zeros((1, 7)), y_rq=np.zeros((1, 7)),
        rttov_cfg={}, native_coordinates={}, slot_calls=[],
        receipt_metadata={"synthetic_fixture": True},
        extra_private_arrays=private)
    checkpoint = tmp_path / "private" / "control_capture.npz"
    capture.write_private_npz_atomic(checkpoint, checkpoint_payload)
    with np.load(checkpoint, allow_pickle=False) as archive:
        for item in public["final_control_gradient"]["arrays"].values():
            key = item["private_npz_key"]
            assert key in archive.files
            assert capture.array_sha256(archive[key]) == item["sha256_f64"]
        for item in public["optimizer"]["state_arrays"].values():
            key = item["private_npz_key"]
            assert key in archive.files
            assert capture.array_sha256(archive[key]) == item["sha256_f64"]
        for item in public["control_background"]["b_sigma_by_state_field"].values():
            key = item["private_npz_key"]
            assert key in archive.files
            assert capture.array_sha256(archive[key]) == item["sha256_f64"]
        for field, item in public["control_background"].items():
            if field.endswith("private_npz_key"):
                assert item in archive.files
    state_array_refs = public["optimizer"]["state_arrays"]
    assert state_array_refs
    assert set(state_array_refs) <= set(private)
    for array_key, item in state_array_refs.items():
        assert item["private_npz_key"] == array_key
