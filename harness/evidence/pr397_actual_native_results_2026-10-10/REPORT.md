# 새 native 입력의 실제 T/Q 분석 결과

기준 main `eec82d65`(PR396). 원래 시작한 모델을 중단·재시작하지 않고 기존
continuation v4로 **native 완료 → intake → 실제 KDM/all-sky RTTOV 한정 분석 →
저장 배열 진단**을 연결했다. 세 consumer는 모두 0으로 반환했다. 새 numerical
case가 확보됐지만, nominal 관측 대응과 선언된 prior에 조건부인 결과다.

## 실제 종료와 입력

모델은 `2025-07-19_05:58:00`에 `SUCCESS COMPLETE WRF`를 기록했다. 독립 OS
관찰에서 rank/launcher의 wait status와 종료코드는 모두 0이었다. Archive의
launcher `exit_code=0`, `experiment_valid=true`, `model_completed=true`이며
invalid reason은 없다. 정확한 8개 Times(05:55:40부터 20초 간격으로 05:58:00),
선택 `(j=86,i=48)`의 39층과 필수 hyperslab을 기존 intake가 확인했다.

**바깥 Python harness의 OS 종료코드는 120으로 별도 관찰됐다.** 이를 0으로
바꾸거나 전체 실행 계층이 정상 종료했다고 보고하지 않는다. Daemon 복구 때
원래 tool/stdout 연결이 사라졌다는 기록이 있고, runner는 archive verdict와
exit marker를 마지막 stdout print 전에 쓴다. Python은 interpreter 정리 중
표준 stream flush 등의 오류가 나면 종료상태를 120으로 바꿀 수 있다고
[공식 문서](https://docs.python.org/3.10/library/sys.html#sys.exit)에 설명한다.
이번 120과 이 경로는 양립하지만 stdout 예외 trace를 확보하지 못했으므로
**정확한 원인은 미확정**이다. Rank/launcher의 실제 0, archive와 입력 검증은
독립 근거이며, 과거 invalid 358분 실행의 원인을 소급 설명하지 않는다.

Green은 archive identity/namelist hashes, dt20·adaptive=false·1 rank/thread,
mp337·variant2/dry-number1/value-only1, ncmin10/10과 intake hash chain을 대조했다.
NPZ 70개 배열의 digest·형상·유한성·frame0 대응·permissions(0600/0700)가 맞았다.
전체 수 GB forecast를 다시 읽거나 stream hash하지 않았으며 그 digest는 null이다.
Native center/interface 39/40과 RTTOV 66/67을 구분한다. P8W는 원래 calc_p8w의
REAL(4) 전사이며 실제 host P8W 출력으로 표현하지 않는다. 실행 binary/source
snapshot `30931e52…`, launch checkout `8e5aab06…`, 소비 코드 `eec82d65`의
동일 tree를 구분하며 current-main native build라고 주장하지 않는다.

## 실제 비용·기울기와 상태

첫 zero-control closure와 최종 accepted-state audit는 동일 signature와
7채널을 유지했고 최종 RTTOV quality는 모두 0이다. 물리매개변수 prior와 제어는
0이며 온위 39개·하단 수증기 12개만 활성이다. 관측 sigma1 K/bias0, Huber delta1,
온위 sigma0.8 K·qv log sigma0.08, all-sky와 고정 forcing/obs_time1을 유지했다.

| 항 | 초기 | 최종 |
| --- | ---: | ---: |
| 관측항 Jo | 26.5885759031 | 26.1356164027 |
| 상태 prior Jb | 0 | 0.2284737909 |
| 매개변수 prior | 0 | 0 |
| 전체 J | 26.5885759031 | 26.3640901936 |

총비용 감소는 **0.84429384%**, 관측항 감소는 **1.70358692%**다. 저장 BT로
별도 NumPy Huber 합계를 계산해 대조했다. 이는 예보 정확도 개선율이 아니다.
Raw zero-mask probe 비용 0은 실제 초기 Jo와 별도로 보존됐다.

일곱 채널이 모두 개선된 것은 아니다. AMI10의 음의 잔차는 −1.030367에서
−1.038011 K로 소폭 악화됐다. AMI13(IR105)은 +4.930225에서 +4.856613 K로
줄었지만 큰 잔차가 남는다. 합산 비용의 감소를 모든 채널 또는 구름 복원으로
표현하지 않는다. [채널별 실제 잔차](CHANNEL_RESIDUALS.json)에 부호를 보존했다.

실제 optimizer counter는 n_iter2, func_evals3(max_eval3), n_window_evals3와
final audit1이다. 성공한 logical H callback은 probe 포함 5개지만 내부 RTTOV
child 횟수는 계측하지 않았다. Stop reason은 UNKNOWN이며 final total-control
gradient L∞=`7.8173583084e-5`(L2=`2.0011374514e-4`)로 tolerance_grad=`1e-10`보다
크다. 따라서 **감소한 유한 분석 결과이며 수렴을 입증한 결과는 아니다.**

네 상태 xb/xa/M(xb)/M(xa)를 실제 NPZ에서 읽었다. 모든 endpoint의 qc/qr/qi/qs/qg는
0이고 NC도 0이다. 초기와 슬롯의 최대 액상 qv/qs는 새 배경에서 **95.534406%**,
분석에서 **96.751478%**이며 모두 하단 0-based3층이다. 이 값은 이전 기록을
복사한 것이 아니라 새 배열의 공개 열역학식 진단이다. 순간 내부 상태 전체를
계측한 것은 아니므로 endpoint 결과 이상으로 확대하지 않는다.

| 초기 분석증분 | 실제 값 | native 층(하단 0-based), 중심압력 |
| --- | ---: | --- |
| 가장 큰 냉각 | −0.15252247 K | 9, 841.485 hPa |
| 가장 큰 가열 | +0.01625616 K | 19, 397.317 hPa |
| 최대 절대 qv 증가 | +1.19243424e-4 kg/kg dry | 9, 841.485 hPa |
| 최대 상대 qv 증가 | +1.70287458% | 11, 764.644 hPa |

전체 층별 증분·포화비는 작은 로컬 `derived_profiles.npz`로 보존했다. 온도
증분의 `(theta_a-theta_b)*Pi`와 원래 `(theta_a*Pi-theta_b*Pi)`는 연산순서의
부동소수점 차이가 있을 수 있다. Bit equality를 주장하지 않는다.

## 실제 물·host/local 진단

첫 시각의 native host eta 건조질량을 고정하면 분석이 추가한 물은
**+0.2216824149 kg/m²**, saved local M의 배경/분석 물 변화는 각각 0이다.
Endpoint 차이와 분해 항등식 잔차 0은 저장 배열의 관계다. 경계·외부 flux는
미측정이며 S17 물/열 수지를 종결하지 않는다.

Host의 05:55:40→05:56:00에서는 움직이는 질량측도까지 별도로 계산했다.

| native host 물 변화 항 | kg/m² |
| --- | ---: |
| 고정 w0의 혼합비 변화 | −0.0028296854158 |
| 질량측도 변화 `sum((w1-w0)*qt1)` | +0.0004696494283 |
| 실제 `sum(w1*qt1)-sum(w0*qt0)` | −0.0023600359875 |
| 두 항 분해잔차 | 약 −9.0e-16 |

이 역시 닫힌 flux budget이 아니다. 기존 고정 w0의 local 진단을 실제 host
두 시각의 총량 변화로 바꾸어 해석하지 않았다.

같은 nominal 05:56 슬롯에서 host–local 최대 절대 차이는 T0.01686770 K,
온위0.03829988 K, qv5.72390854e-6 kg/kg이다. 정의된 온위/Exner 분해의 잔차는
4.47e-14 K이며, 다른 endpoint convention에 배분되는 교차항 최대값은
1.45e-8 K다. 과정·forcing·분할·f32 native/f64 local 연산자의 차이가 포함되므로
이를 미세물리 가열 또는 특정 역학과정의 오차로 명명하지 않는다. NCCN 차이도
물리적 공급으로 귀속하지 않는다. 이 진단에는 추가 M/H/RTTOV 호출이 없다.

## 실제 자료에서 찾은 작은 저장 공백과 해소

원래 actual NPZ에는 최종 quality가 있지만 BT와 frozen mask가 빠졌다. Producer는
legacy `bt/mask`를 찾았고 실제 callback은 `BT_K/fixed_mask`를 기록했기 때문이다.
공개 receipt에는 이 값과 signature가 모두 있어 비용·분석의 수치 결과에는
영향이 없다. **P3 로컬 보존 연결 공백**으로 분류한다.

원래 NPZ/receipt는 수정하지 않았다. 그 digest가 맞는 public receipt의 마지막
수락점 callback에서 BT/mask/quality sidecar를 로컬에 만들고, final state hash,
mask digest와 기존 NPZ quality를 대조했다. 이것은 새 RTTOV 실행이 아니다.
다음 producer는 실제 callback 키와 기존 별칭을 읽도록 작게 수정했고, 실제
callback schema의 저장 roundtrip과 legacy alias를 포함한 집중시험10개가 통과했다.
Executed helper SHA `32391d77…`는 병합 main의 Git blob로 보존되며 현재 수정은
미래용이다. 이미 닫힌 Jo0·PH 단위·실패 단계 문제는 다시 열지 않는다.

## 남은 연구 범위

새 유효 native 입력의 한정 분석·수락 상태 보존·nominal 물리 진단은 확보했다.
Pixel UTC·CTH 기준면·공통 footprint와 과학적 채택은 아직 미확정이다. 실제
활성 제어51개에 대해 관측7개의 국소 rank 상한은7이나 실제 rank를 측정하지
않았고 모든 성분의 독립 복원이라고 표현하지 않는다. 평가 예산의 확대, 관측
시간/기하 민감도, 전체 host 시간간격·다중열·미사용 사건은 별도 후속 연구다.
현재 sigma/prior/bias와 고정 후보를 사후 변경하지 않았다.

관리용 54/75(72%)는 이번 보고에서 유지한다. Numerical case 확보는 새로운
실행 근거이며, 완전한 독립 관측 대응이나 수렴·물/열 보존 승인으로 가산하지 않는다.

[체크리스트](../CHECKLIST_pr397_actual_native_results_2026-10-10.md) ·
[실제 계산](ACTUAL_ARRAY_CALCULATIONS.json) · [기존 진단](SAVED_DIAGNOSTIC.json) ·
[Green intake](GREEN_INTAKE.md) · [Red](RED_REVIEW.md)
