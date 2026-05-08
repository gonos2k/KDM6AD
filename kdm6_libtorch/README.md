# kdm6_libtorch — KDM6 미분가능 변종 (libtorch C++ 운영 경로)

KIM-meso v1.0의 KDM6 microphysics를 **libtorch C++**로 재구현. 현재 KIM-meso 통합 대상은 `mp_physics==137` KDM6AD slot이다. Fortran forward(슬롯 37)와의 operational parity 및 derivative 산출은 G3/G4 범위다.

Python prototype(`/home/yhlee/KDM6/kdm6_torch/`)은 **reference oracle**로 보존 — 수치 정합 검증의 ground truth.

## Why C++ — [[libtorch-cpp-integration]] 참조

- MPI 분산 환경에서 GIL/Python 임베딩 회피
- corporate cert / pip 의존성 제거
- ICON-PyTorch가 보고한 "Fortran-Python bridge complexity" 회피
- 운영 NWP 빌드 체인(`compile`, configure.wrf)에 자연스럽게 통합 가능

## 빌드

```bash
cd kdm6_libtorch
mkdir build && cd build

# Torch_DIR — Python venv의 libtorch 사용 (prototype 단계)
cmake -DCMAKE_PREFIX_PATH="/home/yhlee/KDM6/kdm6_torch/.venv/lib/python3.12/site-packages/torch" ..

# 또는 별도 libtorch 다운로드 사용 (운영)
# cmake -DCMAKE_PREFIX_PATH=/path/to/libtorch ..

make -j$(nproc)
ctest --output-on-failure
```

## 디렉터리 구조

```
include/kdm6/   — public headers
src/            — C++ 구현
bridge/         — Fortran ↔ C++ ABI (extern "C" + ISO_C_BINDING)
tests/          — Catch2 또는 plain main + assert
```

## 현재 상태 (F1–F5 완료, G0 prep 완료)

- ☑ 모든 microphysics 모듈 포팅 (warm/cold/melt_freeze/sedimentation/preamble/cloud_dsd)
- ☑ C++ coordinator chain (kdm62d_step + kdm62d_one_step + sub-cycling + sedimentation_chain)
- ☑ F4 ABI bridge wired (`runtime.cpp` kdm6_fn → kdm62d_step, Task #97)
- ☑ C ABI end-to-end test (`tests/test_c_abi.cpp`, Task #98)
- ☑ Fortran ISO_C_BINDING module (`bridge/kdm6_iso_c.f90`) + smoke test (Task #99)
- ☑ KIM-meso integration handoff doc ([docs/KIM_MESO_INTEGRATION.md](docs/KIM_MESO_INTEGRATION.md), Task #100)
- ☑ ctest **13/13 PASS**, Python kdm6_torch 216/216, local 11-field parity 7/7 (NCCN/QNN excluded), symbol parity allowlist 0건
- ☐ G1–G2: KIM-meso 트리 통합 (Registry slot 137 + dispatcher) — KIM-meso 작업자 측
- ☐ G3: Forward parity (슬롯 37 ↔ 137, NCCN/QNN 및 auxdiag 정책 명시 필요) — Task #54 골든 벡터 대기
- ☐ G4: vjp/jvp 구현 + 4D-Var 결합

## KIM-meso 통합

KIM-meso 측 작업자는 [docs/KIM_MESO_INTEGRATION.md](docs/KIM_MESO_INTEGRATION.md)를
단일 진입점으로 사용. 빌드 → Registry → dispatcher → validation 전 절차 수록.

## 결정 요약 (C-series, [[libtorch-cpp-integration]])

| ID | 결정 |
|---|---|
| C1 | CMake + find_package(Torch) — venv 또는 별도 libtorch |
| C2 | C++17 |
| C3 | extern "C" ABI, opaque handle, int 에러 코드 |
| C4 | tensor zero-copy (torch::from_blob), output buffer caller-allocated |
| C5 | Parameters struct + bitmask `param_grad_flags` ABI |
| C6 | Per-call Handle, RAII close() / dtor |
| C7 | Catch2 또는 plain assert (1차 prototype) |
| C8 | Python `kdm6_torch/` = reference oracle (검증 게이트) |

## Reference

- `/home/yhlee/KDM6/wiki/concepts/libtorch-cpp-integration.md` — 본 결정 문서
- `/home/yhlee/KDM6/wiki/concepts/pytorch-autograd-integration.md` — 상위 아키텍처 (Python·C++ 공통)
- `/home/yhlee/KDM6/kdm6_torch/` — Python reference oracle
