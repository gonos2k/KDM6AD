# 실제 침강 chain의 QI·NI 단계별 짝 기록

**범위:** 공개 Python `sedimentation_chain_torch()`가 실제로 호출한 얼음 substep에서 QI 질량과 NI 수량의 적용량을 같은 단계로 묶는 **분석용 주입**이다. 합성 native 형상의 2열×3층과 2층 입력을 사용하며, 비공개 호스트·RTTOV나 새 KDM 실행 파일은 호출하지 않았다. QNICE 물리 단위와 전체 물리 수지의 `INCONCLUSIVE` 판정은 유지한다. [직접 substep NI 계측](NATIVE_ICE_NUMBER_APPLIED_BUDGET_20261031.md)을 이 호출 순서에 연결한 단계다.

## 호출과 기록의 경계

[`IceChainAppliedCapture`](../harness/ice_chain_applied_budget.py)를 기존 `ice_substep_fn` 자리에 전달한다. 이 래퍼는 같은 인자로 `ice_substep_advection_torch()`를 **한 번만** 호출한다. 호출마다 새 질량 ledger를 만들어 QI 기록을 해당 NI 기록과 결합하고, 상위에서 이미 전달한 질량 ledger에도 원래 record를 그대로 전달한다. 반환된 상태·표면 누적 계산은 변경하지 않는다.

| 같은 얼음 호출에서 보존하는 값 | 해석 |
| --- | --- |
| `n_current`, `mstep_divisor`, 열별 gate | 실제 호출 순서와 활성 열. 비활성 열도 호출을 거치지만 적용 flux는 0이다. |
| `work1_qi`, `workn_qi` | 그 호출에 **실제로 전달된** 얼음 질량·입자수 속도 피연산자. 래퍼는 속도를 재계산하지 않는다. |
| QI 전후 상태와 호출별 질량 attribution | `dend*dz`로 가중한 **층별 실제 이탈·유입·하한 보정 배열**, 계면 차이·하단 이탈 요약 및 반환 상태의 질량 변화 |
| NI 전후 상태와 호출별 number record | 제한 전·실제 이탈과 유입, 0 하한 보정, raw `fall_ni` 누산. 기본 수치 좌표의 집계는 `dz` 가중이다. |

QI 질량과 NI 수량은 **서로 다른 단위·가중치**로 보고한다. 건조 질량 기준 NI 재고는 `rho_d`를 별도로 제공할 때만 조건부로 계산할 수 있다. `dend`를 자동으로 건조공기 밀도라고 가정하지 않는다.

## 속도 재계산과 단계 순서

상위 함수는 주 침강 substep **각 호출 뒤** 다시 slope를 계산하고, 이어서 얼음 substep을 수행한다. 이 연구 브랜치의 기본 handoff에서는 첫 얼음 호출에 주 단계 뒤의 **raw** `vt_i/vtn_i`가 전달된다. `normalize_ice_handoff=True`인 선택적 경로는 첫 호출부터 `vt/dz`를 사용한다. 두 번째 이후 얼음 호출에서는 앞선 얼음 상태를 반영해 slope를 다시 계산한 **`vt/dz`**가 들어간다. `reslope_params=None`이면 호출자가 제공한 work 배열을 반복 사용한다. [상위 호출 순서](../oracle/kdm6/coordinator.py)

합성 대조는 QI와 NI가 모두 양수인 **2열×3층**, 비균일 `dz=300,500,700` 및 `250,450,650 m`, 열별 `mstep_col=1,2`, `mstep_main=mstep_ice=2`, `dtcld=1`을 사용한다. 실제 기록에서 첫 호출은 두 열 모두 활성이고 두 번째는 첫 열만 비활성이다. 기본 경로의 첫 열 첫 `workn_qi`는 약 `0.34490,0.33231,0.30825`; 선택적 정규화 경로에서는 약 `0.0011497,0.0006646,0.0004404`다. 각각 `dz`로 나누는 관계를 확인했다. 첫 QI·NI 속도는 **마지막 주 단계 상태의 preamble**에서, 두 번째 속도는 **첫 얼음 단계 뒤 상태의 preamble**에서 별도로 재계산해 전달 피연산자와 원시 비트로 대조했다. `reslope_params=None` 대조에서는 두 호출 모두 입력 work를 그대로 사용한다. 이 값들은 **합성 입력의 공개 oracle 결과**이며 실제 체크포인트에서 계측한 속도가 아니다.

## 비간섭과 미분 대조

[`test_ice_chain_applied_budget.py`](../harness/tests/test_ice_chain_applied_budget.py)는 f32·f64에서 기본 호출과 분석 래퍼 호출의 **모든 반환 state 필드와 세 표면 출력**을 원시 비트로 비교한다. 기존 누적 질량 ledger에도 QI 기록을 포함한 모든 종의 요약값이 그대로 전달됨을 확인한다. 각 호출의 QI 질량 변화는 해당 단계의 전후 상태와 `dend*dz`에서 독립 재계산하고, NI의 `dz` 가중 분해는 각 피연산자 규모에 따른 반올림 범위에서 닫히는지 확인한다.

선택한 방향에서는 **QI·NI 변화 → preamble 속도 → 주/얼음 재계산 → 최종 상태**의 JVP와 VJP가 계측 on/off에서 원시 비트 일치하며, 실제 중앙차분과도 비교한다. 기준·양 끝점에서 **NI의 층별 제한·하한 flag와 열별 gate**, **QI의 열별 제한 횟수·최상층 하한 flag**가 같은지 확인한다. QI의 층별 제한 위치, 주 침강과 preamble/slope의 모든 내부 분기를 추적한 검사는 아니므로 전체 chain의 모든 분기가 동일하다고 단정하지 않는다. 분기 경계의 양쪽 도함수도 이번 시험 범위 밖이다. 질량이 0인 직접 NI 사례와 달리, 이 시험은 QI·NI가 모두 양수인 상태에서 실제 상위 재계산 경로를 지난다.

선택한 QI 증가·NI 감소 방향에서 (h=10^{-4}) 중앙차분과 JVP의 최대 차이는 약 `7.36e-11`, 상대 L2 차이는 약 `3.22e-12`였다. 이 진단 벡터는 QI 출력에 `1e8`을 곱하고 NI 출력과 이어 붙인 **수치 좌표**이므로, 최대 차이에 물리 단위를 붙이거나 일반 합격 허용오차로 사용하지 않는다.

```bash
python3 -m pytest harness/tests/test_ice_chain_applied_budget.py oracle/tests/test_ice_number_budget.py oracle/tests/test_sed_attribution.py oracle/tests/test_coordinator.py -q
ruff check harness/ice_chain_applied_budget.py harness/tests/test_ice_chain_applied_budget.py
```

이번 환경에서 위 관련 시험은 **82 passed**였고 기존 Torch JIT deprecation 경고 18개가 있었다. 새 chain 시험 중 f32·f64 정방향 비간섭은 재계산을 켠 두 handoff 경로에 적용했고, 고정 work 대조는 f64·주 단계 0회 한 사례다. JVP/VJP 비간섭과 중앙차분은 정규화 handoff의 f64 선택 방향에서 수행했다. 첫 얼음 속도의 raw/정규화 차이는 **서로 다른 선택적 수치 규칙의 비교**이며, 한 규칙의 계측을 켜고 끈 동일성 검사와 구분한다.

## 남은 실행 검증

이 결과는 상위 공개 oracle의 실제 호출 순서를 따라가지만, 전체 `_kdm6_pure()`의 모든 미세물리 과정, 실제 private 호스트의 QI·QNICE 피연산자, 실행 중 적용된 밀도·층두께·속도, KDM DSO 또는 RTTOV까지 인증하지 않는다. 다음 native 자료에는 한 열의 얼음 substep 전후 QI·NI, 사용한 `vt_i/vtn_i`, 매 substep의 `mstep` gate, 적용 이탈·유입·하한 보정과 같은 시점의 밀도·층두께를 함께 남겨야 한다. 그 자료를 현재 ledger에 연결한 뒤 건조 질량 기준과 커널 raw 좌표의 수지 차이를 판단할 수 있다.
