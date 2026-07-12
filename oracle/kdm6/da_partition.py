"""Conserving/bounded partition CVT stage (P1-1, design v1.1 post panel).

Composed AFTER the diagonal CVT: x0 = P_w(D_v(xb)). Four SIGNED channels move
mass between species pairs so total water is invariant by construction and
every increment is bounded by frozen background-derived caps — no unbounded
exp (the P0-3 qi-explosion root cause). The mass hydrometeor fields get
sigma=0 in the diagonal stage under conserving use; number concentrations
keep their diagonal mul controls (no mass, no latent heat).

Channel table (ORDER IS FROZEN — the chain is non-commuting through T, so
order is part of the fingerprint):

    vap<->liq      qv <-> qc   latent xl(T_pre)   (same L both directions)
    vap<->ice      qv <-> qi   latent xls          (constant, symmetric)
    cloud<->rain   qc <-> qr   mass-only
    snow<->graupel qs <-> qg   mass-only

liq<->ice has NO direct channel: it is reachable by composition
vap<->liq(-d) + vap<->ice(+d), whose net latent is exactly xls - xl(T) = L_f
— identical to the freeze operator. This keeps the §37 branch-conditional
latent constants (melt xlf0 vs freeze xls-xl) out of the CVT entirely, so no
sign branch and no kink at the optimizer's w=0 start.

Bounded map (C^1, exact zero):  delta(u) = u / (1 + relu(u)/cap_fwd
+ relu(-u)/cap_rev).  delta(0) = 0 exactly and delta'(0) = 1 from both sides;
saturates at +cap_fwd / -cap_rev. Cells where EITHER frozen donor cap is 0
kill the WHOLE channel (exact-0 value and gradient both sides — the sigma=0
whole-dof death pattern; a one-sided mask would put a kink at w=0, and a bare
torch.where over the raw map is the 0*inf where-backward NaN trap).

Controls are DIMENSIONLESS (like the diagonal CVT's v): the chain feeds
u = sigma * w with sigma = sigma_scale * min(cap_fwd, cap_rev) frozen from
the background — the partition-B standard deviation in physical units. The
prior 0.5*||w||^2 therefore states delta ~ N(0, sigma^2) near the origin
(saturation shrinks the tails), and every L-BFGS leaf (v, v_theta, w) shares
an identity prior Hessian — no kg/kg-vs-dimensionless conditioning skew.
sigma = 0 exactly on dead cells (min cap 0), reproducing the zero-row
invariant: u = 0, delta = 0, g_w row = w -> the prior pins w = 0 forever.

Caps are frozen from the background (v/w-independent — observation-
independent B) with a per-DONOR budget: all channel sides draining one donor
together stay within alpha_total * q_donor(xb) (per-channel alphas would
over-drain shared donors: qc is drained by both vap<->liq reverse and
cloud<->rain forward). Donor positivity is an AUDIT bound, not a hard
guarantee: the diagonal stage can additionally deplete qv within its own
3-sigma envelope (da_cvt V4 formula) — recorded, not clamped.

Energy convention: each channel's latent coefficients (xl, cpm) are evaluated
at its PRE-OP intermediate state — the §5.4 operator convention (da_window).
Per-op the budget dth = +-L_op/(cpm_pre*pi)*delta is exact; the composed
chain is O(delta^2) and order-dependent. Creation is NOT a partition job:
clear cells have a zero donor on one side, so channels are dead there —
regime-2 creation stays with the pseudo-RH bootstrap (da_regime2).

DRIVER-level operators on the fp64 DA path only — the operational mp137
forward never sees them (design §5.3 partition_control_enabled semantics).
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import NamedTuple

import torch

from .state import Forcing, State
from .thermo import compute_cpm, compute_xl, default_thermo_params

# (name, forward donor, forward receiver, latent kind) — frozen order
CHANNELS = (
    ("vap2liq", "qv", "qc", "xl"),
    ("vap2ice", "qv", "qi", "xls"),
    ("cloud2rain", "qc", "qr", None),
    ("snow2graupel", "qs", "qg", None),
)

# donor field -> number of channel sides draining it (forward drains the
# donor, reverse drains the receiver)
_DRAINERS: dict = {}
for _n, _don, _rec, _l in CHANNELS:
    _DRAINERS[_don] = _DRAINERS.get(_don, 0) + 1
    _DRAINERS[_rec] = _DRAINERS.get(_rec, 0) + 1


@dataclass(frozen=True)
class PartitionSpec:
    """Frozen partition-stage config. alpha_total is the per-DONOR budget:
    the caps of all channel sides draining one donor sum to
    alpha_total * q_donor(xb). sigma_scale sets the dimensionless-control
    scale sigma = sigma_scale * min(cap_fwd, cap_rev) — the physical 1-sigma
    of the partition increment under the 0.5*||w||^2 prior."""
    alpha_total: float = 0.5
    sigma_scale: float = 0.25

    def __post_init__(self):
        for name in ("alpha_total", "sigma_scale"):
            a = getattr(self, name)
            if not (isinstance(a, (int, float)) and math.isfinite(a)
                    and 0.0 < a <= 1.0):
                raise ValueError(
                    f"{name} must be finite in (0, 1] (got {a!r})")
            object.__setattr__(self, name, float(a))

    def as_dict(self) -> dict:
        return {"version": 1, "alpha_total": self.alpha_total,
                "sigma_scale": self.sigma_scale,
                "channels": [c[0] for c in CHANNELS]}

    def fingerprint(self) -> str:
        """Name-bound sha256 — sensitive to channel order/pairing/latent
        convention and to alpha/sigma_scale (the chain is non-commuting
        through T; sigma_scale changes the control metric)."""
        payload = "partition-v1|" + "|".join(
            f"{n}:{d}>{r}:{l}" for n, d, r, l in CHANNELS)
        payload += f"|{self.alpha_total.hex()}|{self.sigma_scale.hex()}"
        return hashlib.sha256(payload.encode()).hexdigest()


class PartitionCaps(NamedTuple):
    """Frozen per-channel caps and control scale (n_ch, B, K)."""
    cap_fwd: torch.Tensor
    cap_rev: torch.Tensor
    sigma: torch.Tensor         # sigma_scale * min(caps); 0 <=> channel dead
    active: torch.Tensor        # bool — both donor caps positive


def build_partition_caps(xb: State, spec: PartitionSpec) -> PartitionCaps:
    """Frozen v/w-independent caps from the background. Non-positive donor
    background gives cap 0 (self-exclusion, V3 style — never a sign-flipped
    cap); either side 0 deactivates the whole channel in that cell."""
    with torch.no_grad():
        fwd, rev = [], []
        for _name, don, rec, _lat in CHANNELS:
            for src, out in ((don, fwd), (rec, rev)):
                q = getattr(xb, src).detach().to(torch.float64)
                if not bool(torch.isfinite(q).all()):
                    raise ValueError(
                        f"xb.{src} must be finite to build partition caps")
                a = spec.alpha_total / _DRAINERS[src]
                out.append(torch.where(q > 0, a * q, torch.zeros_like(q)))
        cf, cr = torch.stack(fwd), torch.stack(rev)
        sigma = spec.sigma_scale * torch.minimum(cf, cr)
        return PartitionCaps(cap_fwd=cf, cap_rev=cr, sigma=sigma,
                             active=(cf > 0) & (cr > 0))


def bounded_delta(w: torch.Tensor, cap_fwd: torch.Tensor,
                  cap_rev: torch.Tensor,
                  active: torch.Tensor) -> torch.Tensor:
    """C^1 signed saturating map (module docstring). Dead cells are masked by
    SUBSTITUTING safe caps before the division and zeroing the product — the
    only NaN-free masking with zero gradient from both sides."""
    one = torch.ones_like(w)
    safe_f = torch.where(active, cap_fwd, one)
    safe_r = torch.where(active, cap_rev, one)
    raw = w / (1.0 + torch.relu(w) / safe_f + torch.relu(-w) / safe_r)
    return raw * active.to(w.dtype)


def apply_partition_chain(y: State, forcing: Forcing, w: torch.Tensor,
                          caps: PartitionCaps) -> State:
    """Ordered signed-channel chain — differentiable in w AND in the y fields
    (the minimizer pullback builds a local graph over both). Latent
    coefficients from each op's PRE-OP intermediate state (§5.4 convention).
    No clamp anywhere — positivity is the caps'/optimizer's business."""
    n = len(CHANNELS)
    want = (n,) + tuple(y.th.shape)
    if tuple(w.shape) != want:
        raise ValueError(f"w shape {tuple(w.shape)} != {want}")
    tp = default_thermo_params()
    fld = {f: getattr(y, f)
           for f in ("th", "qv", "qc", "qr", "qi", "qs", "qg")}
    for i, (_name, don, rec, latent) in enumerate(CHANNELS):
        d = bounded_delta(caps.sigma[i] * w[i], caps.cap_fwd[i],
                          caps.cap_rev[i], caps.active[i])
        if latent is not None:
            cpm = compute_cpm(fld["qv"], params=tp)
            lat = (compute_xl(fld["th"] * forcing.pii, params=tp)
                   if latent == "xl" else tp.xls)
            fld["th"] = fld["th"] + lat / (cpm * forcing.pii) * d
        fld[don] = fld[don] - d
        fld[rec] = fld[rec] + d
    return y._replace(**fld)


def chain_with_pullback(y: State, forcing: Forcing, w: torch.Tensor,
                        caps: PartitionCaps):
    """Local-autograd seam for the manual-gradient minimizers (the
    pseudo_rh_term pattern): returns (x0 detached, pullback) where
    pullback(adj_x0) -> (adj_y (12,B,K), g_w_obs).

    Leaves cover ALL 12 y fields — identity fields appear in the inner
    product, so their adjoint rows pass through exactly instead of being
    silently zeroed (allow_unused trap). adj_y feeds the diagonal manual
    chain rule (g_v = v + jac * adj_y) — no double counting: adj_x0 arrives
    detached from the window adjoint."""
    leaves = State(*(t.detach().clone().requires_grad_(True) for t in y))
    w_leaf = w.detach().clone().requires_grad_(True)
    with torch.enable_grad():
        out = apply_partition_chain(leaves, forcing, w_leaf, caps)
    x0 = State(*(t.detach() for t in out))

    def pullback(adj_x0: State):
        with torch.enable_grad():
            inner = sum((a.detach() * o).sum()
                        for a, o in zip(adj_x0, out))
        grads = torch.autograd.grad(inner, [*leaves, w_leaf])
        return torch.stack(grads[:-1]), grads[-1]
    return x0, pullback


# the 5 hydrometeor MASS fields — diagonal mul sigma must be 0 when the
# partition stage is active (conserving contract, enforced)
MASS_HYDRO_FIELDS = ("qc", "qr", "qi", "qs", "qg")


def validate_conserving_sigma(b_sigma: State) -> None:
    """Enforced conserving contract: a live diagonal mul control on a mass
    hydrometeor field double-controls the species (degenerate with the
    channels) and silently breaks the total-water invariance the partition
    stage exists to provide. qv stays allowed — it is the deliberate
    total-water dof (moisture correction)."""
    bad = [f for f in MASS_HYDRO_FIELDS
           if bool((getattr(b_sigma, f) != 0).any())]
    if bad:
        raise ValueError(
            f"partition given but b_sigma is nonzero for mass hydrometeor "
            f"fields {bad} — the conserving contract requires their diagonal "
            "sigma == 0 (species move only through partition channels)")


def validate_partition_forcing(forcing: Forcing, xb: State) -> None:
    """The chain reads forcing.pii (Exner) for its latent terms. On the
    zero-step path this bypasses the model's own forcing validation, so a
    wrong-shape pii would silently broadcast and a 0/NaN pii makes
    non-finite theta increments — exact contract enforced here."""
    pii = forcing.pii
    if tuple(pii.shape) != tuple(xb.th.shape):
        raise ValueError(
            f"partition forcing pii shape {tuple(pii.shape)} != state shape "
            f"{tuple(xb.th.shape)} (silent broadcasting is forbidden)")
    if pii.device != xb.th.device:
        raise ValueError(
            f"partition forcing pii device {pii.device} != state device "
            f"{xb.th.device}")
    if not bool(torch.isfinite(pii).all()) or bool((pii <= 0).any()):
        raise ValueError(
            "partition forcing pii must be finite and > 0 (Exner function)")


def validate_partition(caps: PartitionCaps,
                       active_fields: "tuple | None") -> None:
    """V8: runtime.py zero-masks adjoint rows outside active_fields — a live
    channel whose donor/receiver/th row is masked would get a silently-zero
    g_w (the prior pins w=0 while the channel is recorded as controlled).
    Loud error instead (V5 rationale)."""
    if active_fields is None:
        return
    for i, (name, don, rec, latent) in enumerate(CHANNELS):
        if not bool(caps.active[i].any()):
            continue
        touched = {don, rec} | ({"th"} if latent is not None else set())
        missing = sorted(touched - set(active_fields))
        if missing:
            raise ValueError(
                f"partition channel {name} is active but touched fields "
                f"{missing} are not in active_fields — their window adjoint "
                "rows are zero-masked, so g_w would be silently 0")


def build_partition_record(spec: PartitionSpec, caps: PartitionCaps,
                           w: torch.Tensor) -> dict:
    """JSON-serializable audit record: fingerprint pins channel order/alpha,
    caps sha pins the frozen background budget, n_active is the honest DOF
    count, sat_max flags channels riding their cap at the analysis."""
    with torch.no_grad():
        rec = {"spec": spec.as_dict(), "fingerprint": spec.fingerprint(),
               "n_active": {}, "sat_max": {}}
        for i, (name, _don, _rec, _lat) in enumerate(CHANNELS):
            act = caps.active[i]
            rec["n_active"][name] = int(act.sum())
            d = bounded_delta(caps.sigma[i] * w[i], caps.cap_fwd[i],
                              caps.cap_rev[i], act)
            side = torch.where(d >= 0, caps.cap_fwd[i], caps.cap_rev[i])
            sat = (d.abs() / side)[act]
            rec["sat_max"][name] = float(sat.max()) if sat.numel() else 0.0
        h = hashlib.sha256()
        for t in (caps.cap_fwd, caps.cap_rev):
            h.update(t.detach().cpu().numpy().tobytes())
        rec["caps_sha256"] = h.hexdigest()
    return rec
