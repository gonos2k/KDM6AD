"""P6 -- RttovObsOp custom autograd.Function + obs_adjoint_callback (design 9.1/10/14.3; M6).

The entry point that puts non-torch RTTOV into the torch graph. `RttovObsOp.forward`
packs the RTTOV-unit tensors and runs a SINGLE runK (BT + K cached); `backward`
does the channel contraction `λ_profile = Σ_c K[c]·λ_BT[c]` (K^T·λ_BT) in-process
torch (runK takes no seed, design 9.1). The callback implements da_window's
`obs_adjoint(t, x_t)` (detached state -> covector), closing the loss locally with
`autograd.grad` (never via Handle.vjp, design 10/14.3).

Scope: clear-sky T/Q AND (Phase 2) the all-sky cloud path. Differentiable inputs are
(t_lay, q_lay) -> K ('T','Q') plus, in cloud mode, (clw, ciw, deff_liq, deff_ice) ->
K ('HYDRO6','HYDRO7','HYDRO_DEFF6','HYDRO_DEFF7'); cfrac is a non-differentiable
passthrough. RttovObsOp also returns ``rad_quality`` (marked non-differentiable) so
the loss can enforce the design-8 mask. The einsum + K-shape guard are field-agnostic,
so the cloud expansion is a wider grad-input list, not new contraction logic. Live
cloud K (HYDRO*) needs the AMI hydrotable + cloud fixture (Phases 5-6); the offline
mock validates the full cloud autograd closure now.

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
from .obs_loss import compute_obs_loss, symmetric_obs_error
from .rttov_input_builder import pack_rttov_input

# Fields that NEVER have an RTTOV obs path (0 is the answer; dynamics VJP carries
# their sensitivity). nccn: no BT path. nr/bg: RTTOV-14 has no rain/graupel Deff
# item (design 9.1; rttype.py:94-98). Subset of "not connected" in any mode.
OBS_ZERO_OK = frozenset({"nccn", "nr", "bg"})

# Clear-sky (P2/P6) connected fields: only T(th) and Q(qv) reach BT. Everything
# else (cloud content/number) is legitimately 0 until the cloud path is built.
CLEAR_SKY_CONNECTED = frozenset({"th", "qv"})

# All-sky (cloud) must-connect leaves: clear-sky T/Q + cloud content (qc->clw,
# qi+qs->ciw) AND the number moments nc/ni (via Deff). nc/ni are INCLUDED because the
# bridge's preamble is graph-preserving (torch.where keeps both branches in the graph),
# so in cloud mode nc/ni ALWAYS return a tensor -- a ZERO tensor when the size is
# clamped/inactive, NOT None (verified across clear/liquid/ice/mixed columns). Hence a
# None grad for nc/ni can ONLY mean a structural sever (a numpy/.detach() break in
# model_to_rttov_tensors) -> raise, never silently zero. qr/qg (no VIS/IR Deff item)
# and nccn/nr/bg stay non-connected (legitimate zero; their sensitivity rides dynamics).
ALL_SKY_CONNECTED = frozenset({"th", "qv", "qc", "qi", "qs", "nc", "ni"})


class _Unset:
    """Sentinel distinguishing a cloud arg NOT passed (clear-sky 6-arg apply ->
    backward returns 6) from one passed as None (cloud 11-arg apply -> returns 11).
    torch.autograd backward must return one grad per arg PASSED to apply."""
    __slots__ = ()


_UNSET = _Unset()

# Differentiable RttovObsOp.apply inputs: (apply-arg index, PROFILES_K field). Base
# T/Q always present; cloud content/Deff present in cloud mode. Apply arg order:
#   0 run_k, 1 rttov_config, 2 t_lay, 3 q_lay, 4 p_lay, 5 p_half,
#   6 clw, 7 ciw, 8 deff_liq, 9 deff_ice, 10 cfrac (cfrac = non-diff passthrough)
_GRAD_INPUTS = ((2, "T"), (3, "Q"), (6, "HYDRO6"), (7, "HYDRO7"),
                (8, "HYDRO_DEFF6"), (9, "HYDRO_DEFF7"))


class ObsOperatorConfig(NamedTuple):
    """Bundle for the callback: P2 profile config + P4 input config + loss params."""
    profile_cfg: object        # RttovProfileConfig (P2)
    input_cfg: object          # RttovInputConfig (P4)
    sigma: object              # static obs error (scalar, or PER-CHANNEL if solar_channels)
    huber_delta: float = 1.0
    connected_fields: frozenset = CLEAR_SKY_CONNECTED
    error_model: object = None  # Phase 3: SymmetricObsError (CA-dependent sigma) or None
    # Phase 7: 1-based ids whose observable is REFLECTANCE (the run_k must be built with
    # the SAME set, e.g. make_live_run_k(solar_channels=...)). When non-empty the
    # observable mixes BT + REFL units -> ``sigma`` MUST be per-channel (validated below).
    solar_channels: tuple = ()


class RttovObsOp(torch.autograd.Function):
    """forward: runK 1x -> (BT, rad_quality), cache K. backward: K^T·λ_BT.

    Clear-sky: ``apply(run_k, rttov_config, t_lay, q_lay, p_lay, p_half)`` (6 args).
    All-sky (cloud): ``apply(..., p_half, clw, ciw, deff_liq, deff_ice, cfrac)`` (11
    args, all-or-nothing). ``run_k``/``rttov_config`` are non-tensor; ``t_lay``/
    ``q_lay`` (and cloud content/Deff) are differentiable; ``p_lay``/``p_half``/
    ``cfrac`` are constant grids/weights (no grad). Returns ``(bt, rad_quality)`` with
    ``rad_quality`` marked non-differentiable. backward returns one grad per arg
    PASSED (6 clear-sky / 11 cloud) -- the _UNSET sentinel distinguishes the two.
    """

    @staticmethod
    def forward(ctx, run_k, rttov_config, t_lay, q_lay, p_lay, p_half,
                clw=_UNSET, ciw=_UNSET, deff_liq=_UNSET, deff_ice=_UNSET, cfrac=_UNSET):
        cloud = (clw, ciw, deff_liq, deff_ice, cfrac)
        passed = [x is not _UNSET for x in cloud]
        if any(passed) and not all(passed):
            raise ValueError(
                "cloud inputs are all-or-nothing: pass all 5 "
                "(clw, ciw, deff_liq, deff_ice, cfrac) or none (clear-sky).")
        cloud_mode = all(passed)
        if cloud_mode and any(x is None for x in cloud):
            # a None among the 5 (vs _UNSET) is a PARTIAL cloud profile -- reject, don't
            # silently drop the None field (grad_specs/pack would skip it). reject-don't-drop.
            raise ValueError(
                "cloud mode: all 5 cloud inputs must be tensors; a None among "
                "(clw, ciw, deff_liq, deff_ice, cfrac) is a partial profile.")
        n_args = 11 if cloud_mode else 6
        if not cloud_mode:
            clw = ciw = deff_liq = deff_ice = cfrac = None

        prof = RttovProfileTensors(t_lay=t_lay, q_lay=q_lay, p_lay=p_lay, p_half=p_half,
                                   clw=clw, ciw=ciw, deff_liq=deff_liq, deff_ice=deff_ice,
                                   cfrac=cfrac)
        rin = pack_rttov_input(prof, rttov_config)     # torch -> numpy (detached)
        bt_np, k_dict, rad_quality_np = run_k(rin)     # single runK: BT + K + quality

        # grad spec: (apply-arg index, K field, in-shape) for each DIFFERENTIABLE input
        # present. args mirrors the apply positional order (run_k=0 ... cfrac=10).
        args = (None, None, t_lay, q_lay, None, None, clw, ciw, deff_liq, deff_ice, cfrac)
        grad_specs = [(idx, key, tuple(args[idx].shape))
                      for (idx, key) in _GRAD_INPUTS if idx < n_args and args[idx] is not None]
        # fail FAST at the run_k contract boundary (not later inside autograd):
        missing = [key for (_, key, _) in grad_specs if key not in k_dict]
        if missing:
            raise KeyError(
                f"run_k k_dict missing required K field(s) {sorted(missing)} for the "
                "differentiable inputs (design 9.1 PROFILES_K).")
        ctx.k_dict = k_dict
        ctx.config_hash = rin.config_hash
        ctx.grad_specs = grad_specs
        ctx.n_args = n_args
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
        nprof, nch = lam.shape
        grads = [None] * ctx.n_args            # one slot per arg passed to apply
        for idx, key, in_shape in ctx.grad_specs:
            kt = torch.as_tensor(ctx.k_dict[key], dtype=ctx.dtype, device=ctx.device)
            # Guard the K shape: a transposed (or square nlay==nch) K would give a
            # wrong-but-finite gradient silently (design 9.1/F1-SHAPE seam). Field-
            # agnostic, so it covers the cloud HYDRO*/HYDRO_DEFF* K identically.
            nlay = in_shape[-1]
            if tuple(kt.shape) != (nprof, nch, nlay):
                raise ValueError(
                    f"K['{key}'] shape {tuple(kt.shape)} != expected "
                    f"(nprofiles, nchannels, nlayers) ({nprof}, {nch}, {nlay}); "
                    "guards a transposed/square-K silent wrong-gradient.")
            # channel contraction K^T·λ_BT: grad_field[p,l] = Σ_c K[p,c,l]·λ_BT[p,c]
            grads[idx] = torch.einsum("pcl,pc->pl", kt, lam).reshape(in_shape)
        return tuple(grads)


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


# default_run_k always builds a pure-BT (solar=()) observable -- tag it so the callback
# can detect a config mismatch against a solar ObsOperatorConfig (Phase 7 seam).
default_run_k.solar_channels = ()


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
    if getattr(cfg.profile_cfg, "cloud", False):
        # all-sky: pass the cloud content/Deff (differentiable) + cfrac (passthrough).
        bt_hat, rad_quality = RttovObsOp.apply(
            run_k, cfg.input_cfg, prof.t_lay, prof.q_lay, prof.p_lay, prof.p_half,
            prof.clw, prof.ciw, prof.deff_liq, prof.deff_ice, prof.cfrac)
    else:
        bt_hat, rad_quality = RttovObsOp.apply(
            run_k, cfg.input_cfg, prof.t_lay, prof.q_lay, prof.p_lay, prof.p_half)

    # Phase 7: cfg.solar_channels (which channels are REFL + need per-channel sigma) and
    # the solar set the INJECTED run_k actually merges must AGREE -- else the observable
    # type and the sigma/contraction assumptions desync (e.g. cfg says solar but run_k
    # returns pure BT) -> a silent config-mismatch wrong gradient. make_live_run_k /
    # default_run_k tag the closure with `.solar_channels`; verify it when present (an
    # untagged custom/mock run_k can't be checked -> caller's responsibility).
    rk_solar = getattr(run_k, "solar_channels", None)
    if rk_solar is not None and tuple(int(c) for c in rk_solar) != tuple(int(c) for c in cfg.solar_channels):
        raise ValueError(
            f"run_k solar_channels {tuple(rk_solar)} != ObsOperatorConfig.solar_channels "
            f"{tuple(cfg.solar_channels)} -- the observable type and sigma assumptions "
            "would desync (build run_k with the SAME solar_channels as the config).")
    # A mixed BT+REFL observable (solar_channels set) needs a PER-CHANNEL sigma (BT-scale
    # for IR, reflectance-scale for solar). A scalar static sigma over the mixed vector
    # mis-weights the two unit systems by ~the sigma ratio (~50x) -- reject it (the
    # symmetric error_model path already returns a per-channel sigma). reject-don't-drop.
    if cfg.solar_channels and cfg.error_model is None:
        nch = bt_hat.shape[-1]
        sig_t = torch.as_tensor(cfg.sigma)
        if sig_t.ndim == 0 or sig_t.numel() == 1:
            raise ValueError(
                "ObsOperatorConfig.solar_channels is set (mixed BT+REFL observable) but "
                "sigma is scalar -- pass a per-channel sigma (length nchannels; BT-scale "
                "for IR, reflectance-scale for solar). A scalar mis-weights units ~50x.")
        if sig_t.numel() != nch:
            raise ValueError(
                f"ObsOperatorConfig.sigma length {sig_t.numel()} != nchannels {nch} -- a "
                "per-channel sigma is required for the mixed solar+IR observable.")
    # The symmetric error_model carries BT-scale scalar params (sigma_clr/sigma_cld in
    # Kelvin); it must NOT weight a kept SOLAR channel (0-1 reflectance) -> mis-weight by
    # ~the unit ratio. Precompute the solar columns; reject per-obs below if any is kept.
    solar_cols = None
    if cfg.error_model is not None and cfg.solar_channels:
        solar_set = {int(c) for c in cfg.solar_channels}
        solar_cols = [i for i, c in enumerate(cfg.input_cfg.channels) if int(c) in solar_set]

    j = None
    any_active = False
    for o in obs_list:
        mask = _build_mask(o, rad_quality)
        if float(mask.sum()) > 0.0:   # mask is detached -> .sum() is graph-free
            any_active = True
        # Phase 3: symmetric cloud obs-error sigma(CA) when an error_model + a clear-sky
        # first-guess BT (o["bt_clear"]) are provided; else the static cfg.sigma. The
        # CA-sigma is DETACHED (a weighting, no ghost grad into lambda_BT).
        sigma = cfg.sigma
        if cfg.error_model is not None:
            if solar_cols and float(mask[..., solar_cols].sum()) > 0.0:
                raise ValueError(
                    "ObsOperatorConfig.error_model (BT-scale symmetric obs-error) is set "
                    "but a SOLAR (reflectance) channel is KEPT -- its K-scale sigma would "
                    "mis-weight the 0-1 reflectance residual. Gate the solar channels out "
                    "(obs['channel_gate']) or use a per-channel-type error model.")
            bt_clear = o.get("bt_clear")
            if bt_clear is None:
                # error_model = intent to use CA-sigma; a missing clear-sky first guess
                # would silently fall back to static sigma -> reject, don't drop.
                raise ValueError(
                    "ObsOperatorConfig.error_model is set but obs lacks 'bt_clear' "
                    "(clear-sky first-guess BT) -- required for the symmetric CA obs-error.")
            # pass the keep-mask: bt_clear/bt_hat/bt_obs are validated finite only in
            # KEPT channels (an inf bt_clear is otherwise silently absorbed into sigma_cld).
            sigma = symmetric_obs_error(bt_hat, o["bt"], bt_clear, cfg.error_model, mask=mask)
        term = compute_obs_loss(bt_hat, o, mask, sigma, delta=cfg.huber_delta)
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
