"""P1 — obs↔model-step 정합 scheduler (설계 §2, §10; 검증 M1).

관측 valid time을 checkpoint된 model step-end 경계에 정합한다. 시간보간 없음(§1.3):
off-step 관측은 거부(M1 test_obs_schedule_rejects_off_step_obs). 관측 valid time은 UTC 명시.

STUB — 미구현.
"""
from __future__ import annotations

from typing import NamedTuple


class ObsSchedule(NamedTuple):
    """정합된 관측의 step-index 바인딩 (설계 §4.1)."""
    # step_index -> obs payload(채널·BT_obs·mask·sigma·geometry). 실제 타입은 구현 시 확정.
    by_step: dict


def build_obs_schedule(window_cfg, obs_valid_times, obs_time_tolerance) -> ObsSchedule:
    """obs valid time을 t_k = window_start + k·model_dt에 정합. 정수분할 불가 시 거부.

    contract (§2.1):
        ∃k: |t_obs − t_k| ≤ obs_time_tolerance  → bind to k
        else                                    → reject (보간 금지)
    """
    raise NotImplementedError("P1 scheduler — 설계 §2/§10, M1")
