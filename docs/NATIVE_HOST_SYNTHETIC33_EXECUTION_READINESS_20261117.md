# Synthetic33 A7 실행 준비 경계 — 2026-11-17

이 문서는 PR #593의 `5af74e71` 연구·합성 검증 패킷 이후 실행 준비 변경의 범위를 기록한다. #593의 운영 `libtorch/`, `oracle/`와 A7 C++ 소스는 이 패킷에서 변경하지 않는다. 기존 CI와 A7 빌드 영수증은 소스·빌드 자산의 근거이며, A7 KDM 계산 또는 33회 실측의 근거가 아니다.

## 현재 확인한 사실

- 고정 계획은 합성 fixture 3개, forward 33회, 최대 graph primal 9회·JVP 18회·VJP 9회다. 전체 wall 한도 900초에는 정리 예약 28초가 포함되고, 4 GiB는 표본 RSS 중단 기준이다.
- 부모 감독자는 성공 후보의 자산·종료·replay를 독립적으로 재검사하고, 성공한 경우에만 자산 완료 witness를 발급하도록 구현돼 있다. 실제 실행 플래그는 여전히 꺼져 있다.
- Darwin 무모델 시험에서 release 뒤 orchestrator가 비정상 종료하면, 살아 있는 watchdog은 worker 그룹의 종료·정리를 관측하고 결과를 `INCOMPLETE`로 남긴다.
- 부모의 단일 시도 기록은 승인 manifest에 명시한 정규 경로의 기존 디렉터리에 `O_EXCL`로 만든다. 같은 바이트의 manifest를 다른 위치에 복사해도 같은 기록 파일에 충돌한다. 등록이 중단된 경우에도 기록을 지우지 않고 재시도를 막는다. 이는 trusted-code 절차이며, 동일 사용자의 기록 삭제·디렉터리 교체를 막는 OS 인증 장치로 해석하지 않는다.
- 후속 Draft PR의 fake CI는 `research/atomic-consumer-contract`를 병합 대상 브랜치에 추가한다. 기존 synthetic33 경로 필터와 macOS 무모델 시험만 사용하며, A7 빌드나 실제 33회 호출을 이 workflow에 넣지 않는다.
- watchdog 사망을 주입한 Darwin 무모델 시험은 release 뒤 부모가 `UNWITNESSED`와 `cleanup=UNVERIFIED`를 반환한 후에도 시험용 worker가 응답할 수 있음을 확인한다. 이 worker는 시험용 채널을 통해 자체 종료한다. 실제 경로에서 watchdog이 사라지면 worker가 남을 수 있어 실행 전 정리 조건은 여전히 미충족이다.
- `worker_result.json`의 fixture별 미분 행은 `PRELIMINARY`로 표시한다. 계측 보고의 판정은 부모가 대조한 `completion_candidate.json`의 `validated_assets.offline_replay.rows`에서 읽는다.

## 첫 A7 호출 전 필요한 근거

1. 최종 Python 소스 경로·해시와 33개 입력, DSO·Torch·interpreter·census·loader 정책, 단일 시도 기록 디렉터리, query·시간·메모리 상한을 담은 새로운 private manifest를 독립적으로 검토한다. 이전 후보의 절대 source 경로는 삭제된 임시 작업 트리를 가리키고 `attempt_registry_root`도 없으므로 그대로 사용할 수 없다. 검토 후보 상태를 단순 변경해 승인하지 않는다.
2. orchestrator 실패 후 watchdog이 살아 있는 경우뿐 아니라 watchdog 실패 또는 신원 확인 불가 때의 worker 잔존과 완료 거부를 독립적으로 확인한다. 부모는 예약하지 않은 worker PGID에 직접 신호를 보내지 않는다.
3. 고정 A7 DSO가 선택한 호스트·Torch·컴파일 옵션·source snapshot과 일치하는지 재검증한다. 기존 빌드의 export와 비모델 CTest는 실제 graph selector의 존재를 입증하지 않는다.
4. 실제 worker PID에 묶인 loader/ABI trace, 33개 자산, 66개 시작·완료 event, 종료·정리 결과는 첫 제한 실행에서 수집한다. 이 실행 후 자료를 실행 전 manifest의 선결 조건으로 요구하지 않는다.

위 근거가 충족되기 전 실제 33회 실행은 `NOT READY`다. 첫 실행이 가능해져도 자산 완료와 과학적 판정은 별개이며, 누락·미연결·분기 교차·미해상 결과는 그대로 `INCONCLUSIVE`로 기록한다. 이후 native 45입력 계획과 RTTOV 1차 BT·cost 민감도 연결은 별도 증거 패킷에서 다룬다.
