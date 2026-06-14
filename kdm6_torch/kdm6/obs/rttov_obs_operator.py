"""P6 -- RttovObsOp custom autograd.Function + obs_adjoint_callback (design 9.1/10/14.3; M6).

The entry point that puts non-torch RTTOV into the torch graph. `RttovObsOp.forward`
packs the RTTOV-unit tensors and runs a SINGLE runK (BT + K cached); `backward`
does the channel contraction `λ_profile = Σ_c K[c]·λ_BT[c]` (K^T·λ_BT) in-process
torch (runK takes no seed, design 9.1). The callback implements da_window's
`obs_adjoint(t, x_t)` (detached state -> covector), closing the loss locally with
`autograd.grad` (never via Handle.vjp, design 10/14.3).

Scope (P6, matching P2): the clear-sky T/Q path. The differentiable RTTOV inputs
are (t_lay, q_lay) -> K fields ('T', 'Q'); RttovObsOp also returns ``rad_quality``
(marked non-differentiable) so the loss can enforce the design-8 mask. Cloud
content/Deff fields are appended when the hydrotable lands.

``run_k`` is INJECTED (RttovInput -> (bt, K, rad_quality)): the live adapter wraps
write-case + `rttov_runner.run_rttov_k`; tests pass an analytic mock so the full
autograd closure J_obs -> BT -> K^T·λ_BT -> tensors -> leaves is verified offline
(the acceptance gate for "differentiable obs operator", mirroring the
microphysics test_autograd_endtoend).
"""
from __future__ import annotations

from typing import NamedTuple

import torch

from ..state import Forcing, State
from .model_profile_builder import RttovProfileTensors, model_to_rttov_tensors
from .obs_loss import compute_obs_loss
from .rttov_input_builder import pack_rttov_input

# Fields that NEVER have an RTTOV obs path (0 is the answer; dynamics VJP carries
# their sensitivity). nccn: no BT path. nr/bg: RTTOV-14 has no rain/graupel Deff
# item (design 9.1; rttype.py:94-98). Subset of "not connected" in any mode.
OBS_ZERO_OK = frozenset({"nccn", "nr", "bg"})

# Clear-sky (P2/P6) connected fields: only T(th) and Q(qv) reach BT. Everything
# else (cloud content/number) is legitimately 0 until the cloud path is built.
CLEAR_SKY_CONNECTED = frozenset({"th", "qv"})

# The differentiable RTTOV-input tensors passed to RttovObsOp.apply, in order,
# and the K-matrix field each maps to (design 9.1: gas/T K). Clear-sky.
_GRAD_FIELDS = ("T", "Q")  # (t_lay, q_lay)


class ObsOperatorConfig(NamedTuple):
    """Bundle for the callback: P2 profile config + P4 input config + loss params."""
    profile_cfg: object        # RttovProfileConfig (P2)
    input_cfg: object          # RttovInputConfig (P4)
    sigma: object              # obs error (scalar or per-channel)
    huber_delta: float = 1.0
    connected_fields: frozenset = CLEAR_SKY_CONNECTED


class RttovObsOp(torch.autograd.Function):
    """forward: runK 1x -> (BT, rad_quality), cache K. backward: K^T·λ_BT.

    ``apply(run_k, rttov_config, t_lay, q_lay, p_lay, p_half)`` -- ``run_k`` and
    ``rttov_config`` are non-tensor (backward returns None for them); ``t_lay``/
    ``q_lay`` are the differentiable inputs; ``p_lay``/``p_half`` are constant grids
    (no grad). Returns ``(bt, rad_quality)`` with ``rad_quality`` marked
    non-differentiable.
    """

    @staticmethod
    def forward(ctx, run_k, rttov_config, t_lay, q_lay, p_lay, p_half):
        prof = RttovProfileTensors(t_lay=t_lay, q_lay=q_lay, p_lay=p_lay, p_half=p_half)
        rin = pack_rttov_input(prof, rttov_config)     # torch -> numpy (detached)
        bt_np, k_dict, rad_quality_np = run_k(rin)     # single runK: BT + K + quality
        # fail FAST at the run_k contract boundary (not later inside autograd):
        missing = set(_GRAD_FIELDS) - set(k_dict)
        if missing:
            raise KeyError(
                f"run_k k_dict missing required K field(s) {sorted(missing)} for the "
                f"differentiable inputs {_GRAD_FIELDS} (design 9.1 PROFILES_K).")
        ctx.k_dict = k_dict
        ctx.config_hash = rin.config_hash
        ctx.grad_fields = _GRAD_FIELDS
        ctx.in_shapes = (tuple(t_lay.shape), tuple(q_lay.shape))
        ctx.dtype = t_lay.dtype
        ctx.device = t_lay.device
        bt = torch.as_tensor(bt_np, dtype=t_lay.dtype, device=t_lay.device)
        rad_quality = torch.as_tensor(rad_quality_np, device=t_lay.device)
        ctx.mark_non_differentiable(rad_quality)
        return bt, rad_quality

    @staticmethod
    def backward(ctx, grad_bt, grad_rad_quality):
        # grad_bt = λ_BT [nprofiles, nchannels]; grad_rad_quality is None (non-diff).
        lam = grad_bt
        grads = []
        nprof, nch = lam.shape
        for field, in_shape in zip(ctx.grad_fields, ctx.in_shapes):
            k = ctx.k_dict[field]
            kt = torch.as_tensor(k, dtype=ctx.dtype, device=ctx.device)  # [nprof,nch,nlay]
            # Guard the K shape: a transposed (or square nlay==nch) K would give a
            # wrong-but-finite gradient silently (design 9.1/F1-SHAPE seam, md:601/730).
            nlay = in_shape[-1]
            if tuple(kt.shape) != (nprof, nch, nlay):
                raise ValueError(
                    f"K['{field}'] shape {tuple(kt.shape)} != expected "
                    f"(nprofiles, nchannels, nlayers) ({nprof}, {nch}, {nlay}); "
                    "guards a transposed/square-K silent wrong-gradient.")
            # channel contraction K^T·λ_BT: grad_field[p,l] = Σ_c K[p,c,l]·λ_BT[p,c]
            g = torch.einsum("pcl,pc->pl", kt, lam)
            grads.append(g.reshape(in_shape))   # match the forward input's shape (1-D single profile)
        # forward args: (run_k, rttov_config, t_lay, q_lay, p_lay, p_half)
        return (None, None, grads[0], grads[1], None, None)


def assemble_obs_covector(leaves: State, grads, *, connected_fields=CLEAR_SKY_CONNECTED) -> State:
    """grads (None allowed) -> 12-field State covector.

    A ``None`` grad for a **connected** field (one this operator mode feeds to
    RTTOV) is a STRUCTURAL SEVER (model_to_rttov_tensors broke the graph with
    numpy) -> loud raise. A ``None`` for a non-connected field is the legitimate
    zero (no RTTOV path in this mode; dynamics VJP carries it) -> zeros. This
    generalizes the design's OBS_ZERO_OK to the staged operator: in clear-sky
    only {th, qv} are connected, so the cloud fields are legitimately 0, not severs.
    """
    out = []
    for name, g in zip(State._fields, grads):
        if g is None:
            if name in connected_fields:
                raise RuntimeError(
                    f"obs adjoint structural sever: λ_{name}=None but {name} is a "
                    "connected (RTTOV-fed) field -- model_to_rttov_tensors must be "
                    "all-torch from leaves (design 14.3). silent-zero forbidden.")
            g = torch.zeros_like(getattr(leaves, name))   # legitimate zero (no path in this mode)
        out.append(g.detach())
    return State(*out)


def _build_mask(obs, rad_quality):
    """Combined detached 0/1 keep-mask (design 8): keep (profile, channel) iff
    ``obs_quality == 0`` AND ``rad_quality == 0``.

    ``obs_quality`` and ``rad_quality`` are QUALITY FLAGS, not keep-masks: 0 means
    usable, nonzero means flagged/clipped (the RTTOV/obs convention, design 8 --
    "BOTH quality == 0 enter"). They are gated identically (== 0) so a real obs
    quality flag (0=good) is honored, not inverted. ``channel_gate`` (optional) is
    a genuine keep-condition (1=keep, e.g. IR-only / cloud regime) and multiplies
    directly. ``obs`` may omit ``obs_quality`` (default: all usable).
    """
    dt = torch.float64
    mask = (rad_quality == 0).to(dt)
    oq = obs.get("obs_quality")
    if oq is not None:
        mask = mask * (torch.as_tensor(oq, device=mask.device) == 0).to(dt)
    cg = obs.get("channel_gate")     # keep-condition (1=keep), NOT a quality flag
    if cg is not None:
        mask = mask * torch.as_tensor(cg, dtype=dt, device=mask.device)
    return mask.detach()


def default_run_k(rttov_input):
    """Live RTTOV runner (RttovInput -> (bt, K, rad_quality)) via a fresh case dir.

    Convenience over ``make_live_run_k`` (rttov_case_writer): each call allocates a
    UNIQUE scratch case dir (``mkdtemp``), writes the rttov_test case (overlay model
    T/Q onto the AD-RTTOV fixture) -> out-of-process ``run_rttov_k`` (single runK) ->
    reorders RttovKOutput to (bt, K, rad_quality), then removes the scratch dir. The
    per-call unique dir makes concurrent calls race-free (a shared fixed dir would
    let one call clobber another's case mid-run -> silently wrong BT/K, hence wrong
    gradient). For an explicit/persistent case dir or a custom timeout/fixture,
    build your own via ``make_live_run_k(out_case_dir, ...)`` and inject it. Live run
    stays out-of-process (design 14.2); env-coupled (needs AD_RTTOV_HOME). The
    offline autograd closure is validated with an analytic mock runner.
    """
    import shutil
    import tempfile
    from .rttov_case_writer import make_live_run_k
    case_dir = tempfile.mkdtemp(prefix="kdm6_rttov_run_")
    try:
        # overwrite=True: mkdtemp pre-creates case_dir, so write_rttov_case must replace it.
        return make_live_run_k(case_dir)(rttov_input)
    finally:
        shutil.rmtree(case_dir, ignore_errors=True)


def obs_adjoint_callback(t, x_t, *, schedule, cfg, forcings, run_k,
                         xland=None, ncmin_land=0.0, ncmin_sea=0.0):
    """da_window obs_adjoint(t, x_t) -> covector ∂J_obs/∂x_t (or None).

    Bind the keyword args before handing this to da_window (whose contract is the
    2-arg ``obs_adjoint(t, x_t)``), e.g.::

        obs_adjoint = functools.partial(obs_adjoint_callback, schedule=sched,
                                        cfg=cfg, forcings=config.forcings, run_k=run_k)

    ``forcings`` is the per-step SEQUENCE (same as ``WindowConfig.forcings``); the
    callback uses ``forcings[t]`` because the forcing varies per step (binding a
    single forcing via partial would be wrong for every step but one).

    Closes the loss LOCALLY with autograd.grad (window backward / Handle.vjp NOT
    traversed, design 10/14.3): fresh requires_grad leaves from detached x_t ->
    pure-torch model_to_rttov_tensors -> RttovObsOp.apply -> compute_obs_loss
    (summed over the step's obs footprints) -> autograd.grad -> covector.
    """
    obs_list = schedule.get(t)
    if not obs_list:
        return None   # no obs at this step -> window runs pure dynamics VJP

    # da_window also calls obs_adjoint at the FINAL time t == T (state_final), but
    # WindowConfig.forcings has length T (steps 0..T-1), so forcings[T] is out of
    # range. The scheduler legitimately binds an obs to k = N = T (boundary_obs),
    # so this path is real. Reuse the last forcing for the final state -- the
    # vertical coordinate (pii/p) is ~constant across a DA window; a caller with an
    # exact final-time forcing may pass forcings of length T+1 (then forcings[T] is used).
    if not forcings:
        raise ValueError("forcings is empty -- cannot evaluate the obs operator.")
    forcing = forcings[t] if t < len(forcings) else forcings[-1]
    leaves = State(*(f.detach().clone().requires_grad_(True) for f in x_t))

    # da_window passes a 2-D [1, nlev] single-column state/forcing, but
    # model_to_rttov_tensors wants a 1-D [nlev] column. Squeeze the leading
    # singleton profile dim for the obs path; grads flow back through the view, so
    # the covector keeps the leaves' (2-D) rank and matches x_t for
    # da_window._validate_state_shapes. (A 1-D x_t -- isolated use -- passes through.)
    squeeze = (leaves.th.ndim == 2 and leaves.th.shape[0] == 1)

    def _col(x):
        return x.squeeze(0) if squeeze else x

    col_leaves = State(*(_col(f) for f in leaves))
    col_forcing = (Forcing(*(_col(getattr(forcing, k)) for k in Forcing._fields))
                   if squeeze else forcing)

    prof = model_to_rttov_tensors(col_leaves, col_forcing, cfg.profile_cfg,
                                  xland=xland, ncmin_land=ncmin_land, ncmin_sea=ncmin_sea)
    bt_hat, rad_quality = RttovObsOp.apply(
        run_k, cfg.input_cfg, prof.t_lay, prof.q_lay, prof.p_lay, prof.p_half)

    j = None
    any_active = False
    for o in obs_list:
        mask = _build_mask(o, rad_quality)
        if float(mask.sum()) > 0.0:   # mask is detached -> .sum() is graph-free
            any_active = True
        term = compute_obs_loss(bt_hat, o, mask, cfg.sigma, delta=cfg.huber_delta)
        j = term if j is None else j + term
    if not any_active:
        # obs PRESENT but every (profile, channel) masked out (rad_quality /
        # obs_quality) -> J=0, covector all-zero. Legal & recoverable, but silent
        # -> warn so a fully-flagged step is not mistaken for the no-obs path.
        import warnings
        warnings.warn(
            f"obs_adjoint_callback(t={t}): all obs at this step are masked out "
            "(rad_quality/obs_quality) -> zero obs gradient.", RuntimeWarning, stacklevel=2)

    # materialize_grads is NOT used: a None means "no path" (legitimate zero for a
    # non-connected field) or "severed" (a connected field) -- assemble decides,
    # so a real break fails loud instead of being silently zeroed.
    grads = torch.autograd.grad(j, tuple(leaves), allow_unused=True)
    return assemble_obs_covector(leaves, grads, connected_fields=cfg.connected_fields)
