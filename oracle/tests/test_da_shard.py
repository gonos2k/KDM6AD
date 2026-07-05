"""T0-3 mstep-aware 샤드 구성 검증 (docs/DA_REALTIME_PLAN.md).

핵심 불변식: predict_mstep_col은 _kdm6_pure가 첫 sub-cycle에서 실제로 쓰는
mstep_col_main/ice와 **정확히 일치**해야 한다 — 같은 코드 경로를 재사용하므로,
spy로 sedimentation_chain_torch에 전달된 kwargs를 포획해 대조한다.
"""
from __future__ import annotations

import pytest
import torch

from kdm6 import coordinator as _coord
from kdm6.da_shard import compose_shards, predict_mstep_col, shard_cost_summary
from kdm6.runtime import _kdm6_pure, make_parameters
from kdm6.state import State, Forcing

_F64 = dict(dtype=torch.float64)


def _mixed_batch(B: int = 8, K: int = 12) -> tuple[State, Forcing]:
    """가벼운 컬럼들 + 무거운(강수) 컬럼 2개(인덱스 2, 5)."""
    def full(v):
        return torch.full((B, K), v, **_F64)

    qr = full(1.0e-6)
    qs = full(0.0)
    qg = full(0.0)
    nr = full(1.0e3)
    for b in (2, 5):                      # 강수 대류 컬럼: 큰 vt → 큰 mstep
        qr[b] = 5.0e-3
        qs[b] = 2.0e-3
        qg[b] = 3.0e-3
        nr[b] = 1.0e5
    state = State(
        th=full(290.0), qv=full(8.0e-3), qc=full(2.0e-4), qr=qr,
        qi=full(1.0e-5), qs=qs, qg=qg, nccn=full(1.0e9),
        nc=full(5.0e7), ni=full(1.0e4), nr=nr, bg=full(0.0),
    )
    # 얇은 하부층 (stretched grid) — mstep을 키우는 현실 조건
    delz = torch.linspace(80.0, 600.0, K, **_F64).repeat(B, 1)
    forcing = Forcing(rho=full(1.0), pii=full(0.95), p=full(8.5e4), delz=delz)
    return state, forcing


def test_predictor_matches_first_subcycle_exactly(monkeypatch):
    """스파이로 첫 sub-cycle의 실제 mstep_col을 포획해 예측기와 정확 대조."""
    state, forcing = _mixed_batch()
    captured = {}
    orig = _coord.sedimentation_chain_torch

    def spy(*args, **kwargs):
        if "first" not in captured:                      # 첫 sub-cycle만
            captured["first"] = (kwargs["mstep_col_main"].clone(),
                                 kwargs["mstep_col_ice"].clone())
        return orig(*args, **kwargs)

    monkeypatch.setattr(_coord, "sedimentation_chain_torch", spy)
    _kdm6_pure(state, forcing, make_parameters(), dt=300.0)
    assert "first" in captured

    pred = predict_mstep_col(state, forcing, dt=300.0)
    actual = (captured["first"][0] + captured["first"][1]).to(torch.int64)
    assert torch.equal(pred, actual), f"pred {pred.tolist()} != actual {actual.tolist()}"


def test_predictor_flags_heavy_columns():
    state, forcing = _mixed_batch()
    pred = predict_mstep_col(state, forcing, dt=300.0)
    heavy = {2, 5}
    light_max = max(int(pred[b]) for b in range(8) if b not in heavy)
    for b in heavy:
        assert int(pred[b]) > light_max, (b, pred.tolist())


def test_predictor_is_no_grad_safe():
    """예측기는 연산그래프에 무접촉 — requires_grad 리프에 grad_fn을 남기지 않는다."""
    state, forcing = _mixed_batch()
    state = State(**{k: v.requires_grad_(True) for k, v in state._asdict().items()})
    pred = predict_mstep_col(state, forcing, dt=300.0)
    assert pred.requires_grad is False
    assert pred.grad_fn is None
    for v in state:
        assert v.grad is None                             # backward 없이 오염 없음


def test_compose_shards_partition_and_economics():
    cost = torch.tensor([1, 12, 1, 2, 14, 1, 2, 1], dtype=torch.int64)
    shards = compose_shards(cost, shard_size=4)
    # 분할 완전성
    all_idx = torch.cat(shards).sort().values
    assert torch.equal(all_idx, torch.arange(8))
    # 무거운 컬럼(1, 4)이 같은 샤드로
    heavy_shard = [s for s in shards if 1 in s.tolist()][0]
    assert 4 in heavy_shard.tolist()
    # 경제성: 정렬-분할이 비샤딩(전 배치가 max 지불)보다 싸다
    summary = shard_cost_summary(cost, shards)
    assert summary["sharded_cost"] < summary["unsharded_cost"]
    assert summary["savings_ratio"] > 0.3                 # 이 배치에선 큰 절감


def test_compose_shards_rejects_bad_size():
    with pytest.raises(ValueError):
        compose_shards(torch.tensor([1, 2]), shard_size=0)
