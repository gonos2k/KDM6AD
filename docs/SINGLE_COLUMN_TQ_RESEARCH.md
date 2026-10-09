# 고정 단일 column의 T/Q 연구 경로

`oracle/kdm6/da_single_column.py::run_single_column_analysis()`는 기존 CVT·model
window·frozen all-sky factory·dual 최소화기를 조립하는 opt-in 연구 경로다. 기본
full-domain 함수의 배경 clear 라우팅·네 warm-parameter 결합 추정은 바꾸지 않는다.
T/Q만 바꾸어 구름 생성까지 관측하는 첫 실험에는 이 제한 함수를 사용한다.

입력은 caller가 고정 후보의 새 유효 native 상태에서 추출한 하나의 `[1,K]` State와
전체 forcing sequence, 실제 AMI10–16 `[1,7]` BT/품질, sea/land code, native pressure
grids·RTTOV reference/surface/geometry·실행 설정이다. 초기 NC/NCCN은 원자료를
보존한다. 외부 모델/reanalysis나 cloud seed로 배경을 대체하지 않는다.

```python
from kdm6.da_single_column import run_single_column_analysis
from kdm6.da_window import WindowConfig

# These objects come from the declared native/observation producer, not a
# fabricated background. pool is owned/closed by the caller; use a fresh case.
cfg = WindowConfig(
    dt=20.0, normalized_dry=True, xland=xland,
    ncmin_land=declared_ncmin_land, ncmin_sea=declared_ncmin_sea)
analysis = run_single_column_analysis(
    xb, [forcing], y_bt_10_16, y_quality_10_16, xland,
    clear_cfg, allsky_rttov_cfg, fresh_analysis_case_root,
    window_config=cfg, obs_time=1, pool=pool, n_workers=1, max_iter=1)
```

`clear_cfg`는 재사용한 factory의 설정/서명 인자다. clear 위치는 비어 있어 clear H를
평가하지 않는다. 실제 H는 all-sky로 고정되며 background cloud classification을
서로 다른 H를 선택하는 기준으로 사용하지 않는다. `obs_time>=1`의 실제 M(xb)를
먼저 계산해 관측슬롯의 background 품질을 동결한다.

th .8 K, qv log .08/lower12 이외의 State sigma는0이며 네 parameter sigma도0이다.
고정 기본 물리매개변수로 모델을 적분한다. QC/NC 등의 적분 중 반응은 초기 제어 pin과
별개이고 full-window pullback에 남는다. hidden custom params·eta/eta_pre·partition·
pseudo-RH는 사용하지 않는다. M/H의 xland/ncmin과 zero thermal blends를 일치시킨다.

모든7채널이 background에서 지원돼야 시작한다. trial은 고정 S 품질을 유지해야 하며
위반하면 exception을 전달하고 성공 result를 반환하지 않는다. automatic restoration,
retry, 사후 mask 축소는 없다. 실패 optimizer 객체가 수락점에 남았다고 가정하지 않는다.

return의 `result`는 기존 DualMinimizeResult이며 Jb·Jtheta(0)·Jo와 수락 제어의 마지막
audit를 갖는다. `metadata`는 operator routing/초기 control 수/고정 parameter prior,
성공 callback-result 및 window/audit counts를 갖는다. max_iter를 actual M/H 수로
읽지 않는다. KDM/RTTOV 내부 횟수는 None으로 표시하고 실패 attempts는 성공 수에 넣지 않는다.

native pressure centers는 전달 grid suffix와 비교하지만 native interface 원자료 정체를
helper가 인증하지는 않는다. caller의 p_half와 상층/gas/geometry 가정을 따로 확인하고
기록한다. 새 상태에 이전95.53% 포화비·51개 control을 자동 복사하지 않는다.

[해소 체크리스트](../harness/evidence/CHECKLIST_pr393_tq_integration_2026-10-09.md)와
[실행 범위](../harness/evidence/pr393_tq_integration_2026-10-09/VALIDATION.md)에 구성시험과
새 native/RTTOV 과학 사례를 구분한다. sigma/bias/prior는 탐색 가정이며 검정값이 아니다.
