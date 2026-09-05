# 독립 metric/trajectory 비교 계약 체크리스트

사용자 검토 기준은 PR #206 병합 `8bbacfc7`; 수정 시작은 PR #207 `51ddb89`다.
기존 세 P1(적용 계면 공통 검증, 전체 잔차 분해, CCN 호출 정책)은 해소 상태를 유지한다.
이번 범위는 독립 분석·raw 재사용의 비교 계약과 설명이며 운영 f32/AD ABI는 포함하지 않는다.

| ID | 요구 | 상태 / 완료 기준 |
| --- | --- | --- |
| MT1 | 요청 ↔ 기록의 nsplit/mode/width/profile 검증 | 완료 — 기존 `validated_run_identity(with_calls=True)` 재사용, raw와 실제 subprocess 수집 경로 시험 |
| MT2 | 기준 ↔ arm의 알고리즘/전달 metric/시간/층수/타일/정밀도 일치 | 완료 — 밀도 profile만 개입값, adaptive substeps는 계면 대응으로 판정 |
| MT3 | raw 출처를 재실행으로 표시하지 않음 | 완료 — `provided raw` / `bundle member` / `re-run` 구분, 제공된 baseline과 실제 raw의 동일성 검사 |
| MT4 | 가중치 우선 교차항과 offset 설명 | 완료 — 식 유지, 순서에 따른 배분 반례와 주석 대조 |

## 구현과 검증 범위

비교 검증은 독립 `analysis()` 진입점에 둔다. 기존 run matrix 수집 경로와 직접 `raw=`
경로가 모두 통과하며, 각 arm은 strict parse 한 번에서 식별자와 실제 적용 계면을 얻는다.
`interface_terms()`와 `decompose()`는 피연산자 추출·산술 함수이고, 실험 간 비교의
조건 검증은 `analysis()`의 책임임을 명시한다. 정식 번들의 기존 추가 검증도 유지한다.

기존 식별자에는 strict parser가 확인한 `real_bytes`를 추가했다. `delt`가 같아도
inner loop 수가 달라 `dtcld`가 다른 경우, 같은 column/타일 수라도 실제 타일 범위가
다른 경우를 거부한다. 알고리즘과 전달 metric은 기존 registry 관계도 검증한다.
고정된 profile 이름을 모든 arm에 복제한 기록과 빠진/추가된 arm도 거부한다.

가중치 우선 반례는 `W=-.50`, `T=+.75`, 전체 변화 `+.25`를 확인한다.
반대 순서의 `W=-.25`, `T=+.50`과 차이나는 교차항 `.25`는 현재 수송 반응에 배분된다.
이는 조건부 회계 분해이며 유일한 인과 기여율이 아니다. 새 분해 옵션을 추가하지 않았다.

새 portable 시험 21개는 원본 strict text parser를 사용한다. 핵심 관련 시험
**180 passed**, 전체 portable harness **1,455 passed / 58 skipped / 308 deselected**.
undefined-name lint 및 `git diff --check`도 통과했다. 새 Fortran/WRF/RTTOV 실행은 없다.
팀 기본값 `gpt-5.6-luna` / reasoning `xhigh`를 canonical·PR 양쪽 AGENTS.md에 기록했다.

독립 Luna xhigh Green·Red 재검토에서 요청한 분석 경계의 P1은 발견되지 않았다.
Red가 추가로 발견한 동일한 미지원 mode 입력(P2)은 `carry`/`rezero` 지원값 검사로
해소했다. Red의 최종 새 시험 21개 재검증도 통과했다. Green이 지적한 offset의
`+1` 표현은 비율 1이라는 의미로 명확히 했다. 두 검토는 이 수정 범위의 검증이며
전체 host/AD의 모든 분기를 증명한 결과가 아니다.

실제 10분 WRF 적용량(M1), 최초 음수 QIB 피연산자(M2), 입자수 단위 계약은
별도 열린 과제다. 이번 검증을 호스트/RTTOV 재실행이나 예보 영향 측정으로 확대하지 않는다.
