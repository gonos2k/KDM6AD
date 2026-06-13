"""P4 — RttovInput 직렬화 (설계 §7, §14.3).

`pack_rttov_input`은 이미 RTTOV-unit인 torch 텐서를 RTTOV가 받는 numpy RttovInput으로 **직렬화만**
한다(단위변환 없음 — 변환은 model_profile_builder에서 끝남). 강제 config(§4.6/§14.5):
adk_bt=True, store_rad=True, GasUnits=2, MmrHydro=False, ClwdeParam/IcedeParam=user(Deff 입력).

STUB — 미구현.
"""
from __future__ import annotations


def pack_rttov_input(rttov_tensors, rttov_config):
    """RTTOV-unit torch 텐서들 → numpy RttovInput(profile + cloud + chanprof + options +
    geometry + surface). 단위변환 없음. config-hash는 방어적 assert(§14.2)."""
    raise NotImplementedError("P4 input builder — 설계 §7/§14.5")
