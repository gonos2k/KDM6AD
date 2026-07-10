"""v9 전 도메인 all-sky dual CVT 분석 — 캡 축소 스모크 게이트.

전체 J-부분공간 실행(수십 분)의 축소판: cloudy 12 + clear 50, 2 워커,
max_iter=2. 게이트: J 하강, O−A ≤ O−B, hydrometeor 증분 비영, 보고 dict의
캡 정직 기록. 외부 자산 4종(LC05/GK2A/검정/live cloud RTTOV) 없으면 skip.
"""
from __future__ import annotations

import json

import pytest
import torch

from test_real_innovation_lc05 import _CAL, _GK2A, _WRFIN, needs_all


@needs_all
def test_fulldomain_smoke_capped(tmp_path):
    import numpy as np
    from kdm6.da_fulldomain import run_fulldomain_analysis
    from kdm6.io.frame_reader import read_wrfout_frame
    from kdm6.obs.gk2a_l1b import (CLEAN_IR_CHANNELS, load_cal_table,
                                   read_ko_slot, slot_files)
    from kdm6.obs.obs_ingest import payload_to_column_obs
    from kdm6.obs.rttov_case_writer import fixture_layer_pressure
    from test_rttov_case_writer import (_CHANNELS, _HAVE_CLOUD_EXE,
                                        _fixture_p_half, _fixture_tq)
    if not _HAVE_CLOUD_EXE:
        pytest.skip("live cloud RTTOV (ami_cloud) 부재")

    fr = read_wrfout_frame(str(_WRFIN), 0)
    cal = load_cal_table(_CAL)
    pl = read_ko_slot(slot_files(_GK2A, "202507190000",
                                 channels=CLEAN_IR_CHANNELS), cal, stride=8)
    co = payload_to_column_obs(pl, fr.meta["lat"], fr.meta["lon"],
                               max_dist_km=4.0)
    tr, qr = _fixture_tq()
    grids = dict(p_lay=fixture_layer_pressure(), p_half=_fixture_p_half(),
                 t_ref=tr, q_ref=qr)

    rep = run_fulldomain_analysis(
        fr, co, grids, str(tmp_path / "v9smoke"),
        n_workers=2, max_iter=2, max_cloudy=12, max_clear=50,
        channels=_CHANNELS)

    json.dumps(rep)                                     # 보고 직렬화 가능
    assert rep["n_cloudy"] == 12 and rep["caps"]["max_cloudy"] == 12
    assert rep["n_valid"] > 0
    assert rep["j_trace"][-1]["total"] < rep["j_trace"][0]["total"]
    assert rep["oma"] <= rep["omb"], (rep["oma"], rep["omb"])
    hydro = max(rep["increment_norms"][f] for f in ("qc", "qi", "qs", "nc"))
    assert hydro > 0.0, "hydrometeor 증분 전무"
    for f in ("qr", "qg", "nr", "nccn", "bg"):          # 기본 제외 필드 pin
        assert rep["increment_norms"][f] == 0.0, f
