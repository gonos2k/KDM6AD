# KIM-meso × kdm6_libtorch 통합 가이드

KDM6 microphysics(libtorch C++ 구현)을 KIM-meso v1.0 운영 빌드에 drop-in하기 위한
**handoff 문서**. F1–F5 (Fortran→C→C++→microphysics→Fortran) 전체 chain은 13/13
ctest로 검증되어 있다. 이 문서는 **KIM-meso 트리 측에서 필요한 작업**만 다룬다.

상태: **G0** (handoff prep, this document) → G1 (build/link) → G2 (registry/dispatch)
→ G3 (parity validation against Fortran slot 37) → G4 (4D-Var 결합).

---

## 1. 통합 개요

```
KIM-meso (Fortran)                              kdm6_libtorch (C++)
─────────────────────                           ────────────────────
solve_em                                         libkdm6.a (static)
  └─ microphysics_driver (slot 137)               libkdm6_c.{so,dylib}
       └─ use kdm6_iso_c                            ↑
            └─ kdm6_step(...)  ───────────────────┘ (extern "C" ABI)
                 │                                    │
                 │  ISO_C_BINDING                     │
                 ▼                                    ▼
            kdm6_step_c (bridge)  ────────►  kdm6::kdm6_step
                                                  │
                                                  ▼
                                              kdm6_fn → kdm62d_step
                                                  │
                                                  ▼
                                              preamble + warm/cold/mf
                                              + sedimentation + cleanup
```

**핵심 설계 결정**:
- C 인터페이스만 ABI 경계. C++ 예외는 `kdm6_step_c` 내부에서 모두 catch → int 에러 코드.
- Handle은 opaque `type(c_ptr)`. KIM-meso 측은 매 step **반드시** `kdm6_handle_close`
  호출 (RAII가 Fortran 측에서 보장 안 됨 — leak 방지).
- 입출력 배열은 **caller-allocated**. KIM-meso의 (ims:ime, kms:kme, jms:jme) 배열을
  그대로 전달.

---

## 2. 빌드 prerequisites (KIM-meso 호스트)

### 2.1 libtorch 설치

KIM-meso 빌드 호스트(보통 HPC 노드)에 libtorch C++ 배포본이 필요하다. CUDA 사용 여부에 따라:

```bash
# CPU only (보통 NWP 운영에 충분)
wget https://download.pytorch.org/libtorch/cpu/libtorch-shared-with-deps-2.X.X%2Bcpu.zip
unzip libtorch-shared-with-deps-2.X.X+cpu.zip -d /opt/libtorch

# CUDA 12.1 (4D-Var GPU 가속 필요 시)
wget https://download.pytorch.org/libtorch/cu121/libtorch-shared-with-deps-2.X.X%2Bcu121.zip
```

`Torch_DIR` 또는 `CMAKE_PREFIX_PATH`로 cmake에 경로 알림.

### 2.2 kdm6_libtorch 빌드

```bash
cd $KDM6_LIBTORCH_SRC
mkdir build && cd build
cmake -DCMAKE_PREFIX_PATH=/opt/libtorch \
      -DCMAKE_BUILD_TYPE=Release \
      ..
make -j8
ctest --output-on-failure   # 13/13 PASS 확인 후 진행
make install                # libkdm6_c.{so,dylib} → $PREFIX/lib
```

#### 2.2.1 이 저장소의 구체 빌드 (재현 필수 — `install_miniforge/`는 gitignore됨)

`install_miniforge/`(WRF가 rpath로 링크하는 dylib)와 `build_miniforge/`는 생성물이라 **git에 커밋되지 않는다**(`.gitignore`의 `**/install_miniforge/`, `**/build_miniforge/`). 따라서 fresh clone은 아래로 dylib를 **재생성**해야 WRF가 링크된다. miniforge libtorch를 쓰는 이 저장소의 검증된 incantation (from-scratch로 CMAKE/BUILD/INSTALL rc=0 + ctest 15/15 확인됨):

```bash
TORCH=/opt/homebrew/Caskroom/miniforge/base/lib/python3.9/site-packages/torch  # ← 본인 miniforge 경로
cd kdm6_libtorch
cmake -S . -B build_miniforge -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH="$TORCH"
cmake --build build_miniforge -j8
cmake --install build_miniforge          # → kdm6_libtorch/install_miniforge/lib/libkdm6_c.dylib (기본 prefix)
```

> ⚠️ `CMAKE_PREFIX_PATH`를 **miniforge torch**로 지정하지 않으면 `find_package(Caffe2/protobuf)`가
> homebrew protobuf를 잡아 `absl::absl_check not found` 링크 에러가 난다 (CMakeLists.txt:11 참고).

그 다음 `KIM-meso_v1.0/configure.wrf`의 **호스트-절대경로 2개를 본인 환경에 맞게 수정**한다 (이 값들은
`./configure`가 자동 생성하지 않는 KDM6AD 수동 추가분이다):
- `KDM6AD_PREFIX  = <repo>/kdm6_libtorch/install_miniforge`  (위 cmake --install 기본 prefix)
- `KDM6AD_TORCH_LIB = $TORCH/lib`

### 2.3 KIM-meso 빌드 시스템 hook

`compile`/`configure` 단계에서:
- `LIBKDM6_C_DIR=/path/to/install/lib` 환경변수
- `CFLAGS_LOCAL += -I$LIBKDM6_C_DIR/../include/kdm6`
- `LDFLAGS_LOCAL += -L$LIBKDM6_C_DIR -lkdm6_c -lkdm6 -ltorch -ltorch_cpu -lc10 -Wl,-rpath,$LIBKDM6_C_DIR`
- `bridge/kdm6_iso_c.f90`을 KIM-meso의 `phys/` 또는 `share/` 모듈 경로에 복사 후
  Makefile/Registry에서 컴파일 대상으로 등록.

**주의**: `-Wl,-rpath` 또는 `LD_LIBRARY_PATH`로 런타임에 libtorch 위치를 찾을 수 있게
하지 않으면 `wrf.exe` 시작 시 `cannot open shared object file` 에러 발생.

---

## 3. Registry slot 137 entry (template)

KIM-meso `Registry/Registry.kdm6` (또는 동일 위치)에 신규 mp_physics 옵션 추가:

```
# KDM6 differentiable variant (slot 137) — kdm6_libtorch 경유
package   mp_kdm6ad      mp_physics==137    -    state:moist,scalar  pkg:kdm6_iso_c
```

- `mp_physics==137`은 KDM6_AD 슬롯. 슬롯 37(Fortran KDM6 forward)과 별개로 공존.
- KDM6 prognostic 변수는 KIM-meso에서 이미 정의되어 있으므로(qv/qc/qr/qi/qs/qg/nccn/
  nc/ni/nr + bg) 추가 변수 등록 불필요. **bg(graupel volume mixing ratio)** 만 슬롯 37
  공유 변수 확인 필요.

---

## 4. Dispatcher hook (template)

KIM-meso microphysics dispatcher (`phys/module_microphysics_driver.F` 등)에서:

```fortran
USE kdm6_iso_c, ONLY: kdm6_step, kdm6_handle_close, &
                       KDM6_OK, KDM6_GRAD_ALL, c_ptr, c_double, c_int
TYPE(c_ptr) :: kdm6_handle
INTEGER(c_int) :: kdm6_rc

! ... existing CASE statement on mp_physics ...

CASE (KDM6ADSCHEME)  ! KDM6_AD (kdm6_libtorch)
   kdm6_rc = kdm6_step(                             &
        th, qv, qc, qr, qi, qs, qg,                 &  ! prognostic (in)
        nccn, nc, ni, nr, bg,                       &
        rho, pii, p, dz8w,                          &  ! forcing (in)
        ime-ims+1, kme-kms+1, jme-jms+1,            &  ! dimensions
        REAL(dt, c_double),                         &  ! sub-step (s)
        0_c_int,                                    &  ! params frozen for forward
        1_c_int,                                    &  ! value_only=1 (forward)
        th_new, qv_new, qc_new, qr_new,             &  ! prognostic (out)
        qi_new, qs_new, qg_new,                     &
        nccn_new, nc_new, ni_new, nr_new, bg_new,   &
        kdm6_handle)
   IF (kdm6_rc /= KDM6_OK) THEN
      WRITE(0,*) 'KDM6_AD failed rc=', kdm6_rc, ' at tile (', its, jts, ')'
      CALL wrf_error_fatal('kdm6_step returned nonzero')
   END IF
   ! 매 스텝 반드시 close — leak 방지
   kdm6_rc = kdm6_handle_close(kdm6_handle)
```

**4D-Var/sensitivity**: `value_only=0`으로 호출하면 derivative-ready handle이 반환됨.
이 경우 close하기 전에 `kdm6_handle_vjp/jvp` 호출 가능. **현재(F5 시점) vjp/jvp는
KDM6_ERR_NOT_IMPLEMENTED** — G3 단계에서 구현 예정.

---

## 5. 메모리 모델 + handle 라이프사이클

| 상황 | 의무 |
|---|---|
| 매 step kdm6_step 호출 후 | **반드시** `kdm6_handle_close` 호출 (소유권 KIM-meso 측) |
| 호출 실패(rc≠KDM6_OK) | handle 미할당이므로 close 불필요 (단 출력 배열 신뢰 금지) |
| value_only=1 | handle은 여전히 non-NULL — close 필수 |
| 동일 handle 재호출 | 미정의 동작. 매 step 새 handle |
| 다중 tile 병렬 | 각 thread/tile이 자체 handle. **공유 금지** |

C++ 측은 `kdm6_handle_close_c(NULL)`을 KDM6_OK로 처리하므로 NULL 재호출은 안전.

---

## 6. 단위 + layout 규약

- **시간 단위**: dt는 초 단위 `real(c_double)`. KIM-meso `dt`(s)를 그대로 전달.
- **배열 layout**: Fortran (im, kme, jme) column-major. C++ 측은 (B=im*jme, K=kme)로
  reshape — `kdm6_libtorch/src/state.cpp:from_fortran_arrays` 참조.
- **물리 단위 (KIM-meso ↔ KDM6 1:1)**:
  - th: potential temperature [K]
  - qv/qc/qr/qi/qs/qg: mixing ratio [kg/kg]
  - nc/ni/nr/nccn: number concentration [#/kg]
  - bg: graupel volume mixing ratio [m³/kg]
  - rho: dry air density [kg/m³]
  - pii: Exner function (dimensionless, ≈(p/p0)^(R/cp))
  - p: full pressure [Pa]
  - delz/dz8w: layer thickness [m]

`nccn` is part of the ABI/wrapper state, but the current libtorch coordinator treats
it as pass-through/deferred. The current T3 parity harness excludes `NCCN/QNN`; use
separate wrapper-level tests or a future schema extension for NCCN/QNN parity.

**rho 변환**: KIM-meso의 `rho`가 moist density라면, kdm6 측은 `den = rho`(현재 코드)
→ Fortran KDM6 slot 37과 동일 변환 사용 확인 필요. `parity/run_parity.py`의 `_to_tensor`
경로로 검증할 것 (G3 단계).

---

## 7. 알려진 caveat / 위험

### 7.1 Sub-cycling (compute_loops_max)

`kdm6_step` 내부는 `kdm62d_step`이 자체적으로 dt를 sub-cycle한다 (`dtcld ≤ 60s` 정도).
KIM-meso의 dt가 1800s여도 단일 호출로 안전. 단 sub-step 수 증가에 따라 wallclock 비례
상승.

### 7.2 NaN/Inf 입력

`from_fortran_arrays`는 `nan_gate=false`(기본). NaN 입력 시 출력도 NaN. KIM-meso 측
boundary/IC가 깨져도 silent하게 진행되므로 별도 sentinel 권장:

```fortran
IF (any(qv /= qv) .or. any(th /= th)) CALL wrf_error_fatal('NaN before kdm6_step')
```

### 7.3 dt ≤ 0 보호

`kdm62d_step`은 `delt <= 0.0` 시 입력을 그대로 반환 (Task #95). spin-up first-step
edge 에서 안전.

### 7.4 contiguous 가정

`kdm6_iso_c.f90`의 wrapper는 `contiguous`로 받는다. KIM-meso 측에서 array section
slicing `qc(its:ite, kts:kte, jts:jte)`을 전달하면 컴파일러가 임시 contiguous copy를
만든다. **성능 critical**: copy 발생 여부를 `-O3 -fopt-info-vec` 또는 `-Minfo=array`로
프로파일.

### 7.5 MPI tile boundaries

KDM6 microphysics는 column-local(수직만 결합). halo 교환 불필요. 단 sedimentation은
수직 column 내 종속성이라 tile 분할 영향 없음.

### 7.6 OpenMP / thread safety

`kdm6_step`은 reentrant. 단 동일 handle 다중 thread 공유 금지. `!$OMP DO` tile 루프
내부에서 각 thread가 자체 (state, handle) 사용 가능.

### 7.7 libtorch threading

libtorch CPU backend은 자체 thread pool을 가진다. KIM-meso가 OpenMP/MPI hybrid라면
`OMP_NUM_THREADS` 외 `MKL_NUM_THREADS=1`, `torch::set_num_threads(1)` 명시 권장 —
oversubscription 방지.

---

## 8. Validation 절차 (G3 단계)

1. **Forward parity**: 동일 입력 (KIM-meso 캡처 골든 벡터)에 대해 슬롯 37(Fortran)과
   슬롯 137(KDM6_AD) 출력 비교. 현재 `parity/run_parity.py`는 11개 microphysics-level
   schema fields만 비교하며 `NCCN/QNN`은 제외한다. 목표:
   - qv/qc/qr/qi/qs/qg: rel-tol 1e-10
   - nc/ni/nr: rel-tol 1e-9
   - th: abs-tol 1e-6 K
   - NCCN/QNN: 현 schema 밖. G3에서 제외를 명시하거나 schema/capture를 확장할 것.
   - auxdiag: 현재 runtime/harness default를 쓰므로, operational KIM auxdiag와 다르면
     oracle drift가 아니라 wrapper/diagnostic drift일 수 있음.
2. **Determinism**: 동일 호출 반복 시 비트-재현. libtorch CPU backend은 비결정적
   reduction 가능 — `at::globalContext().setDeterministicAlgorithms(true)` 검토.
3. **AD identity** (G3 후): `J^T·J·v ≈ ‖J·v‖²` 항등식 검증.

골든 벡터 캡처는 **Task #54** 진행 중. KIM-meso 운영 시뮬레이션 한 단계의 (state, forcing,
state_out)을 npz로 저장하여 `parity/run_parity.py --golden-dir <path>` 호출.

---

## 9. 단계별 체크리스트

- [ ] G1: libkdm6_c.{so,dylib} KIM-meso 호스트 빌드/설치
- [ ] G1: 링크 + rpath 검증 (`ldd wrf.exe | grep kdm6`)
- [ ] G2: Registry slot 137 entry 추가
- [ ] G2: dispatcher CASE(KDM6ADSCHEME) 추가, `use kdm6_iso_c`
- [ ] G2: namelist 옵션 `mp_physics = 137` 테스트 케이스
- [ ] G3: 골든 벡터 1샘플 캡처 (Task #54)
- [ ] G3: parity harness 통과 (rel-tol 목표)
- [ ] G4: vjp/jvp 구현 (현재 NOT_IMPLEMENTED) + 4D-Var 결합

---

## 10. 트러블슈팅

| 증상 | 원인 / 해결 |
|---|---|
| `cannot open shared object libkdm6_c.so` | LD_LIBRARY_PATH 또는 rpath 누락. ldd로 확인 |
| `kdm6_step returned -2` (KDM6_ERR_NULL_POINTER) | 입력 배열 중 하나가 미할당. allocate 확인 |
| `kdm6_step returned -1` (KDM6_ERR_INVALID_DIM) | im/kme/jme 중 ≤0. 빈 tile일 가능성 |
| 출력이 입력과 동일 (microphysics 미실행) | dt ≤ 0이거나 모든 셀이 무활성. dt 입력값 확인 |
| 슬롯 37과 다른 출력 | 단위 변환(특히 rho), aux defaults, parameter mismatch. parity harness로 분리 진단 |
| NaN 발견 | 입력 sentinel 추가 (§7.2). kdm62d_step의 delt≤0 guard와 별개 |

---

**문서 maintenance**: 통합 작업 중 발견되는 새 caveat은 §7에 추가, 트러블슈팅
케이스는 §10에 누적. 각 G-단계 완료 시 §9 체크리스트 갱신.
