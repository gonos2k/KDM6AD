"""Versioned dry-number conjugation around the unchanged legacy KDM kernel.

This adapter implements ``C^{-1} K_legacy C`` for the four number fields
``NN, NC, NI, NR``. The host's physical forcing bundle is passed through
unchanged; only the KDM number operands are converted between per-dry-mass and
volume concentration. It supplies first-order products through an opaque K
handle, not higher derivatives or a new native/Fortran ABI.

Admission records are explicit source assertions. This module validates their
shape and digest syntax; the caller must independently bind the source and
receipt hashes to the data it loaded. Registry labels alone are not admission.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import re
from types import MappingProxyType
from typing import Mapping

import numpy as np


NUMBER_FIELDS = ("NN", "NC", "NI", "NR")
NUMBER_ROWS = (7, 8, 9, 10)
NUMBER_UNITS = "number_per_kg_dry_air"
ADMISSION_SCHEMA = "kdm6.native_dry_number.v1"
ADMISSION_ORIGINS = frozenset(("verified_dry_producer", "derived_kernel_volume_coordinate"))
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class NumberBasisAdmission:
    """Explicit caller admission for a versioned native dry-number input.

    ``verified_dry_producer`` means a source-specific producer/receipt declares
    the current arrays as per-kg-dry. ``derived_kernel_volume_coordinate``
    means the caller derived dry controls once as ``N_volume/rho_dry`` from a
    recorded legacy-KDM volume operand. Historical/raw arrays without either
    declaration are refused. The hashes bind external evidence; this value
    object does not read files or certify those hashes itself.
    """

    schema: str
    origin: str
    source_id: str
    source_sha256: str
    receipt_sha256: str
    field_units: Mapping[str, str]

    def __post_init__(self):
        if self.schema != ADMISSION_SCHEMA:
            raise ValueError(f"admission schema must be {ADMISSION_SCHEMA!r}")
        if self.origin not in ADMISSION_ORIGINS:
            raise ValueError("number basis origin is unknown or historical raw")
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ValueError("number-basis source_id is required")
        for name, digest in (("source_sha256", self.source_sha256),
                             ("receipt_sha256", self.receipt_sha256)):
            if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
                raise ValueError(f"{name} must be a lowercase 64-hex SHA-256")
        expected = {name: NUMBER_UNITS for name in NUMBER_FIELDS}
        try:
            actual = dict(self.field_units)
        except (TypeError, ValueError) as exc:
            raise TypeError("field_units must declare all four number fields") from exc
        if actual != expected:
            raise ValueError("field_units must declare exactly NN/NC/NI/NR per kg dry air")
        object.__setattr__(self, "field_units", MappingProxyType(dict(actual)))


def _is_null_handle(handle) -> bool:
    if handle is None:
        return True
    # ctypes.c_void_p null handle returned by value-only C calls.
    return hasattr(handle, "value") and handle.value is None


def _float64_array(value, shape, name):
    if not isinstance(value, np.ndarray) or value.dtype != np.float64:
        raise TypeError(f"{name} must be a float64 ndarray")
    if value.shape != shape:
        raise ValueError(f"{name} must have shape {shape}")
    if not np.isfinite(value).all():
        raise ValueError(f"{name} must be finite")


def _readonly_copy(value):
    out = np.ascontiguousarray(value, dtype=np.float64).copy()
    out.setflags(write=False)
    return out


@dataclass
class NativeDryNumberHandle:
    """Owned wrapper handle and immutable snapshots needed for the chain rule."""

    _owner: object = field(repr=False)
    _inner: object = field(repr=False)
    recorded: bool
    _dry_input: np.ndarray = field(repr=False)
    _volume_input: np.ndarray = field(repr=False)
    _volume_output: np.ndarray = field(repr=False)
    _forcing: np.ndarray = field(repr=False)
    _rho_dry: np.ndarray = field(repr=False)
    closed: bool = False

    @property
    def dry_input(self):
        return self._dry_input.copy()

    @property
    def volume_input(self):
        return self._volume_input.copy()

    @property
    def volume_output(self):
        return self._volume_output.copy()

    @property
    def forcing(self):
        return self._forcing.copy()

    @property
    def rho_dry(self):
        return self._rho_dry.copy()


class NativeDryNumberKernel:
    """Kernel-protocol adapter applying ``Psi = C^-1 K_legacy C``.

    The wrapped object must implement ``forward(s,f,joint,record)``,
    ``jvp(handle,ds,df)``, ``vjp(handle,u)`` and ``close(handle)`` and expose
    ``levels`` and ``dt``. Inputs/outputs follow the existing float64 Python
    verifier boundary: state ``(12,L)`` and forcing ``(4,L)`` in the exact
    order from ``verify_state_forcing_ad``. Forcing row zero is native dry DEN
    in kg dry air/m^3. Rows 7–10 alone are converted.
    """

    def __init__(self, kernel, *, admission: NumberBasisAdmission):
        if isinstance(admission, NumberBasisAdmission):
            checked_admission = admission
        else:
            # Keep the wrapper decoupled from the verifier/receipt module while
            # accepting its immutable admission record by explicit protocol.
            required = ("schema", "origin", "source_id", "source_sha256",
                        "receipt_sha256", "field_units")
            if not all(hasattr(admission, name) for name in required):
                raise TypeError("an explicit NumberBasisAdmission is required")
            checked_admission = NumberBasisAdmission(
                *(getattr(admission, name) for name in required)
            )
        for name in ("forward", "jvp", "vjp", "close", "levels", "dt"):
            if not hasattr(kernel, name):
                raise TypeError(f"wrapped kernel must provide {name}")
        levels = kernel.levels
        dt = kernel.dt
        if isinstance(levels, bool) or not isinstance(levels, int) or levels <= 0:
            raise ValueError("kernel levels must be a positive integer")
        if isinstance(dt, bool) or not isinstance(dt, (int, float)) or not math.isfinite(dt) or dt <= 0:
            raise ValueError("kernel dt must be finite and positive")
        self.kernel = kernel
        self.levels = levels
        self.dt = float(dt)
        self.admission = checked_admission
        self._owner = object()

    def _validate_pair(self, state, forcing):
        _float64_array(state, (12, self.levels), "state")
        _float64_array(forcing, (4, self.levels), "forcing")
        rho = forcing[0]
        if np.any(rho <= 0.0):
            raise ValueError("native dry DEN must be positive")
        if np.any(state[np.asarray(NUMBER_ROWS)] < 0.0):
            raise ValueError("admitted dry-number state counts must be nonnegative")
        return np.ascontiguousarray(state), np.ascontiguousarray(forcing), rho

    def _validate_handle(self, handle, *, require_record):
        if not isinstance(handle, NativeDryNumberHandle) or handle._owner is not self._owner:
            raise TypeError("handle was not created by this NativeDryNumberKernel")
        if handle.closed:
            raise ValueError("boundary handle is closed")
        if require_record and not handle.recorded:
            raise ValueError("JVP/VJP require a record=True boundary handle")
        return handle

    def forward(self, state, forcing, *, joint=True, record=False):
        if record and not joint:
            raise ValueError("a recorded boundary handle requires the full state+forcing KDM ABI")
        state, forcing, rho = self._validate_pair(state, forcing)
        dry_input = state.copy()
        volume_input = state.copy()
        volume_input[np.asarray(NUMBER_ROWS)] *= rho[None, :]
        if not np.isfinite(volume_input).all():
            raise ValueError("dry-to-volume number conversion produced nonfinite values")

        inner = None
        try:
            volume_output, inner = self.kernel.forward(
                np.ascontiguousarray(volume_input), np.ascontiguousarray(forcing.copy()),
                joint=joint, record=record,
            )
            _float64_array(volume_output, (12, self.levels), "legacy kernel output")
            dry_output = np.ascontiguousarray(volume_output.copy())
            rows = np.asarray(NUMBER_ROWS)
            dry_output[rows] /= rho[None, :]
            if not np.isfinite(dry_output).all():
                raise ValueError("volume-to-dry number conversion produced nonfinite values")
            if record and _is_null_handle(inner):
                raise RuntimeError("legacy kernel did not return a recorded handle")
            handle = NativeDryNumberHandle(
                self._owner,
                inner,
                bool(record),
                _readonly_copy(dry_input),
                _readonly_copy(volume_input),
                _readonly_copy(volume_output),
                _readonly_copy(forcing),
                _readonly_copy(rho),
            )
            return dry_output, handle
        except BaseException:
            if not _is_null_handle(inner):
                self.kernel.close(inner)
            raise

    def jvp(self, handle, dstate, dforcing):
        h = self._validate_handle(handle, require_record=True)
        _float64_array(dstate, (12, self.levels), "dstate")
        _float64_array(dforcing, (4, self.levels), "dforcing")
        drho = dforcing[0]
        dvolume_input = np.ascontiguousarray(dstate.copy())
        rows = np.asarray(NUMBER_ROWS)
        dvolume_input[rows] = (
            h._rho_dry[None, :]*dstate[rows]
            + h._dry_input[rows]*drho[None, :]
        )
        dvolume_output = self.kernel.jvp(
            h._inner, np.ascontiguousarray(dvolume_input), np.ascontiguousarray(dforcing.copy())
        )
        _float64_array(dvolume_output, (12, self.levels), "legacy kernel tangent")
        ddry_output = np.ascontiguousarray(dvolume_output.copy())
        ddry_output[rows] = (
            dvolume_output[rows]/h._rho_dry[None, :]
            - h._volume_output[rows]*drho[None, :]/(h._rho_dry[None, :]**2)
        )
        if not np.isfinite(ddry_output).all():
            raise ValueError("volume-to-dry tangent produced nonfinite values")
        return ddry_output

    def vjp(self, handle, cotangent):
        h = self._validate_handle(handle, require_record=True)
        _float64_array(cotangent, (12, self.levels), "cotangent")
        rows = np.asarray(NUMBER_ROWS)
        volume_seed = np.ascontiguousarray(cotangent.copy())
        volume_seed[rows] = cotangent[rows]/h._rho_dry[None, :]
        exit_rho_adjoint = -np.sum(
            h._volume_output[rows]*cotangent[rows], axis=0
        )/(h._rho_dry**2)
        state_volume_adjoint, forcing_adjoint = self.kernel.vjp(
            h._inner, np.ascontiguousarray(volume_seed)
        )
        _float64_array(state_volume_adjoint, (12, self.levels), "legacy kernel state adjoint")
        _float64_array(forcing_adjoint, (4, self.levels), "legacy kernel forcing adjoint")
        state_adjoint = np.ascontiguousarray(state_volume_adjoint.copy())
        state_adjoint[rows] = h._rho_dry[None, :]*state_volume_adjoint[rows]
        entry_rho_adjoint = np.sum(
            h._dry_input[rows]*state_volume_adjoint[rows], axis=0
        )
        forcing_adjoint = np.ascontiguousarray(forcing_adjoint.copy())
        forcing_adjoint[0] += entry_rho_adjoint + exit_rho_adjoint
        _float64_array(state_adjoint, (12, self.levels), "dry-coordinate state adjoint")
        _float64_array(forcing_adjoint, (4, self.levels), "native forcing adjoint")
        return state_adjoint, forcing_adjoint

    def close(self, handle=None):
        if handle is None:
            return
        h = self._validate_handle(handle, require_record=False)
        try:
            if not _is_null_handle(h._inner):
                self.kernel.close(h._inner)
        finally:
            h.closed = True
