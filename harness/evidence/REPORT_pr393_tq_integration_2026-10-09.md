# PR393 e619 두 T/Q 통합 공백 — 제한 연구 경로

검토 기준은 e6198816이다. 추가한 연구 경로는 기존 full-domain 기본 계산을 바꾸지
않고 두 조건부 P2를 해소한다. 기존 clear 경로·물리매개변수 결합 추정이 본래 잘못된
것이라고 판단하거나 과거 실제 분석 오류로 소급하지 않는다.

작업 중 PR393이 병합돼 후속은 그 main 기반 별도 PR로 제출한다. 원래 검토 시점의
main53/75·PR39354/75와 현재 병합된 main54/75를 구분한다. 후속 점수 추가는 없다.

## 의도한 계산과 코드 연결

새 [run_single_column_analysis](../../oracle/kdm6/da_single_column.py)는 하나의 caller
제공 native column과 forcing window를 받아 기존 하위 API를 조립한다.

| 구성 | 실제 연결 |
| --- | --- |
| 관측 연산자 | allsky_pos=[0], clear_pos=[] 고정. 모델 배경 분류는 metadata로만 보존 |
| 품질 기준점 | 고정 기본 매개변수로 계산한 실제 관측슬롯 M(xb); obs_time≥1 |
| 초기 State 제어 | make_default_cvt: th .8 K, qv log .08/lower12, 다른 sigma 모두0 |
| 물리매개변수 | default_param_prior(active=()): 네 effective sigma_log=0, 기본값 고정 |
| Model pullback | 기존 full forcing window·initial th/qv projection. 출력 QC/NC 등 반응은 고정하지 않음 |
| 목적함수 | 기존 run_dual_minimizer의 Jstate+Jtheta+Jobs, zero control 시작·수락점 final audit |
| 관측 정책 | AMI10–16 7/7 배경 지원 필수, strict trial 검사·signature 유지 |
| 제외한 구성 | custom params/eta/eta_pre·partition·pseudo-RH·구름 seed·새 solver 없음 |

M/H의 xland·ncmin을 일치시키며 native center pressure suffix와 0-octave thermal
profile 조건을 확인한다. p_half는 전달된 값을 보존하고 grid 길이를 확인하지만,
helper만으로 native interface 원자료의 정체를 인증할 수 없다. caller가 실제 native
interfaces와 RTTOV 상층 reference·geometry·surface·source를 따로 확인해야 한다.
형상·인터페이스 설정 확인은 물리 admission이나 QA 채택이 아니다.

기존 run_fulldomain_analysis는 배경 clear 분할과 .2/all-active 네 물리매개변수를
보존한다. 첫 T/Q 실험은 그 함수를 그대로 호출하지 않고 새 제한 경로를 사용한다.
데이터·RTTOV 실행 설정·pool은 caller가 공급한다. 실제 설정에서는 H worker를 통해
RTTOV를 실행할 수 있지만 이번 구성시험은 그 경계를 합성 H로 대체했다.

## 직접 확인한 근거

집중시험은 실제 새 helper·frozen-support factory·dual 최소화기·두 KDM 적분을
통과한다. sensor H만 합성 함수다. 39층 시험도 synthetic shape이며 새 native 사례가
아니다. 배경이 맑아도 clear H를 호출하지 않는 fail-spy, 구름 trial의 직접 QC 수반,
네 매개변수 고정, 6/7 배경 거부와 trial 품질 예외를 확인했다.

0.8 K의 비영 합성 혁신에서 T/Q control 이동·양의 prior/관측 비용·Jtheta=0과
마지막 audit의 Jtotal=Jb+Jtheta+Jo를 확인했다. 별도 비영 제어점의 대표 방향에서는
CVT→실제 두 KDM→합성 all-sky H→Jb+Jo를 독립 중앙차분과 대조했다. 이는 기존
실제 RTTOV H∘M 검증을 다시 인증하거나 전체 Jacobian을 검사한 결과가 아니다.

대표 방향의 AD는 .24124595381474626, FD는 .2412459533784883으로 상대차
1.81e−9다. 기존의 넓은 시험 오차를 그대로 두지 않고 rel=2e−8, abs=1e−9로
확인했다. [FD receipt](pr393_tq_integration_2026-10-09/FD_result.json)에 값·설정·
소스 해시를 연결했다. 최종 집중시험12개, 관련 CVT/dual 구성84개가 통과했다.
12개는84개에 포함되므로 합산하지 않는다. 전체 pytest·native·실제 RTTOV는 로컬에서
새로 수행하지 않았다.

기존 clear factory와 .2/all-active prior의 비교 경로는 구름 직접 QC 수반이 없더라도
잠열 T/Q 비용 반응이 남음을 보여준다. high-level 분할은 소스로 추적했고 그에
해당하는 하위 factory 경로를 실행했다. full-domain wrapper 전체를 재실행했다고
주장하지 않는다. [Green](pr393_tq_integration_2026-10-09/GREEN_design.md),
[Red](pr393_tq_integration_2026-10-09/RED_review.md)와
[산술·범위 receipt](pr393_tq_integration_2026-10-09/RESULT.json)에 연결한다.

검토는 2026-10-09 자료를 기준으로 시작했고 실행 검증은 2026-10-10 JST까지 이어졌다.
기존 운영 물리·solver·full-domain 기본값을 변경하지 않았다.

## prior 비용의 조건부 해석

공개 weak-cloud 증분 Δθ=−0.8053122875524954 K를 .8 K 온위 prior로 나누면
Jb=0.506662406627이다. 기존 7채널 Jo=22.616033126543에 더한 총량은
23.122695533170이며, 원래 baseline26.588575903056 대비13.035224% 작다.
이는 원래 배경을 유지한 저장자료 산술이다. 새 native 상태의 분석·최적화 수락 결과가
아니며 v=0의 국소 solver가 그 점에 도달한다는 증거도 아니다.

수증기 +6%는 vq=ln(1.06)/.08, Jbq=.265255129216이지만 해당 receipt가 6/7
지원만 가지므로 동일한 7채널 비교의 유효 후보로 채택하지 않는다.

## 호출량·실패와 다음 단계

max_iter는 실제 M/H 호출 횟수가 아니다. helper는 성공한 non-None callback 결과,
기존 window/final-audit counter를 보고한다. 직접 KDM/RTTOV 내부 횟수는 미계측 None이다.
예외가 발생하면 성공 결과가 반환되지 않으므로 실패 attempts를 성공 callback 수에
포함하거나 자동 복원·retry가 있었다고 보고하지 않는다. fail-closed를 유지한다.

새 목표시각 native case는 여전히 prepared/not launched이며 기존 실행 범위 응답을
기다린다. 성공한 새 상태의 포화·실제 control mask·7채널·native interfaces/가정을
다시 확인해야 한다. 원래 후보·1 K·0 bias와 관측 시나리오를 유지하며 QA/R2·물리
채택·전체 host 시간간격·다중열·미사용 검증은 OPEN이다. 관리용53/75·54/75에도
이 구성 구현·시험 수만으로 추가 점수를 주지 않는다.
