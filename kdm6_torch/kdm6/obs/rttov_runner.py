"""P4/P5 — out-of-process RTTOV runner (설계 §7, §14.2; 검증 M4/M5).

RTTOV는 별도 프로세스로 격리 호출(libtorch+RTTOV-OpenMP 충돌 회피, §14.2). 단일 `runK`가
direct BT(out.Bt, _doStoreRad)와 full per-channel K-matrix를 **동시 산출** → 별도 runDirect 불요.

★ runK는 lambda_BT를 seed로 받지 않는다(pyrttov runK(channels)). 채널 contraction
`λ_profile = Σ_c K[c]·λ_BT[c]`는 호출자(RttovObsOp.backward)가 한다(§9/§14.3).

backend 추상(둘 다 out-of-process):
  - subprocess `run.sh` (검증된 fixture I/O, rttov_ascii 파서) — 1차
  - pyrttov-in-child (rttov_wrapper_f2py.so; runDirect/runK 같은 Rttov 객체) — 최적화
AD_RTTOV_HOME: /Users/yhlee/AD-RTTOV (coef rtcoef_gkompsat2_1_ami_o3co2.dat, rttov13pred54L =
coef predictor 54 levels; user profile grid은 별개 — ami/501 fixture nlayers=69/nlevels=70; §14.5).

STUB — 미구현.
"""
from __future__ import annotations


def run_rttov_k(rttov_input, channels=None):
    """단일 runK: out.Bt(direct BT) + K-matrix(TK, getItemK, getHydroDeffNK; [...,nch,nlay]).
    K accessor는 dict로 캐시(RttovObsOp.forward가 ctx에 저장). λ_BT 인자 없음(§9.1)."""
    raise NotImplementedError("P5 runner(K) — 설계 §7/§9.1/§14.2, M5")


def run_rttov_direct(rttov_input):
    """(선택) value-only 진단 runner — adjoint 경로 아님(§7). 보통 runK 1회로 대체."""
    raise NotImplementedError("P4 runner(direct, 진단용) — 설계 §7, M4")
