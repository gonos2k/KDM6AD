# 새 native–T/Q 결과 확인 체크리스트

기준 main `eec82d65` (PR396). 현재 작업 checkout은 같은 파일 tree의 병합본이며,
기존 consumer 소스 해시는 변경하지 않는다. 새 WRF 실행, 두 번째 대기 프로세스,
추가 solver 또는 닫힌 하위 검증의 반복을 만들지 않는다.

## 실제 확인 상태

2026-10-10 09:56 JST의 첫 확인에서 원래 harness/launcher/rank
`99148/99157/99158`, 기존 continuation `68581`, OS 종료 관찰기 `80753`이
살아 있었다. 마지막 모델시각은 `2025-07-19_05:25:00`이었다. 이 시각은 당시
진행 관찰이며 완료 근거가 아니다. Native 종료 marker, intake, 분석 receipt는
아직 없다. 실행을 중단하거나 중복 시작하지 않았다.

| ID | 확인할 결과 | 완료 근거 | 현재 상태 |
| --- | --- | --- | --- |
| R1 | 원래 native 실행의 실제 종료 | 해당 archive의 launcher `exit_code`, `experiment_valid`, `model_completed`; OS rank/launcher/harness exit는 별도로 기록 | 진행 중 |
| R2 | 새 출력과 정확한 시각 | 정상 archive의 05:55:40–05:58:00 포함 8개 실제 `Times`, 필수 선택 hyperslab 유효성 | 종료 대기 |
| R3 | 기존 intake의 실제 반환 | `INTAKE.json`, private NPZ hash, 선택 (j=86,i=48), 39층/8시각, center/interface·State/Forcing·host 질량 출처 | 종료 대기 |
| R4 | 실제 baseline | `initial_zero_control_closure`의 Jb/Jη=0, 실제 Jo/Jtotal, probe 비용과 분리, signature와 고정 7채널 | Intake 대기 |
| R5 | 한정 T/Q 분석과 수락점 audit | 같은 all-sky·고정 매개변수·prior·sigma/bias·채널의 최종 Jb/Jo/Jtotal, 반환 상태·최종 gradient·기록된 종료정보 | Intake 대기 |
| R6 | 실제 상태 보존 | xb/xa/M(xb)/M(xa), v/b_sigma/gradient·forcing·native 좌표·host mass의 private NPZ와 digest | 분석 대기 |
| R7 | 기존 저장 배열 진단 | continuation의 세 번째 consumer 결과; host/local 온위·Exner 분해와 고정 host 질량측도의 물 변화 | 분석 대기 |
| R8 | 물리적 상태 해석 | 층별 ΔT, qv 절대/상대 증분, 포화비, QC/NC, 질량측도 변화 항. 추가 M/H 없이 보존 배열 사용 | 배열 대기 |
| R9 | 독립 Green/Red 결과 대조 | 실제 receipt/배열의 일관성, 비용·수렴·물리 채택의 구분, 지원집합·관측 시나리오 유지 | 실제 결과 대기 |
| R10 | 확인 범위·미완료 항목과 PR | 실행 사실과 조건부 해석을 근거에 연결해 공개; private 전체 상태·예보파일은 공개하지 않음 | 작업 중 |

## 결과 해석의 유지 조건

- 물 변화의 분해잔차는 대수적 일관성이다. 미측정 경계·외부 flux를 0으로
  채우지 않으며 `closed_water_budget=false`를 유지한다.
- Host 두 시각의 실제 총량 변화에서는 고정 w0 혼합비 변화와
  `sum((w1-w0)*qt1)` 질량측도 변화를 구분한다. 저장된 [8,39] 질량으로 계산한다.
- Host–local 차이는 포함 과정·forcing·분할·수치 연산자의 차이다. 온위/Exner
  좌표 분해를 잠열 또는 특정 역학과정의 기여로 단정하지 않는다.
- 실제 활성 제어 수는 새 상태에서 읽는다. 관측이 7개면 국소 Jacobian의
  rank 상한은 7이지만 실제 rank나 각 상태의 식별성을 새로 측정했다고 하지 않는다.
- 비용감소와 최종 control gradient를 함께 읽는다. 반복 한도나 정상 반환만으로
  수렴을 선언하지 않으며, optimizer가 직접 알려주지 않은 종료 이유는 UNKNOWN이다.
- nominal 시각·고정 후보·7채널·1 K/0 bias·선언된 T/Q prior를 유지한다.
  구름 생성이나 작은 잔차를 사례 채택조건으로 삼지 않는다. Pixel UTC,
  높이 기준면, footprint와 검정된 B/R은 현재 미확정 범위로 남긴다.

관리용 점수는 결과를 검토하기 전까지 54/75(72%)를 유지한다. 진행시간,
문서·시험·PR 개수 또는 예정된 결과로 가산하지 않는다.
