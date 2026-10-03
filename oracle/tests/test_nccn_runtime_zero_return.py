"""Runtime guard for the retained no-op NCCN density round-trip failure."""
from pathlib import Path

import numpy as np
import torch

from kdm6.runtime import _kdm6_pure, make_parameters
from kdm6.state import State, Forcing


def test_actual_noop_nccn_is_identity_at_both_original_fd_endpoints():
    fixture = Path(__file__).resolve().parents[2] / 'harness/evidence/nccn_return_baseline_failed_2026-10-01.npz'
    with np.load(fixture) as saved:
        state = np.array(saved['state_in'])
        forcing = Forcing(*(torch.from_numpy(np.array(row)).reshape(1, -1) for row in saved['forcing']))
        direction = np.array(saved['direction'])
        land = torch.tensor([float(saved['xland'])], dtype=torch.float64)
    for sign in (-1., 0., 1.):
        trial = State(*(torch.from_numpy(row.copy()).reshape(1, -1)
                        for row in state + sign * 1e-4 * direction))
        result = _kdm6_pure(trial, forcing, make_parameters(), dt=20., xland=land,
            ncmin_land=10., ncmin_sea=10., dry_number=True, normalize_ice_handoff=True)
        assert torch.equal(result.nccn, trial.nccn)
