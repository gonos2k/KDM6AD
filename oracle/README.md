# kdm6_torch — KDM6 미분가능 변종 — **REFERENCE ORACLE** (Python prototype)

> **운영 경로는 `/Users/yhlee/KDM6AD-k/libtorch/` (libtorch C++)입니다.**
> 본 Python 트리는 **수치 정합 검증 oracle**로 보존됩니다.
> [[libtorch-cpp-integration]] 참조.

KIM-meso v1.0의 KDM6 microphysics를 PyTorch comp-graph AD 형태로 재구현. 슬롯 47용. forward(슬롯 37, Fortran)와 동반 구동하여 Jacobian/민감도 산출.

## 패러다임

- **Comp-graph AD** (PyTorch dynamic tape) — *not* Tapenade source-to-source TLM/ADJ
- **1D-column batch**: KDM6는 (i,k,j) 칼럼 단위 독립 → 텐서 `(B, K)`로 묶어 한 graph
- **Float64**: Fortran R8 정합. KDM6의 dynamic range(qcrmin=1e-9, lamdaimax=1.82e6)에서 float32 underflow 위험

## 디렉터리 구조 (계획)

```
kdm6/
├── constants.py       — Fortran 상수 직역 (peaut, ncrk1/2, lamda*max, t0c, ...)
├── ops.py             — torch-safe idioms (TODO: 사용자 contribution)
├── state.py           — (B, K) state tensor layout (TODO: 사용자 contribution)
├── slope.py           — slope_kdm6, slope_rain 포팅 (1단계)
├── core.py            — kdm62D 코어 (1단계, ~2630라인 → torch)
├── sedimentation.py   — nislfv_rain_plmr (2단계)
└── kdm6.py            — wrapper (3단계)

tests/
├── test_smoke.py              — 가장 단순 입력 forward+backward 한 패스
└── test_against_fortran.py    — 슬롯 37 정합 검증 (TODO: 허용 오차 결정)
```

## 현재 상태

- ✓ constants.py (Fortran 상수 직역)
- ⚠ ops.py (skeleton — 사용자 contribution 대기)
- ⚠ state.py (skeleton — 사용자 contribution 대기)
- ☐ 그 외 모듈 — 위 두 결정 후 진행

## Reference

프로젝트 위키 참조:
- 패러다임: [[differentiable-microphysics-paradigm]]
- 분기 처리: [[branch-semantics-physical-vs-numerical]]
- 침강: [[nislfv-plm-sedimentation]]
- 원본 코드 분석: [[module-mp-kdm6-fortran]]
