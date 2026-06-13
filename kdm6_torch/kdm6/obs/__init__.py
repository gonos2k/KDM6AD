"""Model-side RTTOV observation operator (scaffold).

설계: `KDM6AD/model-side-rttov-observation-operator.md`. 이 패키지는 관측 valid time의 완료
모델 상태에서 RTTOV direct/K를 수행하고(out-of-process, §14.2), 그 profile adjoint를
KDM6AD-consistent bridge VJP로 state adjoint로 변환해 `da_window`의 `obs_adj[t]`로 주입한다.

구현 순서(설계 §12): scheduler(M1) → profile_builder(M2) → bridge 재사용(M3, rttov_bridge.py)
→ runner direct(M4) → runner K + interface contract(M5) → obs_operator callback(M6).

성숙도(§1.7): 현재 RTTOV 자산은 **clear-sky T/Q 경로만** 즉시 실행 가능(ami/501 O3+CO2 coef
[rttov13pred54L = coef predictor 54 levels] + pyrttov + run.sh). AMI cloudy/hydrometeor K는 matching
hydrotable 부재로 차단 — cloud 경로 모듈은 설계 단계 stub다.

★ grid 주의: coef predictor 54L ≠ user profile grid. RTTOV-14 AMI는 layer-based로 user profile은
ami/501 fixture 기준 nlayers=69/nlevels=70(입력마다 다름) — profile_builder가 fixture/coef에서
derive(hard-code 금지). RTTOV가 user grid→coef 54L 내부 보간.

모든 모듈은 아직 stub(NotImplementedError). reference 공식/상수/매핑은 `_rttov_reference/`.
"""
