"""Synthetic storage-boundary checks; these tests never open native inputs."""
from __future__ import annotations

import json
import stat
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch

import capture_tq_state as capture
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
    assert result["physical_matchup_and_science_acceptance"]["status"] == "NOT_ASSESSED"
    assert not checkpoint.exists()
    assert json.loads(failed_receipt.read_text())["status"] == "ANALYSIS_EXCEPTION"
    assert calls == []
    assert not checkpoint.parent.exists()


def test_private_npz_roundtrips_four_distinct_full_states_and_forcings(tmp_path: Path):
    states = {
        "background_initial_state": _tagged_state(1),
        "returned_analysis_initial_state": _tagged_state(2),
        "background_slot_state": _tagged_state(3),
        "final_slot_state": _tagged_state(4),
    }
    forcing_window = (_tagged_forcing(1),)
    final_forcing = _tagged_forcing(2)
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
