"""mstep-aware 샤드 구성 (DA_REALTIME_PLAN T0-3).

근거(정밀 검토 실측): sedimentation mstep은 **batch-global** — 루프 상한이 배치 내
최악 컬럼의 mstep(runtime.py:529 ``mstep_col.max()``)이라, 무거운 대류 컬럼 1개가
샤드 전체를 재가격한다(1/512 heavy ≈ 512/512 heavy). 현실적 stretched-grid 대류
컬럼은 mstep 11–18로 프로브 바닥(1) 대비 fwd 2.0×/vjp 2.9×. 따라서 **비슷한 mstep
끼리 샤드를 묶는 것만으로**(코드/물리 무변경) 2–3×를 회수한다.

예측기는 runtime._kdm6_pure의 첫 sub-cycle mstep 계산과 **동일한 코드 경로**를
no_grad로 재사용한다(_state_to_coord/_build_coord_forcing/preamble_torch + F:1107-1117
공식 그대로). 이후 sub-cycle에서 상태가 진화하며 mstep이 달라질 수 있으나, 샤드
구성엔 순위(무거움/가벼움)만 필요하므로 첫 sub-cycle 예측으로 충분하다 — 이 모듈은
스케줄링 휴리스틱이며 물리 결과에 영향이 없다(컬럼 독립성은 ABI 테스트로 보장).
"""
from __future__ import annotations

from typing import NamedTuple

import torch

from . import constants as c
from . import coordinator as _coord
from . import fconst as _fc
from .state import State, Forcing
from .runtime import _build_coord_forcing, _flip_k, _state_to_coord


def predict_mstep_col(state: State, forcing: Forcing, *, dt: float,
                      xland: torch.Tensor | None = None) -> torch.Tensor:
    """컬럼별 첫 sub-cycle mstep 예측 — MstepPrediction(main, ice), 각 (B,) int64.

    runtime.py:519-532의 공식을 초기 상태에 그대로 적용한다(같은 헬퍼·같은
    preamble·같은 NINT(x+0.5)=floor(x+1) 라운딩). 전 과정 no_grad — 연산그래프
    무접촉(스케줄링 전용).
    """
    with torch.no_grad():
        cs = _state_to_coord(state, forcing)
        cf = _build_coord_forcing(forcing)
        # 진입 패딩 미러 (runtime.py:489-494) — 음수 프로그노스틱이 slope를 오염하지 않게.
        cs = cs._replace(
            qc=torch.clamp(cs.qc, min=0.0), qr=torch.clamp(cs.qr, min=0.0),
            qi=torch.clamp(cs.qi, min=0.0), qs=torch.clamp(cs.qs, min=0.0),
            qg=torch.clamp(cs.qg, min=0.0), nr=torch.clamp(cs.nr, min=0.0),
            nc=torch.clamp(cs.nc, min=0.0), ni=torch.clamp(cs.ni, min=0.0, max=1.0e6),
            brs=torch.clamp(cs.brs, min=0.0),
        )
        loops = _coord.compute_loops_max(dt, c.DTCLDCR)
        dtcld = _fc._f32(dt / float(loops))

        if xland is not None:
            sea_mask = (xland.to(cs.qc.dtype).reshape(-1) >= 1.5
                        ).unsqueeze(1).expand_as(cs.qc).contiguous()
        else:
            sea_mask = torch.ones_like(cs.qc, dtype=torch.bool)

        cs_flip = _coord.CoordinatorState(
            qv=_flip_k(cs.qv), qc=_flip_k(cs.qc), qr=_flip_k(cs.qr), qs=_flip_k(cs.qs),
            qg=_flip_k(cs.qg), qi=_flip_k(cs.qi), nc=_flip_k(cs.nc), nr=_flip_k(cs.nr),
            ni=_flip_k(cs.ni), brs=_flip_k(cs.brs), t=_flip_k(cs.t),
        )
        cf_flip = _coord.CoordinatorForcing(
            p=_flip_k(cf.p), den=_flip_k(cf.den), delz=_flip_k(cf.delz),
            dend=_flip_k(cf.dend),
        )
        delz_safe = torch.clamp(cf_flip.delz, min=1.0e-9)

        pre = _coord.preamble_torch(cs_flip, cf_flip, sea_mask,
                                    params=_coord.default_coordinator_params())
        w1_qr = pre.slope.vt_r / delz_safe
        wn_qr = pre.slope.vtn_r / delz_safe
        w1_qs = pre.slope.vt_s / delz_safe
        w1_qg = pre.slope.vt_g / delz_safe
        w1_qi = pre.slope.vt_i / delz_safe
        wn_qi = pre.slope.vtn_i / delz_safe
        vmax_main = torch.maximum(torch.maximum(w1_qr, wn_qr),
                                  torch.maximum(w1_qs, w1_qg)).amax(dim=-1)
        vmax_ice = torch.maximum(w1_qi, wn_qi).amax(dim=-1)
        mstep_main = torch.clamp(torch.floor(vmax_main * dtcld + 1.0), 1, 100)
        mstep_ice = torch.clamp(torch.floor(vmax_ice * dtcld + 1.0), 1, 100)
        return MstepPrediction(main=mstep_main.to(torch.int64),
                               ice=mstep_ice.to(torch.int64))


class MstepPrediction(NamedTuple):
    """컬럼별 mstep 예측 — 두 축을 분리 유지.

    runtime은 mstep_main과 mstep_ice를 **별개의 루프 상한**으로 max한다
    (runtime.py:529/532) — 샤드의 진짜 비용은 max(main)+max(ice)이지
    max(main+ice)가 아니다 (합산 키는 main-지배 컬럼과 ice-지배 컬럼을
    같은 값으로 뭉개 잘못 묶는다: (10,1)과 (1,10)의 합은 같지만 한 샤드에
    두면 10+10을 지불).
    """
    main: torch.Tensor   # (B,) int64
    ice: torch.Tensor    # (B,) int64


def compose_shards(pred: MstepPrediction, shard_size: int) -> list[torch.Tensor]:
    """(main, ice) 사전식 정렬로 크기 shard_size의 연속 샤드 분할.

    각 샤드의 실행 비용 ∝ max(main)+max(ice) (두 루프 상한이 독립으로 max —
    runtime.py:529/532). 사전식 정렬(주축 main, 부축 ice)은 지배축을 계층화해
    Σ((max_main+max_ice)·|s|)를 낮춘다. 반환: 원 배치 인덱스 (B_s,) 텐서
    리스트 (전체가 0..B-1의 분할).
    """
    if shard_size <= 0:
        raise ValueError(f"shard_size must be positive, got {shard_size}")
    # 사전식 (main 우선, ice 부차): stable argsort를 부축→주축 순으로 두 번.
    order = torch.argsort(pred.ice, stable=True)
    order = order[torch.argsort(pred.main[order], stable=True)]
    return [order[i:i + shard_size] for i in range(0, order.numel(), shard_size)]


def shard_cost_summary(pred: MstepPrediction, shards: list[torch.Tensor]) -> dict:
    """샤딩 전/후 비용 프록시 — 진짜 모델 (max main + max ice)·size 로 집계."""
    total = int(pred.main.numel())
    unsharded = (int(pred.main.max()) + int(pred.ice.max())) * total
    sharded = sum(
        (int(pred.main[s].max()) + int(pred.ice[s].max())) * int(s.numel())
        for s in shards)
    return dict(unsharded_cost=unsharded, sharded_cost=sharded,
                savings_ratio=1.0 - sharded / unsharded if unsharded else 0.0,
                n_shards=len(shards), B=total)
