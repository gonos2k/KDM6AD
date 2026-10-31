# 얼음 입자수 침강의 실제 적용량 — 두·세 층 진단

**범위:** 공개 Python `ice_substep_advection_torch()`의 opt-in NI 계측과 합성 한 substep 대조다. 운영 mp37/mp137의 계산이나 기본 정방향 결과를 바꾸지 않는다. 실제 비공개 호스트 실행에서의 빈도·전체 수지, QNICE의 물리 단위 계약, 분석 수용은 이번 자료로 확정하지 않는다. [단위 경계 조사](NATIVE_QNICE_UNIT_COORDINATE_AUDIT_20261031.md)의 `INCONCLUSIVE` 판정을 유지한다.

## 기록하는 양

새 [`IceNumberAppliedLedger`](../oracle/kdm6/ice_number_budget.py)는 NI 갱신 함수가 사용한 **각 substep·층의 피연산자**를 분리해 보존한다. NI 진단은 기존 물 질량 ledger의 `rho*dz` 가중치나 `kg/m²` 필드를 재사용하지 않는다.

| 기록 | 의미 |
| --- | --- |
| `before`, `after` | substep 전·후의 실제 NI 상태 |
| `candidate_out`, `applied_out` | 제한 전 낙하 후보와 상태식에서 뺀 양. 최상층은 후보를 그대로 빼고 0 하한을 적용한다. |
| `candidate_in`, `applied_in` | 위층의 **저장된 이탈 flux**와 층두께 비율로 만든 후보, 위층의 **갱신 후 값**으로 제한해 실제 더한 양 |
| `projection` | 0 하한이 음수 중간 상태에 더한 양 |
| `fall_before`, `fall_after` | raw `fall_ni` 누산값. 이 값은 적용 이탈량이나 WRF 표면 입자수 진단이 아니다. 하단의 제한 전 후보는 누산값의 차감으로 복원하지 않고 `candidate_out`에서 직접 계산한다. |
| `delz`, `dend`, `gate`, `mstep_divisor`, `dtcld`, `n_current` | 수직 척도와 실제 분기·substep 맥락. NI 식에는 `dend`를 곱하지 않는다. |

모든 기록은 detached clone이며, `number_ledger=None`인 기본 함수 경로에는 추가 진단 산술이 없다. [`sedimentation.py`](../oracle/kdm6/sedimentation.py)의 최상층과 내부 갱신식은 기존 순서를 유지한다. 제한기 활성 여부는 후보·적용량과 projection에서 따로 기록한다.

한 기록에 가중치 (w_k)를 선택하면 다음 수치 항등식을 검사할 수 있다. 층 인덱스는 **위에서 아래로** 증가한다.

\[
L=\sum_k w_k(N_k^{pre}-N_k^{post}),\quad
B=w_{bottom}O_{bottom},\quad
D_k=w_{k-1}O_{k-1}-w_k I_k,\quad
A=\sum_k w_k P_k.
\]
\[
L=B+\sum_{k=1}^{K-1}D_k-A+\varepsilon_{arith}.
\]

`summarize_ice_number_substep()`은 **연산자 숫자 좌표**의 `w=dz`와, 외부에서 별도 건조공기 밀도를 지정한 **조건부 건조 질량 좌표**의 `w=rho_d*dz`를 구분한다. `dend`를 건조밀도라고 자동 가정하지 않는다. 수지의 잔차가 작다는 것은 기록된 갱신을 설명한다는 뜻이며, 계면 차이 (D_k\ne0)을 보존으로 재해석하지 않는다.

## 실제 함수의 합성 대조

아래 숫자는 실제 공개 함수를 실행한 뒤 record와 반환 상태를 대조한 결과다. 새로운 호스트·RTTOV 호출은 없다. 단위는 입력 NI의 수치 좌표에 따른 값이며, 물리적 입자수 단위를 인증한 표가 아니다.

| 사례 | 입력 NI, 위→아래 | 후보/적용 이탈 | 후보/적용 유입 | 반환 NI | `dz` 가중 열 감소 | 설명 |
| --- | --- | --- | --- | --- | ---: | --- |
| 두 층, 비제한 | `10, 0` | 위 `2/2` | 아래 `2/2` | `8, 2` | `0` | 양쪽 적용량 일치 |
| 두 층, 유입 제한 | `10, 0` | 위 `8/8` | 아래 `8/2` | `2, 2` | `6` | 계면 이탈–유입 차이 `6` |
| 세 층, `dz=1,2,4` | `10,2,3` | `20/20, 1/1, 0.75/0.75` | `0/0, 10/0, 0.5/0.5` | `0,1,2.75` | `13` | 하한 보정 `10`; 계면 차이 `20,0`; 하단 적용 이탈 `3` |
| 두 층, 하단 이탈 제한, `dz=1,3` | `0,2` | 하단 `4/2` | `0/0` | `0,0` | `6` | raw 하단 fall 후보 `12`, 실제 적용 이탈 `6` |

세 층 사례는 `L=13`, `B=3`, `ΣD=20`, `A=10`으로 `13=3+20−10`을 확인한다. **같은 상태**를 명시적인 `rho_d=0.5,1,2`로 조건부 건조 질량 가중하면 `L=9`, `B=6`, `ΣD=8`, `A=5`로 `9=6+8−5`다. 별도의 두 층 비제한 이동에서 `dz` 가중 열 감소는 0이지만 비균일한 `rho_d=0.5,1.5`를 적용한 조건부 건조 질량 감소는 **−2**다. 밀도 좌표를 선택하지 않고 하나의 보존값을 선언할 수 없음을 보여 준다.

## 재현과 비간섭

```bash
python3 -m pytest oracle/tests/test_ice_number_budget.py -q
python3 -m pytest oracle/tests/test_sed_attribution.py oracle/tests/test_audit_sedimentation_contract.py oracle/tests/test_sedimentation.py -q
```

새 시험은 f32·f64 단일층, f64 두·세 층, 별도 f32 세 층 연산 순서, 서로 다른 층두께·밀도, 상·하단 제한, 두 열의 `mstep_col` gate, 반복 substep을 검사한다. 별도 NumPy f32 계산으로 후보·적용량·최종 NI의 **원시 비트**를 대조한다. 큰 기존 `fall_ni` 누산값이 f32 반올림으로 새 증가량을 흡수하는 사례에서는 **제한 전 하단 후보 1과 누산값 차이 0을 따로 기록**한다. 계측 off/on의 QI·NI·`fall_qi`·`fall_ni` 원시 비트와 매끄러운 경우의 JVP·VJP도 일치한다. 기존 질량 ledger 및 침강 시험도 그대로 통과했다. 이 검사는 독립적인 비공개 Fortran 호스트 계측이나 전체 커널 수량 예산 검증을 대신하지 않는다.

다음 단계는 실제 native 한 열에서 같은 항을 기록하고, mp37·mp137의 입출구에서 건조 질량 기준 `rho_d*n_d`와 커널의 현재 NI·DEN을 함께 측정하는 것이다. 그 뒤 선택적 단위 변환을 설계할 때는 질량·입자수·graupel 부피 모멘트, 모든 재작성·문턱, 출구 역변환 및 밀도 JVP/VJP를 함께 평가해야 한다.
