"""Golden-vector schema for parity harness.

Validates that a golden-vector directory conforms to the layout described in
`README.md`. Used by `run_parity.py` and `import_fortran.py`.

Storage format: a directory containing
  - state_in.npz / state_out.npz  — prognostic state arrays
  - forcing.npz                   — p/den/delz/dend
  - meta.json                     — scalars, surface_accum, metadata (typed JSON)

We avoid pickled object arrays (npz of dicts) for security: untrusted .npz
files with `allow_pickle=True` can execute arbitrary code on load.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import NamedTuple

import numpy as np


SCHEMA_EXCLUDED_FIELDS = frozenset({"nccn", "NCCN", "qnn", "QNN", "nn", "NN"})


class StateFields(NamedTuple):
    """11 prognostic state fields the Fortran `kdm62D` mutates.

    NCCN/QNN/NN is intentionally outside this T3 golden-vector schema. The
    current harness compares microphysics-level `CoordinatorState` fields only;
    wrapper-level NCCN pass-through is covered by libtorch/C ABI tests.
    """

    qv: np.ndarray
    qc: np.ndarray
    qr: np.ndarray
    qs: np.ndarray
    qg: np.ndarray
    qi: np.ndarray
    nc: np.ndarray
    nr: np.ndarray
    ni: np.ndarray
    brs: np.ndarray
    t: np.ndarray


class ForcingFields(NamedTuple):
    """4 forcing arrays held constant across one kdm62D call."""

    p: np.ndarray
    den: np.ndarray
    delz: np.ndarray
    dend: np.ndarray


class GoldenVector(NamedTuple):
    state_in: StateFields
    forcing: ForcingFields
    scalars: dict        # dtcld, ccn0, qmin, ...
    state_out: StateFields
    surface_accum: dict  # rain_mm, snow_mm, graupel_mm (each a list of length B)
    metadata: dict


_REQUIRED_SCALARS = {"dtcld", "ccn0", "qmin", "ncmin_land", "ncmin_sea"}


def load(path) -> GoldenVector:
    """Load and validate a golden-vector directory."""
    root = Path(path)
    if not root.is_dir():
        raise ValueError(f"golden vector path must be a directory, got {root}")

    state_in_npz = np.load(root / "state_in.npz", allow_pickle=False)
    state_out_npz = np.load(root / "state_out.npz", allow_pickle=False)
    forcing_npz = np.load(root / "forcing.npz", allow_pickle=False)
    meta = json.loads((root / "meta.json").read_text())

    state_in = StateFields(*[state_in_npz[f] for f in StateFields._fields])
    state_out = StateFields(*[state_out_npz[f] for f in StateFields._fields])
    forcing = ForcingFields(*[forcing_npz[f] for f in ForcingFields._fields])

    scalars = meta["scalars"]
    surface_accum = meta.get("surface_accum", {})
    metadata = meta.get("metadata", {})

    missing = _REQUIRED_SCALARS - scalars.keys()
    if missing:
        raise ValueError(f"golden vector {root} missing scalars: {missing}")

    K = state_in.qv.shape[-1]
    for name, arr in zip(StateFields._fields, state_in):
        if arr.shape[-1] != K:
            raise ValueError(f"input/state/{name} K-dim mismatch: {arr.shape}")

    return GoldenVector(
        state_in=state_in,
        forcing=forcing,
        scalars=scalars,
        state_out=state_out,
        surface_accum=surface_accum,
        metadata=metadata,
    )


def save(path, *, state_in: StateFields, forcing: ForcingFields,
         scalars: dict, state_out: StateFields,
         surface_accum: dict | None = None,
         metadata: dict | None = None) -> None:
    """Write a validated golden-vector directory."""
    root = Path(path)
    root.mkdir(parents=True, exist_ok=True)

    np.savez(root / "state_in.npz",
             **{f: getattr(state_in, f) for f in StateFields._fields})
    np.savez(root / "state_out.npz",
             **{f: getattr(state_out, f) for f in StateFields._fields})
    np.savez(root / "forcing.npz",
             **{f: getattr(forcing, f) for f in ForcingFields._fields})

    meta = {
        "scalars": scalars,
        "surface_accum": surface_accum or {},
        "metadata": metadata or {},
    }
    (root / "meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True))
