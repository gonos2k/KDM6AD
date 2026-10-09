# PR395 병합본 팀 재점검

기준 main `e74cf3fa`, 검토한 PR395 head `f447477d`. Green/Red가 실제 생산
입출력 schema와 신규 연구 도구의 연결을 독립 추적했다. 아래 재현은 격리된
합성 파일/배열/예외 주입이며 실제 native/RTTOV 실행으로 합산하지 않는다.

| ID | 발견 | 범위 | 해소/확인 |
| --- | --- | --- | --- |
| A1 | CLI intake 경로를 바꿔도 builder가 기본 경로 hash를 읽음 | 조건부 연구 실행기 통합 오류; 예정 default 경로는 영향 없음 | validated binding만 main에서 전달. 기본 파일 없는 override 합성 경로 확인 |
| A2 | receipt의 post-link 정리 예외 후 success 파일만 남고 checkpoint 삭제 가능 | 연구 산출물 publication 경계 | receipt commit 후 임시 alias 정리는 best-effort. private NPZ hash는 link 전 계산. fault injection에서 두 산출물 일관성 확인 |
| A3 | ncmin 출처가 실행 archive 대신 복원된 case namelist | 출처 기록; 실제 현재 값은 두 파일 모두10/10 | archive의 실행 namelist를 읽고 hash 기록. 다른 두 파일 값 반례 확인 |
| A4 | runtime signature가 검증되지만 최종 저장에서 빠짐 | 내구성 있는 감사 근거 | final trace의 signature·7개 count·frozen mask hash를 private/public에 연결 |
| A5 | masked QNCCN이 유한 fill로 변환돼 finite 검사 통과 | 조건부 신규 reader 입력 경계 | 필수 **선택 hyperslab**의 mask/fill/nonfinite를 변환 전 거부. 실제 새 cell에 결측이 있다는 주장은 없음 |
| A6 | 저장 실패를 minimizer 미반환으로 표시하고 raw optimizer arrays를 public failure에 포함 | 실패 단계/저장 경계 | RETURNED_BUT_CAPTURE_FAILED와 stage 구분. raw arrays 제외; shape/hash만 보존 |
| A7 | 유효 종료/8개 Times만으로는 adaptive 실행을 고정 dt로 볼 수 없음 | 실행 설정 출처 | archived effective dt/flag와 실제 producer schema를 검증. CLI fixed_dt flag 자체는 효과와 분리 |
| A8 | zero-mask 품질 probe 비용 0을 초기 Jo로 보고 | P2 연구 비용 기록 | 실제 첫 zero-control closure의 Jo/Jb/Jtotal과 고정 signature를 보존. Probe의 원래 비용은 별도 기록하고 저장 BT·고정 mask로 교차 확인 |
| A9 | PH/PHB를 Pa로 표기 | P3 단위 메타데이터 | m² s⁻² 지오포텐셜로 수정. 값·압력 배열·과거 기록은 변경하지 않음 |
| A10 | 이미 계산한 host 건조층 질량을 저장하지 않음 | 물리 해석용 로컬 자료 보존 | native REAL(4) [8,39] 및 첫 시각 [39] 배열을 저장. EOS rho×dz로 대체하지 않음 |
| A11 | host와 국소 KDM을 같은 연산자로 해석할 위험 | 후속 진단 준비 | 저장 배열만 사용하는 비교 실행기를 준비. Exner 항과 온위 항, 고정 질량측도의 분석·적분 물 변화 분리. 실제 결과는 아직 대기 중 |

미세물리·AD·원래 solver의 새 필수 P1/P2 결함은 이 점검에서 확인하지 않았다.
도구의 조건부 통합/저장 오류와 출처 보완은 실제 모델/관측 결과의 정확도 승인과
구분한다. 기존 MPI·거리·소산·국소 미분·all-sky/parameter pin의 종결을 유지한다.

native PID99158은 계속 진행 중이다. 수정 전에 아직 consumer가 실행되지 않은
대기 v2를 철회했으며 추가 비용/단위 검토 때 미실행 v3도 철회했다. 모델은
중단/재시작하지 않았다. 수정 소스 검증과 새 pin 뒤 v4가 동일한 native 완료를
기다린다. 정상 종료·실제 8개 Times·최종 필드가
확인되기 전에는 intake/분석을 실행하지 않는다. 과거 invalid 자료는 그대로다.

선택 QA의 한정 해석은 유지하며 pixel UTC·CTH datum·공통 footprint·물리적 채택은
미완료다. 54/75(72%)는 유지한다. 테스트/문서 수로 새 science 완료를 가산하지 않는다.
