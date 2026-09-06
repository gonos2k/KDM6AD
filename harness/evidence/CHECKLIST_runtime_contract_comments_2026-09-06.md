# Python runtime 설명 정합성

기준은 PR #212 병합 main `ba2b90a819fd2533905f4d9abaf4e70dbb60815d`다.
동결 AD 지원 범위 제한은 완료 상태로 유지한다. 이번 변경은 주석·docstring이다.

| ID | 우선도 | 현재 계약 | 상태 |
|---|---|---|---|
| RT213-01 | P3 | Python의 live 또는 기본값에서 변경된 파라미터는 warm-phase 묶음으로 연결된다. 기본값과 같은 frozen 파라미터는 상수 경로를 사용한다. | 설명 정정 완료 |
| RT213-02 | P3 | xland가 있으면 ncmin_tensor를 보존 예산과 autoconversion·number accretion·cloud-water riming·contact freezing·Bigg-cloud freezing gate에 전달한다. 없으면 scalar 기본값을 사용한다. | docstring 및 같은 내용의 인라인 주석 정정 완료 |

이전 설명은 파라미터가 아직 AD에 연결되지 않았고 ncmin이 보존 예산에만
적용된다고 잘못 기술했다. 실행 코드의 `_params_live` 분기와 다섯 과정률
파라미터 연결은 이미 존재했다. 이번에는 그 동작에 설명을 맞췄다.
Python 지원 범위를 C++/C ABI의 파라미터 계약으로 확대하지 않는다.

검증은 docstring을 제외한 전체 모듈 AST가 기준과 동일함을 확인했다.
기존 파라미터·ncmin 연결 시험 **7개가 통과**했다. 여기에는 단일 step 및
2단계 창의 파라미터 FD 대조, rate gate, 관측 bridge 연결이 포함된다.
새 시험은 추가하지 않았으며 로컬 전체 oracle·WRF/MPI·live RTTOV를 재실행한
것은 아니다. Ruff F821/F822/F823와 `git diff --check`도 통과했다.

PR #212 병합 커밋의 CI는 이번 재조회에서 macOS를 포함한 5개 모두 성공이다.
이는 이후 설명 수정 PR의 CI 결과와 구분한다. 원시 검증 자료는 작업 checkout의
`graphify-out/runtime-contract-comments-20260906/`에 보존한다.
M1·M2, 입자수 단위, D4와 실제 예보 성능은 별도 열린 과제로 유지한다.
