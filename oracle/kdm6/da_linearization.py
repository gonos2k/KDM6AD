"""창-선형화 API (DA_REALTIME_PLAN T2-6) — 유지된 핸들 + 반복 vjp/jvp.

run_da_window(checkpoint/recompute)는 backward 스윕마다 스텝 그래프를 재구축한다
(메모리 O(체크포인트), CG 반복당 재계산 비용). 이 모듈은 그 반대 트레이드오프:
**한 선형화점의 per-step 핸들 T개를 유지**하고, CG 내부반복마다 반복 vjp/jvp만
재적용한다 — 실측 한계비용 0.95×vjp1 (재계산 없음). 메모리 실측: 36그래프 ≈
8.3GB(B=128)/17.8GB(B=512) → **B≤512 전용** (기본 가드; 정밀 검토 산정).

범위: strong-constraint(η 없음), obs covector는 고정 시각 dict로 주입.
비용모델: build = T×(fwd(value-only) + fwd+graph), apply_adjoint = T×vjp_repeat,
apply_tangent = T×jvp. GN-CG 반복당 = apply_tangent + apply_adjoint (재계산 0).
"""
from __future__ import annotations

from typing import Mapping, Sequence

import torch

from .runtime import kdm6_step, make_parameters, _validate_state_shapes
from .state import State, Forcing


def _zeros_like_state(s: State) -> State:
    return State(**{k: torch.zeros_like(v) for k, v in s._asdict().items()})


def _add(a: State, b: State) -> State:
    return State(*(x + y for x, y in zip(a, b)))


def _f64(s):
    return type(s)(*(f.detach().to(torch.float64) for f in s))


class WindowLinearization:
    """한 선형화점 x0의 창 접선(M v)/수반(Mᵀ u) 연산자 — 핸들 T개 유지.

    사용:
        lin = WindowLinearization(x0, forcings, dt=300.0)      # build (1회)
        adj = lin.apply_adjoint({12: u12, 36: u36})            # CG마다 재적용
        tan = lin.apply_tangent(v0, obs_times=[12, 36])
        lin.close()          # 또는 with-문
    """

    def __init__(self, x0: State, forcings: Sequence[Forcing], *, dt: float,
                 params=None, xland: torch.Tensor | None = None,
                 ncmin_land: float = 0.0, ncmin_sea: float = 0.0,
                 max_b: int = 512):
        B = int(x0.th.shape[0])
        if B > max_b:
            raise ValueError(
                f"WindowLinearization holds T retained graphs — measured "
                f"~17.8GB at B=512/T=36; B={B} exceeds max_b={max_b}. Use "
                f"run_da_window (recompute) or shard, or raise max_b explicitly.")
        self._params = params if params is not None else make_parameters()
        self._dt = dt
        self._kw = dict(xland=xland, ncmin_land=ncmin_land, ncmin_sea=ncmin_sea)
        self.T = len(forcings)
        self._forcings = [_f64(f) for f in forcings]
        self._handles = []
        self.checkpoints: list[State] = []

        # forward: 스텝마다 그래프 포함 1회로 값+핸들을 동시에 얻는다
        # (run_da_window의 value-only 체크포인트 + 재계산 2-pass 를 1-pass 로 —
        # 어차피 핸들을 유지할 것이므로 value-only 선행 pass 가 불필요).
        x = _f64(x0)
        try:
            for t in range(self.T):
                self.checkpoints.append(x)
                leaves = State(*(f.detach().clone().requires_grad_(True)
                                 for f in x))
                out, h = kdm6_step(leaves, self._forcings[t], self._params,
                                   self._dt, value_only=False, **self._kw)
                self._handles.append(h)
                x = State(*(f.detach() for f in out))
        except Exception:
            self.close()
            raise
        self.state_final = x
        self._closed = False

    # ── 연산자 ───────────────────────────────────────────────────────────────

    def apply_adjoint(self, obs_adj: Mapping[int, State],
                      *, active_fields: tuple[str, ...] | None = None) -> State:
        """adj_x0 = Σ_t M_0ᵀ…M_{t-1}ᵀ u_t — 유지 핸들에 반복 vjp만 (재계산 0).

        obs_adj: {t: covector} (t = 0..T; run_da_window 과 동일 규약 —
        u_t 는 x_t 공간, t=T 는 state_final 공간).
        """
        self._assert_open()
        # 사전 검증 (Codex stop-review): broadcast-호환이지만 틀린 covector shape
        # ((1,K) vs (B,K) 등)는 vjp 내적/누산에서 조용히 broadcast 되어
        # wrong-but-finite adjoint 가 된다 — run_da_window 와 동일한 exact-shape
        # 가드(F1-SHAPE)를 적용. 범위 밖 시각 키도 조용히 무시하지 않는다.
        # 키 정규화 (Codex stop-review 2차): int(key) 검증만 하고 소비를 원본
        # 키로 하면, int() 변환은 되지만 int와 해시-동등하지 않은 키("2" 문자열,
        # torch 스칼라 텐서)가 `t in obs_adj` 조회에 실패해 관측이 여전히 조용히
        # drop 된다. 검증 시 canonical-int dict 를 만들어 소비도 그것으로 —
        # 검증과 소비의 키 공간을 하나로 통일한다. 정규화 충돌("2"와 2 동시
        # 존재)도 침묵 병합 대신 loud 거부.
        norm: dict[int, State] = {}
        for t_key, u in obs_adj.items():
            tk = int(t_key)
            if not (0 <= tk <= self.T):
                raise ValueError(
                    f"obs_adj time key {t_key!r} outside [0, {self.T}]")
            if tk in norm:
                raise ValueError(
                    f"obs_adj keys collide after int-normalization at t={tk} "
                    "(e.g. 2 and '2' both present)")
            ref = self.state_final if tk == self.T else self.checkpoints[tk]
            _validate_state_shapes(u, ref, arg=f"obs_adj[{tk}]",
                                   ref_name="x_t")
            norm[tk] = u
        adj = norm.get(self.T)
        adj = (_f64(adj) if adj is not None
               else _zeros_like_state(self.state_final))
        for t in reversed(range(self.T)):
            adj = self._handles[t].vjp(adj, retain_graph=True,
                                       active_fields=active_fields)
            if t in norm:
                adj = _add(adj, _f64(norm[t]))
        return adj

    def apply_tangent(self, v0: State,
                      obs_times: Sequence[int] = ()) -> dict:
        """접선 전파 M v: {t: tangent_at_x_t} (요청 시각) + 'final' (x_T 공간).

        tangent_at_x_t 는 스텝 t 적용 전 접선 (obs 가 x_t 를 보는 규약과 동일).
        """
        self._assert_open()
        _validate_state_shapes(v0, self.checkpoints[0], arg="v0",
                               ref_name="x_0")
        want = set(int(t) for t in obs_times)
        bad = [t for t in want if not (0 <= t <= self.T)]
        if bad:
            raise ValueError(f"obs_times {sorted(bad)} outside [0, {self.T}]")
        out: dict = {}
        tan = _f64(v0)
        for t in range(self.T):
            if t in want:
                out[t] = tan
            tan = self._handles[t].jvp(tan)
        if self.T in want:
            out[self.T] = tan
        out["final"] = tan
        return out

    # ── 수명 ────────────────────────────────────────────────────────────────

    def close(self) -> None:
        for h in getattr(self, "_handles", []):
            try:
                h.close()
            except Exception:
                pass
        self._handles = []
        self._closed = True

    def _assert_open(self) -> None:
        if getattr(self, "_closed", True):
            raise RuntimeError("WindowLinearization is closed")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False
