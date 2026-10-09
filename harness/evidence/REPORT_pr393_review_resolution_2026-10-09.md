# PR393 심층 검토의 항목별 해소

기준은 병합 main `ce77afa2`와 아직 미병합인 PR393 head `c543b98c`다.
이후 해석·준비 기록은 새 실제 기상 사례나 물리식 변경과 구분한다.
[체크리스트](CHECKLIST_pr393_review_resolution_2026-10-09.md)에 진행 상태를 연결한다.

## 1. 기존 품질 검사와 현재 실패 정책

고정 S의 trial 품질 검사는 기존 근거에서 종결을 유지한다. all-sky 내부에서 일부
비용/수반 계산이 이미 수행될 수 있지만, 품질 위반 시 유효 ObsEvalResult를 밖으로
발행하지 않는다. 기존 7채널·sigma=1 K·bias=0·물리·solver·legacy 동작을 바꾸지 않는다.

현재 실패 정책은 **중단·성공 산출물 미발행**이다. 설치된 PyTorch **2.13.0**의
독립 1차원 합성 LBFGS 실험에서 closure는 x=0, x=1에서 호출됐고, x>0.5에서
발생한 예외 뒤 x=1이 남았다. 사용자 검토의 2.10.0 실험과 별도의 빌드다.
이는 프로젝트의 실제 T/Q 최적화가 아니며, 다른 Torch 버전의 동작까지 인증하지 않는다.

두 기존 최소화기는 opt.step 정상 반환 이후에 수락점 audit/result를 만든다.
full-domain은 finally에서 pool을 닫고 예외를 전달한다. 따라서 실패 객체를 수락점으로
복원됐다고 가정해 계속 사용하지 않는다. 작은 탐색 실험도 fail-closed로 시작할 수
있으므로 복원/retry를 새 필수 수정으로 추가하지 않는다. 향후 요청할 경우 수락 제어·
optimizer 상태·명시적인 품질실패 종류·재시도 한계와 종료조건을 먼저 정해야 한다.

[소스 감사·합성 실험](pr393_optimizer_failure_2026-10-09/RED_review.md)에 설치 버전,
소스 해시, 실제 예외 경로 및 범위를 기록했다. 일반 ValueError를 삼키는 생산 처리나
새 solver를 구현하지 않았다.

## 2. 포화잔차의 부호 교대와 감쇠

clamp/cap가 비활성이고 p 및 열역학 상수를 고정한 물 포화식에서

\[
q_s=\epsilon\frac{e_s}{p-e_s},\qquad
\frac{\partial q_s}{\partial T}
=q_s\frac{p}{p-e_s}
\left(-\frac aT+\frac{bT_{tp}}{T^2}\right).
\]

활성화 적용량 a 뒤의 상태에서 g=qv−qs, A=L/cp라 두면,
현재 적용량 c=g/Dimpl 및 T⁺=T+A c에 대해 국소적으로

\[
g^+=\left(1-\frac{D_{exact}}{D_{impl}}\right)g+O(g^2),
\quad D_{exact}=1+A\frac{\partial q_s}{\partial T}.
\]

여기서 L/cp는 **해당 호출에 포착된 값을 고정**한다. Dexact는 이 조건의 포화식
정확 미분 분모이지 전체 KDM/열역학 연산자의 정확 Jacobian이라는 뜻이 아니다.
기존 Dimpl의 left-associated 연산 순서를 보존해 재계산했다.

| 5초 호출 | Dimpl | Dexact | 선형 예측 g⁺/g | 저장 endpoint g⁺/g |
| --- | ---: | ---: | ---: | ---: |
| 2 | 3.630693760813 | 3.707384080121 | −0.021122772770 | −0.021023471024 |
| 3 | 3.630022709881 | 3.706670897179 | −0.021115071013 | −0.021117159265 |

세 번째 호출의 차이는 약 2.0883e−6이다. 첫 호출은 큰 유한변화여서 비율 예측
−0.02081과 endpoint −0.02484의 차이가 더 크다. 네 번째의 매우 작은 잔차 비율은
roundoff에도 민감하다. 이 사례의 약 2.1% 감쇠 진동은 근사 분모와 양립하지만,
전체 안정성·약 6차 시간수렴·새 생산 산술 결함을 입증한 것이 아니다.

[공개 receipt 재구성](pr393_satadj_residual_2026-10-09/GREEN_review.md)은 두 공개
JSON만 읽으며 새 KDM 적분·RTTOV·native forecast·NPZ를 사용하지 않았다. a/c는
기존 자료에서 재구성한 적용량이며 미보관 내부 rate를 새 계측값으로 부르지 않는다.
물/잠열 잔차도 포착된 satadj 단계에만 한정한다. 정확 미분 분모나 root solve로의
교체는 다른 연구변형으로 유보하며 기존 legacy/normalized 계산을 바꾸지 않는다.

별도로 실제 `compute_qs_water()`의 scalar AD를 네 포착 온도에서 실행해 해석 미분과
대조했다. 최대 상대차는 2.14e−15이며, [소스 확인 receipt](pr393_satadj_residual_2026-10-09/SCALAR_source_check.json)에
Torch 버전·소스 해시를 기록했다. 이 확인은 전체 KDM 적분/미분 검증이 아니다.

## 3. 수농도와 실제 다음 실험

기존 20/10/5초 자료의 첫 활성화량과 +1e8 m⁻³ 하한 복원은 모두 같다. 호출 사이
NCCN 체적값의 변화는 dry-density 재평가와 구분한다. 양의 과포화 gate가 켜져도
F≤Nc/(Nc+NCCN)이면 실제 활성화량은 0이다. 현재 하한은 경험적 하한 유지가
포함된 탐색 모형으로 명시하며 유한 reservoir 보존이나 관측된 외부 CCN 공급으로
승격하지 않는다. 하한의 물리 채택은 R1/D3에서 남겨 둔다.

[관측·목표실행 준비](pr393_observation_scope_2026-10-09/SUMMARY.md)에서는 현재
후보의 확인값·가정·미확정 조건을 나누고, 원래 IC부터 새 독립 실행을 준비한다.
관측 QA/시간/시차/footprint 미완료는 명목 좌표 진단의 해석 범위를 제한하지만,
새 모델 실행 자체를 막는 영구 선행조건은 아니다. 과거 invalid forecast를 재시작
입력으로 바꿔 유효성을 소급 승인하지 않는다.

격리 case는 `/private/tmp/KDM6AD-pr393-target-preparation-20261009/case_nominal`에
실제로 준비했다. 원래 IC/경계/chain 입력과 79개 curated 정적 링크·실행파일 링크,
독립 namelist·빈 출력 영역을 확인했다. forecast/restart/RSL/output 링크는 없다.
[준비 receipt](pr393_target_preparation_2026-10-09/PREPARATION.md)의 과거 빌드 head와
현재 검토 head는 구분하며 이번 preflight는 과거 receipt와 소비할 파일을 대조한 것이다.
새 c543 빌드나 실제 runtime load를 확인한 것은 아니다. 전체 private host-tree 해시를
새 실행의 추가 선행조건으로 만들지 않았다. 장시간 실행 범위 질문의 응답을 기다리며
아직 실행하지 않았다.

[실제 제한 T/Q 분석 명세](PR393_limited_analysis_spec_2026-10-09.md)는 Jb+Jo,
사전 선언 제어/prior·고정 S·증분·분기·최종 재평가·실패 상태를 함께 기록하도록 한다.
기존 CVT 시작값 th_sigma=0.8 K(온위), qv_sigma=0.08(log-space), lower 12층은
관측 sigma=1 K와 별개이며 검정된 B가 아니다. −0.8 K what-if를 배경으로 다시
부르지 않고 초기 제어 0을 기준으로 한다. 새 유효 native/명시된 관측 시나리오와
실행 범위를 정하기 전 실제 분석을 했다고 주장하지 않는다.

## 4. 완성도 배점과 남은 완료 조건

[관리용 배점 기록](pr393_completeness_2026-10-09.json)은 **사용자 제공 검토자의
5영역×15점 평가**를 출처로 명시한다. 합계/환산 산술은 이전 49/75=65.3%,
main 53/75=70.7%, PR393 반영 54/75=72.0%다. 이번 재구성·문서 정리에는 추가
점수를 주지 않는다. 배점은 주관적 관리 지표이며 정확성 확률·코드 커버리지·남은
시간 비율이 아니다. 약 70–75% 수준으로만 읽고 배포·릴리스·무인 운영을 분모에
추가하지 않는다.

남은 핵심 결과는 새 정상 목표시각 native 상태, 설명된 독립 관측 대응, 그 사례의
실제 T/Q 분석, 전체 host 시간간격, native 다중열·미사용 자료 검증이다. 공식
D1–D4/R1/R2/S17은 하위 산술 확인의 완료로 자동 종결하지 않는다.

## 검증과 공개 범위

새 산술 reader 및 합성 optimizer probe의 receipt/source/version를 연결하고,
Green/Red 교차점검과 구문·JSON·정적 검사·graph semantic 갱신을 기록한다.
기존 179 passed/2 skipped와 PR393 c543b98c의 5개 성공 CI는 이전 head의 근거다.
새 원자료 기반 실험·전체 pytest·native 빌드의 수행을 주장하지 않는다.
공개 변경에는 작성한 진단 소스·파생 결과·검토 문서만 포함한다. private host 입력,
전체 State/Forcing·NetCDF·RTTOV 라이선스 자산·바이너리는 포함하지 않는다.

[최종 Green](pr393_final_review_2026-10-09/GREEN_review.md)과
[최종 Red](pr393_final_review_2026-10-09/RED_review.md)가 범위·counterexample·출처를
대조했다. 과거 빌드 source-head 표현의 모호성은 수정했다. 새 생산 P1/P2 결함이나
기존 물리식의 필수 변경을 입증한 결과로 확대하지 않는다.
