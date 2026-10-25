import numpy as np
import pytest

pytest.importorskip("torch", reason="native checkpoint profile tensors require Torch")

from harness.native_checkpoint_observation import (
    _flat_profile,
    _rho_d_from_al,
    checkpoint_output_from_fields,
    original_chunk_bounds,
)


def _fields(ny=2, nx=3, levels=2):
    shape = (levels, ny, nx)
    idx = np.arange(np.prod(shape), dtype=np.float32).reshape(shape)
    center = {
        name: idx + np.float32(offset)
        for name, offset in {
            "THM_2": 1.0, "QVAPOR": 2.0, "QCLOUD": 3.0, "QICE": 4.0,
            "QSNOW": 5.0, "QNCLOUD": 6.0, "QNICE": 7.0, "QRAIN": 8.0,
            "QGRAUP": 9.0, "QNCCN": 10.0, "QNRAIN": 11.0, "QIB": 12.0,
            "P": 13.0, "PB": 90000.0,
        }.items()
    }
    center["QNCLOUD"][0, 0, 0] = -7.0  # raw initial moment is retained; no floor here
    center["AL"] = np.full(shape, 0.25, dtype=np.float32)
    center["ALB"] = np.full(shape, 0.75, dtype=np.float32)
    center["RHO"] = np.full(shape, 99.0, dtype=np.float32)  # deliberately not used as rho_d
    for name, offset in (("PH_2", 100.0), ("PHB", 500.0)):
        center[name] = np.arange(levels + 1, dtype=np.float32)[:, None, None] + np.float32(offset)
        center[name] = np.broadcast_to(center[name], (levels + 1, ny, nx)).copy()
    return center


def test_native_batch_uses_actual_center_pressure_interfaces_and_dry_density():
    fields = _fields()
    flat = np.array([1, 4, 5], dtype=np.int32)  # non-square 2x3 grid, C-order j*nx+i
    output, selected = checkpoint_output_from_fields(fields, flat, nx=3, ny=2, levels=2)

    expected_p = np.add(
        _flat_profile(fields["P"], flat, nx=3, ny=2, levels=2),
        _flat_profile(fields["PB"], flat, nx=3, ny=2, levels=2),
        dtype=np.float32,
    ).astype(np.float64)
    expected_phi = np.add(
        _flat_profile(fields["PH_2"], flat, nx=3, ny=2, levels=3),
        _flat_profile(fields["PHB"], flat, nx=3, ny=2, levels=3),
        dtype=np.float32,
    ).astype(np.float64)
    expected_rho = _rho_d_from_al(
        _flat_profile(fields["AL"], flat, nx=3, ny=2, levels=2),
        _flat_profile(fields["ALB"], flat, nx=3, ny=2, levels=2),
    ).astype(np.float64)

    np.testing.assert_array_equal(output.native_profile.p_center_Pa.numpy(), expected_p)
    np.testing.assert_array_equal(output.native_profile.phi_interfaces.numpy(), expected_phi)
    np.testing.assert_array_equal(output.rho_d.numpy(), expected_rho)
    assert np.all(output.rho_d.numpy() != 99.0)  # the saved RHO field is only cross-check evidence
    np.testing.assert_array_equal(output.native_profile.thm_pert.numpy(), selected["THM_2"].astype(np.float64))
    np.testing.assert_array_equal(output.native_profile.qv.numpy(), selected["QVAPOR"].astype(np.float64))


def test_all_raw_checkpoint_moments_are_widened_unchanged_without_flooring():
    fields = _fields()
    flat = np.array([0, 2, 5], dtype=np.int32)
    output, selected = checkpoint_output_from_fields(fields, flat, nx=3, ny=2, levels=2)
    assert output.cloud_state.nc[0, 0].item() == -7.0
    for target, source in (("qc", "QCLOUD"), ("qi", "QICE"), ("qs", "QSNOW"),
                           ("nc", "QNCLOUD"), ("ni", "QNICE"), ("qr", "QRAIN"),
                           ("qg", "QGRAUP"), ("nccn", "QNCCN"), ("nr", "QNRAIN"),
                           ("bg", "QIB")):
        np.testing.assert_array_equal(
            getattr(output.cloud_state, target).numpy(),
            selected[source].astype(np.float64),
        )


def test_original_full_domain_partition_keeps_tail_and_every_flat_index_once():
    bounds = original_chunk_bounds()
    assert len(bounds) == 129
    assert [stop - start for start, stop in bounds[:-1]] == [512] * 128
    assert bounds[-1] == (65536, 65988)
    assert bounds[-1][1] - bounds[-1][0] == 452
    flat = np.concatenate([np.arange(start, stop, dtype=np.int32) for start, stop in bounds])
    np.testing.assert_array_equal(flat, np.arange(65988, dtype=np.int32))


def test_native_source_profile_flattening_uses_j_times_nx_plus_i():
    values = np.arange(2 * 3 * 4, dtype=np.float32).reshape(2, 3, 4)
    flat = np.array([1, 4, 11], dtype=np.int32)
    result = _flat_profile(values, flat, nx=4, ny=3, levels=2)
    np.testing.assert_array_equal(result, np.array([[1, 13], [4, 16], [11, 23]], dtype=np.float32))
