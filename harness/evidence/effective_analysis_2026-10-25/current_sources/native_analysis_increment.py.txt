"""Encode dry-theta/QV analysis states as native WRF prognostic increments.

The dry-theta conversion is value-only and operates on aligned NumPy arrays.
The satellite-control adapter separately binds already-native T2/QV controls
to a checkpoint; neither path applies a control or runs the host.
The differentiable transform/JVP/VJP below are an optional
Torch-f64 math contract for the coordinate conversion only; they do not include
host dynamics, physics, observations, or a full-host adjoint.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
from typing import Any

import numpy as np
try:
    import torch
except ImportError:  # NumPy value-boundary users do not require the oracle dependency.
    torch = None


# Verified active WRF constants: host/KIM-meso_v1.0/share/module_model_constants.F
# R_d=287, R_v=461.6, T0=300. The host parameters are REAL (binary32), and
# native THETA_M uses their rounded binary32 quotient. This captured alpha is
# deliberately distinct from the nominal-ratio f64 frame-reader coordinate.
R_D = 287.0
R_V = 461.6
HOST_ALPHA_BITS = "3FCDDED2"
HOST_ALPHA = float(np.float32(np.float32(R_V) / np.float32(R_D)))
THETA_COORDINATE = "wrf_use_theta_m_hostf32_alpha_3FCDDED2"
T0 = 300.0
_WRF_TIME_FORMAT = "%Y-%m-%d_%H:%M:%S"
_THETA_UNITS = "K"
_QV_UNITS = "kg kg-1 dry air"
_NATIVE_LAYOUT = "i,k,j"


@dataclass(frozen=True)
class AnalysisStamp:
    """Provenance needed before a posterior can be encoded for a live host."""

    model_valid_time: str
    analysis_valid_time: str
    geometry_id: str
    checkpoint_id: str
    background_checkpoint_id: str | None = None
    native_layout: str = _NATIVE_LAYOUT
    use_theta_m: bool = True
    theta_coordinate: str = THETA_COORDINATE
    alpha_bits: str = HOST_ALPHA_BITS
    theta_dry_units: str = _THETA_UNITS
    qv_units: str = _QV_UNITS


@dataclass(frozen=True)
class ThermodynamicState:
    """Aligned dry potential temperature and vapor mixing ratio arrays."""

    theta_dry: np.ndarray
    qv: np.ndarray
    stamp: AnalysisStamp


@dataclass(frozen=True)
class NativeAnalysisIncrement:
    """Full-domain increments for T_2 and QVAPOR; not yet native-quantized."""

    delta_theta_m: np.ndarray
    delta_qv: np.ndarray
    unchanged_mask: np.ndarray
    model_valid_time: str
    geometry_id: str
    native_layout: str
    background_checkpoint_id: str
    posterior_checkpoint_id: str

    @property
    def delta_t_2(self) -> np.ndarray:
        """T_2 is theta_m perturbation, so its increment equals delta theta_m."""
        return self.delta_theta_m


def bind_satellite_control(checkpoint, control, *, posterior_checkpoint_id):
    """Bind prepared flat-column T2/QV wire deltas to an actual checkpoint.

    Satellite controls already use moist-theta perturbation. There is no
    dry-theta conversion here. ``posterior_checkpoint_id`` is the caller's
    analysis provenance identifier; this adapter does not write a restart.
    The live stepper rechecks the binding and exact application before send.
    """
    import netCDF4
    from harness.native_analysis_control import prepare_effective_analysis
    from harness.native_live_stepper import checkpoint_geometry_id

    if not isinstance(posterior_checkpoint_id, str) or not posterior_checkpoint_id:
        raise ValueError("posterior_checkpoint_id must identify the prepared analysis")
    checkpoint.file.verify()
    if control.get("background_checkpoint_id") != checkpoint.file.sha256:
        raise ValueError("satellite control belongs to a different complete background checkpoint")
    dims = dict(checkpoint.schema[0])
    nx, ny, nz = (dims[n] for n in ("west_east", "south_north", "bottom_top"))
    shape = (2, ny * nx, nz)
    if control.get("horizontal_shape") != (ny, nx):
        raise ValueError("satellite control horizontal shape differs from checkpoint")
    wire = np.asarray(control["wire_delta"])
    candidate = np.asarray(control["candidate"])
    if (wire.dtype != np.float32 or wire.shape != shape
            or candidate.dtype != np.float64 or candidate.shape != shape):
        raise ValueError("satellite wire/candidate arrays require matching native column layout")
    background = []
    with netCDF4.Dataset(checkpoint.file.path) as ds:
        ds.set_auto_maskandscale(False)
        for name in ("THM_2", "QVAPOR"):
            if (name not in ds.variables or ds[name].dimensions !=
                    ("Time", "bottom_top", "south_north", "west_east")
                    or np.dtype(ds[name].dtype) != np.float32
                    or ds[name].shape != (1, nz, ny, nx)):
                raise ValueError("checkpoint must expose full native binary32 THM_2/QVAPOR")
            background.append(np.asarray(ds[name][0]).transpose(1, 2, 0).reshape(ny * nx, nz))
    background = np.stack(background).astype(np.float64)
    if hashlib.sha256(background.tobytes()).hexdigest() != control.get("background_sha256"):
        raise ValueError("satellite control was prepared from a different native background")

    def native(array):
        return np.ascontiguousarray(array.reshape(ny, nx, nz).transpose(1, 2, 0))

    prepared = prepare_effective_analysis(
        native(background[0].astype(np.float32)), native(background[1].astype(np.float32)),
        native(wire[0]), native(wire[1]), native(np.all(wire == 0.0, axis=0)),
        bounds=(1, nx, 1, nz, 1, ny),
    )
    expected = np.stack((native(candidate[0]), native(candidate[1])))
    actual = np.stack((prepared.effective_theta_m, prepared.effective_qv)).astype(np.float64)
    if actual.tobytes() != expected.tobytes():
        raise ValueError("satellite wire does not produce the declared effective state")
    geometry = checkpoint_geometry_id(checkpoint)
    checkpoint.file.verify()
    return NativeAnalysisIncrement(
        delta_theta_m=prepared.delta_theta_m, delta_qv=prepared.delta_qv,
        unchanged_mask=~prepared.changed_mask,
        model_valid_time=checkpoint.time, geometry_id=geometry, native_layout="i,k,j",
        background_checkpoint_id=checkpoint.file.sha256,
        posterior_checkpoint_id=posterior_checkpoint_id,
    )


def _validate_wrf_time(value: str, label: str) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a WRF Times string")
    try:
        parsed = datetime.strptime(value, _WRF_TIME_FORMAT)
    except ValueError as exc:
        raise ValueError(f"{label} must use YYYY-MM-DD_HH:MM:SS") from exc
    if parsed.strftime(_WRF_TIME_FORMAT) != value:
        raise ValueError(f"{label} must use exact YYYY-MM-DD_HH:MM:SS form")


def _validate_stamp(stamp: AnalysisStamp, label: str) -> None:
    if not isinstance(stamp, AnalysisStamp):
        raise TypeError(f"{label}.stamp must be AnalysisStamp")
    _validate_wrf_time(stamp.model_valid_time, f"{label}.model_valid_time")
    _validate_wrf_time(stamp.analysis_valid_time, f"{label}.analysis_valid_time")
    if stamp.model_valid_time != stamp.analysis_valid_time:
        raise ValueError(
            f"{label}: model valid time must equal analysis valid time before applying increments"
        )
    if not stamp.geometry_id or not isinstance(stamp.geometry_id, str):
        raise ValueError(f"{label}.geometry_id must be a nonempty geometry identifier")
    if not stamp.checkpoint_id or not isinstance(stamp.checkpoint_id, str):
        raise ValueError(f"{label}.checkpoint_id must identify the represented checkpoint")
    if stamp.native_layout != _NATIVE_LAYOUT:
        raise ValueError(f"{label}.native_layout must be {_NATIVE_LAYOUT!r}")
    if stamp.use_theta_m is not True:
        raise ValueError(f"{label}: only the audited USE_THETA_M=1 coordinate is supported")
    if stamp.theta_coordinate != THETA_COORDINATE or stamp.alpha_bits != HOST_ALPHA_BITS:
        raise ValueError(f"{label}: native moist-theta coefficient/coordinate differs from captured host f32")
    if stamp.theta_dry_units != _THETA_UNITS:
        raise ValueError(f"{label}.theta_dry_units must be {_THETA_UNITS!r}")
    if stamp.qv_units != _QV_UNITS:
        raise ValueError(f"{label}.qv_units must be {_QV_UNITS!r}")
    if stamp.background_checkpoint_id is not None and (
        not isinstance(stamp.background_checkpoint_id, str)
        or not stamp.background_checkpoint_id
    ):
        raise ValueError(f"{label}.background_checkpoint_id must be nonempty when supplied")


def _validate_values(state: ThermodynamicState, label: str) -> tuple[np.ndarray, np.ndarray]:
    if not isinstance(state, ThermodynamicState):
        raise TypeError(f"{label} must be ThermodynamicState")
    _validate_stamp(state.stamp, label)
    arrays = []
    for name, value in (("theta_dry", state.theta_dry), ("qv", state.qv)):
        if np.ma.isMaskedArray(value) and np.ma.getmaskarray(value).any():
            raise ValueError(f"{label}.{name} contains masked values")
        array = np.asarray(value)
        if array.dtype.kind not in "fiu" or array.dtype.kind == "b":
            raise ValueError(f"{label}.{name} must be a real numeric array")
        array = np.asarray(array, dtype=np.float64)
        if not np.isfinite(array).all():
            raise ValueError(f"{label}.{name} must be finite")
        arrays.append(array)
    theta, qv = arrays
    if theta.shape != qv.shape or theta.ndim == 0:
        raise ValueError(f"{label}: theta_dry and qv must have the same non-scalar shape")
    if np.any(theta <= 0.0):
        raise ValueError(f"{label}.theta_dry must be positive absolute potential temperature")
    if np.any(qv < 0.0):
        raise ValueError(f"{label}.qv must be nonnegative mixing ratio")
    return theta, qv


def theta_m_total(theta_dry: Any, qv: Any) -> Any:
    """Return native total moist potential temperature using captured host alpha.

    Accepts same-shape NumPy arrays or Torch tensors without detaching/casting;
    Torch inputs therefore retain autograd through this coordinate map. The
    coefficient is binary32 ``461.6f/287.0f`` captured from the active host,
    promoted to the operand dtype; it is not the nominal-ratio f64 reader map.
    """
    if torch is not None and isinstance(theta_dry, torch.Tensor) and isinstance(qv, torch.Tensor):
        if theta_dry.shape != qv.shape or theta_dry.device != qv.device:
            raise ValueError("theta_dry and qv tensors must have matching shape and device")
        return theta_dry * (1.0 + HOST_ALPHA * qv)
    if isinstance(theta_dry, np.ndarray) and isinstance(qv, np.ndarray):
        if theta_dry.shape != qv.shape:
            raise ValueError("theta_dry and qv arrays must have matching shape")
        return theta_dry * (1.0 + HOST_ALPHA * qv)
    raise TypeError("theta_m_total expects two NumPy arrays or two Torch tensors")


def _same_coordinate_operands(reference: Any, *values: Any, name: str) -> None:
    if torch is not None and isinstance(reference, torch.Tensor):
        if any(not isinstance(value, torch.Tensor) for value in values):
            raise TypeError(f"{name} operands must all be Torch tensors")
        if any(value.shape != reference.shape or value.device != reference.device
               or value.dtype != reference.dtype for value in values):
            raise ValueError(f"{name} Torch operands must match shape, device, and dtype")
        return
    if isinstance(reference, np.ndarray):
        if any(not isinstance(value, np.ndarray) for value in values):
            raise TypeError(f"{name} operands must all be NumPy arrays")
        if any(value.shape != reference.shape or value.dtype != reference.dtype for value in values):
            raise ValueError(f"{name} NumPy operands must match shape and dtype")
        return
    raise TypeError(f"{name} expects NumPy arrays or Torch tensors")


def theta_m_jvp(theta_dry: Any, qv: Any, dtheta_dry: Any, dqv: Any) -> Any:
    """Directional derivative of total moist potential temperature."""
    _same_coordinate_operands(theta_dry, qv, dtheta_dry, dqv, name="theta_m_jvp")
    return dtheta_dry * (1.0 + HOST_ALPHA * qv) + HOST_ALPHA * theta_dry * dqv


def theta_m_vjp(theta_dry: Any, qv: Any, cotangent: Any) -> tuple[Any, Any]:
    """Pull back an output cotangent through the dry-theta/QV coordinate map."""
    _same_coordinate_operands(theta_dry, qv, cotangent, name="theta_m_vjp")
    return cotangent * (1.0 + HOST_ALPHA * qv), cotangent * HOST_ALPHA * theta_dry


def encode_native_increment(
    background: ThermodynamicState,
    posterior: ThermodynamicState,
) -> NativeAnalysisIncrement:
    """Map dry-theta/QV prior and posterior into native T_2/QV increments.

    The posterior stamp must identify the exact background checkpoint from which
    it was produced. Model and analysis valid times and geometry must agree.
    `theta_dry` is interpreted with the captured active-host binary32 alpha
    (`461.6f/287.0f`, bits `3FCDDED2`), not the public reader's nominal f64
    ratio coordinate.
    Output is float64 and must be quantized/serialized by a separately audited
    native packet boundary. This function does not claim a global water/energy
    budget or apply the increment to a running model.
    """
    theta_b, qv_b = _validate_values(background, "background")
    theta_a, qv_a = _validate_values(posterior, "posterior")
    sb, sa = background.stamp, posterior.stamp
    if sb.model_valid_time != sa.model_valid_time:
        raise ValueError("background and posterior model valid times differ")
    if sb.analysis_valid_time != sa.analysis_valid_time:
        raise ValueError("background and posterior analysis valid times differ")
    if sb.geometry_id != sa.geometry_id:
        raise ValueError("background and posterior geometry identifiers differ")
    if sb.native_layout != sa.native_layout:
        raise ValueError("background and posterior native layouts differ")
    if theta_b.shape != theta_a.shape:
        raise ValueError("background and posterior profile shapes differ")
    if sa.background_checkpoint_id != sb.checkpoint_id:
        raise ValueError("posterior is not bound to the supplied background checkpoint")

    theta_m_b = theta_m_total(theta_b, qv_b)
    theta_m_a = theta_m_total(theta_a, qv_a)
    delta_theta_m = np.asarray(theta_m_a - theta_m_b, dtype=np.float64)
    delta_qv = np.asarray(qv_a - qv_b, dtype=np.float64)
    if not np.isfinite(delta_theta_m).all() or not np.isfinite(delta_qv).all():
        raise ValueError("encoded T_2/QV increments must be finite")
    unchanged = (delta_theta_m == 0.0) & (delta_qv == 0.0)
    # Copy to make the packet source independent from caller-owned arrays.
    return NativeAnalysisIncrement(
        delta_theta_m=delta_theta_m.copy(),
        delta_qv=delta_qv.copy(),
        unchanged_mask=unchanged.copy(),
        model_valid_time=sb.model_valid_time,
        geometry_id=sb.geometry_id,
        native_layout=sb.native_layout,
        background_checkpoint_id=sb.checkpoint_id,
        posterior_checkpoint_id=sa.checkpoint_id,
    )
