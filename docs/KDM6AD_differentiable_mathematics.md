# 미분가능 KDM6AD 미시물리: 수학적 정식화와 자동미분(AD) 공학

**대상**: KDM6AD = KDM6 벌크운적 미시물리 스킴(WRF-KIM `mp_physics=37`, Fortran)의
C++/libtorch 미분가능 이식본(`mp_physics=137`).
**목적**: 작동(operational) 경로에서 Fortran 원본과 **비트 동일**을 유지하면서, 자료동화(DA)
경로에서 **JVP·VJP·HVP**를 제공하는 이중 경로 설계의 수학적 근거와 공학적 구현을 상세 기술한다.

> 표기: 상태벡터 $x\in\mathbb{R}^{N}$ ($N = 12\,\text{fields}\times B\times K$, $B=i_m\,j_m$, $K=k_m$),
> 한 미시물리 스텝 사상 $F:\mathbb{R}^N\to\mathbb{R}^N$, 야코비안 $J=\partial F/\partial x\in\mathbb{R}^{N\times N}$.
> 코드 참조는 `파일:줄`로 표기하며 모두 이 저장소의 실제 위치다.

---

## 0. 초록

KDM6AD의 핵심 설계는 **하나의 연산자 코드가 dtype에 따라 두 개의 다른 수학적 대상**이 된다는 점이다.

- **작동 경로 (float32)**: `torch::NoGradGuard` 아래에서 실행되어 autograd 테이프를 만들지 않고,
  초월함수는 원소별 libm 루프로 계산되어 gfortran 원본과 **비트 동일**하다. 수학적으로는 부동소수점
  반올림 계단(piecewise-constant staircase)으로서 조각적으로 상수이며 미분 불가능하다.
- **자료동화 경로 (float64)**: 모든 상태장을 `requires_grad=true` 리프로 만들어 autograd 그래프를
  구성한다. 수학적으로는 스위칭 곡면(온도 게이트, 임계값, 클램프)으로 분할된 각 셀 내부에서 $C^\infty$이고,
  경계에서만 Lipschitz(꺾임) 또는 불연속인 **조각적 매끄러운 사상**이다. 이 매끄러운 대상 위에서 JVP/VJP/HVP가 정의된다.

두 경로의 분기는 데이터 의존적 `.item()` 조건이 아니라 **`scalar_type()` 구조적 검사**로 이루어지므로
autograd 그래프를 절단하지 않는다 (dtype 분기 코드 예: `coordinator.cpp:1991`·`:2022`, `warm.cpp:293`).

> **"비트 동일"의 범위와 근거.** 여기서 비트 동일은 **작동(f32) 경로가 Fortran `mp37`과 넷플로 산출물
> 수준에서 비트 일치**함을 지향한다는 뜻이며, 원소별 libm이 gfortran 수학 라이브러리와 일치한다는
> 메커니즘(§7.1)과 uint32 비트 동등 비교 하네스(`harness/strict_bitwise_nc.py`)로 뒷받침된다. 특정
> 적분 길이·병렬수에서의 통과 여부(단·중거리, np1/MPI)는 캠페인 진행에 따라 갱신되는 사안이므로 최신
> 상태는 이 저장소의 로그(`wiki/log.md`)·정합성 개념 페이지를 참조하라 — 본 문서는 특정 통과 수치를
> 단정하지 않는다. 요점은 이 **작동 경로 정합성 검증**이 아래 §9의 자동미분 테스트(수반 항등식·FD
> 게이트)와 **별개**라는 것이다: §9는 f32 통과와 무관하게 **DA(f64) 경로의 미분 정확성**을 검증한다.

---

## 1. 이중 경로 설계 (op-f32 / DA-f64)

### 1.1 dtype이 곧 스위치

포트 전반의 관용구는 다음과 같다 (예: 강수 증발 계수 `coeres`, `warm.cpp:293-306`):

```cpp
auto rr_prod = rslope_r * rslopeb_r;
auto sqrt_arg = (qr.scalar_type() == torch::kFloat32)
    ? rr_prod                                     // op: Fortran F:1924의 raw sqrt (비트 동일)
    : torch::clamp(rr_prod, /*min=*/constants::QCRMIN);  // DA: 유한 수반을 위한 클램프
auto coeres = rslope2_r * torch::sqrt(sqrt_arg) * rslopemu_r;
```

`QCRMIN` 바닥값을 무조건 적용하면 미소강수 셀에서 `coeres`가 약 6자리수 팽창하여 f32 비트 일치를 깨뜨린다
(§53u). 그래서 f32에서는 원시(raw) 형태를 유지하고, f64에서만 클램프하여 수반(adjoint)을 유한하게 만든다.
분기는 `scalar_type()` — **구조적 검사이지 `.item()`이 아니므로** autograd 그래프가 끊기지 않는다.

### 1.2 작동 경로는 테이프를 만들지 않는다

```cpp
// runtime.cpp:711-736
if (value_only) {
    torch::NoGradGuard no_grad;            // 테이프 없음
    auto fn_out = kdm6_fn(...);
    return StepResult{..., /*handle=*/nullptr, ...};
}
auto fn_out = kdm6_fn(...);               // 테이프 라이브
auto handle = std::make_unique<Handle>(state, fn_out.state_out, forcing, params, dt, false);
```

`value_only=true`(작동 WRF 호출)는 전체 forward를 `NoGradGuard`로 감싸 autograd 오버헤드를 0으로 만든다.
`value_only=false`(DA 호출)는 테이프를 살린 채 forward를 실행하고, 그래프의 두 끝점(입력 리프·출력)을
`Handle`에 담아 나중의 VJP/JVP에 쓴다.

---

## 2. 수학적 정식화: 미시물리 스텝을 합성 사상으로

### 2.1 상태 공간과 스텝 사상

한 물리 스텝은 12개 예단장(prognostic field)을 갱신한다:

$$x = (\theta,\ q_v,\ q_c,\ q_r,\ q_i,\ q_s,\ q_g,\ n_{ccn},\ n_c,\ n_i,\ n_r,\ b_g)^\top .$$

(질량혼합비 $q_\bullet$, 수농도 $n_\bullet$, CCN 저장소 $n_{ccn}$, 우박 부피 $b_g$, 온위 $\theta$.)
스텝 $F$는 시간 $\Delta t$를 $L=\max(\lceil \Delta t/\Delta t_{cr}\rceil,1)$ 개의 소사이클(sub-cycle)로 나눈다
($\Delta t_{cr}=120\,\mathrm{s}$, `runtime.cpp:391`):

$$F = G_{\Delta t_{cld}}\circ G_{\Delta t_{cld}}\circ\cdots\circ G_{\Delta t_{cld}}\qquad(L\ \text{회}),\quad \Delta t_{cld}=\Delta t/L .$$

각 소사이클 사상 $G$는 다시 **침강 → 재기울기 → 미시물리 1패스**로 합성된다 (`runtime.py:529-556`):

$$G = \underbrace{K}_{\text{kdm62d\_one\_step}}\circ\ \underbrace{R}_{\text{rebuild aux / re-slope}}\circ\ \underbrace{S}_{\text{sedimentation}} .$$

`cur` 상태는 소사이클 사이에서 **detach 없이** 이어지므로, 입력 리프에서 출력까지 하나의 연속 그래프가 된다
(`runtime.cpp:480-527`). 소사이클 정수 반복수 `mstep`만 `NoGradGuard` 블록에서 계산된다 (§8.6).

### 2.2 침강 연산자 $S$

$S$는 $\{q_r,n_r,q_s,q_g,q_i,n_i,b_g\}$만 변환하고 $\{q_v,q_c,n_c,n_{ccn},\theta\}$는 손대지 않는다
(`coordinator.py:2260-2400`). 비매끄러운 점: (1) CFL 기반 정수 소스텝수 `mstep`은 조각적 상수 게이트이며
`no_grad`에서 계산됨, (2) PLM 고갈 클램프가 $\partial/\partial q$를 0으로 만듦, (3) 소스텝별 $b_g$ 리셋 where-게이트.

### 2.3 미시물리 1패스 $K$의 연산자 합성

`kdm62d_one_step` 내부는 19개의 순서화된 부연산자의 좌→우 합성이다. **아래 순서는 실제 이식본인 C++
`coordinator.cpp:642-1291`을 기준**으로 한다(Python 오라클 `coordinator.py:1909-2195`은 한 곳이 다르다 —
아래 표의 $L_9$ 각주 참조):

$$
K = \underbrace{L_{19}}_{\text{DSD 수 제한}}\circ L_{18}^{\text{cleanup}}\circ \underbrace{L_{17}}_{\text{satadj}}\circ L_{16}\circ L_{15}^{\text{Picons}}\circ \underbrace{L_{14}}_{b_g\text{-reclamp}}\circ \underbrace{L_{13}}_{\text{state\_update}}\circ \underbrace{L_{12}}_{\text{conservation}}\circ \cdots \circ \underbrace{L_1}_{\text{preamble}} .
$$

| # | 연산자 | 변환 대상 변수 | 성격 |
|---|--------|----------------|------|
| 1 | preamble (thermo·DSD·ProgB·slope) | (없음, 진단) | DSD/기울기 진단, 클램프 꺾임 |
| 2 | $b_g$-reclamp #1 | $b_g$ | rhox∈[100,900] 클램프 |
| 3 | D1 융해 | $q_r,q_s,q_g,q_i,q_c,n_r,n_c,n_i,b_g,\theta$ | warm-게이트 Heaviside(T=t0c) |
| 4 | 균질동결 (supcol>40) | $q_c,q_i,n_c,n_i,\theta$ | 이중 Heaviside 곱 마스크 |
| 5 | rebuild_aux #1 + λ-스냅 | $n_c,n_i,n_r$ | λ 경계 꺾임 |
| 6 | D2–D4 동결 (접촉·Bigg) | $q_c,q_i,n_c,n_i,q_r,q_g,n_r,b_g,\theta$ | supcol>0 게이트, cap min |
| 7 | rebuild_aux #2 + λ-스냅 | $n_c,n_r,n_i$ | λ 경계 꺾임 |
| 8 | warm_phase | (진단, 8 rates) | supcol/supsat 게이트 |
| 9† | 완전강수증발 $n_r\!\to\!n_{ccn}$ | $n_{ccn},n_r$ | where-마스크 |
| 10 | cold_phase | (진단, 34 rates) | 게이트·cap min |
| 11 | D5 강화융해 | (진단, 4 rates) | — |
| 12 | scale_rates_for_conservation | (rate 재척도) | 14 예산의 max() 꺾임 |
| 13 | **state_update** | 전 예단장 | 수상 8 + $b_g$ 비음 클램프(qv·nccn·θ 비클램프) + 마스크 |
| 14 | $b_g$-reclamp #4 | $b_g$ | rhox 클램프 |
| 15 | Picons: 큰 얼음→눈 | $q_s,q_i,n_i$ | avedia≥200μm 임계 |
| 16 | 작은 비→구름 | $q_c,q_r,n_c,n_r$ | avedia≤82μm 임계 |
| 17 | **satadj** (활성화+포화조정) | $q_v,q_c,\theta,n_c,n_{ccn}$ | $\text{pow}(\cdot)^{<1}$ 무한 기울기, 등식 게이트 |
| 18 | threshold cleanup | $q_c,n_c,q_r,n_r,q_s,q_g,q_i,n_i$ | 경성 임계(불연속 점프) |
| 19 | DSD 수 제한 | $n_r,n_c,n_i$ | λ-스냅 + NRMAX/NCMAX cap |

연산자 8·10·11(warm/cold/D5)은 **진단적**이다 — rate 텐서를 방출할 뿐 예단장을 직접 갱신하지 않으며,
그 야코비안은 연산자 12·13이 rate를 소비할 때만 $J_K$에 들어간다.

> **† $L_9$의 배치 차이 (C++ vs Python).** 완전강수증발 전이($n_r\!\to\!n_{ccn}$, 이후 모든 $n_r$ 소비자가
> 0을 보게 함)는 **C++ 이식본에서는 warm과 cold 사이**(`coordinator.cpp:1063-1074`)에서 `working.nr`를 0으로
> 만들어, cold의 $n_r$ 게이트(niacr/nraci/nsacr/ngacr)와 이후 보존·state_update가 모두 0을 본다. Python
> 오라클은 이를 **cold·state_update 이후**(`coordinator.py:2108`, `:2165`)에 적용하므로 cold 게이트가 보는
> $n_r$가 다르다 — **두 배치는 일반적으로 동일한 최종 상태를 주지 않는다**. 본 문서의 표·부록 B는 실제
> 이식본이자 Fortran 원본과 비트-일치하는 **C++ 순서를 권위 기준**으로 삼는다(Python 오라클은 참조 구현이며
> 아래 부록 B 서두의 다른 알려진 불일치들과 함께 이 지점에서 갈린다).

### 2.4 조각적 매끄러움

합성 사상 $F$는 다음 스위칭 곡면들로 유도된 분할의 각 셀 **내부에서 $C^\infty$**이고, 경계에서만
Lipschitz(꺾임) 혹은 불연속이다 (`coordinator.py` 전역 취합):

- **(A) 온도 Heaviside**: $\text{warm}=(supcol<0)$, $\text{cold}=(supcol\ge0)$, $supcol=t_{0c}-t$ (T=273.15K); 균질동결 $supcol>40$.
- **(B) 라우팅 임계**: $\delta_2=(q_r<10^{-4}\wedge q_s<10^{-4})$, $\delta_3=(q_r<10^{-4})$.
- **(C) 재분류 임계**: avedia$_i\ge200\mu m$, avedia$_r\le82\mu m$.
- **(D) 비음 ReLU 클램프**: $\text{clamp}(\cdot,\min=0)$ (state_update의 수상 8필드 $q_c,q_r,q_s,q_g,q_i,n_c,n_r,n_i$ + $b_g$; $q_v$·$n_{ccn}$·$\theta$는 여기서 클램프 안 함).
- **(E) λ-스냅 꺾임**: LAMDA$_{\{C,I,R\}\{MIN,MAX\}}$.
- **(F) 보존 limiter**: $\max(\text{source},\text{value})$ 꺾임.
- **(G) satadj**: $\text{pow}(\cdot)^{ACTK<1}$ + min + 등식 게이트.
- **(H) cleanup**: 경성 임계 마스크로 부임계 수상을 0으로 만드는 **점프(불연속)** 연산자.

**연속 vs 불연속의 판별 기준(원리).** 각 스위치는 $y=\text{where}(\text{cond},\,A,\,B)$ 형태다. 이 사상은
스위칭 곡면 $\{\text{cond 경계}\}$ 위에서 **$A=B$이면 연속(기껏해야 꺾임/Lipschitz)**, **$A\neq B$이면 불연속(점프)**이다.
따라서 어떤 연산자가 점프인지는 "전이량이 경계에서 0으로 사라지느냐"로 결정된다.

- **연속·꺾임(Lipschitz)형**: $D$(ReLU 클램프 $\text{clamp}(\cdot,0)$ — 경계에서 값 연속, 기울기만 꺾임),
  $E$(λ-스냅 — 스냅 경계에서 $n$ 값 연속), $F$(보존 limiter의 $\max(\text{source},\text{value})$ — 경계에서 factor 연속),
  그리고 전이 rate가 게이트 경계에서 $\to0$으로 사라지는 rate-형(대부분의 warm/cold 항). 이런 곳에서 곱셈
  where-마스크는 한쪽 편도함수(Clarke 부분기울기의 한 원소)를 유효하게 준다.
- **점프(불연속)형**: 경계에서 **유한량**을 옮기는 마스크-곱들 — $A$의 균질동결($supcol>40$에서 유한 $q_c\!\to\!q_i$),
  $C$의 재분류($L_{15}/L_{16}$, avedia 임계에서 유한 질량을 종끼리 이동), $H$의 cleanup(부임계 수상을 0으로 버림),
  그리고 **등식/임계 게이트로 유한 전이를 켜는** 항들 — $L_9$ 완전강수증발($n_r\!\to\!n_{ccn}$, `coordinator.cpp:1071`),
  satadj의 완전증발 전이(`satadj.cpp:73`, `coordinator.cpp:2229`), D1의 순간융해(`melt_freeze.cpp:147`),
  임계에서 0→유한으로 뛰는 warm 자동전환(`warm.cpp:63`) 등이 포함된다. **즉 점프 집합은 위 §목록의
  $\{A,C,H\}$보다 넓으며, 위 판별식(경계에서 $A\neq B$)으로 정해진다** — 이 목록은 대표 예시이지 완전열거가 아니다.

점프 지점에서는 도함수(따라서 부분기울기)가 **존재하지 않는다**. autograd는 그 지점에서 **활성 분기 내부의
조각별 편도함수(한쪽 극한)**를 반환할 뿐, 점프를 관통하는 수학적 subgradient를 만들지 않는다. 실무적으로 이
점프 집합은 스위칭 곡면(측도 0)에 국한되므로 거의 모든 점에서 기울기가 well-defined이고 4D-Var 최소화는 이
조각별-매끄러운 구조 위에서 동작한다. 설계 불변식으로 **모든 분기는 `torch.where` + 곱셈 마스크로만
이루어지며 `.item()`도 in-place 연산도 없어**(dtype 구조 분기 예 `coordinator.cpp:1991`·`:2022` 제외),
autograd가 각 셀 내부의 편도함수를 일관되게 관통시킨다.

### 2.5 연쇄율(야코비안) 구조

합성의 야코비안은 역순 곱이다. 소사이클 $L$개, 각 소사이클이 $K\circ R\circ S$이고 $K$가 19개 부연산자이므로,

$$
J = \prod_{\ell=L}^{1} J_{G}^{(\ell)},\qquad
J_G = J_K\,J_R\,J_S,\qquad
J_K = J_{L_{19}} J_{L_{18}}\cdots J_{L_1}.
$$

각 인자는 해당 셀에서의 국소 야코비안이다. VJP는 이 곱을 **오른쪽에서 왼쪽으로 벡터에 곱하고**(reverse-mode),
JVP는 **왼쪽에서 오른쪽으로** 곱한다(forward-mode). autograd는 이 곱을 자동으로 누적한다.

---

## 3. 연산그래프

### 3.1 리프 생성

**작동(f32) 경로**의 리프 생성 진입점은 `from_fortran_arrays`(`state.h:71-74`, 구현 `state.cpp:59-91`)로,
Fortran `float*` 버퍼를 12-필드 State로 바꾼다. (DA(f64) 경로는 별도로 `double*` 패킹 버퍼를
`unpack_packed_state`로 풀고(`kdm6_c_api.cpp:330`) 12개 상태장에 `requires_grad_(true)`를 호출한다(`:334`, 부록 A.2).)
아래는 f32 어댑터의 핵심:

```cpp
// from_blob_3d: 비소유 뷰 → (선택적 NaN 게이트/클립) → 리프
auto view3d = torch::from_blob(const_cast<float*>(ptr), {jme,kme,im}, opts)
                  .permute({2,1,0}).contiguous();          // (i,k,j) 열우선
auto flat = view3d.permute({0,2,1}).reshape({im*jme, kme}); // (B, K)
if (nan_gate) flat = torch::where(torch::isfinite(flat), flat, torch::zeros_like(flat)); // [D10]
if (clip_neg && !is_th) flat = torch::clamp(flat, /*min=*/0.0);                          // [D11]
if (requires_grad) flat = flat.detach().clone().requires_grad_(true);  // [D9] 미분가능 리프
else               flat = flat.clone();                                // 소유 복사(그래프 외부)
```

`detach().clone().requires_grad_(true)`가 **새 미분가능 리프**를 만든다 — 이것이 4D-Var의 제어변수
정의 방식이다. 강제장(rho, pii, p, delz) 4개는 항상 `requires_grad=false`로 들어간다(접선/수반 모델의 상수, `state.cpp:113-130`).

### 3.2 소사이클 스레딩과 그래프 연속성

```cpp
// runtime.cpp:391-529 (요지)
auto cur = cs;
for (int i = 0; i < loops; ++i) {
    // 1. 침강(정수 mstep은 NoGradGuard, 연속 flux는 on-graph)
    // 2. rslopec = diag_cloud_slope(...); aux = build_default_aux(cur, ...)
    // 3. cur = kdm62d_one_step(cur, cf, aux, ...);   // detach 없음
}
```

소사이클 사이에 detach가 없으므로 입력 리프 → 출력까지 **하나의 연속 autograd 그래프**가 형성된다.
소사이클 사이의 `.to(dtype)` 캐스트(`runtime.cpp:497-503`)는 f32 작동 경로에서만 반올림 계단이고,
f64 DA 경로에서는 `sdt==Double`이라 항등(no-op)이므로 테이프를 건드리지 않는다.

### 3.3 그래프를 붙잡는 핸들

```cpp
// runtime.cpp:540-559
struct Handle::Impl {
    State state_in;    // requires_grad=true 리프 (그래프 입력)
    State state_out;   // grad_fn 체인이 state_in까지 이어짐 (그래프 출력)
    Forcing forcing; Parameters params; double dt;
    bool value_only; bool closed = false;
};
```

그래프는 순전히 `state_in` 리프와 `state_out` 텐서를 `Handle::Impl` 안에 **살려둠으로써** 유지된다.
`kdm6_handle_t`(C 래퍼)가 살아있는 한 그래프는 해제되지 않아 이후 `torch::autograd::grad`가 순회할 수 있다.

> **그래프 리프 = 12개 상태장 (현재).** 오늘의 DA ABI는 12개 상태장만 미분가능 리프로 만든다. 물리 상수
> (PEAUT/NCRK1/… )는 학습 가능 리프로 승격할 수 있는 배관(`make_parameters`, `runtime.cpp:13-30`)이 있으나,
> C ABI가 `make_parameters(0)`(`kdm6_c_api.cpp:338`)로 호출하고 `kdm6_fn`이 상수로 굳혀 쓰므로
> (`runtime.cpp:314-316` 주석) **현재 파라미터는 학습되지 않는다** — 즉 야코비안은 상태→상태만이다.

---

## 4. 역방향 모드 (VJP / 수반)

### 4.1 정의와 증명

**정의.** 코탄젠트(seed) $u\in\mathbb{R}^N$에 대한 VJP는 $J^\top u$이다.

**보조정리 (VJP = grad of inner product).** 스칼라 $s(x)=\langle F(x),u\rangle$를 정의하면 $\nabla_x s = J^\top u$.

*증명.* $s(x)=\sum_k F_k(x)\,u_k$이므로
$\dfrac{\partial s}{\partial x_j}=\sum_k u_k\,\dfrac{\partial F_k}{\partial x_j}=\sum_k J_{kj}u_k=(J^\top u)_j$. $\square$

즉 seed $u$를 **grad_outputs로 주입하는 대신** 스칼라 $\langle F(x),u\rangle$에 접어 넣고 그 스칼라를
입력에 대해 역전파하면 정확히 $J^\top u$가 나온다. 이것이 구현의 핵심이다.

### 4.2 구현

```cpp
// runtime.cpp:611-637  Handle::vjp
State Handle::vjp(const State& u, const GraphOptions& opts) const {
    validate_state_shapes(u, impl_->state_out, "u", "state_out");  // 브로드캐스트 방지
    auto scalar = state_dot(impl_->state_out, u);                  // s = <F(x), u>
    std::vector<torch::Tensor> inputs;
    for (auto* p : impl_->state_in.fields()) inputs.push_back(*p);
    auto grads = torch::autograd::grad(
        {scalar}, inputs, /*grad_outputs=*/{},
        /*retain_graph=*/opts.retain_graph || opts.create_graph,
        /*create_graph=*/opts.create_graph, /*allow_unused=*/true);
    // 의존하지 않는 입력 리프 → J의 영(0) 열 = (J^T u)의 영 성분
    *out_ptrs[i] = grads[i].defined() ? grads[i] : torch::zeros_like(inputs[i]);
    return apply_active_mask(std::move(out), opts.active_field_mask);   // P∘J^T
}
```

여기서 `state_dot`는 12개 필드 전체의 유클리드 내적이다 (`state.cpp:18-26`):

$$\langle a,b\rangle=\sum_{f=1}^{12}\sum_{B,K} a_f\,b_f .$$

`grad_outputs={}`는 스칼라에 암묵적 $1.0$을 주는 것이고, 실제 seed는 $s=\langle F(x),u\rangle$에 이미 들어 있다.
$F$가 입력 $x_j$에 의존하지 않으면 $J$의 열 $j$가 0($\partial F/\partial x_j=0$)이고, 따라서 $(J^\top u)_j=0$이다.
`allow_unused=true` + `zeros_like` 물질화는 이런 미연결 리프에 대해 **$J^\top u$의 정확한 영 성분**(등가로 $J$의 영 열)을 준다.
`active_field_mask`는 대각 사영 $P$를 곱해 $P\,J^\top u$를 만든다(제어 부공간 의미론).

> **형상 검증** (`runtime.cpp:586-597`): `state_dot`이 조용히 브로드캐스트하므로, $(2,1)$ vs $(1,2)$ 같은
> 불일치는 그럴듯하지만 틀린 수반을 만들고 일회성 그래프를 소모한다. autograd 호출 전에 각 $u$ 필드 형상이
> `state_out`과 정확히 같은지 `TORCH_CHECK`한다(적대검토 F1-SHAPE 대응).

### 4.3 C ABI (수반의 Fortran 노출)

```cpp
// kdm6_c_api.cpp:375-401
extern "C" int kdm6_handle_vjp_c(kdm6_handle_t* h,
    const double* u_packed, double* grad_out_packed) {
    ...
    auto u = unpack_packed_state(u_packed, h->im, h->kme, h->jme, h->dtype);
    kdm6::GraphOptions opts; opts.retain_graph = true;   // 한 스텝에 여러 관측 수반 적용 가능
    auto grad = h->impl->vjp(u, opts);
    pack_packed_state(grad, grad_out_packed, h->im, h->kme, h->jme);
    return KDM6_OK;
}
```

코탄젠트는 `const double* u_packed`로 들어오고 입력 기울기는 `double* grad_out_packed`로 반환된다.
두 버퍼 모두 $12\,i_m k_m j_m$ 개의 double, 필드우선·Fortran 열우선 배치다. `retain_graph=true`이므로
같은 핸들에 여러 관측 수반을 반복 적용할 수 있다(DA 구동기가 4D-Var에서 여러 관측 연산자 수반을 적용).

---

## 5. 순방향 모드 (JVP) — Pearlmutter 이중-VJP

### 5.1 왜 forward-mode를 직접 못 쓰는가

`torch.func`의 순방향 AD(이중수/dual number)는 **사용 불가**하다 — 커스텀 autograd Function(§7)들이
**forward-mode 규칙을 갖지 않기** 때문이다 (`runtime.cpp:640-646` 주석). 대신 JVP를 두 번의 역방향 패스로 합성한다.

### 5.2 Pearlmutter 구성과 증명

**정리 (Pearlmutter 이중-VJP).** 더미 코탄젠트 $u$에 대해 $w(u)=J^\top u$는 $u$에 대해 **선형**이다. 그러면

$$\langle w(u),v\rangle = \langle J^\top u, v\rangle = u^\top J v,\qquad
\nabla_u\big(u^\top J v\big) = J v .$$

$w$가 $u$에 선형이므로 이 그래디언트는 $u$의 값과 무관하다 — 따라서 **$u=0$** 시드로 계산해도 정확하다.

*증명.* $w(u)=J^\top u$이므로 $\langle w(u),v\rangle=(J^\top u)^\top v=u^\top(Jv)$. 이는 $u$에 관한 선형형식이므로
$\nabla_u[u^\top(Jv)]=Jv$ (상수, $u$ 무관). $\square$

구현 (`runtime.cpp:639-708`, Python 오라클 `runtime.py:238-293`과 메커니즘 동일):

```cpp
// u = 0값 requires_grad 리프 (그래프는 u에 선형이므로 값 무관)
scalar = state_dot(impl_->state_out, u_state);
auto w = torch::autograd::grad({scalar}, inputs, {},
         /*retain_graph=*/true, /*create_graph=*/true, /*allow_unused=*/true); // w = J^T u (u에 대해 미분가능 유지)
torch::Tensor inner = Σ_i (w[i] * v_eff[i]).sum();                              // <w, v>
auto tangents = torch::autograd::grad({inner}, u_leaves, {},
         /*retain_graph=*/false, /*create_graph=*/false, /*allow_unused=*/true); // Jv = d<w,v>/du
```

첫 grad는 `create_graph=true`로 $w$를 $u$에 대해 미분가능하게 유지하고, 둘째 grad가 $\langle w,v\rangle$를
$u$ 리프에 대해 미분해 $Jv$를 얻는다. 비용은 역방향 2패스, fp 정밀도까지 정확하다. `active_field_mask`는
**입력 방향** $v$를 사영해 $J\,Pv$를 만든다(§5.3).

### 5.3 수반 항등식 (정확 증명, FD 아님)

가장 강한 정확성 진술은 **수반 항등식**이다:

$$\boxed{\ \langle Jv,\,u\rangle = \langle v,\,J^\top u\rangle\ }\qquad(\text{양변 모두 reverse-mode}).$$

*증명.* $\langle Jv,u\rangle=(Jv)^\top u=v^\top J^\top u=\langle v,J^\top u\rangle$. $\square$

이는 `test_handle_vjp.cpp:113-129`(C++)과 `test_handle_vjp_jvp.py:204-218`(Python)에서
**상대오차 $<10^{-12}$**로 검증된다 — 이중-VJP JVP가 VJP 수반의 정확한 전치임을 증명한다. 두 변 모두
역방향이므로 FD에 구속되지 않고, 비매끄러운 방향(24성분 전체)까지 포함한다.

**마스크 수반 항등식.** 사영 $P$가 대각($P=P^\top=P^2$)이므로 입력-마스크 JVP와 출력-마스크 VJP는 정확히 수반 쌍이다:

$$\langle J\,Pv,\,u\rangle=\langle v,\,P\,J^\top u\rangle\qquad(\text{rel}<10^{-12},\ \texttt{test\_handle\_vjp.cpp:132-152}).$$

(적대검토 F1-MASK-ADJOINT-ASYM: 출력공간 JVP 마스크가 rel~$10^{-9}$에서 수반성을 깨뜨렸던 것을 정확 쌍으로 수정.)

---

## 6. 헤시안-벡터 곱 (HVP) — 이중 역전파

### 6.1 grad-of-grad 원리

전용 `hvp()`/`hessian()` 함수는 존재하지 않는다. HVP는 JVP를 구동하는 **동일한 이중-역전파 원시연산**으로
제공된다. 스칼라 손실 $L(x)=\phi(F(x))$에 대해 $g(x)=\nabla_x L$이고,

$$\nabla_x\big(g(x)^\top v\big)=\nabla^2_x L(x)\,v=(\text{HVP}).$$

`GraphOptions.create_graph` 플래그(`runtime.h:84`, "true → grad-of-grad (double-VJP)")가 노출된 스위치다:

```cpp
// runtime.cpp:611-637 (create_graph=true 경로)
auto grads = torch::autograd::grad({scalar}, inputs, {},
    /*retain_graph=*/opts.retain_graph || opts.create_graph,
    /*create_graph=*/opts.create_graph,   // true → 반환된 grad 자체가 미분가능(그래프의 노드)
    /*allow_unused=*/true);
```

`vjp(create_graph=true)`가 반환한 $g=J^\top u$는 그 자체로 그래프의 노드이므로, $g$로 만든 스칼라를 다시
`torch::autograd::grad`하면 grad-of-grad(스칼라 손실의 헤시안-벡터 곱)가 나온다.

### 6.2 이중-역전파 미분가능성 요건 (Pearlmutter의 숨은 전제)

HVP와 JVP가 성립하려면 **경로상의 모든 커스텀 autograd Function의 backward가 그 자체로 미분가능**해야
한다 (`once_differentiable` 금지). 이것을 grad-of-grad로 실증한다 (`test_handle_vjp_jvp.py:155-178`,
`test_handle_vjp.cpp:155-179`):

```python
y = _rgmma_tensor(x32)
(g,)  = torch.autograd.grad(y.sum(), x32, create_graph=True)  # 1차 도함수, 그래프 연결
(gg,) = torch.autograd.grad(g.sum(), x32)                      # 2차 도함수 (grad-of-grad)
assert torch.isfinite(gg).all() and (gg != 0).any()           # 유한·비영
# 전체 fp64: probe = |J^T u|^2 를 다시 미분
g1    = handle.vjp(u, create_graph=True)
probe = sum((f*f).sum() for f in g1)
g2    = torch.autograd.grad(probe, tuple(state), allow_unused=True, materialize_grads=True)
```

이는 헤시안-벡터형 이중 역전파이며, 2차 도함수가 유한·비영일 것을 요구한다. 검증 대상 커스텀 Function은
`RgmmaT`/`LibmLog`/`LibmExp`/`LibmPowTensor` — 각 backward가 미분가능한 torch 연산만 쓴다(§7).

---

## 7. 커스텀 autograd Function (libm 계열)

### 7.1 왜 커스텀인가

두 가지 이유가 결합한다 (`ops.cpp:12-14, 57-59`):

1. **비트 일치**: IEEE-754는 $\exp/\log/\text{pow}$의 올림정확(correctly-rounded)을 요구하지 않는다.
   Apple `libSystem_m` $=$ `libgfortran` 수학 라이브러리라서 f32 원소별 `std::exp/log/pow`는 gfortran과
   비트 동일이지만, torch의 벡터화 Sleef는 마지막 비트가 다르다. → f32는 원소별 libm 루프.
2. **그래프 보존**: 원시 libm 루프(`data_ptr`로 `empty_like`에 기록)는 autograd에 불투명하여 그래프를 끊는다.
   커스텀 Function이 **해석적 backward를 재부착**한다. 단, DA 경로에서만 쓴다 — 작동 경로는 `InferenceMode`
   가정 하에 `Function::apply`가 SIGSEGV를 내므로 토글이 이를 배제한다.

### 7.2 다섯 개 Function의 전미분/역미분 공식

`ops.cpp:60-127`. forward 값은 (f32) libm / (f64) torch native; backward(VJP)는 항상 해석적 torch native.

| Function | forward $f(x)$ | backward (VJP), $g_o$=grad_output |
|----------|----------------|-----------------------------------|
| `LibmExp` | $e^{x}$ | $g_o\cdot e^{x}$ |
| `LibmLog` | $\ln x$ | $g_o / x$ |
| `LibmPowScalar` | $x^{p}$ (상수 $p$) | $g_o\cdot p\,x^{p-1}$ (그리고 $p$ 슬롯은 빈 텐서) |
| `LibmPowTensor` | $x^{y}$ | $\big(g_o\,y\,x^{y-1},\ \ g_o\,x^{y}\ln x\big)$ |
| `RgmmaT` | $\Gamma(x)=e^{\text{gammln}(x)}$ | $g_o\cdot\Gamma(x)\,\psi(x)$, $\psi=$digamma |

`RgmmaT`는 backward에서 재계산을 피하려고 입력 $x$와 **출력 $\Gamma(x)$를 함께 저장**한다. 그 결과 backward의
$\Gamma(x)$ 인자는 forward 값과 비트 동일이다. `LibmPowTensor`는 $f=x^y$의 두 편도함수를 모두 반환한다:
$\partial f/\partial x=y\,x^{y-1}$, $\partial f/\partial y=x^{y}\ln x$.

f32 감마 전미분은 Numerical-Recipes Lanczos $\ln\Gamma$(6계수, 내부 double, f32 반환; `fconst.h:24-38`,
gfortran GAMMLN 대응)이고, backward는 `torch::digamma`(Lanczos 급수의 미분이 아님)를 쓴다.

### 7.3 토글: op(libm) vs DA(커스텀 Function)

```cpp
// ops.cpp:128-134
inline bool use_custom_autograd(const torch::Tensor& x) {
    return at::GradMode::is_enabled() && !c10::InferenceMode::is_enabled() && x.requires_grad();
}
```

3중 AND: (1) grad 추적 on, (2) InferenceMode **아님**(추론 텐서에 `Function::apply` 시 SIGSEGV 방어),
(3) 입력이 requires_grad. 하나라도 거짓이면 원시 libm 전미분으로 폴백한다. 즉 작동 f32 경로(NoGradGuard)는
항상 libm 루프, DA 경로는 커스텀 Function. 디스패처 예:

```cpp
torch::Tensor libm_log(const torch::Tensor& x) {
    return use_custom_autograd(x) ? LibmLog::apply(x) : log_fwd(x);       // ops.cpp:161-163
}
torch::Tensor safe_pow(const torch::Tensor& x, double y) {               // ops.cpp:194-197
    auto xc = torch::clamp(x, /*min=*/constants::EPS);   // 클램프는 Function 밖(올바른 클램프 기울기)
    return use_custom_autograd(xc) ? LibmPowScalar::apply(xc, y) : pow_fwd(xc, y);
}
```

### 7.4 `fma_acc`는 왜 커스텀이 아닌가

```cpp
// ops.cpp:154-159
torch::Tensor fma_acc(const torch::Tensor& acc, const torch::Tensor& t1,
                      const torch::Tensor& t2, double value) {
    if (value == 1.0)  return acc + t1 * t2;
    if (value == -1.0) return acc - t1 * t2;
    return acc + (t1 * value) * t2;
}
```

두 mp 모듈 모두 `-ffp-contract=off`로 컴파일되므로, 소스순서 2회-반올림 형태 $(t_1\cdot v)\to\cdot t_2\to+acc$가
비트 정확한 대응이고, **순수 텐서 연산이라 커스텀 autograd 규칙이 불필요하며 InferenceMode에서도 안전**하다.
(과거엔 `-ffp-contract=fast` 대응으로 단일-반올림 `std::fmaf` 커스텀 Function이었으나, `torch::addcmul`이
형상 의존적으로 융합(스칼라 꼬리는 융합·SIMD 본체는 미융합)하여 같은 셀에서 `0x4EAD0F17` vs `0x4EAD0F18`이
나온 step-44 시드 이후 IEEE 전환에서 현재 형태로 바뀜.)

---

## 8. AD-safe 수치 공학 (유한 수반)

### 8.1 핵심 원리: 해석적 유한 ≠ autograd 유한

가장 명료한 예 (`thermo.cpp:143-147`, `melt_freeze.cpp:29-32`):

$$\text{점성계수}\ \nu \propto \frac{t\sqrt{t}}{t+120}\frac1\rho .$$

전미분 값 $t\sqrt t=t^{3/2}$는 $t=0$에서 도함수 $\tfrac32\sqrt t$가 **유한(=0)**하다. 그러나 autograd는 곱셈규칙을
적용한다:

$$\frac{d}{dt}\big[t\cdot\sqrt t\big]=\sqrt t+t\cdot\frac{1}{2\sqrt t}.$$

둘째 항은 $t=0$을 $\sqrt{\cdot}$ 노드로 라우팅하며, 그 국소 기울기 $1/(2\sqrt t)\to+\infty$가 $0\cdot\infty=\text{NaN}$을
만든다. 4D-Var 제어변수가 온위 $\theta$이고 $t=\theta\,\Pi$가 일시적으로 $\le0$이 될 수 있어 **실제로 발화**한다.
해법은 $\text{clamp}(t,\min=1\,\mathrm{K})$: sqrt 노드 기울기를 $1/(2\sqrt1)=0.5$로 유한하게 하고 물리 온도(>1K)에서는 무해하다.

> **이것이 포트 전체를 관통하는 논지다: 전미분의 해석적 유한성은 autograd 그래프의 유한성을 보장하지 않는다.**
> 곱셈규칙이 특이 노드를 경유시키기 때문이다.

### 8.2 안전 원시연산과 유한 경계 (`ops.cpp:170-203`)

| 원시연산 | 정의 | 원시 도함수의 특이성 | 클램프 후 경계 |
|----------|------|----------------------|----------------|
| `safe_sqrt` [D2] | $\sqrt{\text{clamp}(x,\varepsilon)}$ | $\tfrac{1}{2\sqrt x}\to\infty$ ($x\to0^+$) | $\le \tfrac{1}{2\sqrt\varepsilon}\approx1.58\times10^{7}$ |
| `safe_div_pos` [D1] | $\text{num}/\text{clamp}(d,\varepsilon)$ | $-\text{num}/d^2\to\pm\infty$, $0/0\to$NaN | $\le\text{num}/\varepsilon^2$ |
| `safe_pow` [D3] | clamp$(x,\varepsilon)$ 후 $x^p$ | $p\,x^{p-1}\to\infty$ ($p<1$, $x\to0$) | $x^{p-1}$가 $x\ge\varepsilon$에서 유한 |
| `libm_log` | $\ln x$ (호출측이 clamp) | $1/x\to\infty$ | 저장 입력이 $\ge$바닥값이면 유한 |

$\varepsilon=$`constants::EPS`$=10^{-15}$. 엄격히 클램프된 영역($x<\varepsilon$)에서는 `torch::clamp`의 기울기가
0이므로 그 셀들의 합성 backward는 **정확히 0**이지 Inf/NaN이 아니다(경계 $x=\varepsilon$에서는 PyTorch clamp의
기울기가 1이지만, 그때 하류 $1/(2\sqrt\varepsilon)$ 등은 이미 유한하다). 이 idiom [D1]–[D6]이 포트의 토대다(`ops.h:9-15`).

`safe_pow`는 **클램프를 Function 밖**에 둔다 (`ops.cpp:193` "Clamp stays outside for correct clamp gradient"):
그래야 클램프 기울기가 torch-native로 정확히 처리되고 클램프된 $x_c$만 Function에 들어간다.

### 8.3 where-마스크 + clamp 이중 가드

레이트 항의 표준 가드 (`melt_freeze.cpp:98-102`, cold.cpp/melt_freeze.cpp에 ~40회 반복):

```cpp
auto sfac_raw = in.rslope_s * in.n0so * in.n0sfac
                / torch::clamp(in.qs, /*min=*/p.qcrmin);          // (2) 내부 backward 유한
auto sfac = torch::where(
    torch::logical_and(snow_active, in.qs > p.qcrmin),
    sfac_raw, zero);                                              // (1) 비활성 셀 기울기 0
```

두 가드가 함께 작동한다: (1) `where`의 backward는 **선택(select)**이므로 마스크된 셀은 정확히 0을 주입한다
(단순 곱셈 마스크 $0\cdot\infty$가 아님); (2) clamp가 선택되지 않은 분기의 내부 backward까지 유한하게 만들어
NaN 제조를 원천 차단한다.

### 8.4 op-f32-raw / DA-f64-clamped 이중 나눗셈 (§53b)

```cpp
// melt_freeze.cpp:138-145 — 우박 밀도 rhox로 나눔
auto rhox_div = (in.rhox.scalar_type() == torch::kFloat32)
    ? in.rhox                                          // op: rhox=0 셀에서 ±Inf (문서화된 brs -inf, 원본 비트 동일)
    : torch::clamp(in.rhox, /*min=*/constants::DENS);  // DA: 유한 수반 (DENS=100)
auto delta_brs = torch::where(graupel_active, pgmlt / rhox_div, zero);
```

$d/d(\rho_x)[p/\rho_x]=-p/\rho_x^2\to\pm\infty$. f32 작동 경로는 원시 $\rho_x$로 나눠 원본의 $\pm$Inf 거동까지
비트 재현하고(하류 fmaxnm이 정확히 0으로 붕괴), f64 DA 경로는 $\text{clamp}(\rho_x,100)$으로 나눠 그래프에
$\pm$Inf가 들어가지 않게 한다. **분기는 `scalar_type()` 구조적 검사라 그래프를 끊지 않는다.**

### 8.5 부호보존 나눗셈 및 NaN 방화벽

- **부호보존** `safe_div_signed` [D1b] (`ops.cpp:175-185`): 분모가 음수가 될 수 있을 때 단순 `clamp(min=ε)`은
  작은 음수를 0 너머로 밀어 **부호를 뒤집는다**(작은 음수 분모에서 몫이 큰 양수로 튀는 부호 오류). 대신
  $|d|<\text{floor}$를 $\text{sign}(d)\cdot\text{floor}$로 치환해 **0을 제외한 양쪽에서 부호를 유지하고 크기만
  제한**한다: $-\text{num}/d^2$가 $\text{num}/\text{floor}^2$로 유한. 주의 — $d=0$에서는 $\text{sign}(0)=+1$로
  정의되어 $-\text{floor}\!\to\!+\text{floor}$ 점프가 있으므로 이 사상 자체는 0에서 불연속이다(측도 0). 요점은
  연속성이 아니라 **clamp가 유발하는 부호 뒤집음을 피하면서 수반 크기를 유한하게** 만드는 것이다.
- **NaN 게이트** `isfinite_else` (`ops.cpp:227-230`): $\text{where}(\text{isfinite}(x),x,\text{fallback})$.
  이미 비유한이 된 셀은 상수 fallback으로 대체되고 그 backward가 0이라, 해당 셀이 backward 전체를 NaN으로
  오염시키지 않는다. (포트는 forward에서 NaN을 잡으려 `torch::min/max/clamp`(NaN 전파)를 선호하고, 이 게이트를
  지정된 회복점으로 둔다.)

### 8.6 `.item()`은 반드시 NoGradGuard, detach 그래프 절단

정수 소스텝수 `mstep`은 미분 의미가 없는 루프 경계다 (`runtime.cpp:462-479`):

```cpp
{
    torch::NoGradGuard no_grad;   // .item() 추출을 autograd가 추적하지 않도록
    auto vmax_main_col = torch::maximum(...).amax(-1);
    mstep_col_main = torch::clamp(torch::floor(vmax_main_col*dtcld + 1.0).to(torch::kLong),
                                  /*min=*/1, /*max=*/100).to(w1_qr.dtype());
    mstepmax_main = static_cast<int>(mstep_col_main.max().item<double>());  // 그래프 누수 방지
}
```

이는 사용자 표준 규칙 **".item() 사용시 반드시 NoGradGuard"**의 직접 구현이다. 연속 침강 flux만 기울기를
운반하고, 이산 `mstep`은 상수로 흘러나간다. detach의 세 용도: (1) 작동 forward의 NoGradGuard(그래프 0),
(2) `detach().clone().requires_grad_(true)`로 **새 리프 생성**(제어변수 정의), (3) `detach().to(kFloat32).cpu()`로
진단 .bin 덤프용 값 복사(손실로 되먹임 없음).

---

## 9. 검증: 수치적 증명

| # | 명제 | 방법 | 허용오차 | 위치 |
|---|------|------|----------|------|
| 1 | $\langle Jv,u\rangle=\langle v,J^\top u\rangle$ | 양변 reverse-mode(정확) | rel $<10^{-12}$ | `test_handle_vjp.cpp:113-129` |
| 2 | 마스크 수반: $\langle JPv,u\rangle=\langle v,PJ^\top u\rangle$ | reverse-mode | rel $<10^{-12}$ | `test_handle_vjp.cpp:132-152` |
| 3 | JVP $=$ 중심차분 접선 | $[M(x{+}v){-}M(x{-}v)]/2$ | rel $<10^{-5}$ | `test_handle_vjp_jvp.py:181-201` |
| 4 | VJP 방향도함수 $=$ FD | $\langle J^\top u,v\rangle$ vs $\tfrac{d}{d\epsilon}\langle M(x{+}\epsilon v),u\rangle$ | rel $<10^{-6}$ | `test_handle_vjp_jvp.py:128-149` |
| 5 | 이중-역전파 준비성 | grad-of-grad 유한·비영 | — | `test_handle_vjp_jvp.py:155-178` |
| 6 | 합성 클라우드 경로(RTTOV) | 정확 내적 + 성분별 FD | $10^{-9}$/$10^{-4}$ | `test_cloud_path_fd_vjp.py:56-108` |

**FD 게이트의 정당성**: 중심차분 $[M(x{+}v)-M(x{-}v)]/2$는 매끄러운 부공간에서 $O(\epsilon^2)$로 정확하다.
그래서 명제 3·4는 게이트/클램프 꺾임을 피해 **매끄러운 열역학 방향** $(\theta,q_v,q_c)$로 제한한다(S4-jump류 회피).
비매끄러운 방향까지 포함하는 **정확** 명제는 1·2(수반 항등식)이며 FD에 구속되지 않는다.

---

# 부록 A. C ABI 상세

### A.1 핸들과 패킹 배치

```cpp
// kdm6_c_api.cpp:20-37
extern "C" struct kdm6_handle_t {
    std::unique_ptr<kdm6::Handle> impl;   // 라이브 autograd 그래프 소유
    int im = 0, kme = 0, jme = 0;         // 패킹 차원
    c10::ScalarType dtype = c10::ScalarType::Float;  // op=Float32, DA=Float64
};
```

패킹 레이아웃: 필드우선 시퀀스, 각 필드가 Fortran $(i_m,k_m,j_m)$ 열우선 블록. 필드 순서 =
`State::fields()` = $(\theta,q_v,q_c,q_r,q_i,q_s,q_g,n_{ccn},n_c,n_i,n_r,b_g)$. 총 크기 $12\,i_m k_m j_m$.

### A.2 진입점

| 함수 | 용도 | dtype | 위치 |
|------|------|-------|------|
| `kdm6_step_c` | 작동 f32 스텝 (+선택적 f32 테이프) | Float32 | `kdm6_c_api.cpp:143-217` |
| `kdm6_step_ad_c` | DA fp64 스텝 (모든 필드 리프) | Float64 | `kdm6_c_api.cpp:312-361` |
| `kdm6_handle_vjp_c` | $J^\top u$ (수반) | 핸들 dtype | `kdm6_c_api.cpp:375-401` |
| `kdm6_handle_jvp_c` | $Jv$ (Pearlmutter) | 핸들 dtype | `kdm6_c_api.cpp:403-427` |
| `kdm6_handle_close_c` | 그래프 해제 + 래퍼 delete | — | `kdm6_c_api.cpp:429-434` |

DA 진입은 별도로 `double*` 패킹을 받아 모든 텐서를 `ScalarType::Double`로 올리고 12개 상태장에
`requires_grad_(true)`를 호출한다(`kdm6_c_api.cpp:312-361`). "same physics, float64 graph" — 동일한
`kdm6_step`이 실행되고 dtype(모든 `scalar_type()==kFloat32` 분기를 클램프/native DA 팔로 뒤집음)과 grad만 다르다.

### A.3 수명 계약

Fortran 호출자는 매 스텝 후 `kdm6_handle_close_c`를 호출해야 한다 (`kdm6_c_api.cpp:429`). 이 함수는
`Handle::close()`로 `state_in/state_out/forcing/params`를 비워 그래프를 해제한 **뒤 `delete h`로 C 래퍼
자체를 해제**한다. 따라서 닫은 뒤 같은 포인터를 재사용하는 것은 정의되지 않은 동작(UB)이다
(`test_c_abi.cpp:347`) — 브리지 내부에 `is_closed()` 검사(`kdm6_c_api.cpp:380`)가 있으나 이는 방어일 뿐,
정상 사용에서 닫힌 핸들 포인터를 다시 넘기면 안 된다. `NULL` 핸들은 `kdm6_handle_close_c`에서 `KDM6_OK`로
무시된다. **value-only 스텝**(`value_only!=0`)은 애초에 `*handle=NULL`을 반환하므로(`kdm6_c_api.cpp:209-210`),
그 뒤 VJP/JVP 호출은 널 포인터 검사에 걸려 `KDM6_ERR_NULL_POINTER`를 반환한다(`test_c_abi.cpp:361`).
(내부 `is_value_only()`→`KDM6_ERR_VALUE_ONLY` 경로는 비-널 핸들이 value-only인 도달불가 방어 경로다.)

---

# 부록 B. 연산자별 코드 상세 (§2.3의 19 연산자)

아래는 각 부연산자의 변환 대상과 비매끄러운 점. **권위 기준은 실제 이식본이자 Fortran 원본과 비트-일치하는
C++(`coordinator.cpp`)**이고, Python 오라클(`coordinator.py`)은 참조 구현으로 대체로 대응하나 **몇 곳에서
갈린다**: (i) $L_9$ 완전강수증발의 배치(§2.3 각주), (ii) Picons의 $n_i>0$ 게이트가 Python엔 있고 C++엔 없음
(`coordinator.py:1414` vs `coordinator.cpp:2329`), (iii) 최종 얼음 수 제한이 Python은 스칼라 게이트, C++는
per-cell 게이트(`coordinator.py:1586` vs `coordinator.cpp:2561`). 아래 줄 참조는 이해를 돕는 오라클 위치이며,
정합성 기준값은 C++을 따른다.

- **$L_1$ preamble** (`:119-179`): $c_{pm}(q_v),\ x_l(t),\ supcol=t_{0c}{-}t,\ q_s^{1,2}(t,p),\ rh_w,\ rh_{ice},\ supsat$,
  denfac, `rslopec`, `progb`, `slope_kdm6`. 순수 진단. 꺾임: $\max(q_v,q_{min})$, λ·rhox 클램프.
- **$L_3$ D1 융해** (`:958-1020`): warm_mask$=(supcol<0)$; $q_r{-}=\Delta t(p_{smlt}{+}p_{gmlt})\text{mask}$,
  $q_s{+}=\dots$, $q_i,q_c,n_r,n_c,n_i,b_g,\theta$ 갱신. Heaviside(T=t0c, 엄격 $<$), min-cap.
- **$L_4$ 균질동결** (`:1851-1882`): mask$=(supcol>40)\wedge(q_c>0)$; $q_c(1{-}\text{mask})$, $q_i{+}=q_c\text{mask}$, ….
  이중 Heaviside 곱.
- **$L_{5,7}$ rebuild_aux + λ-스냅** (`:1947-2019, 2034-2098`): $\lambda=(\text{pidn}\cdot n/(q\,\rho))^{1/dm}$;
  $n$을 $[\lambda_{min},\lambda_{max}]$로 스냅(where 꺾임). $\{n_c,n_i,n_r\}$ 재기록.
- **$L_6$ D2–D4 동결** (`:660-714`): 접촉(pinuc)·Bigg-구름(pfrzdtc, POST-D2 저장소)·Bigg-비(pfrzdtr).
  $\{q_c,q_i,n_c,n_i,q_r,q_g,n_r,b_g,\theta\}$. supcol>0 게이트, POST-D2 cap.
- **$L_{8,10,11}$ warm/cold/D5** (`:219-288, 381-572, 747-781`): 진단 rate만 방출(§2.3). cold는 warm.prevp를
  읽음(C3/C4 결합), D5는 cold의 HM-조정 paacw/psacr/pgacr를 읽음.
- **$L_9$ 완전강수증발** (`coordinator.cpp:1071-1074`): $n_{ccn}{+}=n_r\cdot\text{rce}$, $n_r=\text{where}(\text{rce},0,n_r)$.
  루프 내 전이(이후 모든 $n_r$ 소비자가 0을 봄).
- **$L_{12}$ 보존 재척도** (`:820-955`): 14 예산, $\text{factor}=\text{where}(\text{gate},\text{value}/\max(\text{source},\text{value}),1)$.
  max() 꺾임, cold/warm 게이트, $\delta_2/\delta_3$ 라우팅.
- **$L_{13}$ state_update** (`:1023-1336`): 전 예단장 갱신. 지배적 비매끄러움 — 수상 8필드
  $q_c,q_r,q_s,q_g,q_i,n_c,n_r,n_i$ + $b_g$의 비음 클램프($\text{clamp}/\text{fmax}(\cdot,0)$, C++ `coordinator.cpp:2038·2102`),
  cold/warm 마스크, $\delta_2/\delta_3$ 라우팅, $\text{clamp}(\rho_x,\text{DENS})$, $\text{clamp}(c_{pm},\text{QCRMIN})$.
  **$q_v$·$n_{ccn}$·$\theta$는 여기서 클램프하지 않는다**($q_v$는 §53t로 클램프 제거, $n_{ccn}$은 satadj의 저장소
  클램프에서 처리, $\theta$는 음수 허용 — 모두 원본과 동일).
- **$L_{14}$ $b_g$-reclamp** (`:2159-2164`): $b_g=\text{where}(q_g>q_{crmin},\ \text{progb}(q_g,b_g).bg,\ 0)$. rhox∈[100,900].
- **$L_{15}$ Picons 큰얼음→눈** (`:1381-1436`): mask$=\text{ice\_active}\wedge(t<t_{0c})\wedge(\text{avedia}_i\ge200\mu m)$.
- **$L_{16}$ 작은비→구름** (`:1442-1497`): mask$=\text{rain\_active}\wedge(\text{avedia}_r\le82\mu m)$.
- **$L_{17}$ satadj** (`:1747-1848`): sw_percent$=(q_v/q_{s1}{-}1)\cdot100$; activated_fraction$=\min(1,\text{pow}(\text{clamp}(\text{sw\_ratio},\varepsilon),\text{ACTK}))$
  — **ACTK<1이라 base=0에서 기울기 →∞, 그래서 base를 ε로 클램프**(의도적 부분기울기 정규화). 완전증발 등식 게이트 pcond$=-q_c/\Delta t$.
- **$L_{18}$ threshold cleanup** (`:1342-1375`): 5개 경성 임계 0/1 마스크 — 부임계 수상을 0으로 버리는
  **불연속(점프)** 연산자. (이것만 점프인 것은 아니다 — §2.4의 판별식 "경계에서 $A\neq B$"에 따라 $L_4$
  균질동결·$L_{15}/L_{16}$ 재분류·$L_9$ 완전강수증발·$L_{17}$ 완전증발·$L_3$ 순간융해 등도 점프에 속한다.)
- **$L_{19}$ DSD 수 제한** (`:1503-1561`): 종단 λ-스냅 + NRMAX/NCMAX cap. $\{n_r,n_c,n_i\}$.

---

# 부록 C. 커스텀 Function 코드 원문 (`libtorch/src/ops.cpp`)

```cpp
// 이중경로 전미분: f32 = 원소별 libm(gfortran 비트 일치), f64 = torch native
inline torch::Tensor exp_fwd(const torch::Tensor& x) {
    if (x.scalar_type() == torch::kFloat32) {
        auto xc = x.contiguous(); auto out = torch::empty_like(xc);
        const float* xp = xc.data_ptr<float>(); float* op = out.data_ptr<float>();
        for (int64_t i = 0; i < xc.numel(); ++i) op[i] = std::exp(xp[i]);
        return out;
    }
    return x.exp();
}
// (log_fwd, pow_fwd(scalar/tensor), rgmma_fwd 동일 형태)

struct LibmLog : public torch::autograd::Function<LibmLog> {
    static torch::Tensor forward(AutogradContext* ctx, torch::Tensor x) {
        ctx->save_for_backward({x}); return log_fwd(x);
    }
    static tensor_list backward(AutogradContext* ctx, tensor_list go) {
        return {go[0] / ctx->get_saved_variables()[0]};       // d/dx log = 1/x
    }
};

struct RgmmaT : public torch::autograd::Function<RgmmaT> {
    static torch::Tensor forward(AutogradContext* ctx, torch::Tensor x) {
        auto out = rgmma_fwd(x); ctx->save_for_backward({x, out}); return out;
    }
    static tensor_list backward(AutogradContext* ctx, tensor_list go) {
        auto s = ctx->get_saved_variables();
        return {go[0] * s[1] * torch::digamma(s[0])};         // d/dx Γ = Γ·ψ
    }
};

inline bool use_custom_autograd(const torch::Tensor& x) {
    return at::GradMode::is_enabled() && !c10::InferenceMode::is_enabled() && x.requires_grad();
}
```

f32 감마 전미분 (`fconst.h:24-38`): 6계수 Lanczos $\ln\Gamma$(내부 double, f32 반환), `rgmma_f = expf(gammln_f)`.

---

# 부록 D. AD-safe idiom 카탈로그 (`libtorch/src/ops.cpp:170-230`)

```cpp
// [D1]  양의 분모 나눗셈
torch::Tensor safe_div_pos(num, denom)   { return num / torch::clamp(denom, /*min=*/EPS); }
// [D1b] 부호보존 나눗셈
torch::Tensor safe_div_signed(num, denom, floor) {
    auto sign = torch::where(denom != 0, torch::sign(denom), torch::ones_like(denom));
    auto safe = torch::where(denom.abs() < floor, sign * floor, denom);
    return num / safe;
}
// [D2]  안전 제곱근
torch::Tensor safe_sqrt(x)               { return torch::sqrt(torch::clamp(x, /*min=*/EPS)); }
// [D3]  안전 거듭제곱 (클램프는 Function 밖). 스칼라 지수는 1-인자 토글, 텐서 지수는 2-인자 토글
//       use_custom_autograd(xc, y) — 지수 y의 requires_grad까지 반영해야 ∂/∂y 경로가 보존됨.
torch::Tensor safe_pow(x, double y)      { auto xc = torch::clamp(x, EPS);
                                           return use_custom_autograd(xc) ? LibmPowScalar::apply(xc,y) : pow_fwd(xc,y); }
torch::Tensor safe_pow(x, Tensor y)      { auto xc = torch::clamp(x, EPS);
                                           return use_custom_autograd(xc, y) ? LibmPowTensor::apply(xc,y) : pow_fwd(xc,y); }
// [D4]  매끄러운 minmod (비미분 지시함수를 tanh 시그모이드로)
//       0.5*(tanh((a*b)/smooth_eps)+1) * sign(a) * min(|a|,|b|),  smooth_eps=1e-4
// [D10] NaN 방화벽
torch::Tensor isfinite_else(x, fallback) { return torch::where(torch::isfinite(x), x,
                                                               torch::full_like(x, fallback)); }
// EPS = constants::EPS = 1.0e-15
```

`smooth_minmod`의 Smoothed 모드는 비미분 지시함수 $(ab>0)$를 tanh 시그모이드
$\tfrac12(\tanh(ab/\text{smooth\_eps})+1)$로 대체해 minmod를 미분가능하게 만든다(`ops.cpp:220-224`).

---

## 결어

KDM6AD의 미분가능성은 세 축의 협업이다: **(1)** dtype을 스위치로 삼아 하나의 연산자 코드가 f32 비트-동일
작동 사상과 f64 매끄러운 DA 사상을 겸하고, **(2)** 초월함수만 커스텀 autograd Function으로 감싸 libm forward의
비트-정확성과 해석적 backward의 그래프 보존을 동시에 얻으며, **(3)** JVP는 커스텀 Function에 forward 규칙이
없다는 제약 때문에 Pearlmutter 이중-VJP로, HVP는 동일한 create_graph 이중-역전파로 합성한다. 수반 항등식
$\langle Jv,u\rangle=\langle v,J^\top u\rangle$이 상대오차 $10^{-12}$로 성립함이 이 구성 전체의 정확성 증명이며,
"해석적 유한 ≠ autograd 유한" 원칙에 따른 클램프·where-마스크 유한-수반 idiom이 4D-Var 제어가 물리
경계를 넘나들 때에도 그래프에 Inf/NaN이 들어가지 않게 보장한다.
