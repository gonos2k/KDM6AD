# kdm6_torch — KDM6 미분가능 변종 — **REFERENCE ORACLE** (Python)

> **운영 비트정합 경로는 저장소의 `libtorch/`(libtorch C++)입니다.**
> 본 Python 트리는 fp64 **자료동화/미분 경로**이자 C++ forward의 **수치 정합
> 검증 oracle**입니다. 두 경로의 계약 분리는 루트 `README.md` 참조.

KIM-meso v1.0의 KDM6 microphysics를 PyTorch comp-graph AD 형태로 재구현.
슬롯 47용. forward(슬롯 37, Fortran/C++)와 동반 구동하여 Jacobian/민감도를
산출하며, 물리 모듈과 VJP/JVP/HVP가 구현·검증되어 있습니다.

## 패러다임

- **Comp-graph AD** (PyTorch dynamic tape) — *not* Tapenade source-to-source TLM/ADJ
- **1D-column batch**: KDM6는 (i,k,j) 칼럼 단위 독립 → 텐서 `(B, K)`로 묶어 한 graph
- **Float64**: Fortran R8 정합. KDM6의 dynamic range(qcrmin=1e-9, lamdaimax=1.82e6)에서 float32 underflow 위험

## 디렉터리 구조 (현행)

```
kdm6/
├── constants.py       — Fortran 상수 직역 (peaut, ncrk1/2, lamda*max, t0c, ...)
├── ops.py             — torch-safe idioms (safe_div, clamp 규약 등)
├── state.py           — (B, K) State/Forcing NamedTuple layout
├── coordinator.py     — warm/cold/melt-freeze/satadj 단계 조율 (미분가능)
├── sedimentation.py   — nislfv_rain_plmr (per-column mstep)
├── runtime.py         — kdm6_step / _kdm6_pure (C++ forward 정합, VJP/JVP)
├── da_*.py            — CVT/window/minimizer/dual/partition/regime2 (fp64 DA)
└── obs/               — GK2A 어댑터·superob·RTTOV 연산자

tests/                 — 정합·수반 항등식·DA·경계검증 스위트
```

## 현재 상태

- ✓ 물리 모듈(coordinator/sedimentation/satadj)·runtime — C++ forward와
  ~5e-14 상대 정합, autograd 전 leaf 도달.
- ✓ VJP/JVP/HVP + fp64 자료동화 경로(da_*) 구현·검증.
- ✓ 경계 입력 검증(dt/ncmin/xland/superob) — 리뷰 P1-2/P1-3.
- 로드맵: RTTOV 5-species 매핑 + 연속 cfrac, 확률적 4-regime 혼합 우도.

## Reference

프로젝트 위키 참조:
- 패러다임: [[differentiable-microphysics-paradigm]]
- 분기 처리: [[branch-semantics-physical-vs-numerical]]
- 침강: [[nislfv-plm-sedimentation]]
- 원본 코드 분석: [[module-mp-kdm6-fortran]]
