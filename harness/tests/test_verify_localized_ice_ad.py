import ctypes as ct

import numpy as np
import pytest

import harness.verify_localized_ice_ad as verify


def test_batch_ffi_uses_fortran_one_by_level_by_column_field_blocks(
    tmp_path, monkeypatch
):
    batch, levels = 2, 4
    state = np.arange(12 * batch * levels, dtype=np.float64).reshape(12, batch, levels)
    forcing = 1000 + np.arange(4 * batch * levels, dtype=np.float64).reshape(
        4, batch, levels
    )
    calls = []

    class Function:
        def __init__(self, callback):
            self.callback = callback

        def __call__(self, *args):
            return self.callback(*args)

    def forward(
        s, f, im, kme, jme, dt, value_only, output, handle, land, nl, ns, variant, dry
    ):
        calls.append((im, kme, jme, dt, value_only, nl, ns, variant, dry))
        assert (im, kme, jme) == (1, 4, 2)
        sb = np.ctypeslib.as_array(s, shape=(12 * batch * levels,))
        fb = np.ctypeslib.as_array(f, shape=(4 * batch * levels,))
        # Independent ABI offset i + im*k + im*kme*j within a field.
        assert sb[11 * 8 + 0 + 1 * 3 + 1 * 4 * 1] == state[11, 1, 3]
        assert fb[3 * 8 + 0 + 1 * 2 + 1 * 4 * 1] == forcing[3, 1, 2]
        assert np.ctypeslib.as_array(land, shape=(2,)).tolist() == [1.0, 2.0]
        np.ctypeslib.as_array(output, shape=sb.shape)[:] = sb
        return 0

    class Library:
        kdm6_step_ad_state_forcing_c = Function(forward)
        kdm6_handle_state_forcing_jvp_c = Function(lambda *args: 0)
        kdm6_handle_state_forcing_vjp_c = Function(lambda *args: 0)
        kdm6_handle_closep_c = Function(lambda *args: 0)

    monkeypatch.setattr(verify.ct, "CDLL", lambda _: Library())
    kernel = verify.BatchKernel(tmp_path / "fake.dylib", np.array([1.0, 2.0]), levels)
    actual, handle = kernel.forward(state, forcing)
    np.testing.assert_array_equal(actual, state)
    assert isinstance(handle, ct.c_void_p)
    assert calls == [(1, 4, 2, 20.0, 1, 10.0, 10.0, 0, 0)]
    with pytest.raises(ValueError):
        kernel.forward(state.astype(np.float32), forcing)
    assert len(calls) == 1


def test_eight_directions_localize_only_the_target_and_separate_forcing_rows():
    state = np.ones((12, 3, 5), dtype=np.float64)
    forcing = np.ones((4, 3, 5), dtype=np.float64)
    all_directions = verify.directions(state, forcing, 1)
    assert len(all_directions) == 8
    for ds, df in all_directions.values():
        assert not np.any(ds[:, [0, 2]]) and not np.any(df[:, [0, 2]])
    for row, name in enumerate(("density", "pii", "pressure", "delz")):
        ds, df = all_directions[name]
        assert not np.any(ds)
        assert np.any(df[row, 1])
        assert not np.any(np.delete(df, row, axis=0))
    pairs = [pair for name, pair in all_directions.items() if name != "mixed"]
    for block in (0, 1):
        np.testing.assert_array_equal(
            all_directions["mixed"][block], sum(p[block] for p in pairs)
        )


@pytest.mark.parametrize("field", [0, 7, 16])
def test_fd_gate_checks_each_output_field_over_all_columns(field):
    tangent = np.zeros((17, 2, 3), dtype=np.float64)
    fd = tangent.copy()
    fd[field, 1, 2] = float(verify.SCALES[field, 0, 0]) * 1.5 * verify.ATOL[field]
    metrics = verify.fd_metrics(fd, tangent)
    assert metrics["max_tolerance_ratio"] > 1.0
    assert metrics["per_field_tolerance_ratio"][verify.FIELDS[field]] > 1.0
    assert all(
        v == 0
        for name, v in metrics["per_field_tolerance_ratio"].items()
        if name != verify.FIELDS[field]
    )


def test_finish_tendency_direct_old_state_cancels_identity_kernel():
    pytest.importorskip(
        "torch", reason="native thermo-finish derivative needs optional Torch"
    )
    from oracle.kdm6.native_finish import FinishConfig, ZeroOutConfig

    state = np.ones((12, 2, 4), dtype=np.float64)
    state[0] = 300.0
    state[1:7] = 0.001
    operator = verify.BatchFinish(
        FinishConfig(dt=20.0, alpha=1.6083624362945557, t0=300.0, mp_tend_lim=10.0),
        ZeroOutConfig(mode=2, threshold=1e-8),
    )
    direction = np.sin(np.arange(state.size).reshape(state.shape) + 1.0) * 0.01
    tangent = operator.jvp(state, state.copy(), direction, direction)
    # H/QV/QC rates are zero under an identity physical update, including derivatives.
    np.testing.assert_array_equal(tangent[13:16], np.zeros((3, 2, 4)))
    u = np.zeros((17, 2, 4), dtype=np.float64)
    u[13:16] = np.arange(24).reshape(3, 2, 4) + 1.0
    old, seed = operator.vjp(state, state.copy(), u)
    assert np.any(old != 0.0)
    np.testing.assert_allclose(old + seed[:3], 0.0, atol=1e-11, rtol=0.0)


def test_entry_interior_pair_directions_hold_entry_ratios_without_changing_state():
    state = np.ones((12, 2, 4), dtype=np.float64)
    state[7, 1] = [1e8, 1.0000005e8, 1.1e8, 2e10]
    state[6, 1] = 900.0 * state[11, 1]
    forcing = np.ones((4, 2, 4), dtype=np.float64)
    before = state.copy()
    chosen = verify.directions(state, forcing, 1, "entry_interior_pairs")
    mass = chosen["cloud_mass"][0]
    for qrow, nrow in ((2, 8), (3, 10), (4, 9), (6, 11)):
        np.testing.assert_allclose(
            mass[qrow, 1] / state[qrow, 1],
            mass[nrow, 1] / state[nrow, 1],
            rtol=2e-16,
            atol=0.0,
        )
    nn = chosen["number"][0][7, 1]
    assert nn[0] == nn[1] == nn[3] == 0.0 and nn[2] != 0.0
    for eps in verify.EPSILONS:
        assert 1e8 < state[7, 1, 2] - abs(eps * nn[2])
        assert state[7, 1, 2] + abs(eps * nn[2]) < 2e10
    np.testing.assert_array_equal(state, before)
    assert np.any(
        verify.directions(state, forcing, 1, "raw")["number"][0][7, 1, [0, 3]]
    )


def test_finish_branch_signature_assigns_exact_limit_to_clipped_side():
    pytest.importorskip(
        "torch", reason="native finish configuration requires optional Torch"
    )
    from oracle.kdm6.native_finish import FinishConfig, ZeroOutConfig

    state = np.ones((12, 1, 2), dtype=np.float64)
    state[0] = 300.0
    operator = verify.BatchFinish(
        FinishConfig(dt=20.0, alpha=1.6083624362945557, t0=300.0, mp_tend_lim=10.0),
        ZeroOutConfig(mode=2, threshold=1e-8),
    )
    tied = state.copy()
    tied[0] += 200.0
    outside = tied.copy()
    outside[0] += 1.0
    inside = tied.copy()
    inside[0] -= 1.0
    assert operator.branch(state, tied) == operator.branch(state, outside)
    assert operator.branch(state, tied) != operator.branch(state, inside)


def test_substep_dump_is_refused_before_any_model_file_or_library_access(
    tmp_path, monkeypatch
):
    pytest.importorskip("torch", reason="verifier imports optional Torch")
    monkeypatch.setenv("KDM6_ICE_FACTORIAL_MODE", "norm_actual")
    monkeypatch.setenv("KDM6_SUBSTEP_DUMP", str(tmp_path / "dump"))
    with pytest.raises(ValueError, match="bulk trace must be off"):
        verify.run(
            tmp_path / "missing_case",
            tmp_path / "missing_library",
            "0" * 64,
            tmp_path / "missing_finish",
            0,
            tmp_path / "output",
        )
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("passed,expected_status", [(True, 0), (False, 1)])
def test_cli_exit_status_follows_written_verification_gate(
    tmp_path, monkeypatch, passed, expected_status
):
    seen = []

    def measured(*args):
        seen.append(args)
        return {"passed": passed}

    monkeypatch.setattr(verify, "run", measured)
    args = []
    for name in ("case", "library", "finish-reference", "output"):
        args.extend(["--" + name, str(tmp_path / name)])
    args.extend(["--library-sha256", "0" * 64, "--target", "0"])
    assert verify.main(args) == expected_status
    assert len(seen) == 1 and seen[0][-1] == "raw"
