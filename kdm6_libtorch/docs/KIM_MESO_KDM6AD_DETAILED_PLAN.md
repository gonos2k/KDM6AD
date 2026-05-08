# KIM-meso × KDM6 자동미분 통합 상세계획

이 문서는 `KIM_MESO_INTEGRATION.md`의 handoff 내용을 실행 가능한 단계로 풀어 쓴 상세계획이다. 기존 문서는 빌드·Registry·dispatcher의 단일 진입점이고, 이 문서는 KIM-meso 트리에서 실제로 어떤 순서로 검증하고 확장할지를 정의한다.

## 0. 현재 상태 요약

### 이미 반영된 항목

- `kdm6_libtorch`는 Fortran → C ABI → C++ → KDM6 microphysics → Fortran 라운드트립 smoke까지 완료된 상태다.
- KIM-meso 트리에는 KDM6AD slot 137 경로가 일부 반영되어 있다.
  - `Registry/Registry.EM_COMMON`: `mp_physics==137` package entry 존재.
  - `phys/module_microphysics_driver.F`: `KDM6ADSCHEME` case와 `module_mp_kdm6ad` 사용 경로 존재.
  - `phys/module_mp_kdm6ad.F`: KIM 배열을 `kdm6_step`으로 전달하는 wrapper 존재.
  - `phys/kdm6_iso_c.f90`: `kdm6_step`, `kdm6_handle_vjp`, `kdm6_handle_jvp`, `kdm6_handle_close` ISO_C_BINDING wrapper 존재.
  - `phys/Makefile`, `phys/CMakeLists.txt`: `kdm6_iso_c`와 `module_mp_kdm6ad` 컴파일 대상 등록 존재.

### 현재 통합의 의미

현재 `module_mp_kdm6ad` 경로는 자동미분 가능한 libtorch 구현을 호출하지만, 호출 모드는 `value_only=1`이다. 따라서 현재 단계는 **KDM6AD forward 통합**이지, 4D-Var에서 VJP/JVP를 실제 사용하는 단계는 아니다.

Derivative-ready 경로는 forward parity가 확인된 뒤 별도 단계로 확장한다.

## 1. 전체 목표

1. KIM-meso 운영 빌드에서 `mp_physics=137`로 KDM6AD forward가 안정적으로 실행되게 한다.
2. 기존 Fortran KDM6 slot 37과 KDM6AD slot 137의 forward 결과를 동일 입력에서 검증한다.
3. forward parity가 확보된 뒤, `value_only=0` handle 기반 VJP/JVP 경로를 설계·구현한다.
4. 최종적으로 KDM6 microphysics block을 KIM-meso 4D-Var/sensitivity 계산에서 comp-graph AD island로 연결한다.

## 1.1 수학적 문제 정의

KDM6 microphysics 한 timestep을 다음 함수로 둔다.

```text
y = F_θ(x, a; Δt)
```

- `x`: prognostic state vector. KIM tile `(im, kme, jme)`의 각 격자값을 field 순서대로 packing한 벡터.
- `a`: forcing/diagnostic vector. `rho`, `pii`, `p`, `delz`처럼 microphysics update에는 필요하지만 기본 sensitivity 대상은 아닌 입력.
- `θ`: tunable microphysics parameters. 현재 ABI의 `param_grad_flags`가 가리키는 `peaut`, `ncrk1`, `ncrk2`, `eccbrk`가 1차 후보.
- `Δt`: KIM physics timestep. KDM6 내부에서는 `dtcld` sub-cycling으로 분해될 수 있다.
- `y`: update 후 prognostic state vector.

초기 state vector packing 순서는 다음처럼 고정한다.

```text
x = [TH, QV, QC, QR, QI, QS, QG, NCCN, NC, NI, NR, BG]
```

각 field는 Fortran storage 순서의 tile-local `(im, kme, jme)` 값을 동일한 순서로 flatten한다. 이 순서는 forward output, VJP seed, JVP tangent, gradient unpacking에서 모두 동일해야 한다.

자료동화 관점에서 필요한 미분은 전체 Jacobian을 명시적으로 만드는 것이 아니라 다음 두 선형 연산이다.

```text
J_x v      = ∂F/∂x · v        (JVP, tangent-linear action)
J_x^T u    = (∂F/∂x)^T · u    (VJP, adjoint action)
J_θ^T u    = (∂F/∂θ)^T · u    (parameter-gradient action)
```

여기서 `u`는 후속 cost function 또는 adjoint model에서 넘어오는 output cotangent이고, `v`는 tangent perturbation이다. KDM6AD의 핵심은 dense Jacobian을 저장하지 않고, libtorch autograd graph handle을 통해 위 연산만 계산하는 것이다.

## 1.2 4D-Var 비용함수와 KDM6AD의 역할

일반적인 strong-constraint 4D-Var 비용함수는 다음 형태다.

```text
J(z0) = 1/2 ||z0 - zb||_{B^-1}^2 + 1/2 Σ_i ||H_i(z_i) - d_i||_{R_i^-1}^2
z_{i+1} = M_i(z_i)
```

KDM6는 전체 model operator `M_i` 안의 moist physics block이다. dynamics, radiation, surface physics와 섞인 전체 Jacobian을 한 번에 libtorch로 대체하는 것이 아니라, KDM6 block만 다음처럼 독립 derivative provider로 취급한다.

```text
z^-  ── KDM6 block F ──> z^+
λ^+  ── VJP(F)       ──> λ^-
```

따라서 KIM adjoint/tangent path와의 결합점은 `microphysics_driver` 전체가 아니라 KDM6 call boundary다. forward parity가 확보되면, KDM6 block에 들어가는 state slice와 나오는 state slice 사이에서 `J_x^T u`를 계산해 기존 adjoint 변수에 누적한다.

## 1.3 수치 검증 기준

Forward parity는 다음 norm을 함께 본다.

```text
abs_err = ||y_ad - y_f90||_∞
rel_err = ||y_ad - y_f90||_2 / max(||y_f90||_2, ε)
```

Near-zero hydrometeor field는 relative error가 과대해지므로 absolute tolerance를 함께 둔다. derivative 검증은 다음 항등식으로 시작한다.

```text
<u, Jv> = <J^T u, v>
```

finite-difference 검증은 central difference를 기본으로 한다.

```text
Jv ≈ (F(x + εv) - F(x - εv)) / (2ε)
```

`ε`는 field scale에 따라 달라져야 한다. mixing ratio처럼 작은 양수 field는 무차별 절대 perturbation을 주면 음수가 되어 branch가 바뀔 수 있으므로, `ε · max(|x|, scale_floor)` 형태의 scale-aware perturbation을 사용한다.

## 2. 통합 원칙

### 2.1 Tapenade AD 경로와 분리

KIM-meso에는 `wrftladj/` 기반 Tapenade TLM/ADJ 코드와 adStack 메커니즘이 있다. KDM6AD는 이 source-to-source AD 경로에 합류하지 않고, libtorch dynamic graph를 사용하는 독립 경로로 유지한다.

### 2.2 forward parity 우선

VJP/JVP는 forward 함수의 Jacobian에 대한 연산이다. 따라서 slot 37 Fortran KDM6와 slot 137 KDM6AD forward가 충분히 일치하기 전에는 자동미분 결과를 신뢰하지 않는다.

### 2.3 handle lifetime 명시

`kdm6_step(..., value_only=0, ...)` 호출 시 반환되는 handle은 autograd graph lifetime을 가진다. Fortran 쪽 RAII가 없으므로, handle 소유권과 close 시점을 caller가 명확히 관리해야 한다.

### 2.4 `.item` / graph break 금지

Python/C++ 구현에서 scalar 추출이 필요한 경우 연산그래프 보존 여부를 먼저 판단한다. `.item`에 해당하는 graph break 연산은 derivative path에서는 금지하고, 진단·로그·shape-only 분기처럼 gradient와 무관한 경우에만 `NoGradGuard` 또는 동등한 보호 아래 사용한다.

### 2.5 branch와 limiter의 미분 해석

KDM6에는 활성/비활성 hydrometeor, 온도 임계값, saturation 여부, 수농도 limiter 같은 조건부 연산이 많다. comp-graph AD에서는 실행 시점에 선택된 branch만 graph에 기록된다. 따라서 미분은 전역 smooth Jacobian이 아니라 **현재 trajectory에서 활성화된 piecewise branch의 국소 Jacobian**이다.

운영 해석은 다음 원칙을 따른다.

- `where`/mask 기반 branch는 선택된 branch 안에서만 미분된다.
- threshold에서의 불연속점은 고전적 의미의 미분이 없으므로 parity와 derivative test는 threshold를 정확히 밟는 샘플과 일반 샘플을 분리한다.
- clamp/min/max limiter는 interior에서는 일반 미분, 포화 구간에서는 0 subgradient로 해석한다.
- mass-fixer나 positivity cleanup은 물리 안정성을 우선하며, derivative test에서는 해당 limiter가 활성화되었는지 함께 기록한다.
- branch decision을 위해 scalar를 host로 꺼내는 구현은 graph를 끊으므로 피한다. 필요한 경우 tensor mask로 표현한다.

따라서 KDM6AD의 derivative 산출물은 “KDM6 물리 parameterization의 smooth surrogate 미분”이 아니라, **Fortran KDM6 forward와 같은 branch semantics를 갖는 실행 경로 국소 미분**으로 정의한다.

## 3. Phase 0 — baseline 정리

### 목표

현재 KIM-meso 트리에 이미 들어간 KDM6AD 관련 변경이 실제 빌드 원본 기준으로 일관적인지 확인한다.

### 작업

1. `phys/module_mp_kdm6ad.F`와 generated `phys/module_mp_kdm6ad.f90` 차이를 확인한다.
2. `phys/kdm6_iso_c.F`와 `phys/kdm6_iso_c.f90` 차이를 확인한다.
3. 실제 빌드가 `.F` 원본을 전처리해서 `.f90`를 만드는지, 또는 `.f90`를 직접 쓰는지 확인한다.
4. 수정 기준 파일을 `.F` 원본으로 고정한다.
5. Registry 수정 여부를 확인한다. Registry를 수정하지 않았다면 사용자 지침상 `clean -a`는 생략 가능하다.
6. generated slot constant가 Registry와 일치하는지 확인한다.
   - `Registry/Registry.EM_COMMON`의 `mp_physics==137` entry가 source of truth다.
   - generated `frame/module_state_description.F` 또는 `.f90`에서 `KDM6ADSCHEME`가 실제로 137로 export되는지 확인한다.
   - 단순히 `PARAM_* = 137` 숫자가 존재하는지만 보지 말고, `KDM6ADSCHEME` 이름이 그 parameter에 alias되는지 확인한다.
   - `phys/module_microphysics_driver.F`가 import하는 `KDM6ADSCHEME`와 generated constant가 같은 symbol인지 확인한다.
   - mismatch가 있으면 Registry 재생성/clean build 전에는 `mp_physics=137` smoke를 진행하지 않는다.

### generated constant mismatch 위험

WRF/KIM Registry 계열에서는 `Registry` 파일의 package entry와 실제 Fortran에서 import되는 generated constant 사이에 불일치가 생길 수 있다. 이 경우 문서상 slot 137이 맞아도 dispatcher의 `CASE (KDM6ADSCHEME)`가 기대한 값으로 진입하지 않거나, namelist `mp_physics=137`이 다른 scheme으로 해석될 수 있다.

따라서 Phase 0의 완료 조건은 Registry entry 확인이 아니라 다음 3-way consistency 확인이다.

```text
Registry package mp_physics==137
  == generated module_state_description KDM6ADSCHEME value
  == runtime namelist/config_flags%mp_physics value used by dispatcher
```

이 검증은 build/link보다 앞선 게이트다. generated constant가 틀리면 이후 link, parity, VJP/JVP 검증은 모두 잘못된 scheme을 대상으로 수행될 수 있다.

### 완료 조건

- KDM6AD 관련 원본 파일과 generated 파일의 관계가 명확하다.
- 이후 수정 대상 파일이 확정된다.
- `mp_physics==137`이 `module_state_description`에 정상 반영되는 경로가 확인된다.
- generated `KDM6ADSCHEME` constant가 137이며, `module_microphysics_driver`가 동일 symbol을 import한다.
- `config_flags%mp_physics=137`이 `CASE (KDM6ADSCHEME)`로 진입한다는 smoke/debug 확인 절차가 정의된다.

## 4. Phase 1 — G1 build/link 검증

### 목표

KIM-meso 실행 바이너리가 `libkdm6_c`와 libtorch runtime을 링크하고, 런타임에서 symbol/library lookup 실패 없이 시작되게 한다.

### 작업

1. `kdm6_libtorch` Release 빌드
   - `CMAKE_PREFIX_PATH` 또는 `Torch_DIR`로 libtorch 위치 지정.
   - `ctest --output-on-failure`로 기존 test suite 통과 확인.
2. 설치 산출물 확인
   - `libkdm6_c.{so,dylib}`
   - `libkdm6`
   - `libtorch`, `libtorch_cpu`, `libc10`
3. KIM-meso 링크 플래그 주입
   - include path: `kdm6_iso_c`와 C ABI header를 찾을 수 있어야 한다.
   - library path: `-L<kdm6-install-lib>`
   - libraries: `-lkdm6_c -lkdm6 -ltorch -ltorch_cpu -lc10`
   - runtime path: `-Wl,-rpath,<kdm6-install-lib>` 또는 `LD_LIBRARY_PATH`.
4. KIM-meso 표준 빌드 절차 사용
   - configure 시 `37`, `1` 선택.
   - `nohup compile -j 4 em_b_wave` 사용.
   - 개별 디렉터리에서 임의 `make`는 하지 않는다.
5. 최종 바이너리 확인
   - Linux: `ldd wrf.exe | grep -E 'kdm6|torch|c10'`
   - macOS: `otool -L wrf.exe | grep -E 'kdm6|torch|c10'`
   - unresolved `kdm6_step_c`가 없어야 한다.

### ABI 경계 설계

Fortran과 C++ 사이의 안정 경계는 C ABI 하나로 제한한다.

```text
KIM Fortran
  -> kdm6_iso_c.f90
  -> extern "C" kdm6_step_c
  -> C++ kdm6::kdm6_step
  -> torch autograd graph
```

경계 규칙은 다음과 같다.

- C++ exception은 ABI 밖으로 나가지 않는다. `kdm6_step_c` 내부에서 catch하고 음수 error code로 변환한다.
- Fortran은 C++ object를 직접 보지 않는다. graph lifetime은 opaque `type(c_ptr)` handle로만 다룬다.
- 모든 input/output field buffer는 caller-allocated다.
- `value_only=1`에서도 handle close 규칙은 유지한다. 구현이 non-null value-only handle을 반환할 수 있기 때문이다.
- ABI에 새 field를 추가할 때는 Fortran interface, C header, C++ adapter, tests를 같은 순서로 갱신한다.

### Runtime/link 정책

KIM-meso 실행환경에서는 compile-time link 성공과 runtime load 성공을 분리해서 확인해야 한다.

- compile/link 확인: final link line에 `-lkdm6_c -lkdm6 -ltorch -ltorch_cpu -lc10` 포함.
- runtime 확인: `libkdm6_c`뿐 아니라 libtorch transitive dependency까지 `ldd`/`otool`로 확인.
- HPC module 환경에서는 login node와 compute node의 library path가 다를 수 있으므로, smoke run은 실제 compute 환경에서 수행한다.
- `LD_LIBRARY_PATH`만 의존하면 batch scheduler 환경에서 누락될 수 있으므로, 가능하면 rpath를 우선한다.

### 리스크

- libtorch shared library를 런타임에 찾지 못할 수 있다.
- Fortran/C++ compiler ABI 또는 libstdc++ 버전이 맞지 않을 수 있다.
- libtorch CPU thread pool과 KIM OpenMP/MPI hybrid 실행이 oversubscription을 일으킬 수 있다.

### 완료 조건

- KIM-meso가 KDM6AD 관련 object를 포함해 링크된다.
- 실행 시작 시 shared library 로딩 오류가 없다.
- `mp_physics=137` 설정으로 최소 case가 microphysics driver까지 진입한다.

## 5. Phase 2 — G2 forward wrapper 검증

### 목표

현재 `module_mp_kdm6ad` wrapper가 KIM-meso tile state를 올바른 단위·layout·precision으로 `kdm6_step`에 전달하는지 확인한다.

### 현재 wrapper 구조

1. KIM `REAL` 배열을 tile-local `REAL(c_double)` buffer로 복사한다.
2. `kdm6_step(..., param_grad_flags=0, value_only=1, ...)`를 호출한다.
3. 반환된 output buffer를 KIM prognostic 배열에 되돌린다.
4. handle을 즉시 `kdm6_handle_close`로 닫는다.

### 메모리 layout과 precision 설계

KIM-meso Fortran field는 `(i, k, j)` 형태의 column-major array다. C++/torch 쪽 계산은 column batch 관점에서 `(B, K)`가 자연스럽다.

```text
Fortran tile:  field(ITS:ITE, KTS:KTE, JTS:JTE)
Local buffer:  field_dbl(im, kme, jme)
Column batch:  B = im * jme, vertical dimension K = kme
```

초기 wrapper가 `REAL(c_double)` buffer를 명시적으로 할당해 복사하는 이유는 다음과 같다.

- KIM의 `REAL` kind가 build option에 따라 달라질 수 있다.
- Fortran array section이 non-contiguous일 때 compiler temporary가 생길 수 있다.
- C ABI는 contiguous `double*`를 기대한다.
- forward parity 단계에서는 성능보다 layout/precision 명시성이 더 중요하다.

다만 운영 성능 단계에서는 이 복사가 주요 병목일 수 있으므로 다음 순서로 개선한다.

1. copy 비용을 먼저 측정한다.
2. KIM build의 real kind가 이미 8-byte인지 확인한다.
3. contiguous full tile 전달이 가능한 call site를 찾는다.
4. workspace 재사용으로 allocate/deallocate 비용을 줄인다.
5. 마지막에만 zero-copy를 검토한다.

### State/forcing 분리

수학적으로 `x`와 `a`를 분리했듯, engineering interface도 prognostic state와 forcing/diagnostic을 분리해 관리한다.

- state: `TH, QV, QC, QR, QI, QS, QG, NCCN, NC, NI, NR, BG`
- forcing: `rho, pii, p, delz, dt`
- metadata: `im, kme, jme`, tile index, timestep

Derivative path의 기본 gradient 대상은 state와 selected parameter다. forcing에 대한 gradient가 필요해지면 ABI와 packing 규약을 별도로 확장한다.

### 작업

1. 전달 변수 매핑 검증
   - `TH` → potential temperature
   - `Q/QV` → water vapor
   - `QC, QR, QI, QS, QG` → hydrometeor mixing ratios
   - `NN` → `nccn`
   - `NC, NI, NR` → number concentrations
   - `BG/QIB` → graupel volume mixing ratio
   - `DEN` → KDM6에서 기대하는 density와 동일한지 확인
   - `PII, P, DELZ` → Exner, pressure, layer thickness
2. optional field 요구조건 비교
   - 기존 `KDM6SCHEME`은 `RHOPO3D`, precipitation accumulators, diagnostics를 더 많이 요구한다.
   - `KDM6ADSCHEME`은 prognostic state 중심으로 최소 호출한다.
   - parity 범위는 우선 prognostic state로 제한한다.
3. NaN sentinel 도입 여부 결정
   - 초기 검증 build에서는 `TH`, `Q`, 주요 hydrometeor에 NaN check를 넣는 것이 좋다.
   - 운영 build에서는 성능을 고려해 compile-time guard 또는 debug option으로 제한한다.
4. thread 설정 검토
   - KIM-meso OpenMP/MPI 환경에서는 libtorch 내부 thread를 1로 제한하는 방안을 검토한다.

### 완료 조건

- slot 137 wrapper의 입력·출력 변수 매핑표가 확정된다.
- `DEN/rho` 의미가 slot 37과 같은지 확인하거나 parity issue 후보로 명시된다.
- 최소 실행에서 handle close leak 없이 반복 timestep을 통과한다.

## 6. Phase 3 — G3 forward parity

### 목표

동일 입력에서 기존 Fortran KDM6 slot 37과 KDM6AD slot 137의 prognostic output이 허용오차 안에서 일치하는지 검증한다.

### 검증 단계

#### 6.1 synthetic smoke parity

- 작은 `(im, kme, jme)` tile을 구성한다.
- KDM6AD wrapper가 NaN 없이 실행되는지 확인한다.
- 이 단계는 KIM runtime field capture 전의 wiring 검증이다.

#### 6.2 KIM golden vector capture

- 실제 KIM-meso에서 slot 37 KDM6 호출 직전 state/forcing을 저장한다.
- 같은 call 이후 slot 37 output도 저장한다.
- 저장 대상:
  - `TH`
  - `QV/Q`
  - `QC, QR, QI, QS, QG`
  - `QNC, QNI, QNR`
  - `QNN/NCCN`은 wrapper/ABI provenance용으로 별도 기록한다. 현재 `parity/_schema.py`
    T3 비교에는 포함되지 않는다.
  - `QIB/BG`
  - `rho`, `pi_phy`, `p`, `dz8w`, `dt`
- 가능하면 tile index, timestep, domain metadata도 함께 기록한다.

#### 6.3 parity harness 실행

- `parity/run_parity.py --golden-dir <path>` 형태로 검증한다.
- 우선 current T3 schema의 11개 microphysics-level prognostic state만 비교한다.
- `NCCN/QNN`은 current schema 밖이므로 pass-through/provenance test로 분리하거나 schema를 확장한다.
- precipitation accumulator, diagnostic reflectivity, effective radius 등은 후속 범위로 둔다.

### 허용오차 초안

- `qv/qc/qr/qi/qs/qg`: relative tolerance `1e-10`
- `nc/ni/nr`: relative tolerance `1e-9`
- `nccn/QNN`: current T3 parity schema 밖. wrapper-level pass-through/provenance 또는 schema 확장 후 별도 기준 설정.
- `th`: absolute tolerance `1e-6 K`
- `bg`: relative tolerance `1e-10`, 단 near-zero 영역은 absolute tolerance 병행

### drift 발생 시 우선 점검 순서

1. `rho`가 dry density인지 moist density인지 확인한다.
2. `NN`이 KDM6의 `nccn`과 같은 의미인지 확인한다.
3. `BG/QIB` 단위가 slot 37과 같은지 확인한다.
4. KDM6AD default constants가 Fortran KDM6 constants와 같은지 확인한다.
5. sub-cycling `dtcld`/`numdt` 계산이 slot 37과 같은지 확인한다.
6. cleanup/limiter 순서가 Fortran과 같은지 확인한다.
7. float precision 변환이 drift를 키우는지 확인한다.

### 완료 조건

- 최소 1개 실제 KIM golden vector에서 slot 37과 slot 137 prognostic state parity가 통과한다.
- drift가 있으면 원인이 단위/layout/constants/algorithm 중 어디인지 분류된다.
- parity 결과와 허용오차가 문서화된다.

## 7. Phase 4 — 성능·메모리 프로파일

### 목표

forward parity 이후 운영 실행에서 허용 가능한 비용인지 측정하고, 필요한 최적화만 수행한다.

### 측정 항목

1. slot 37 대비 slot 137 wall-clock overhead.
2. `module_mp_kdm6ad` buffer allocate/copy 비용.
3. libtorch CPU backend thread overhead.
4. MPI rank × OpenMP thread × libtorch thread 조합별 oversubscription.
5. memory leak 여부.

### 공학적 성능 모델

slot 137 한 호출의 비용은 다음처럼 분해해서 본다.

```text
T_total = T_pack + T_bridge + T_torch_forward + T_unpack + T_handle
```

- `T_pack`: KIM field를 `REAL(c_double)` contiguous buffer로 복사하는 비용.
- `T_bridge`: Fortran → C ABI → C++ adapter 호출 비용.
- `T_torch_forward`: 실제 KDM6 tensor 연산 비용.
- `T_unpack`: output buffer를 KIM field로 되돌리는 비용.
- `T_handle`: autograd graph 생성·보존·close 비용. `value_only=1`에서는 최소화되어야 한다.

운영 forecast에서는 `value_only=1`로 `T_handle`을 최소화하고, 4D-Var/sensitivity window에서만 `value_only=0` graph를 만든다. 이 정책이 지켜지지 않으면 일반 예보 실행이 불필요한 autograd graph 비용을 부담한다.

### Threading 정책

KIM-meso가 MPI rank와 OpenMP thread를 이미 사용하므로 libtorch 내부 thread pool은 보수적으로 제한한다.

- 초기 검증: libtorch intra-op thread = 1, inter-op thread = 1.
- 성능 실험: `MPI ranks × OpenMP threads × torch threads`의 곱이 physical cores를 넘지 않게 sweep한다.
- 동일 case에서 bitwise 또는 tolerance-level determinism을 확인한다.
- thread 수 변경이 parity 결과에 영향을 주면 reduction determinism 설정을 검토한다.

### 메모리 정책

`value_only=1` path에서는 graph를 오래 보존하지 않는다. `value_only=0` path에서는 handle이 graph와 saved tensors를 소유하므로 memory budget을 별도로 산정한다.

```text
M_handle ≈ Σ saved_tensor_bytes per active tile/timestep
M_window ≈ M_handle × active_tiles × stored_timesteps
```

4D-Var window 전체 handle 보존은 메모리 폭증 위험이 있으므로, 초기 결합은 replay/checkpoint 방식을 우선 검토한다.

### 최적화 순서

1. libtorch thread 수를 1로 고정한다.
2. tile-local buffer allocation을 재사용 가능한 workspace로 바꿀지 검토한다.
3. array section copy 발생 여부를 compiler report로 확인한다.
4. `REAL(c_double)` 직접 전달 또는 zero-copy 가능성을 검토한다.
5. 필요할 때만 `value_only=0` graph를 만들고, 일반 forecast path는 `value_only=1` 유지한다.

### 완료 조건

- slot 137 overhead가 정량화된다.
- 가장 큰 병목이 copy, allocation, libtorch compute, thread oversubscription 중 어디인지 확인된다.
- 자동미분 경로와 운영 forward 경로의 성능 정책이 분리된다.

## 8. Phase 5 — derivative-ready 경로 설계

### 목표

forward-only `kdm6ad`와 별도로 VJP/JVP를 사용할 수 있는 KIM-side API를 설계한다.

### 권장 API 분리

1. `kdm6ad`
   - 운영 forward용.
   - `value_only=1`.
   - handle 즉시 close.
2. `kdm6ad_with_handle`
   - sensitivity/4D-Var forward용.
   - `value_only=0`.
   - caller에게 handle 반환.
3. `kdm6ad_vjp`
   - adjoint seed를 packed vector로 받아 `kdm6_handle_vjp` 호출.
   - gradient를 KIM state 변수별로 unpack.
4. `kdm6ad_jvp`
   - tangent seed를 packed vector로 받아 `kdm6_handle_jvp` 호출.
   - tangent output을 KIM state 변수별로 unpack.
5. `kdm6ad_close`
   - handle close 책임을 명시적으로 수행.

### packing 규약

VJP/JVP seed와 gradient vector는 다음 순서로 고정한다.

1. `TH`
2. `QV`
3. `QC`
4. `QR`
5. `QI`
6. `QS`
7. `QG`
8. `NCCN/NN`
9. `NC`
10. `NI`
11. `NR`
12. `BG`

각 field는 Fortran tile layout `(im, kme, jme)` 순서를 그대로 사용하고, C++ bridge에서 기존 `from_fortran_arrays`와 동일한 reshape 규약을 적용한다.

Packed vector 길이는 다음과 같다.

```text
n_cell = im × kme × jme
n_state = 12 × n_cell
```

VJP 입력 `u_packed`는 output state `y`에 대한 cotangent다. VJP 출력 `grad_out_packed`은 input state `x`에 대한 cotangent다.

```text
u_packed        ~ ∂L/∂y
grad_out_packed ~ ∂L/∂x = J_x^T · ∂L/∂y
```

JVP 입력 `v_packed`은 input state perturbation이고, JVP 출력 `tangent_out_packed`은 output perturbation이다.

```text
v_packed           ~ δx
tangent_out_packed ~ δy = J_x · δx
```

Parameter gradient가 필요한 경우 state gradient와 같은 buffer에 섞지 않는다. `param_grad_flags`로 활성화된 parameter는 별도 ABI 또는 별도 packed suffix를 설계해 field gradient와 구분한다.

### seed scaling과 물리 단위

VJP/JVP seed는 물리 단위가 섞인 벡터다. `TH`의 1 K perturbation과 `QC`의 `1e-6 kg/kg` perturbation은 같은 수치 크기가 아니다. 따라서 derivative test에서는 다음 원칙을 둔다.

- inner product test는 같은 packing과 같은 scaling을 양쪽에 적용한다.
- finite difference perturbation은 field별 scale floor를 사용한다.
- cost-function 기반 VJP seed는 실제 observation/operator scaling을 반영한 값을 사용한다.
- 단순 unit vector seed test는 field별로 분리해 수행한다.

### handle lifetime 정책

- handle은 한 forward call에만 유효하다.
- 같은 handle을 여러 timestep에서 재사용하지 않는다.
- VJP/JVP 호출이 끝나면 반드시 close한다.
- 실패한 `kdm6_step`의 handle은 신뢰하지 않는다.
- OpenMP thread 간 handle 공유는 금지한다.

### 완료 조건

- derivative API의 Fortran signature가 확정된다.
- seed/gradient packing 순서가 고정된다.
- handle close 책임이 caller별로 명확하다.

## 9. Phase 6 — VJP/JVP 구현 및 검증

### 목표

C++ handle에 보존된 autograd graph를 사용해 KDM6 block의 VJP/JVP를 계산한다.

### 구현 순서

1. `kdm6_libtorch`에서 `kdm6_handle_vjp_c` 구현.
2. 필요 시 `kdm6_handle_jvp_c` 구현.
3. Fortran `kdm6_iso_c` wrapper가 packed vector 크기와 contiguity를 보장하는지 확인.
4. 단일 column test 추가.
5. tile batch test 추가.
6. KIM-side derivative smoke driver 추가.

### C++ autograd 구현 지침

VJP는 PyTorch reverse-mode autograd의 기본 연산이다. handle 내부는 forward output tensor list와 input leaf tensor list를 보존해야 한다.

```text
outputs = F(inputs)
VJP(u) = autograd.grad(outputs, inputs, grad_outputs=u)
```

구현 시 확인할 점은 다음과 같다.

- input state tensor는 gradient 대상이면 leaf tensor여야 한다.
- `from_blob` view 자체는 non-owning이므로, gradient 대상 leaf가 필요하면 clone 후 `requires_grad_(true)`가 필요하다.
- output을 Fortran buffer로 복사하더라도 handle은 원래 torch output tensor를 보존해야 한다.
- `value_only=1` path에서는 `NoGradGuard` 또는 equivalent inference/no-grad mode를 사용해 graph 생성을 피한다.
- `value_only=0` path에서는 graph 생성을 막는 guard를 사용하지 않는다.
- in-place update는 autograd version counter 문제를 만들 수 있으므로, derivative path에서는 out-of-place tensor update를 우선한다.

JVP는 forward-mode가 가능하면 직접 구현하고, 불가능하면 reverse-over-reverse 또는 finite-difference fallback을 검토한다. 단 fallback은 검증용이지 운영 tangent-linear provider로 확정하지 않는다.

### 검증

1. finite-difference directional derivative
   - `Jv ≈ (f(x + eps v) - f(x - eps v)) / (2 eps)`.
2. VJP/JVP identity
   - `<u, Jv> ≈ <J^T u, v>`.
3. energy/mass sanity
   - forward update가 물리적으로 말이 되는 범위인지 확인.
4. graph break audit
   - derivative path에서 `.item` 또는 scalar extraction으로 graph가 끊기지 않는지 확인.

### 완료 조건

- VJP/JVP C ABI가 `KDM6_OK`를 반환한다.
- identity test가 허용오차 안에서 통과한다.
- KIM tile 기준 packed seed/unpack round-trip이 검증된다.

## 10. Phase 7 — 4D-Var/sensitivity 결합

### 목표

KDM6AD를 KIM-meso 4D-Var 또는 sensitivity 계산의 moist physics block derivative provider로 연결한다.

### 결합 전략

- 기존 Tapenade-generated adjoint 전체에 KDM6AD 코드를 직접 섞지 않는다.
- KDM6 microphysics block을 독립 derivative island로 취급한다.
- forward pass에서 derivative가 필요한 timestep/tile만 handle 또는 replay state를 보존한다.
- adjoint pass에서 seed를 packed vector로 만들어 `kdm6ad_vjp`를 호출한다.
- 반환 gradient를 KIM adjoint state 변수에 누적한다.

### 설계 선택지

#### A. handle 보존 방식

- forward pass에서 handle을 저장하고 adjoint pass까지 유지한다.
- 장점: replay 불필요.
- 단점: memory 사용량이 매우 커질 수 있다.

#### B. replay 방식

- forward pass에서 필요한 state만 저장하고, adjoint pass에서 `value_only=0`으로 재실행해 handle을 만든다.
- 장점: memory 절약.
- 단점: replay 비용과 determinism 관리 필요.

초기 구현은 replay 방식을 우선 검토한다. KDM6 microphysics는 column-local이므로 필요한 state snapshot 범위를 제한하기 쉽다.

### checkpoint/replay 공학 기준

4D-Var window에서 모든 timestep/tile handle을 보존하면 autograd saved tensor가 누적된다. 따라서 다음 기준으로 checkpoint 전략을 정한다.

- 짧은 single-column 또는 unit test: handle 보존 방식 허용.
- tile-level smoke: handle 보존과 replay를 모두 비교.
- real 4D-Var window: replay 또는 checkpoint interval 방식 우선.

Replay 방식에서는 forward 재실행이 원래 forward와 같은 branch를 선택해야 한다. 이를 위해 다음 metadata를 함께 저장한다.

- input state/forcing snapshot
- timestep `Δt`와 sub-cycling 관련 값
- tile/domain index
- physics constants/version hash
- build mode와 thread/determinism 설정

branch가 threshold 근처에서 바뀌면 VJP가 원래 trajectory의 adjoint가 아니게 되므로, replay parity를 `value_only=1` forward output과 먼저 비교한 뒤 VJP를 계산한다.

### 4D-Var 결합 수식

KDM6 block 직후 adjoint 변수를 `λ_y = ∂L/∂y`라고 하면 KDM6 block 이전 변수에 더할 gradient는 다음과 같다.

```text
λ_x += J_x^T λ_y
λ_θ += J_θ^T λ_y
```

KIM 전체 adjoint에서 다른 physics/dynamics가 같은 state 변수에 gradient를 누적할 수 있으므로, KDM6AD 반환 gradient는 overwrite가 아니라 accumulation으로 결합한다.

### 완료 조건

- 4D-Var 경로에서 KDM6 block VJP가 호출된다.
- 기존 moist physics adjoint 변수에 gradient가 누적된다.
- tangent/adjoint consistency test가 최소 case에서 통과한다.

## 11. 위험 목록

| 위험 | 영향 | 대응 |
|---|---|---|
| libtorch runtime 로딩 실패 | 실행 시작 실패 | rpath/LD_LIBRARY_PATH/ldd 검증 |
| slot 37/137 forward drift | AD 신뢰 불가 | G3 parity를 G4 전 필수 게이트로 둠 |
| generated `KDM6ADSCHEME` mismatch | namelist 137이 잘못된 CASE로 진입 | Registry ↔ module_state_description ↔ dispatcher 3-way consistency gate |
| `rho` 의미 불일치 | 전체 rate drift | slot 37 입력 캡처로 density 변환 확인 |
| `NN`/`nccn` 의미 불일치 | aerosol/cloud number drift | variable mapping test 추가 |
| handle leak | 장기 실행 memory 증가 | 모든 path에 close 책임 명시 |
| libtorch thread oversubscription | 심각한 성능 저하 | `torch::set_num_threads(1)`, env 고정 |
| `.item`/scalar extraction graph break | gradient 오류 | derivative path graph audit |
| array copy overhead | 운영 성능 저하 | parity 후 workspace/zero-copy 최적화 |
| Tapenade AD와 comp-graph AD 혼선 | 4D-Var 결합 복잡도 증가 | KDM6 block derivative island 유지 |

## 12. 권장 실행 순서

1. `.F`/`.f90` 생성 관계와 현재 KDM6AD 반영 상태 확인.
2. Registry `mp_physics==137`, generated `KDM6ADSCHEME`, dispatcher import의 3-way consistency 확인.
3. `kdm6_libtorch` Release build + test 통과 확인.
4. KIM-meso link/rpath 설정 반영.
5. `mp_physics=137` smoke run.
6. slot 37 golden vector capture.
7. slot 37 vs 137 forward parity.
8. performance profile.
9. derivative-ready API 설계 확정.
10. VJP/JVP C++ 구현.
11. Fortran derivative wrapper 구현.
12. finite-difference 및 VJP/JVP identity 검증.
13. 4D-Var/sensitivity driver 결합.

## 13. 즉시 다음 작업

가장 가까운 다음 작업은 다음 3개다.

1. `phys/module_mp_kdm6ad.F`와 `phys/module_mp_kdm6ad.f90` 동기화 확인.
2. `Registry/Registry.EM_COMMON`의 `mp_physics==137`과 generated `frame/module_state_description.*`의 `KDM6ADSCHEME` 값이 일치하는지 확인.
3. KIM-meso 최종 링크 라인에 `libkdm6_c`, `libkdm6`, libtorch libraries가 실제로 포함되는지 확인.
4. `mp_physics=137` 최소 실행에서 `microphysics_driver: calling kdm6ad` 로그와 shared library loading 성공을 확인.

이 3개가 통과하면 G3 forward parity로 넘어간다.
