"""P4 -- RttovInput serialization (design 7, 14.3; M4).

`pack_rttov_input` is the **torch -> numpy boundary**: it serializes the already-
RTTOV-unit torch tensors from `model_to_rttov_tensors` (P2) into an in-memory
`RttovInput` (numpy profile arrays + validated config + config-hash). It does NO
unit conversion (that finished in P2) and NO autograd-relevant work -- it detaches
to numpy, so it sits OUTSIDE the graph (RttovObsOp.backward supplies the gradient
via K^T·λ_BT, design 14.3).

Forced config (design 4.6/14.5), all REQUIRED (no permissive default -- a wrong
RTTOV option silently changes what BT/K mean): `adk_bt=True` (thermal K seed in BT
space), `store_rad=True` (RADIANCE%BT + rad_quality exposed), `gas_units=2`
(ppmv over moist air), `mmr_hydro=False` (cloud content in g/m^3). Particle size
is user-Deff via positive HydroDeff6/7 (gate = hydro_deff>0), not a `'user'` enum.

Writing the RttovInput to the on-disk rttov_test case (the env-coupled
profile-file format consumed by `rttov_runner.run_rttov_k(case_dir)`) is a thin
separate adapter (`write_rttov_case`, deferred -- needs the AD-RTTOV case
template); the autograd closure (P6) is exercised with a mock runner that takes
`RttovInput -> (bt, K)` directly, so this serialization is fully testable offline.
"""
from __future__ import annotations

import hashlib
import math
from typing import NamedTuple


# Forced RTTOV options (design 4.6/14.5). Each is REQUIRED to equal these values.
_REQUIRED_GAS_UNITS = 2          # ppmv over moist air
_REQUIRED_MMR_HYDRO = False      # cloud content in g/m^3
_REQUIRED_ADK_BT = True          # thermal K seed -> BT space (BT-K, not radiance-K)
_REQUIRED_STORE_RAD = True       # exposes RADIANCE%BT + rad_quality


class RttovInputConfig(NamedTuple):
    """Static RTTOV run config (not the profile). Times/grids derived upstream.

    ``channels`` is the 1-based RTTOV channel list. ``coef_id`` identifies the
    coefficient file (provenance/config-hash only -- the binary stays in
    AD-RTTOV). The four forced options must equal their required values.
    ``surface``/``geometry`` are opaque dicts passed through to the runner.
    """
    coef_id: str
    channels: tuple
    gas_units: int = _REQUIRED_GAS_UNITS
    mmr_hydro: bool = _REQUIRED_MMR_HYDRO
    adk_bt: bool = _REQUIRED_ADK_BT
    store_rad: bool = _REQUIRED_STORE_RAD
    surface: dict | None = None
    geometry: dict | None = None


class RttovInput(NamedTuple):
    """Serialized RTTOV input: numpy profile arrays + config + config-hash.

    ``profile`` maps RTTOV field -> numpy array ([nprofiles, nlayers] for
    T/Q/content, [nprofiles, nlevels] for P_HALF). ``config_hash`` is a defensive
    fingerprint (design 7) of the coef + channels + options + grid; a separate
    value-only direct run must match it.
    """
    profile: dict
    config: RttovInputConfig
    config_hash: str
    nprofiles: int
    nlayers: int


def _require_options(cfg) -> None:
    """Fail unless the four forced RTTOV options are exactly the required values.

    These are REQUIRED, not defaulted-and-trusted: silently running with
    adk_bt=False would make TK/GasesK radiance-K (not BT-K) and break the entire
    obs-loss/adjoint contract -- a wrong option silently changes what BT/K mean.
    """
    bad = []
    if cfg.gas_units != _REQUIRED_GAS_UNITS:
        bad.append(f"gas_units={cfg.gas_units!r} (must be {_REQUIRED_GAS_UNITS}, ppmv moist)")
    if bool(cfg.mmr_hydro) != _REQUIRED_MMR_HYDRO:
        bad.append(f"mmr_hydro={cfg.mmr_hydro!r} (must be {_REQUIRED_MMR_HYDRO}, g/m^3)")
    if bool(cfg.adk_bt) != _REQUIRED_ADK_BT:
        bad.append(f"adk_bt={cfg.adk_bt!r} (must be {_REQUIRED_ADK_BT}; else K is radiance-K)")
    if bool(cfg.store_rad) != _REQUIRED_STORE_RAD:
        bad.append(f"store_rad={cfg.store_rad!r} (must be {_REQUIRED_STORE_RAD}; else no BT/quality)")
    if bad:
        raise ValueError("RTTOV config violates the forced contract (design 4.6/14.5): "
                         + "; ".join(bad))
    if not cfg.channels:
        raise ValueError("RttovInputConfig.channels is empty -- need >=1 RTTOV channel.")
    if not cfg.coef_id:
        raise ValueError("RttovInputConfig.coef_id is required (provenance + config-hash).")


def _to_numpy_2d(tensor, name):
    """Detach a torch tensor to a finite 2-D [nprofiles, n] numpy array.

    Detach is the graph boundary (design 14.3 -- grad re-enters via K^T·λ_BT, not
    through this numpy). A non-finite input is rejected (it would silently corrupt
    the RTTOV run); a 1-D column is promoted to [1, n] (single profile).
    """
    import numpy as np  # local import: keep module import-light / torch-optional
    arr = tensor.detach().to("cpu").to(torch_float64()).numpy()
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    if arr.ndim != 2:
        raise ValueError(f"{name} must be 1-D or 2-D (got ndim={arr.ndim}).")
    if not np.isfinite(arr).all():
        raise ValueError(f"{name} has non-finite values -- invalid RTTOV input.")
    return arr


def torch_float64():
    import torch
    return torch.float64


# All-sky cloud profile fields (design 9.1): attr on RttovProfileTensors -> RTTOV
# PROFILES_K field key. Content HYDRO6/7 [g/m^3], effective DIAMETER HYDRO_DEFF6/7
# [micron], cloud fraction CFRAC. Present only in cloud mode.
_CLOUD_FIELD_MAP = (("clw", "HYDRO6"), ("ciw", "HYDRO7"),
                    ("deff_liq", "HYDRO_DEFF6"), ("deff_ice", "HYDRO_DEFF7"),
                    ("cfrac", "CFRAC"))


def _canon_mapping(m):
    """Order-independent, number-normalized canonical form of a dict / list-of-dicts /
    None, for hashing. (30 and 30.0 must hash the same; key order must not matter.)"""
    if m is None:
        return None
    if isinstance(m, (list, tuple)):
        return tuple(_canon_mapping(x) for x in m)
    if isinstance(m, dict):
        return tuple(sorted((str(k), _canon_mapping(v)) for k, v in m.items()))
    if isinstance(m, bool):
        return m
    if isinstance(m, (int, float)):
        return repr(float(m))                      # 30 == 30.0 -> same fingerprint
    return m


def _grid_fingerprint(grids) -> tuple:
    """Bit-exact fingerprint of the pressure-grid ARRAYS (P_HALF/P), not just their
    counts. Two configs with the same nlayers/nlevels but different grids are runtime-
    distinct (different BT/K) and MUST get different config hashes (Codex review; same
    rationale as folding geometry/surface in)."""
    import numpy as np
    return tuple(None if g is None else np.ascontiguousarray(g, dtype=np.float64).tobytes()
                 for g in grids)


def _config_hash(cfg, nlayers, nlevels, profile_keys=(), grids=()) -> str:
    """Defensive fingerprint of everything that must match between a direct run
    and the K run (design 7): coef, channels, forced options, grid sizes, the set of
    profile fields present (clear vs cloud is a different run mode), AND the per-obs
    geometry/surface (runtime-significant: the viewing/solar angles change BT and K, so
    two inputs differing only in geometry MUST get distinct fingerprints -- else a
    config-hash-keyed cache would return stale BT/K, Codex stop-review)."""
    key = repr((cfg.coef_id, tuple(cfg.channels), cfg.gas_units, bool(cfg.mmr_hydro),
                bool(cfg.adk_bt), bool(cfg.store_rad), int(nlayers), int(nlevels),
                tuple(sorted(profile_keys)),
                _canon_mapping(getattr(cfg, "geometry", None)),
                _canon_mapping(getattr(cfg, "surface", None)),
                _grid_fingerprint(grids)))
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def pack_rttov_input(profile_tensors, rttov_config) -> RttovInput:
    """RTTOV-unit torch profile tensors (P2 `RttovProfileTensors`) + config ->
    `RttovInput` (numpy). Serialization only -- no unit conversion, no grad work.

    Validates the forced RTTOV options and the layer/level invariant
    (Nlevels == Nlayers + 1), and rejects non-finite profiles. ``profile_tensors``
    must carry ``t_lay``/``q_lay`` (layers) and ``p_half`` (levels); all-sky cloud
    fields (clw/ciw/deff_liq/deff_ice/cfrac) are serialized when present (cloud mode).
    """
    _require_options(rttov_config)
    t = _to_numpy_2d(profile_tensors.t_lay, "t_lay")
    q = _to_numpy_2d(profile_tensors.q_lay, "q_lay")
    if t.shape != q.shape:
        raise ValueError(f"t_lay {t.shape} != q_lay {q.shape} (same profile/layer grid).")
    nprofiles, nlayers = t.shape

    profile = {"T": t, "Q": q}
    nlevels = None
    if getattr(profile_tensors, "p_half", None) is not None:
        ph = _to_numpy_2d(profile_tensors.p_half, "p_half")
        nlevels = ph.shape[-1]
        if nlevels != nlayers + 1:
            raise ValueError(
                f"Nlevels {nlevels} != Nlayers+1 ({nlayers + 1}) -- RTTOV-14 "
                "layer-based grid (design 5/profile.py:124).")
        profile["P_HALF"] = ph
    if getattr(profile_tensors, "p_lay", None) is not None:
        profile["P"] = _to_numpy_2d(profile_tensors.p_lay, "p_lay")

    # all-sky cloud fields (present only in cloud mode); each on the T/Q layer grid.
    for attr, fkey in _CLOUD_FIELD_MAP:
        val = getattr(profile_tensors, attr, None)
        if val is not None:
            arr = _to_numpy_2d(val, attr)
            if arr.shape != (nprofiles, nlayers):
                raise ValueError(
                    f"{attr} shape {arr.shape} != T/Q grid ({nprofiles}, {nlayers}) "
                    "-- cloud fields must ride the same layer grid.")
            profile[fkey] = arr

    return RttovInput(
        profile=profile, config=rttov_config,
        config_hash=_config_hash(rttov_config, nlayers,
                                 nlevels if nlevels else nlayers + 1, profile.keys(),
                                 grids=(profile.get("P_HALF"), profile.get("P"))),
        nprofiles=nprofiles, nlayers=nlayers)
