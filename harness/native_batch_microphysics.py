"""First-order native-column batch adapter around the existing KDM6 ABI.

Each native column reuses ``native_prep`` and ``native_finish``. The only
opaque boundary is one full-B state+forcing KDM call, whose checkpoint stores
NumPy value buffers and whose backward uses the matching C ABI VJP. Inputs and
outputs retain native level order and the legacy KDM number coordinates.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple
import weakref

import numpy as np

from harness.verify_localized_ice_ad import BatchKernel
from oracle.kdm6 import native_finish, native_prep


class BatchPrepGeometry(NamedTuple):
    """Fixed per-column prep geometry, shaped ``(B,L)``/``(B,L+1)``."""

    phb: object
    c3h: object
    c4h: object
    c3f: object
    c4f: object


class NativeProfile(NamedTuple):
    thm_pert: object
    qv: object
    p_center_Pa: object
    phi_interfaces: object


class CloudProfile(NamedTuple):
    qc: object
    qr: object
    qi: object
    qs: object
    qg: object
    nn: object
    nc: object
    ni: object
    nr: object
    bg: object


class NativeBatchOutput(NamedTuple):
    native_profile: NativeProfile
    cloud_state: CloudProfile
    rho_d: object
    finish: object


class NativeBatchDirection(NamedTuple):
    """First-order direction for differentiable native batch controls."""

    theta_m_pert: object
    qv: object
    ph: object
    rest: object


_GEOMETRY_FIELDS = ("phb", "c3h", "c4h", "c3f", "c4f")
_MASS_ROWS = (1, 2, 3, 4, 5, 6)  # QV, QC, QR, QI, QS, QG.


def _close_once(kernel, handle):
    closed = False

    def close():
        nonlocal closed
        if not closed:
            closed = True
            kernel.close(handle)

    return close


class _BatchKernelFunction:
    """Construct the one-forward ABI boundary with optional explicit JVP."""

    @staticmethod
    def make(torch):
        from torch.autograd.function import once_differentiable

        class Apply(torch.autograd.Function):
            @staticmethod
            def forward(ctx, state, forcing, dstate, dforcing, kernel, with_jvp):
                record = bool(ctx.needs_input_grad[0] or ctx.needs_input_grad[1] or with_jvp)
                state_np = np.ascontiguousarray(state.detach().cpu().numpy(), dtype=np.float64)
                forcing_np = np.ascontiguousarray(forcing.detach().cpu().numpy(), dtype=np.float64)
                with torch.set_grad_enabled(record):
                    out, handle = kernel.forward(state_np, forcing_np, record=record)
                tangent = None
                if record:
                    guard = _close_once(kernel, handle)
                    ctx.guard = guard
                    ctx.finalizer = weakref.finalize(ctx, guard)
                    ctx.kernel = kernel
                    ctx.handle = handle
                    ctx.reversed = False
                if with_jvp:
                    try:
                        ds = np.ascontiguousarray(dstate.detach().cpu().numpy(), dtype=np.float64)
                        df = np.ascontiguousarray(dforcing.detach().cpu().numpy(), dtype=np.float64)
                        with torch.enable_grad():
                            tangent = kernel.jvp(handle, ds, df)
                    except BaseException:
                        if record:
                            ctx.guard()
                        raise
                result = torch.from_numpy(np.array(out, dtype=np.float64, order="C", copy=True)).to(
                    device=state.device, dtype=state.dtype
                )
                if tangent is None:
                    return result, None
                tangent = torch.from_numpy(
                    np.array(tangent, dtype=np.float64, order="C", copy=True)
                ).to(device=state.device, dtype=state.dtype)
                ctx.mark_non_differentiable(tangent)
                return result, tangent

            @staticmethod
            @once_differentiable
            def backward(ctx, cotangent, tangent_cotangent):
                if ctx.reversed:
                    raise RuntimeError("batch ABI checkpoint supports a single reverse pass")
                ctx.reversed = True
                try:
                    u = np.ascontiguousarray(cotangent.detach().cpu().numpy(), dtype=np.float64)
                    with torch.enable_grad():
                        gs, gf = ctx.kernel.vjp(ctx.handle, u)
                    return (
                        torch.from_numpy(np.array(gs, dtype=np.float64, order="C", copy=True)).to(
                            device=cotangent.device, dtype=cotangent.dtype
                        ),
                        torch.from_numpy(np.array(gf, dtype=np.float64, order="C", copy=True)).to(
                            device=cotangent.device, dtype=cotangent.dtype
                        ),
                        None,
                        None,
                        None,
                        None,
                    )
                finally:
                    ctx.guard()

        return Apply


@dataclass
class NativeBatchMicrophysics:
    """Compose native prep, one B-column KDM call, cleanup, finish and EOS.

    ``mu_total`` and ``geometry`` are fixed controls. ``theta_m_pert``, ``qv``,
    ``ph`` and ``rest`` are Torch tensors with shapes ``(B,L)``, ``(B,L)``,
    ``(B,L+1)`` and ``(10,B,L)``. The KDM cadence is fixed at 20 seconds.
    Each recorded ABI checkpoint supports one reverse pass, even if Torch's
    graph is retained. Create a fresh forward for another VJP. Higher
    derivatives are unsupported. Positive cleanup-threshold ties reject AD;
    no-grad forward values retain the host's strict-less-than cleanup rule.
    """

    kernel: BatchKernel
    geometry: BatchPrepGeometry
    prep_config: object
    finish_config: object
    zero_config: object

    def __post_init__(self):
        import torch

        if not isinstance(self.geometry, BatchPrepGeometry):
            raise TypeError("geometry must be BatchPrepGeometry")
        if not isinstance(self.prep_config, native_prep.NativePrepConfig):
            raise TypeError("prep_config must be NativePrepConfig")
        if not isinstance(self.finish_config, native_finish.FinishConfig):
            raise TypeError("finish_config must be FinishConfig")
        mode, threshold = native_finish._validate_zero_out_config(self.zero_config)
        self.mode, self.threshold = mode, threshold
        self.batch, self.levels = self.kernel.B, self.kernel.L
        if self.finish_config.dt != 20.0:
            raise ValueError("native batch KDM cadence is fixed at 20 seconds")
        self._torch = torch
        self._apply_kernel = _BatchKernelFunction.make(torch)
        self._geometry = {}
        for name in _GEOMETRY_FIELDS:
            value = getattr(self.geometry, name)
            expected = (self.batch, self.levels + 1) if name in ("phb", "c3f", "c4f") else (self.batch, self.levels)
            if not isinstance(value, torch.Tensor) or value.dtype != torch.float64 or value.shape != expected:
                raise ValueError(f"geometry.{name} must be fixed float64 with shape {expected}")
            if value.requires_grad or not bool(torch.isfinite(value).all().item()):
                raise ValueError(f"geometry.{name} must be finite and fixed")
            self._geometry[name] = value

    def _validate(self, theta_m_pert, qv, mu_total, ph, rest):
        torch = self._torch
        levels, batch = self.levels, self.batch
        expected = (("theta_m_pert", theta_m_pert, (batch, levels)),
                    ("qv", qv, (batch, levels)),
                    ("mu_total", mu_total, (batch,)),
                    ("ph", ph, (batch, levels + 1)),
                    ("rest", rest, (10, batch, levels)))
        for name, value, shape in expected:
            if not isinstance(value, torch.Tensor) or value.dtype != torch.float64 or value.shape != shape:
                raise ValueError(f"{name} must be float64 with shape {shape}")
            if value.device != theta_m_pert.device:
                raise ValueError(f"{name} must be on theta_m_pert's device")
            if not bool(torch.isfinite(value).all().item()):
                raise ValueError(f"{name} must be finite")
        if mu_total.requires_grad:
            raise ValueError("mu_total is a fixed native control")

    def _prep_batch(self, thm, qv, mu, ph, direction=None):
        torch = self._torch
        outputs = []
        if direction is not None:
            dthm, dqv, dph = direction
        for row in range(self.batch):
            geom = native_prep.FrozenPrepGeometry(**{
                name: self._geometry[name][row] for name in _GEOMETRY_FIELDS
            })
            state = native_prep.NativePrepState(thm[row], qv[row], mu[row], ph[row])
            output = native_prep.native_prep(state, geom, self.prep_config)
            if direction is None:
                outputs.append((output,))
            else:
                dstate = native_prep.NativePrepState(
                    dthm[row], dqv[row], torch.zeros_like(mu[row]), dph[row]
                )
                tangent = native_prep.native_prep_jvp(
                    state, geom, dstate, self.prep_config
                )
                outputs.append((output, tangent))

        def stack(index):
            return native_prep.NativePrepResult(**{
                name: torch.stack([getattr(pair[index], name) for pair in outputs], dim=0)
                for name in native_prep.NativePrepResult._fields
            })

        return stack(0) if direction is None else (stack(0), stack(1))

    def _validate_direction(self, direction, reference):
        torch = self._torch
        if not isinstance(direction, NativeBatchDirection):
            raise TypeError("direction must be NativeBatchDirection")
        for name, value, ref in zip(direction._fields, direction,
                                    (reference[0], reference[1], reference[3], reference[4])):
            if (not isinstance(value, torch.Tensor) or value.dtype != torch.float64
                    or value.shape != ref.shape or value.device != ref.device):
                raise ValueError(f"direction.{name} metadata must match its native control")
            if value.requires_grad:
                raise ValueError("explicit JVP directions are fixed first-order inputs")
            if not bool(torch.isfinite(value).all().item()):
                raise ValueError(f"direction.{name} must be finite")

    def _clean_jvp(self, raw, draw):
        torch = self._torch
        thermo = native_finish.post_microphysics_jvp(
            native_finish.ThermoState(raw[0], raw[1], raw[2]),
            native_finish.ThermoState(draw[0], draw[1], draw[2]), self.zero_config,
        )
        rows = [draw[i] for i in range(12)]
        rows[0], rows[1], rows[2] = thermo.th, thermo.qv, thermo.qc
        if self.mode:
            for row in _MASS_ROWS[2:]:
                if self.threshold > 0.0 and bool((raw[row] == self.threshold).any().item()):
                    raise ValueError(f"cleanup discontinuity tie in mass row {row}")
                mask = raw[row] >= self.threshold if self.threshold > 0.0 else raw[row] > 0.0
                rows[row] = draw[row] * mask.to(dtype=draw.dtype)
        return torch.stack(rows, dim=0)

    def _clean(self, raw):
        torch = self._torch
        if (self.mode and self.threshold > 0.0 and raw.requires_grad
                and bool((raw[2:7] == self.threshold).any().item())):
            raise ValueError("cleanup discontinuity at positive mass threshold")
        # Reuse the established thermodynamic cleanup map, then apply the same
        # mode/threshold rule to all other KDM mass coordinates.
        thermo = native_finish.post_microphysics_thermo(
            native_finish.ThermoState(raw[0], raw[1], raw[2]), self.zero_config
        )
        rows = [raw[i] for i in range(12)]
        rows[0], rows[1], rows[2] = thermo.th, thermo.qv, thermo.qc
        if self.mode:
            for row in _MASS_ROWS[2:]:
                if self.threshold == 0.0:
                    rows[row] = torch.where(raw[row] > 0.0, raw[row], torch.zeros_like(raw[row]))
                else:
                    rows[row] = torch.where(raw[row] < self.threshold, torch.zeros_like(raw[row]), raw[row])
        return torch.stack(rows, dim=0)

    def __call__(self, theta_m_pert, qv, mu_total, ph, rest):
        return self._evaluate(theta_m_pert, qv, mu_total, ph, rest)

    def forward_with_jvp(self, theta_m_pert, qv, mu_total, ph, rest, direction):
        """Return primal and explicit first-order tangent from one full-B K call.

        The tangent is a value-only first-order result; it has no higher-order
        derivative contract. The primal retains the same opaque checkpoint for
        one VJP, after which backward closes the handle in ``finally``.
        """
        inputs = (theta_m_pert, qv, mu_total, ph, rest)
        self._validate_direction(direction, inputs)
        primal, tangent = self._evaluate(*inputs, direction=direction)
        return primal, _detach_output(tangent)

    def _evaluate(self, theta_m_pert, qv, mu_total, ph, rest, direction=None):
        torch = self._torch
        self._validate(theta_m_pert, qv, mu_total, ph, rest)
        if direction is None:
            prep = self._prep_batch(theta_m_pert, qv, mu_total, ph)
            dprep = None
        else:
            prep, dprep = self._prep_batch(
                theta_m_pert, qv, mu_total, ph,
                (direction.theta_m_pert, direction.qv, direction.ph)
            )
        state = torch.cat((prep.th.unsqueeze(0), qv.unsqueeze(0), rest), dim=0).contiguous()
        forcing = torch.stack((prep.rho, prep.pii, prep.p, prep.delz), dim=0).contiguous()
        if direction is None:
            raw, _ = self._apply_kernel.apply(
                state, forcing, torch.empty(0, dtype=state.dtype, device=state.device),
                torch.empty(0, dtype=state.dtype, device=state.device), self.kernel, False
            )
            draw = None
        else:
            ds = torch.cat((dprep.th.unsqueeze(0), direction.qv.unsqueeze(0), direction.rest), dim=0).contiguous()
            df = torch.stack((dprep.rho, dprep.pii, dprep.p, dprep.delz), dim=0).contiguous()
            raw, draw = self._apply_kernel.apply(state, forcing, ds, df, self.kernel, True)
        clean = self._clean(raw)
        before = native_finish.ThermoState(state[0], state[1], state[2])
        after = native_finish.ThermoState(clean[0], clean[1], clean[2])
        finished = native_finish.native_finish(before, after, self.finish_config)
        if direction is None:
            post = self._prep_batch(finished.t_new_after, clean[1], mu_total, ph)
        else:
            dbefore = native_finish.ThermoState(ds[0], ds[1], ds[2])
            dclean = self._clean_jvp(raw, draw)
            dafter = native_finish.ThermoState(dclean[0], dclean[1], dclean[2])
            dfinished = native_finish.native_finish_jvp(
                before, after, dbefore, dafter, self.finish_config
            )
            post, dpost = self._prep_batch(
                finished.t_new_after, clean[1], mu_total, ph,
                (dfinished.t_new_after, dclean[1], direction.ph)
            )
        phi = ph + self._geometry["phb"]
        primal = NativeBatchOutput(
            NativeProfile(finished.t_new_after, clean[1], post.p, phi),
            CloudProfile(clean[2], clean[3], clean[4], clean[5], clean[6],
                         clean[7], clean[8], clean[9], clean[10], clean[11]),
            post.rho,
            finished,
        )
        if direction is None:
            return primal
        tangent = NativeBatchOutput(
            NativeProfile(dfinished.t_new_after, dclean[1], dpost.p, direction.ph),
            CloudProfile(dclean[2], dclean[3], dclean[4], dclean[5], dclean[6],
                         dclean[7], dclean[8], dclean[9], dclean[10], dclean[11]),
            dpost.rho,
            dfinished,
        )
        return primal, tangent


def make_batch_kernel(library, xland, levels):
    """Create the existing full-B kernel with its fixed 20-second cadence."""
    return BatchKernel(library, xland, levels)


def _detach_output(output):
    """Mark the explicit tangent as first-order value-only output."""
    return NativeBatchOutput(
        NativeProfile(*(value.detach() for value in output.native_profile)),
        CloudProfile(*(value.detach() for value in output.cloud_state)),
        output.rho_d.detach(),
        type(output.finish)(*(value.detach() for value in output.finish)),
    )
