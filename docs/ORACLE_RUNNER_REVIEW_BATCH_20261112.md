# Oracle 실행기 검토 보강과 수농도 좌표 계약

이 묶음은 #584의 두 비차단 보강점과 후속 후보 1–7을 같은 후보 커밋에서 검증한다. 운영 KDM 계산 소스는 변경하지 않는다. 필수 CI의 suite 범위와 `oracle pytest (f64 reference)` 이름을 보존하고, 새 호스트·RTTOV 계산 없이 실행기·진단·소스 검토를 진행한다.

## 1. 타임아웃 뒤 손자 프로세스 정리

기존 실행기는 자식 unittest 리더가 SIGTERM 뒤 먼저 종료하면 같은 그룹에 남은 손자를 다시 확인하지 않았다. 짧은 합성 재현에서 손자가 SIGTERM을 무시하고 남았다. 수정한 실행기는 자식이 시간초과되거나 정상 종료한 뒤에도 프로세스 그룹을 확인한다. 남은 그룹에는 SIGTERM과 제한된 유예 뒤 SIGKILL을 적용하고, 정상 종료 뒤 잔여 그룹을 발견한 suite도 **실패**로 분류한다. macOS의 `killpg`가 `EPERM`을 반환해도 정리 오류를 기록하고 불완전 실행 JSON을 남기도록 했다. 취소·시간초과와 PID 파일 생성 지연을 구분하는 회귀 검사를 둔다. 실제 #584 증거 suite에서 손자가 남았다는 관측은 없었다.

## 2. 연구 브랜치에서 접근 가능한 pip 다운로드 캐시

[#584의 첫 실행](https://github.com/gonos2k/KDM6AD/actions/runs/43154376935)은 pip cache miss 뒤 저장됐다. GitHub의 [캐시 접근 규칙](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching#restrictions-for-accessing-a-cache)에 따르면 PR merge-ref 캐시는 형제 PR이 직접 복원하지 못한다. 새 `oracle-pip-cache-seed` 작업은 **연구 브랜치 push에서 두 요구사항 파일 또는 seed 정책이 바뀔 때만** 같은 고정 의존성을 설치해 base-branch의 pip 다운로드 캐시를 채운다. 캐시 유무와 무관하게 후속 Oracle 작업은 설치와 버전 검사를 계속 수행한다. #583 설치 24초, #584 설치 30초였으므로 이 작업의 효과는 낮은 비용 항목으로 다룬다. seed 작업 성공과 다음 PR의 실제 cache hit·설치 시간은 각각 따로 확인하기 전에는 절감으로 계산하지 않는다.

## 3. Oracle pytest 시간·CPU·메모리 계측

`harness/ci_diagnostics/profile_pytest.py`는 기존 `python -m pytest -rs -q` 선택을 유지하고 `--durations=30`만 추가한다. GNU/Linux의 `wait4` 자식 사용량에서 벽시계·user/system CPU·최대 RSS(KiB)를, pytest 출력에서 느린 setup/call/teardown 구간을 기록한다. Darwin의 RSS 단위는 bytes로 명시한다. 이는 **pytest 자식 프로세스 기준**이며 동시에 실행된 다른 CI 작업의 총 메모리 피크가 아니다. 실패·취소 시 원래 종료 상태와 래퍼 판정을 분리해 기록하고, SIGTERM을 받아 0으로 끝나는 자식이나 출력 파이프를 닫은 잔여 손자를 성공으로 취급하지 않는다. 실제 느린 테스트와 자원 수치는 변경 후 CI artifact에서 판정한다.

## 4. 느린 세 suite의 1-worker/2-worker 좁은 비교

#584에서 일반 모드 경과시간이 긴 `native_nr16_vjp_fd`, `native_d1_coeres_upstream_cpp_ad`, `native_nc16_fd_expanded` 세 suite만 같은 로컬 Mac에서 연속 실행했다. [비합격 원자료](../harness/evidence/oracle_runner_worker_probe_2026-11-12/README.md)의 1-worker 실행은 **25/25 통과, 409.722초, skip 0**이었다. 2-worker 실행에서는 coeres 13개와 NC16 6개가 통과했지만 NR16은 **300초 시간 제한**에 걸렸다. 당시 실행기의 macOS 프로세스 그룹 조회가 `EPERM`을 내어 완성된 두 worker 결과 JSON도 남기지 못했다. 이 예외는 합성 회귀 검사로 수정했으며, **비싼 실험을 더 긴 제한시간으로 재시도하지 않았다**. 따라서 1-vs-2 결과 일치와 속도 향상은 `INCONCLUSIVE`다. 로컬 Python 3.10/Torch 2.13/NumPy 2.2의 이 단일 표본을 hosted Ubuntu Python 3.12/Torch 2.8 CI 성능으로 옮기지 않는다.

## 5–6. 승인된 skip과 실행 출처

명시적으로 허용하는 skip은 비공개 타일·DSO가 필요한 기존 세 테스트의 **정확한 테스트 ID와 사유**뿐이다. 그 검사가 자료 제공으로 통과하는 것은 허용하지만, 새로운 skip이나 사유 변화는 필수 작업 실패로 처리한다. 일반·최적화 모드는 같은 등록 목록을 사용하고, 모든 자식의 종료·테스트 수·skip·시간초과·미실행을 검사한다.

모드별 실행 artifact에는 Git HEAD 커밋·tree, 등록 목록 SHA, Python 버전·실행 경로, worker 수·suite 제한시간, GitHub run/attempt를 기록한다. CI에서 `GITHUB_SHA`와 실제 checkout이 어긋나거나 출처가 빠지면 실행 전에 거부한다. 이는 저장된 로그를 어느 코드·목록에서 만들었는지 연결하는 조건이며, 비공개 원본 바이너리의 출처 인증을 대신하지 않는다.

## 7. NC/NI/NR/NCCN의 raw 좌표와 Registry 표기

[소스 검토](../harness/evidence/native_number_coordinate_contract_2026-11-12/report.md)는 active private Registry가 네 수농도 필드를 `#/kg`로 선언하고, mp137 wrapper가 NN/NC/NI/NR을 **별도의 `rho_d` 변환 없이** `c_float`로 포장해 legacy C ABI에 넘긴 뒤 결과도 직접 되돌리는 경로를 확인한다. 첫 단계 NN의 별도 초기화와 수상체별 소비 경로를 필드마다 기록한다. 반면 `dry_number=1`은 `rho_d=rho/(1+qv)`의 입출력 변환을 명시적으로 적용하는 **별도 opt-in 맵**이며, 내부 수농도 cap·문턱의 숫자는 그대로다. Registry의 `#/kg` 표기만으로 건조 공기 질량당인지 습윤 공기 질량당인지, 또는 legacy 내부 raw 좌표의 물리적 체적 기준이 정확히 무엇인지 확정하지 않는다. 따라서 #580의 저장 단어를 새 단위로 소급해 재해석하지 않고 물리 단위 판정을 `INCONCLUSIVE`로 유지한다.

후속의 같은 열 계측 묶음에는 이미 준비된 [공통 캡처 계획](NATIVE_HOST_COLUMN_SHARED_CAPTURE_PLAN_20261112.md)을 사용한다. 장시간 실험 재개 기능과 C++ 컴파일 캐시는 이 후보 묶음의 실제 결과·재사용 조건을 확인한 뒤 별도로 평가한다.
