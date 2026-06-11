"""
KDM6 PyTorch runtime — 슬롯 47 진입점 + autograd handle.

이 모듈은 *아키텍처 골격*. 실제 물리 계산은 slope/core/sedimentation 모듈이 차면
`kdm6_fn(...)` 안에서 호출된다. 본 파일이 담당하는 것:

  1. 입력 state·forcing·params 준비 (state.from_fortran_arrays + Parameters 처리)
  2. dynamic graph 빌드용 pure function `kdm6_fn(state, forcing, params, dt) → State`
  3. JVP / VJP / Jacobian 추출용 `Handle` 클래스
  4. DA-친화 entry point `kdm6_step(...)` — Fortran-side에서 호출하는 함수

설계 결정은 wiki/concepts/pytorch-autograd-integration.md 참조 (G1-G7).

──────────────────────────────────────────────────────────────────────
현재 상태:
  - 인터페이스 시그니처 + TODO 마커만 존재 (slope/core/sedimentation 미구현)
  - kdm6_step 호출하면 NotImplementedError
  - 본 파일이 의미있게 동작하려면 slope.py 먼저 필요
──────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, NamedTuple
import torch

from .state import State, Forcing, from_fortran_arrays, to_fortran_arrays
from . import constants as c
from . import coordinator as _coord
from . import cloud_dsd as _cdsd
from . import sedimentation as _sed


# ─── Parameters: opt-in differentiable model parameters ────────────────────────

class Parameters(NamedTuple):
    """[G4] torch.func-friendly 모델 파라미터 pytree.

    각 필드는 constants.py와 1:1 대응하는 leaf tensor다. 기본 생성은
    `make_parameters()`를 사용한다.
    """

    peaut: torch.Tensor
    ncrk1: torch.Tensor
    ncrk2: torch.Tensor
    eccbrk: torch.Tensor


def _mkparam(
    value: float,
    *,
    device: torch.device | str,
    dtype: torch.dtype,
    requires_grad: bool,
) -> torch.Tensor:
    t = torch.tensor(value, device=device, dtype=dtype)
    if requires_grad:
        t = t.detach().clone().requires_grad_(True)
    return t


def make_parameters(
    *,
    all_grad: bool = False,
    peaut_grad: bool = False,
    ncrk_grad: bool = False,
    device: torch.device | str = "cpu",
    dtype: torch.dtype = torch.float64,
) -> Parameters:
    """[G4] `Parameters` 생성 helper.

    기본값은 모든 파라미터 frozen이며, 보정 실험에서 필요한 항목만 grad를 켠다.

    ⚠️ STAGE BOUNDARY (G4, not yet wired): the `*_grad`/`all_grad` flags set
    `requires_grad=True` on the returned leaves, but `_kdm6_pure` / C++ `kdm6_fn`
    currently build every phase-param bundle from `default_*_params()` (module
    constants), NOT from this `Parameters` object (runtime.py:277, runtime.cpp:229).
    So these leaves are NOT in the forward graph yet — `loss.backward()` leaves their
    `.grad` as None, and `Handle.param_grad()` raises NotImplementedError. ∂loss/∂param
    (parameter sensitivity for 4D-Var calibration) requires the G4 plumbing — threading
    these values into the phase-param builders + warm/cold/mf formulas in BOTH trees —
    which is a scoped future stage alongside the G3 vjp/jvp/jacobian adjoint API. The
    validated deliverable today is the differentiable forward wrt the 12 STATE leaves.
    """
    # TODO[G4]: wire these params into the phase-param builders (both trees) so ∂loss/∂param
    # flows; add a param-leaf gradient test. Until then the flags are reserved, not live.
    # 우선 PEAUT가 가장 자주 튜닝되는 표면이라 이것부터 노출
    return Parameters(
        peaut=_mkparam(c.PEAUT, device=device, dtype=dtype, requires_grad=peaut_grad or all_grad),
        ncrk1=_mkparam(c.NCRK1, device=device, dtype=dtype, requires_grad=ncrk_grad or all_grad),
        ncrk2=_mkparam(c.NCRK2, device=device, dtype=dtype, requires_grad=ncrk_grad or all_grad),
        eccbrk=_mkparam(c.ECCBRK, device=device, dtype=dtype, requires_grad=all_grad),
    )


# ─── Handle: JVP / VJP / Jacobian 추출 인터페이스 ──────────────────────────────

@dataclass
class Handle:
    """[G3] kdm6_step 호출의 *autograd 결과 핸들*.

    내부에 `state_in`, `state_out`, `forcing`, `params`, `dt`와 future derivative
    extraction에 필요한 `pullback` 또는 `func`를 보존한다. 사용 후 `close()`로
    참조를 해제해 graph가 GC되도록 하는 것을 권장한다.

    지원 연산:
      - vjp(u): J^T @ u — DA adjoint (4D-Var)
      - jvp(v): J @ v   — DA tangent (EnKF perturbation)
      - jacobian(rows, cols): 부분 Jacobian 행렬 — 진단·디버깅
      - param_grad(scalar): 임의 스칼라 손실에 대한 ∂L/∂params

    Notes
    -----
    `value_only=True`로 생성된 Handle은 derivative API를 지원하지 않는다.
    `close()` 호출 후 derivative API는 `RuntimeError`를 발생시킨다.
    """
    state_in: State | None
    state_out: State | None
    forcing: Forcing | None
    params: Parameters | None
    dt: float | None
    pullback: Callable[..., object] | None = None
    func: Callable[[State, Forcing, Parameters, float], State] | None = None
    value_only: bool = False
    closed: bool = False

    def close(self) -> None:
        """Release tensor references so the autograd graph can be garbage-collected."""
        self.state_in = None
        self.state_out = None
        self.forcing = None
        self.params = None
        self.dt = None
        self.pullback = None
        self.func = None
        self.closed = True

    def _ensure_derivative_ready(self) -> None:
        if self.closed:
            raise RuntimeError("Handle is closed")
        if self.value_only:
            raise RuntimeError("Handle is value-only")
        if (
            self.state_in is None
            or self.state_out is None
            or self.forcing is None
            or self.params is None
            or self.dt is None
        ):
            raise RuntimeError("Handle is missing derivative context")
        if self.pullback is None and self.func is None:
            raise RuntimeError("Handle is missing derivative context")

    def vjp(self, u: State) -> State:
        """[G3] J^T @ u — adjoint 연산.

        Parameters
        ----------
        u : State
            state_out 공간의 covector (e.g., 관측-모델 잔차)

        Returns
        -------
        state_in_grad : State
            ∂(u · state_out) / ∂state_in
        """
        self._ensure_derivative_ready()
        raise NotImplementedError("[G3] VJP — implement after core kdm6_step works")

    def jvp(self, v: State) -> State:
        """[G3] J @ v — tangent linear 연산.

        Note: 일반적으로 vjp보다 비싸 (forward-mode가 활용되면 cheaper); 본 메서드는
        후행 도입을 위한 placeholder. torch.func.jvp 활용 예정.
        """
        self._ensure_derivative_ready()
        raise NotImplementedError("[G3] JVP — implement after core kdm6_step works")

    def jacobian(
        self,
        rows: tuple[str, ...] | None = None,
        cols: tuple[str, ...] | None = None,
    ) -> dict[tuple[str, str], torch.Tensor]:
        """[G3] 부분 Jacobian 추출.

        Parameters
        ----------
        rows : 출력 필드 이름 tuple (e.g., ("qc", "qr")); None이면 전체
        cols : 입력 필드 이름 tuple (e.g., ("qv", "th")); None이면 전체

        Returns
        -------
        dict (out_field, in_field) → tensor (B, K_out, K_in)
        """
        self._ensure_derivative_ready()
        raise NotImplementedError("[G3] Jacobian — implement using torch.func.jacrev")

    def param_grad(self, scalar_loss: torch.Tensor) -> dict[str, torch.Tensor]:
        """[G4] 파라미터 grad — 임의 스칼라 loss에 대한 ∂L/∂params."""
        self._ensure_derivative_ready()
        raise NotImplementedError("[G4] param_grad — uses torch.autograd.grad")


# ─── Pure function: 단일 KDM6 호출의 *autograd-friendly* 형태 ──────────────────

# ── State ↔ CoordinatorState conversion (1:1 mirror of C++ runtime.cpp:40-64) ──
# NOTE: K-order is NOT flipped here — WRF stages K=0 at the surface and the
# coordinator/microphysics run in that order; only sedimentation wants K=0 at the
# TOP, so the flip is localised inside _kdm6_pure around the sediment call.

def _state_to_coord(s: State, f: Forcing) -> "_coord.CoordinatorState":
    """State → CoordinatorState. t = th·pii, brs = bg. nccn is NOT carried (the
    Python CoordinatorState has no nccn field — CCN activation is deferred, Task #74);
    nccn stays on the State and passes through unchanged."""
    return _coord.CoordinatorState(
        qv=s.qv, qc=s.qc, qr=s.qr, qs=s.qs, qg=s.qg, qi=s.qi,
        nc=s.nc, nr=s.nr, ni=s.ni, brs=s.bg, t=s.th * f.pii,
    )


def _build_coord_forcing(f: Forcing) -> "_coord.CoordinatorForcing":
    """Forcing → CoordinatorForcing. den = rho; **dend = rho (air density ALONE,
    NOT density × delz)** — see C++ build_forcing comment + project memory
    `project_kdm6_dend_must_be_density_only`. The `coordinator.py:63` "density × delz"
    label is the mis-documentation that comment flags (falk = dend·q·work1/mstep with
    work1 = vt/delz cancels delz only when dend = ρ; an extra delz gives ~250× RAINNC)."""
    return _coord.CoordinatorForcing(p=f.p, den=f.rho, delz=f.delz, dend=f.rho)


def _coord_to_state(cobj: "_coord.CoordinatorState", orig: State, f: Forcing) -> State:
    """CoordinatorState → State (reverse). th = t/pii, bg = brs. nccn passes through
    from `orig` unchanged (not processed by the Python coordinator — Task #74)."""
    return orig._replace(
        qv=cobj.qv, qc=cobj.qc, qr=cobj.qr, qs=cobj.qs, qg=cobj.qg, qi=cobj.qi,
        nc=cobj.nc, nr=cobj.nr, ni=cobj.ni, bg=cobj.brs, th=cobj.t / f.pii,
    )


def _flip_k(t: torch.Tensor) -> torch.Tensor:
    """WRF K-order (K=0 surface) ↔ sedimentation K-order (K=0 top)."""
    return torch.flip(t, dims=[1])


# ─── Pure function: 단일 KDM6 호출의 *autograd-friendly* 형태 ──────────────────

def _kdm6_pure(
    state: State,
    forcing: Forcing,
    params: Parameters,
    dt: float,
    xland: "torch.Tensor | None" = None,
    ncmin_land: float = 0.0,
    ncmin_sea: float = 0.0,
) -> State:
    """[G1] One-step KDM6 — autograd dynamic graph가 통과할 pure function.

    1:1 mirror of the C++ operational driver ``kdm6_fn`` (kdm6_libtorch/src/runtime.cpp:221-364):
    sub-cycle the outer ``dt`` into ``compute_loops_max(dt, DTCLDCR)`` steps and, per substep,
    run the Stage-S2 order — SEDIMENT at the top (Fortran :1119) → re-slope/aux on the
    post-fall state (:1422-1480) → ONE microphysics pass ``kdm62d_one_step`` over dtcld (:1274+).

    All differentiable physics flow through this one function; ``state`` graph is preserved.

    STATUS: implemented + differentiable + **C++-forward-parity-validated** — matches C++
    ``kdm6_fn`` on the test IC to ~5e-14 relative (fp64 machine precision) across ALL fields
    (qv/qc/qr/qi/qs/qg/nc/ni/nr/th/bg/nccn), with CCN activation now ported. Autograd reaches
    all 8 leaves; the 222 component tests (nccn=None path) are unchanged.

    nccn architecture: the Python CoordinatorState has no nccn field, so nccn is threaded
    SEPARATELY (driver → kdm62d_one_step → apply_satadj_step, in/out) rather than carried in
    the state tuple. CCN activation (pcact/ncact + complete-evap NC→NCCN + the [NCCN_MIN,
    NCCN_MAX] clamp) runs inside apply_satadj_step exactly as C++ apply_satadj_step.

    Remaining documented simplification:
      - **mstep**: ``sedimentation_chain_torch`` takes a SCALAR mstep (= max over columns =
        C++ ``mstepmax``), not a per-column tensor — identical for a single column / mstep=1
        (the parity above is B=1). Heterogeneous-mstep multi-column columns carry the #10
        residual until the per-column tensor is threaded.

    Control inputs (mirroring C++ ``kdm6_fn(..., xland, ncmin_land, ncmin_sea)``):
      - ``xland`` (None → maritime, the C++ no-xland branch) sets the land/sea ``sea_mask``,
        which drives the per-substep ``qcr`` override via ``diag_qcr_torch`` (Fortran :842-847).
      - ``ncmin_land``/``ncmin_sea`` build a per-cell ``ncmin_tensor`` (from ``sea_mask``) that
        drives the CONSERVATION number-floor (#18, the path Python supports) — so they are
        FUNCTIONAL, not no-op. The warm/cold rate-GATE ncmin stays scalar (#10, Python phase
        params are scalar-typed). The per-cell tensor is floored at the scalar ``c.NCMIN``
        safety minimum, so the default 0.0 collapses to ``c.NCMIN`` everywhere == the no-xland
        (scalar) path — never a 0-floor (which would 0/0-NaN in the conservation scaling).
      - ``params`` is currently baked into the default phase params (as in C++ ``kdm6_fn``),
        not yet AD-trainable on this path.

    Returns ``State`` only (no surface rain/snow/graupel increments — those are a C++ ABI
    concern; ``_kdm6_pure``'s job is the differentiable state evolution).
    """
    cs = _state_to_coord(state, forcing)
    cf = _build_coord_forcing(forcing)

    # delt<=0 → no-op (dtcld=0 would NaN the per-rate mass/dtcld divisions). Mirror C++ :239.
    if dt <= 0.0:
        return _coord_to_state(cs, state, forcing)

    full_p = _coord.default_coordinator_params()
    warm_p = _coord.default_warm_phase_params()
    cold_p = _coord.default_cold_phase_params()
    mf_p = _coord.default_melt_freeze_phase_params()
    cloud_p = _cdsd.default_cloud_dsd_params()
    sed_params = _sed.default_substep_advection_params()

    # Control input: xland → sea_mask (xland>=1.5 sea, else land), mirroring C++ :255-272.
    # When xland is None → ones (maritime), the C++ no-xland branch. sea_mask drives the
    # per-substep land/sea qcr override below; sedimentation ignores it.
    _use_xland = xland is not None
    if _use_xland:
        xl_flat = xland.to(cs.qc.dtype).reshape(-1)
        sea_mask = (xl_flat >= 1.5).unsqueeze(1).expand_as(cs.qc).contiguous()
        # Per-cell ncmin floor for the conservation NUMBER budgets (#18), from xland +
        # ncmin_land/ncmin_sea (mirror C++ runtime.cpp:261-265: sea→ncmin_sea, land→ncmin_land).
        # Feeds the conservation floor only; the warm/cold PHASE gates stay scalar (#10).
        # Floored at the scalar safety minimum c.NCMIN: a 0 (e.g. the default ncmin) must NOT
        # drop the conservation floor to 0, else limit_ncmin's value/max(source,value) hits 0/0
        # → NaN when a number reservoir AND its source are both 0. With the default 0.0 this
        # collapses to c.NCMIN everywhere == the no-xland (None→c.NCMIN) path.
        ncmin_tensor = torch.clamp(
            torch.where(sea_mask, torch.full_like(cs.qc, ncmin_sea),
                        torch.full_like(cs.qc, ncmin_land)),
            min=c.NCMIN)
    else:
        sea_mask = torch.ones_like(cs.qc, dtype=torch.bool)
        ncmin_tensor = None  # → scalar c.NCMIN fallback inside the conservation floor

    # Inject the per-cell ncmin into the rate-GATE params too — NOT only the conservation floor.
    # The C++/Fortran autoconv/number-accretion/riming/contact/Bigg gates use the operational
    # per-cell ncmin (sea 10 / land 100 from xland); without this the Python oracle's gates used
    # scalar c.NCMIN (1e-2), a qualitative C++↔Python divergence in low-nc cells on the live xland
    # path (audit round-5). Mirrors C++ runtime.cpp:273-277. None (no-xland) → params keep their
    # scalar ncmin (== the C++ no-xland branch), so the no-xland parity path is unchanged.
    if ncmin_tensor is not None:
        warm_p = warm_p._replace(autoconv=warm_p.autoconv._replace(ncmin_tensor=ncmin_tensor))
        cold_p = cold_p._replace(
            number_accretion=cold_p.number_accretion._replace(ncmin_tensor=ncmin_tensor),
            cloud_water_riming=cold_p.cloud_water_riming._replace(ncmin_tensor=ncmin_tensor),
        )
        mf_p = mf_p._replace(
            contact=mf_p.contact._replace(ncmin_tensor=ncmin_tensor),
            bigg_cloud=mf_p.bigg_cloud._replace(ncmin_tensor=ncmin_tensor),
        )

    loops = _coord.compute_loops_max(dt, c.DTCLDCR)
    dtcld = dt / float(loops)

    # cf is constant → flip + delz-clamp hoisted out of the loop (C++ :287-291).
    cf_flip = _coord.CoordinatorForcing(
        p=_flip_k(cf.p), den=_flip_k(cf.den), delz=_flip_k(cf.delz), dend=_flip_k(cf.dend),
    )
    delz_safe = torch.clamp(cf_flip.delz, min=1.0e-9)

    # CCN reservoir: clamp once at entry (Fortran :801; C++ runtime.cpp:297), then carry +
    # deplete it across the sub-cycles through kdm62d_one_step → apply_satadj_step activation.
    cur_nccn = torch.clamp(state.nccn, min=c.NCCN_MIN, max=c.NCCN_MAX)

    # Fortran entry padding (F:822-839): zero the dynamics-generated negative
    # prognostics ONCE per kernel call (mirror of C++ runtime.cpp; the step-46 nn
    # seed — negative qc must become 0 so the complete-evap NC→NCCN transfer can
    # fire at pcond==-0.0/dt).
    cs = cs._replace(
        qc=torch.clamp(cs.qc, min=0.0), qr=torch.clamp(cs.qr, min=0.0),
        qi=torch.clamp(cs.qi, min=0.0), qs=torch.clamp(cs.qs, min=0.0),
        qg=torch.clamp(cs.qg, min=0.0), nr=torch.clamp(cs.nr, min=0.0),
        nc=torch.clamp(cs.nc, min=0.0), ni=torch.clamp(cs.ni, min=0.0, max=1.0e6),
        brs=torch.clamp(cs.brs, min=0.0),
    )

    cur = cs  # WRF K-order, evolves across sub-cycles
    for _ in range(loops):
        # 1. SEDIMENT(dtcld) at the TOP of the sub-cycle (flipped to K=0-top order).
        cur_flip = _coord.CoordinatorState(
            qv=_flip_k(cur.qv), qc=_flip_k(cur.qc), qr=_flip_k(cur.qr), qs=_flip_k(cur.qs),
            qg=_flip_k(cur.qg), qi=_flip_k(cur.qi), nc=_flip_k(cur.nc), nr=_flip_k(cur.nr),
            ni=_flip_k(cur.ni), brs=_flip_k(cur.brs), t=_flip_k(cur.t),
        )
        pre_sed = _coord.preamble_torch(cur_flip, cf_flip, sea_mask, params=full_p)
        w1_qr = pre_sed.slope.vt_r / delz_safe
        wn_qr = pre_sed.slope.vtn_r / delz_safe
        w1_qs = pre_sed.slope.vt_s / delz_safe
        w1_qg = pre_sed.slope.vt_g / delz_safe
        w1_qi = pre_sed.slope.vt_i / delz_safe
        wn_qi = pre_sed.slope.vtn_i / delz_safe
        # PER-COLUMN mstep (Fortran :1107-1117 per-column nint; 1:1 fix #10): mstep_col(i) =
        # clamp(nint(vmax(i)·dtcld+0.5),1,100) as a (B,) tensor; the loop bound mstepmax =
        # max over columns. Integer work under no_grad (gate/divisor only). Passing the (B,)
        # tensors closes the multi-column scalar-mstep divergence (== scalar at single-col/mstep=1).
        # NINT(x+0.5) for x>=0 = floor(x+1.0) (round-half-UP) — NOT torch.round (banker's half-to-even),
        # which selects the wrong substep count at exact CFL ties vmax·dtcld∈ℤ (Codex round-3 Finding 3).
        with torch.no_grad():
            vmax_main_col = torch.maximum(torch.maximum(w1_qr, wn_qr),
                                          torch.maximum(w1_qs, w1_qg)).amax(dim=-1)
            mstep_col_main = torch.clamp(torch.floor(vmax_main_col * dtcld + 1.0), 1, 100)  # (B,)
            mstep_main = int(mstep_col_main.max().item())                                   # mstepmax (loop bound)
            vmax_ice_col = torch.maximum(w1_qi, wn_qi).amax(dim=-1)
            mstep_col_ice = torch.clamp(torch.floor(vmax_ice_col * dtcld + 1.0), 1, 100)
            mstep_ice = int(mstep_col_ice.max().item())
        sed = _coord.sedimentation_chain_torch(
            cur_flip, cf_flip, w1_qr, wn_qr, w1_qs, w1_qg, w1_qi, wn_qi,
            mstep_main=mstep_main, mstep_ice=mstep_ice, dtcld=dtcld,
            params=sed_params, reslope_params=full_p, sea_mask=sea_mask,
            mstep_col_main=mstep_col_main, mstep_col_ice=mstep_col_ice,
        )
        # flip back to WRF K-order
        cur = _coord.CoordinatorState(
            qv=_flip_k(sed.state.qv), qc=_flip_k(sed.state.qc), qr=_flip_k(sed.state.qr),
            qs=_flip_k(sed.state.qs), qg=_flip_k(sed.state.qg), qi=_flip_k(sed.state.qi),
            nc=_flip_k(sed.state.nc), nr=_flip_k(sed.state.nr), ni=_flip_k(sed.state.ni),
            brs=_flip_k(sed.state.brs), t=_flip_k(sed.state.t),
        )
        # 2. Re-slope + aux on the POST-FALL state (WRF order), Fortran :1422-1480.
        rslopec = _cdsd.diag_cloud_slope_torch(cur.qc, cur.nc, cf.den, params=cloud_p,
                                               ncmin_tensor=ncmin_tensor)
        aux = _coord.build_default_aux_torch(cur, cf, rslopec, thermo_params=full_p.thermo)
        # qcr from land/sea (Fortran :842-847). Applied UNCONDITIONALLY: no-xland ⇒ sea_mask=all-sea
        # ⇒ qc0 (maritime, ≈8.3776e-5), the Fortran maritime default — replaces build_default_aux's
        # 8.0e-5 placeholder which autoconverted ~4.5% too early on the no-xland path (Codex round-4 F1).
        aux = aux._replace(qcr=_cdsd.diag_qcr_torch(sea_mask, params=cloud_p, ref=cur.qc))
        # 3. ONE microphysics pass over dtcld (melt → … → state_update), Fortran :1274+.
        cur, cur_nccn = _coord.kdm62d_one_step_torch(
            cur, cf, aux, sea_mask,
            full_params=full_p, warm_params=warm_p, cold_params=cold_p, mf_params=mf_p,
            dtcld=dtcld, ncmin_tensor=ncmin_tensor, nccn=cur_nccn,
        )

    return _coord_to_state(cur, state, forcing)._replace(nccn=cur_nccn)


kdm6_fn = _kdm6_pure


# ─── Public entry point: kdm6_step ─────────────────────────────────────────────

def kdm6_step(
    state: State,
    forcing: Forcing,
    params: Parameters | None = None,
    dt: float = 60.0,
    value_only: bool = False,
    xland: "torch.Tensor | None" = None,
    ncmin_land: float = 0.0,
    ncmin_sea: float = 0.0,
) -> tuple[State, Handle]:
    """[G3] 슬롯 47 진입점 — Fortran forward와 *동반 구동*되어 derivative 정보 산출.

    Parameters
    ----------
    state : State
        prognostic state, (B, K) 텐서들 with requires_grad as configured
    forcing : Forcing
        rho, pii, p, delz — 보통 grad off
    params : Parameters, optional
        모델 파라미터 텐서들. None이면 디폴트(frozen).
    dt : float
        timestep [s]. KDM6 내부에서 DTCLDCR=120s 단위 sub-cycling.
    value_only : bool, default False
        True이면 `torch.no_grad()`로 forward 값만 계산한다. False이면 full graph를
        유지한 Handle을 반환한다.
    xland : torch.Tensor, optional
        land/sea mask (xland>=1.5 → sea, else land). None이면 maritime (C++ no-xland branch).
        per-substep qcr override를 구동 — `_kdm6_pure` 참조. Handle의 VJP/JVP func에도 bind됨.
    ncmin_land, ncmin_sea : float
        regime별 droplet-number floor. xland와 함께 per-cell ncmin_tensor를 만들어 conservation
        number-floor(#18)를 구동 — FUNCTIONAL. 단 warm/cold rate-GATE ncmin은 scalar(#10).
        default 0.0은 scalar c.NCMIN safety floor로 collapse (== no-xland scalar path) —
        0-floor 0/0 NaN 방지.

    Returns
    -------
    state_out : State
        갱신된 state. *forward 정합* 검증용으로 슬롯 37 출력과 비교.
    handle : Handle
        VJP/JVP/Jacobian/param_grad 추출 인터페이스.

    Notes
    -----
    [G2] 본 함수의 출력 state는 production state 갱신에 *사용하지 않음* (Fortran
         슬롯 37이 그 역할). 본 함수의 일차 산출은 derivative 그 자체.
    [G6] 메모리: per-step graph만 보존. timestep 간 chain은 하지 않음.
         dt를 외부 model의 dt와 일치시켜 호출하면 자연스럽게 graph 분리됨.
    forward-mode vs reverse-mode 선택은 `torch.func.{jvp,vjp,jacrev,jacfwd}`를
    `kdm6_fn`에 직접 적용해 제어한다.
    """
    if params is None:
        params = make_parameters()

    if value_only:
        with torch.no_grad():
            state_out = kdm6_fn(state, forcing, params, dt, xland, ncmin_land, ncmin_sea)
        return state_out, Handle(
            state_in=state,
            state_out=state_out,
            forcing=forcing,
            params=params,
            dt=dt,
            pullback=None,
            func=None,
            value_only=True,
        )

    # build dynamic graph
    state_out = kdm6_fn(state, forcing, params, dt, xland, ncmin_land, ncmin_sea)
    handle = Handle(
        state_in=state,
        state_out=state_out,
        forcing=forcing,
        params=params,
        dt=dt,
        pullback=None,
        # bind the control inputs so VJP/JVP/Jacobian respect xland/ncmin
        func=lambda s, f, p, d: kdm6_fn(s, f, p, d, xland, ncmin_land, ncmin_sea),
    )
    return state_out, handle


# ─── Verification helper: forward 정합 ─────────────────────────────────────────

def compare_to_fortran(
    state_in_dict: dict[str, torch.Tensor],
    fortran_state_out_dict: dict[str, torch.Tensor],
    forcing_dict: dict[str, torch.Tensor],
    *,
    im: int,
    kme: int,
    jme: int,
    dt: float,
    rtol: float = 1e-8,
    atol: float = 1e-12,
) -> dict[str, dict[str, float]]:
    """[T4] 슬롯 37(Fortran) 출력과 슬롯 47(PyTorch) 출력의 정합 검증.

    Returns
    -------
    per-field metrics (max abs error, max rel error, allclose pass/fail).
    rtol/atol은 사용자 지정 forward 정합 허용 오차.
    """
    raise NotImplementedError(
        "[T4] compare_to_fortran — implement after _kdm6_pure works. "
        "Default tolerance to be confirmed by user (concept/pytorch-autograd-integration.md §9)"
    )
