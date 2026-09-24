import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from moment_validity import (  # noqa: E402
    classify_volume_moments,
    mask_admissible_output,
)


BOUNDS = (1.0e-12, 1.0e-6)  # explicit synthetic species interval, kg per particle


def classify(c, n, *, c_floor=1.0e-12, n_floor=1.0e-8):
    return classify_volume_moments(
        c,
        n,
        mass_floor_kg_m3=c_floor,
        number_floor_m3=n_floor,
        mean_particle_mass_bounds_kg=BOUNDS,
        basis="volume",
    )


def test_tiny_below_floor_pairs_are_inactive_without_mass_per_particle_test():
    state = classify([1.0e-30, 0.0], [1.0e-24, 0.0])

    assert state.inactive.tolist() == [True, True]
    assert state.active.tolist() == [False, False]
    assert state.admissible.tolist() == [False, False]
    assert np.isnan(state.mean_particle_mass_kg).all()
    assert state.reason.tolist() == ["inactive_below_floor"] * 2


def test_positive_mass_with_zero_number_is_active_but_incompatible():
    state = classify([1.0e-4, 1.0e-4], [0.0, 1.0e9])

    assert state.active.tolist() == [True, True]
    assert state.admissible.tolist() == [False, False]
    assert state.reason.tolist() == [
        "one_moment_below_floor",
        "mean_mass_out_of_range",
    ]
    with pytest.raises(ValueError, match="active C,N pair is inadmissible"):
        mask_admissible_output(state, [np.nan, np.nan])


def test_same_physical_pair_and_floors_preserve_class_under_density_conversion():
    rho_d = 0.4
    c_d = np.array([2.0e-5, 2.0e-14])
    n_d = np.array([2.0e6, 2.0e-10])
    c_floor_d, n_floor_d = 1.0e-8, 1.0e-4
    in_dry = classify_volume_moments(
        rho_d * c_d,
        rho_d * n_d,
        mass_floor_kg_m3=rho_d * c_floor_d,
        number_floor_m3=rho_d * n_floor_d,
        mean_particle_mass_bounds_kg=BOUNDS,
        basis="volume",
    )
    in_volume = classify_volume_moments(
        [8.0e-6, 8.0e-15],
        [8.0e5, 8.0e-11],
        mass_floor_kg_m3=4.0e-9,
        number_floor_m3=4.0e-5,
        mean_particle_mass_bounds_kg=BOUNDS,
        basis="volume",
    )

    assert in_dry.reason.tolist() == ["admissible", "inactive_below_floor"]
    assert in_dry.reason.tolist() == in_volume.reason.tolist()
    assert in_dry.admissible.tolist() == in_volume.admissible.tolist()
    np.testing.assert_allclose(
        in_dry.mean_particle_mass_kg,
        in_volume.mean_particle_mass_kg,
        rtol=4 * np.finfo(float).eps,
        atol=0,
        equal_nan=True,
    )


def test_validity_mask_does_not_inspect_inactive_producer_slots():
    class Unreadable:
        def __float__(self):
            raise AssertionError("inactive producer output was read")

    state = classify([1.0e-4, 0.0], [1.0e5, 0.0])
    output = np.array([2.5, Unreadable()], dtype=object)

    assert mask_admissible_output(state, output).tolist() == [2.5, 0.0]


def test_validity_mask_rejects_nonfinite_output_only_on_admissible_cells():
    state = classify([1.0e-4, 0.0], [1.0e5, 0.0])

    with pytest.raises(ValueError, match="finite on admissible cells"):
        mask_admissible_output(state, [np.nan, np.nan])


def test_python_cloud_and_progb_inactive_outputs_are_masked_but_not_native_proof():
    import torch

    from kdm6 import constants as c
    from kdm6.cloud_dsd import default_cloud_dsd_params, diag_cloud_slope_torch
    from kdm6.progb import RHO_MID, default_progb_params, progb_param_torch

    dtype = torch.float64
    qg = torch.tensor([[0.0, 0.5 * c.QCRMIN, 2.0 * c.QCRMIN]], dtype=dtype)
    bg = torch.tensor([[0.0, 0.5e-15, 0.5e-15]], dtype=dtype)
    progb = progb_param_torch(qg, bg, params=default_progb_params())
    assert torch.isfinite(progb.rhox).all()
    assert progb.rhox[0, :2].tolist() == [RHO_MID, RHO_MID]
    assert progb.bg[0, :2].tolist() == bg[0, :2].tolist()
    assert torch.count_nonzero(progb.cmg[0, :2]) == 0
    assert torch.count_nonzero(progb.pidn0g[0, :2]) == 0
    assert torch.count_nonzero(progb.avtg[0, :2]) == 0

    qc = torch.tensor([[0.0, 1.0e-3, 1.0e-3]], dtype=dtype)
    nc = torch.tensor([[1.0e8, 0.0, 1.0e8]], dtype=dtype)
    den = torch.ones_like(qc)
    slope = diag_cloud_slope_torch(qc, nc, den, params=default_cloud_dsd_params())
    assert torch.isfinite(slope).all()
    assert slope[0, 0].item() == 1.0 / default_cloud_dsd_params().lamdacmax
    assert slope[0, 1].item() == 1.0 / default_cloud_dsd_params().lamdacmax

    # Python uses explicit safe inactive values; this does not establish that
    # native Fortran INTENT(OUT) outputs are defined on the same branch.


def test_unconverted_floor_changes_a_valid_physical_pair():
    # q_d=2e-8, n_d=200, rho=.25: C/N=1e-10 kg/particle in both encodings.
    correct = classify([5e-9], [50.0], c_floor=2.5e-9, n_floor=0.25)
    wrong = classify([5e-9], [50.0], c_floor=1e-8, n_floor=1.0)
    assert correct.admissible.tolist() == [True]
    assert wrong.reason.tolist() == ["one_moment_below_floor"]
