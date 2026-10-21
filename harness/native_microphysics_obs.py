"""First-order prep -> KDM -> zero-out -> finish -> post-finish EOS map.

This is a single-column offline observation-state adapter. It does not call
RTTOV, run RK dynamics, or advance a forecast. The returned post-EOS pressure
and density are recomputed from finished moist theta and cleaned vapor using
the same fixed MU and interface geopotential as prep.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from harness.verify_native_prep_ad import pack_state, unpack_state
from harness.verify_native_finish_ad import finish_jvp, finish_vjp
from oracle.kdm6 import native_finish as finish_api


_MASS_ROWS = (1, 2, 3, 4, 5, 6)  # QV, QC, QR, QI, QS, QG in KDM state order.


def _array(value, shape, name):
    if not isinstance(value, np.ndarray) or value.dtype != np.float64:
        raise TypeError(f"{name} must be a float64 ndarray")
    if value.shape != shape:
        raise ValueError(f"{name} must have shape {shape}")
    if not np.isfinite(value).all():
        raise ValueError(f"{name} must be finite")


@dataclass
class MicrophysicsObservationRecord:
    x: np.ndarray
    rest: np.ndarray
    state: np.ndarray
    raw_after: np.ndarray
    clean_after: np.ndarray
    finish_value: np.ndarray
    post_x: np.ndarray
    handle: object
    signature: np.ndarray
    closed: bool = False


class MicrophysicsObservationState:
    """Compose existing native prep, opaque KDM, cleanup, finish and EOS maps.

    ``x`` is ``(theta_m_pert, QV, MU_total, PH)`` packed as ``3L+2`` values;
    ``rest`` is the ten remaining KDM state rows. Fixed prep geometry and
    scalar configuration remain owned by ``prep``. ``finish`` supplies the
    opaque KDM kernel and captured finish/zero-out configurations.
    """

    def __init__(self, prep, finish):
        if not hasattr(prep, "levels") or not hasattr(prep, "geometry"):
            raise TypeError("prep must provide levels, geometry, forward, jvp and vjp")
        if not all(hasattr(prep, name) for name in ("forward", "jvp", "vjp")):
            raise TypeError("prep must provide forward, jvp and vjp")
        if not all(hasattr(finish, name) for name in ("forward", "kernel", "config", "zero")):
            raise TypeError("finish must provide forward, kernel, config and zero")
        self.prep, self.finish = prep, finish
        self.levels = int(prep.levels)
        if self.levels <= 0:
            raise ValueError("prep levels must be positive")
        if not hasattr(prep.geometry, "phb"):
            raise TypeError("prep geometry must provide fixed PHB interfaces")
        phb = prep.geometry.phb
        if tuple(phb.shape) != (self.levels + 1,) or phb.requires_grad:
            raise ValueError("PHB must be a fixed (L+1) interface vector")
        mode, threshold = finish_api._validate_zero_out_config(finish.zero)
        self.mode, self.threshold = mode, threshold

    def _validate_inputs(self, x, rest):
        _array(x, (3*self.levels+2,), "x")
        _array(rest, (10, self.levels), "rest")

    def _cleanup(self, raw):
        clean = raw.copy()
        if self.mode == 2:
            clean[1] = np.maximum(raw[1], 0.)
        if self.mode:
            for row in _MASS_ROWS[1:]:
                clean[row] = np.where(raw[row] < self.threshold, 0., raw[row])
        return clean

    def _clean_tangent(self, raw, tangent):
        masks = np.ones_like(raw)
        if self.mode == 2:
            masks[1] = (raw[1] > 0.).astype(np.float64)  # clipped side at zero
        if self.mode:
            for row in _MASS_ROWS[1:]:
                masks[row] = (raw[row] >= self.threshold).astype(np.float64)
                if self.threshold > 0. and np.any(raw[row] == self.threshold):
                    raise ValueError(f"cleanup branch tie in state row {row}")
                if self.threshold == 0.:
                    masks[row][raw[row] == 0.] = 0.  # clipped side at the kink
        return masks*tangent

    def _signature(self, state, raw, clean):
        from harness.verify_native_finish_ad import branch_codes
        codes = branch_codes(state[:3], raw[:3], vars(self.finish.config),
                             {"mode": self.mode, "threshold": self.threshold})
        rows = [codes[0]]
        # The finish helper already reports QV/QC gates. Add all six mass
        # cleanup branches in Registry order so FD eligibility sees QI/QS too.
        for row in _MASS_ROWS:
            if row == 1 and self.mode == 2:
                mask = np.where(raw[row] > 0., 1, np.where(raw[row] < 0., 0, 2))
            elif row == 1 or self.mode == 0:
                mask = np.ones(self.levels, dtype=np.int8)
            else:
                mask = np.where(raw[row] > self.threshold, 1,
                                np.where(raw[row] < self.threshold, 0, 2))
            rows.append(mask.astype(np.int8))
        # Retain finish's limiter signature in row zero; seven rows are stable
        # across calls and encode all six cleanup species.
        return np.stack(rows)

    def _check_differentiable_branch(self, record):
        if record.closed:
            raise ValueError("record handle is closed")
        if self.mode and self.threshold > 0.:
            for row in _MASS_ROWS[1:]:
                if np.any(record.raw_after[row] == self.threshold):
                    raise ValueError(f"cleanup discontinuity tie in state row {row}")

    def forward(self, x, rest, *, record=False):
        self._validate_inputs(x, rest)
        x0, r0 = x.copy(), rest.copy()
        g = self.prep.forward(x0)
        _array(g, (5, self.levels), "prep output")
        native = unpack_state(x0, self.levels)
        state = np.ascontiguousarray(np.vstack((g[0], native[1], r0)))
        forcing = np.ascontiguousarray(g[1:])
        handle = None
        try:
            # KernelFinish.forward evaluates the established three-field Z∘K
            # and finish value while retaining the K handle and full raw state.
            finish_value, handle, raw = self.finish.forward(state, forcing, record=record)
            _array(finish_value, (5, self.levels), "finish output")
            _array(raw, (12, self.levels), "raw KDM output")
            clean = self._cleanup(raw)
            post_x = pack_state((finish_value[0], clean[1], native[2], native[3]))
            post = self.prep.forward(post_x)
            _array(post, (5, self.levels), "post-finish prep output")
            # PHB is fixed geometry; this conversion is a value-only boundary.
            phi = native[3] + self.prep.geometry.phb.cpu().numpy()
            y = np.concatenate((finish_value[0], clean[1], post[3], phi, post[1],
                                clean[2], clean[4], clean[5], raw[8], raw[9]))
            _array(y, (10*self.levels+1,), "post-finish observation state")
            sig = self._signature(state, raw, clean)
            rec = MicrophysicsObservationRecord(x0, r0, state.copy(), raw.copy(), clean,
                                                finish_value.copy(), post_x, handle, sig)
            return y, rec
        except BaseException:
            if handle is not None:
                self.finish.kernel.close(handle)
            raise

    def _check_record(self, record):
        if not isinstance(record, MicrophysicsObservationRecord):
            raise TypeError("record must be MicrophysicsObservationRecord")
        if record.closed:
            raise ValueError("record handle is closed")
        _array(record.x, (3*self.levels+2,), "record.x")
        _array(record.rest, (10, self.levels), "record.rest")
        _array(record.state, (12, self.levels), "record.state")
        _array(record.raw_after, (12, self.levels), "record.raw_after")

    def jvp(self, record, dx, dr):
        self._check_record(record)
        self._check_differentiable_branch(record)
        _array(dx, record.x.shape, "dx")
        _array(dr, record.rest.shape, "dr")
        dnative = unpack_state(dx, self.levels)
        dg = self.prep.jvp(record.x, dx)
        _array(dg, (5, self.levels), "prep tangent")
        ds = np.ascontiguousarray(np.vstack((dg[0], dnative[1], dr)))
        df = np.ascontiguousarray(dg[1:])
        draw = self.finish.kernel.jvp(record.handle, ds, df)
        _array(draw, (12, self.levels), "KDM tangent")
        dclean = self._clean_tangent(record.raw_after, draw)
        before = record.state[:3]
        after = record.clean_after[:3]
        result = finish_jvp(before, after, ds[:3], dclean[:3], self.finish.config)
        post_dx = pack_state((result[0], dclean[1], dnative[2], dnative[3]))
        dpost = self.prep.jvp(record.post_x, post_dx)
        phi = dnative[3]
        out = np.concatenate((result[0], dclean[1], dpost[3], phi, dpost[1],
                              dclean[2], dclean[4], dclean[5], draw[8], draw[9]))
        _array(out, (10*self.levels+1,), "observation tangent")
        return out

    def vjp(self, record, flat_uy):
        self._check_record(record)
        self._check_differentiable_branch(record)
        _array(flat_uy, (10*self.levels+1,), "flat_uy")
        levels = self.levels
        parts = np.split(flat_uy, (levels, 2*levels, 3*levels, 4*levels+1,
                                   5*levels+1, 6*levels+1, 7*levels+1,
                                   8*levels+1, 9*levels+1))
        u_th, u_qv, u_p, u_phi, u_rho, u_qc, u_qi, u_qs, u_nc, u_ni = parts

        # Post-finish EOS transpose: only P and rho are exposed from this prep.
        u_post = np.zeros((5, levels), dtype=np.float64)
        u_post[1], u_post[3] = u_rho, u_p
        post_seed = self.prep.vjp(record.post_x, u_post)
        post_parts = unpack_state(post_seed, levels)
        u_finish = np.zeros((5, levels), dtype=np.float64)
        u_finish[0] = u_th + post_parts[0]
        clean_u = np.zeros((12, levels), dtype=np.float64)
        clean_u[1] = u_qv + post_parts[1]
        clean_u[2], clean_u[4], clean_u[5] = u_qc, u_qi, u_qs
        clean_u[8], clean_u[9] = u_nc, u_ni
        direct_before, direct_after = finish_vjp(record.state[:3], record.clean_after[:3],
                                                  u_finish, self.finish.config)
        clean_u[:3] += direct_after

        # Pull through all six cleanup maps, then K's complete 12-state / 4-F ABI.
        zmask = np.ones((12, levels), dtype=np.float64)
        if self.mode == 2:
            zmask[1] = (record.raw_after[1] > 0.).astype(np.float64)
        if self.mode:
            for row in _MASS_ROWS[1:]:
                zmask[row] = (record.raw_after[row] >= self.threshold).astype(np.float64)
                if self.threshold == 0.:
                    zmask[row][record.raw_after[row] == 0.] = 0.
        k_u = zmask*clean_u
        gs, gf = self.finish.kernel.vjp(record.handle, np.ascontiguousarray(k_u))
        _array(gs, (12, levels), "KDM state adjoint")
        _array(gf, (4, levels), "KDM forcing adjoint")

        # Direct R_s paths plus K's upstream state/forcing are mapped through
        # the initial prep; incoming QV also enters K as an independent state.
        u_pre = np.zeros((5, levels), dtype=np.float64)
        u_pre[0] = gs[0] + direct_before[0]
        u_pre[1:] = gf
        gx = self.prep.vjp(record.x, u_pre)
        gx[levels:2*levels] += gs[1] + direct_before[1]
        gx[2*levels] += post_parts[2]
        gx[2*levels+1:] += post_parts[3] + u_phi
        gr = np.ascontiguousarray(gs[2:])
        gr[0] += direct_before[2]
        _array(gx, record.x.shape, "initial-state adjoint")
        _array(gr, record.rest.shape, "remaining-state adjoint")
        return gx, gr

    def branch_signature(self, record):
        self._check_record(record)
        return record.signature.copy()

    def close(self, record):
        if not isinstance(record, MicrophysicsObservationRecord):
            raise TypeError("record must be MicrophysicsObservationRecord")
        if not record.closed:
            if record.handle is not None:
                self.finish.kernel.close(record.handle)
            record.closed = True
