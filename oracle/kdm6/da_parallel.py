"""프로세스-샤딩 병렬 OSSE 드라이버 (DA_REALTIME_PLAN — 10분 티어 실증).

근거: 컬럼 독립성은 ABI 레벨에서 비트단위 검증됐고(비대칭 타일 테스트),
정밀 검토가 프로세스 샤딩을 dylib 무변경 안전으로 판정(가드 2종 포함).
B=128 단일 프로세스 실측(민감도 60s/분석 4min) × N 프로세스 = N×128 컬럼을
같은 벽시계에 — 이 모듈이 그 배관이다.

안전 가드 (정밀 검토 스펙, 드라이버가 강제):
  1. 샤드별 독립 RTTOV 케이스 디렉토리 (공유 make_live_run_k 클로저 금지).
  2. KDM6_SUBSTEP_DUMP unset (env-gated 고정이름 CWD 덤프 — worker에서 제거).
  3. torch 스레드 1 고정 (worker와 in-process 참조가 동일 감산 순서를 갖게 —
     샤드-vs-인프로세스 bitwise 동등성 게이트의 전제).

macOS 관례: multiprocessing spawn (fork는 torch와 불안정). worker는 모듈
최상위 함수여야 pickle 가능.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import torch

from .da_window import WindowConfig
from .state import State, Forcing

_F64 = dict(dtype=torch.float64)


@dataclass
class ShardSpec:
    """worker 1개의 완전한 입력 (pickle로 전달)."""
    shard_id: int
    col_idx: torch.Tensor              # 원 배치 컬럼 인덱스 (B_s,)
    x_truth: State                     # 해당 샤드 컬럼만 (B_s, K)
    x_background: State
    forcing: Forcing                   # (B_s, K) — 창 내 상수 가정 (드라이버 관례)
    n_steps: int
    dt: float
    obs_times: tuple
    case_root: str                     # 이 샤드 전용 RTTOV 케이스 루트
    profile_kwargs: dict               # RttovProfileConfig 재구성 인자 (텐서 포함)
    input_kwargs: dict                 # RttovInputConfig 재구성 인자
    obs_sigma: float
    t_ref: torch.Tensor | None
    q_ref: torch.Tensor | None
    q_blend_octaves: float


def _shard_worker(spec: ShardSpec) -> dict:
    """worker 프로세스 본체 (spawn-safe 모듈 최상위). 민감도 사이클 1회."""
    os.environ.pop("KDM6_SUBSTEP_DUMP", None)          # 가드 2
    torch.set_num_threads(1)                           # 가드 3
    from .da_driver import OsseObsConfig, run_osse_sensitivity
    from .obs.model_profile_builder import RttovProfileConfig
    from .obs.rttov_case_writer import make_live_run_k
    from .obs.rttov_input_builder import RttovInputConfig

    obs_cfg = OsseObsConfig(
        run_k=make_live_run_k(Path(spec.case_root)),    # 가드 1: 샤드 전용 dir
        profile_cfg=RttovProfileConfig(**spec.profile_kwargs),
        input_cfg=RttovInputConfig(**spec.input_kwargs),
        obs_sigma=spec.obs_sigma,
        t_ref=spec.t_ref, q_ref=spec.q_ref,
        q_blend_octaves=spec.q_blend_octaves)
    rep = run_osse_sensitivity(
        spec.x_truth, spec.x_background, [spec.forcing] * spec.n_steps,
        list(spec.obs_times), WindowConfig(dt=spec.dt), obs_cfg)
    return dict(shard_id=spec.shard_id,
                col_idx=spec.col_idx,
                j_obs=rep.j_obs,
                n_obs_times=rep.n_obs_times,
                adj_x0={k: getattr(rep.window.adj_x0, k) for k in State._fields})


def run_sharded_sensitivity(specs: Sequence[ShardSpec], *, n_workers: int,
                            parallel: bool = True) -> dict:
    """샤드들을 N worker 프로세스로 실행하고 원 컬럼 순서로 재조립.

    parallel=False면 같은 worker 함수를 in-process 순차 실행 — 병렬-vs-순차
    bitwise 동등성 게이트의 참조 경로 (같은 코드, 같은 스레드 고정).
    반환: {"j_obs": Σ, "adj_x0": State (B_total, K) 원 인덱스 재조립, ...}
    """
    if parallel:
        import multiprocessing as mp
        # spawn 자식은 부모의 sys.path 수정(conftest)을 상속하지 않는다 —
        # oracle 루트를 PYTHONPATH로 물려줘 worker의 `from .` 체인이 성립하게.
        oracle_root = str(Path(__file__).resolve().parents[1])
        pp = os.environ.get("PYTHONPATH", "")
        if oracle_root not in pp.split(os.pathsep):
            os.environ["PYTHONPATH"] = oracle_root + ((os.pathsep + pp) if pp else "")
        ctx = mp.get_context("spawn")
        with ctx.Pool(processes=n_workers) as pool:
            results = pool.map(_shard_worker, list(specs))
    else:
        torch.set_num_threads(1)                        # 참조 경로도 동일 고정
        results = [_shard_worker(s) for s in specs]

    # B_total은 샤드 크기 합이 아니라 **인덱스 공간**에서 유도 — 크기 합으로
    # 잡으면 누락 분할(gap)이 IndexError로 죽어 union 가드에 못 닿는다.
    B_total = max(int(s.col_idx.max()) for s in specs) + 1
    K = specs[0].x_truth.th.shape[1]
    merged = {k: torch.zeros((B_total, K), **_F64) for k in State._fields}
    seen = torch.zeros(B_total, dtype=torch.bool)
    for r in results:
        ci = r["col_idx"]
        if bool(seen[ci].any()):
            raise RuntimeError("shard column overlap — partition broken")
        seen[ci] = True
        for k in State._fields:
            merged[k][ci] = r["adj_x0"][k]
    if not bool(seen.all()):
        raise RuntimeError("shard union != full batch — partition broken")
    return dict(
        j_obs=float(sum(r["j_obs"] for r in results)),
        adj_x0=State(**merged),
        per_shard_j=[(r["shard_id"], r["j_obs"]) for r in results],
        n_shards=len(results))


def build_shard_specs(x_truth: State, x_background: State, forcing: Forcing,
                      shard_indices: Sequence[torch.Tensor], *,
                      n_steps: int, dt: float, obs_times: Sequence[int],
                      case_root: str, profile_kwargs: dict, input_kwargs: dict,
                      obs_sigma: float = 1.0,
                      t_ref: torch.Tensor | None = None,
                      q_ref: torch.Tensor | None = None,
                      q_blend_octaves: float = 4.0) -> list:
    """(B_total, K) 입력 + 분할 인덱스 리스트(예: da_shard.compose_shards 출력)
    → ShardSpec 리스트. col_idx는 [0, B_total) 재조립 인덱스 그 자체."""
    specs = []
    for i, ci in enumerate(shard_indices):
        sub = lambda s: type(s)(**{k: v[ci] for k, v in s._asdict().items()})
        specs.append(ShardSpec(
            shard_id=i, col_idx=ci.clone(),
            x_truth=sub(x_truth), x_background=sub(x_background),
            forcing=sub(forcing),
            n_steps=n_steps, dt=dt, obs_times=tuple(int(t) for t in obs_times),
            case_root=str(Path(case_root) / f"shard{i:03d}"),
            profile_kwargs=profile_kwargs, input_kwargs=input_kwargs,
            obs_sigma=obs_sigma, t_ref=t_ref, q_ref=q_ref,
            q_blend_octaves=q_blend_octaves))
    return specs
