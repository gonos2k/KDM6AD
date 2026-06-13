# `_rttov_reference/` — AD-RTTOV building blocks (verbatim reference copy)

자매 세션 **AD-RTTOV `scripts/`**에서 verbatim 복사(2026-06-13). upstream 원본이 canonical이며
필요 시 재동기한다(코드 디렉토리는 분리 관리 — model-side 설계 §14.1/§14.4).

| 파일 | upstream | 역할 |
|---|---|---|
| `humidity_unit_conversion.py` | `AD-RTTOV/scripts/` | qv↔RTTOV Q(ppmv moist) 변환 **공식·상수**(M_d/M_v) |
| `rttov_profile_pressure_grid.py` | `AD-RTTOV/scripts/` | RTTOV pressure-grid(half/full level) 유도·검증 |
| `kdm6ad_rttov_mapping.py` | `AD-RTTOV/scripts/` | **KDM6AD→RTTOV 변수 매핑 테이블**(t→T, qv→Q clear-sky; q*→hydrometeor candidate) |
| `rttov_ascii.py` | `AD-RTTOV/scripts/` | RTTOV ASCII 출력(radiance/BT) 파서 — subprocess `run.sh` 경로용 |

## ⚠ 사용 규약 — 이것들은 **reference**다 (torch 경로에 직접 쓰지 말 것)

이 스크립트는 전부 **scalar-float** API(`kgkg_mixing_ratio_to_ppmv_moist(float)->float`)다. 설계
§14.3-units는 단위변환·보간이 **`RttovObsOp.apply` 이전 torch 연산**이어야 grad가 leaves까지
전파된다고 요구한다. 따라서:

- **단위변환(qv→Q), 보간(W 행렬)**: 여기 공식·상수를 **torch로 재구현**한다(`model_profile_builder.py`).
  `humidity_unit_conversion`의 ∂Q/∂qv 해석식과 `rttov_profile_pressure_grid`의 log-pressure
  weight를 torch 상수 텐서로 옮긴다. 이 파일들을 직접 호출하면 grad가 끊긴다.
- **매핑 테이블(`kdm6ad_rttov_mapping`)·ascii 파서(`rttov_ascii`)**: 데이터/파싱이라 그대로 import해
  써도 무방(미분 경로 아님). 단 매핑 테이블의 hydrometeor 행은 VIS/IR 슬롯 규약(설계 §9.1)으로
  재해석 필요 — 원본의 `*_candidate`는 clear-sky baseline 기준 표기다.

verbatim 복사이므로 내용은 수정하지 않는다(upstream 재동기 가능). torch 재구현은 `obs/`의 해당
모듈에 둔다.
