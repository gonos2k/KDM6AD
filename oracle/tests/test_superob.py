"""superob 전처리 검증 — GK2A → 모델격자 사상의 순수/실데이터 게이트."""
from __future__ import annotations

from pathlib import Path

import pytest
import torch

from kdm6.obs.obs_ingest import ObsPayload
from kdm6.obs.superob import (load_superobs, save_superobs,
                               superob_to_model_grid, superob_with_mapping)

_F64 = dict(dtype=torch.float64)
_REPO = Path(__file__).resolve().parents[2]
_GK2A = _REPO / "GK2A"
_CAL = _REPO / "oracle" / "kdm6" / "obs" / "data" / "gk2a_ami_cal_202507190000.json"
_WRFIN = Path("/Users/yhlee/KDM6AD+/KIM-meso_v1.0/test/"
              "ss_real_case_20260619_063620/SS/wrfinput_d01")
needs_real = pytest.mark.skipif(
    not (_GK2A.is_dir() and _CAL.exists() and _WRFIN.exists()),
    reason="GK2A / cal / LC05 wrfinput 부재")


def _payload(lat, lon, bt_vals, quality=None, nch=2):
    n = len(lat)
    bt = torch.zeros((n, nch), **_F64)
    bt[:, 0] = torch.tensor(bt_vals, **_F64)
    bt[:, 1] = torch.tensor(bt_vals, **_F64) + 1.0
    q = torch.zeros((n, nch), **_F64) if quality is None else quality
    return ObsPayload(bt=bt, obs_quality=q,
                      lat=torch.tensor(lat, **_F64), lon=torch.tensor(lon, **_F64))


def test_superob_cell_mean_and_min_pixels():
    """셀 평균이 정확하고, min_pixels 미달 셀은 quality=1."""
    glat = torch.tensor([35.0, 36.0], **_F64)
    glon = torch.tensor([125.0, 125.0], **_F64)
    # 셀0 주변 3화소 (250/252/254 → 평균 252), 셀1 주변 1화소 (min_pixels 미달)
    pl = _payload(lat=[35.001, 35.002, 34.999, 36.001],
                  lon=[125.0, 125.001, 124.999, 125.0],
                  bt_vals=[250.0, 252.0, 254.0, 260.0])
    so = superob_to_model_grid(pl, glat, glon, max_dist_km=4.0, min_pixels=3)
    assert float(so.bt[0, 0]) == pytest.approx(252.0)
    assert float(so.obs_quality[0, 0]) == 0.0
    assert float(so.obs_quality[1, 0]) == 1.0          # 화소 1개 → 미충족
    assert float(so.n_pixels[0, 0]) == 3.0
    assert so.n_dropped_far == 0


def test_superob_quality_pixels_excluded_and_far_gate():
    """플래그 화소는 평균에서 배제; max_dist 밖 화소는 far-drop 집계."""
    glat = torch.tensor([35.0, 36.0], **_F64)
    glon = torch.tensor([125.0, 125.0], **_F64)
    q = torch.zeros((5, 2), **_F64); q[1, 0] = 1.0     # 화소1의 ch0만 플래그
    pl = _payload(lat=[35.001, 35.002, 34.999, 35.0, 20.0],
                  lon=[125.0, 125.001, 124.999, 125.002, 100.0],
                  bt_vals=[250.0, 999.0, 254.0, 252.0, 300.0], quality=q)
    so = superob_to_model_grid(pl, glat, glon, max_dist_km=4.0, min_pixels=3)
    assert float(so.bt[0, 0]) == pytest.approx(252.0)  # 999 배제 (250+254+252)/3
    # ch1은 화소1도 quality-0 → 4화소 평균 (251+1000+255+253)/4
    assert float(so.bt[0, 1]) == pytest.approx((251.0 + 1000.0 + 255.0 + 253.0) / 4)
    assert so.n_dropped_far == 1


@needs_real
def test_superob_full_model_domain_real():
    """실데이터: GK2A 00 UTC 전화소 → LC05 전 도메인 superob — 커버리지·물리성."""
    from kdm6.io.frame_reader import read_wrfout_frame
    from kdm6.obs.gk2a_l1b import CLEAN_IR_CHANNELS, load_cal_table, read_ko_slot, slot_files
    fr = read_wrfout_frame(str(_WRFIN), 0)
    cal = load_cal_table(_CAL)
    pl = read_ko_slot(slot_files(_GK2A, "202507190000", channels=CLEAN_IR_CHANNELS),
                      cal, stride=2)                    # 4km 화소 (테스트 경량)
    # 4km 솎음 밀도에선 5km 셀당 화소 1-2개 — min_pixels=1로 낮춘다
    # (운영 전처리는 stride=1(2km)로 셀당 ~6화소 → 기본 min_pixels=3 사용).
    so = superob_to_model_grid(pl, fr.meta["lat"], fr.meta["lon"],
                               max_dist_km=4.0, min_pixels=1)
    B = fr.state.th.shape[0]
    cov = float((so.obs_quality[:, 12] == 0).float().mean())
    assert cov > 0.3                                    # KO 커버 영역 (~39%)
    ok = so.obs_quality[:, 12] == 0
    assert 180.0 < float(so.bt[ok, 12].min()) and float(so.bt[ok, 12].max()) < 320.0
    # superob 평활 효과: 셀 평균이므로 원화소보다 극값이 안쪽
    assert float(so.bt[ok, 12].min()) >= float(pl.bt[:, 12].min()) - 1e-9


# ── input-validation contract (external review P1-3) ────────────────────────

def test_superob_min_pixels_must_be_positive():
    """min_pixels < 1 makes `good = n >= 0` include EMPTY cells -> 0/0 mean
    and a spuriously usable quality flag; reject at the boundary."""
    glat = torch.tensor([35.0, 36.0], **_F64)
    glon = torch.tensor([125.0, 125.0], **_F64)
    pl = _payload(lat=[35.001], lon=[125.0], bt_vals=[250.0])
    for bad in (0, -1):
        with pytest.raises(ValueError, match="min_pixels"):
            superob_to_model_grid(pl, glat, glon, max_dist_km=4.0,
                                  min_pixels=bad)


def test_superob_max_dist_must_be_finite_positive():
    glat = torch.tensor([35.0], **_F64)
    glon = torch.tensor([125.0], **_F64)
    pl = _payload(lat=[35.001], lon=[125.0], bt_vals=[250.0])
    for bad in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="max_dist_km"):
            superob_to_model_grid(pl, glat, glon, max_dist_km=bad,
                                  min_pixels=1)


def test_kdtree_mapping_shares_coordinate_validation():
    """The SciPy fast path rejects the same bad coordinates as collocate."""
    from kdm6.obs.superob import build_pixel_mapping
    good_obs_lat = torch.tensor([35.0], **_F64)
    good_obs_lon = torch.tensor([125.0], **_F64)
    good_grid_lat = torch.tensor([35.0, 36.0], **_F64)
    good_grid_lon = torch.tensor([125.0, 125.0], **_F64)
    cases = [
        (torch.tensor([float("nan")], **_F64), good_obs_lon,
         good_grid_lat, good_grid_lon, "observation coordinates"),
        (good_obs_lat, good_obs_lon, torch.tensor([95.0, 96.0], **_F64),
         good_grid_lon, "grid coordinates out of range"),
        (good_obs_lat, good_obs_lon, torch.tensor([35.0, 35.0], **_F64),
         torch.tensor([125.0, 125.0], **_F64), "degenerate grid"),
    ]
    for args in cases:
        with pytest.raises(ValueError, match=args[-1]):
            build_pixel_mapping(*args[:-1], max_dist_km=4.0)


def test_kdtree_mapping_uses_actual_distance_for_large_gate():
    """A gate beyond a hemisphere must not fold through chord sin()."""
    from kdm6.obs.superob import build_pixel_mapping
    mapping = build_pixel_mapping(
        torch.tensor([35.0], **_F64), torch.tensor([125.0], **_F64),
        torch.tensor([35.0, 36.0], **_F64),
        torch.tensor([125.0, 125.0], **_F64), max_dist_km=50_000.0)
    assert mapping.tolist() == [0]


def test_superob_with_mapping_validates_B_and_mapping_range():
    from kdm6.obs.superob import superob_with_mapping
    pl = _payload(lat=[35.0, 36.0], lon=[125.0, 125.0], bt_vals=[250.0, 251.0])
    good = torch.tensor([0, 1], dtype=torch.int64)
    with pytest.raises(ValueError, match="B"):
        superob_with_mapping(pl, good, 0, min_pixels=1)
    with pytest.raises(ValueError, match="min_pixels"):
        superob_with_mapping(pl, good, 2, min_pixels=0)
    bad_hi = torch.tensor([0, 2], dtype=torch.int64)   # >= B: out of range
    with pytest.raises(ValueError, match="mapping"):
        superob_with_mapping(pl, bad_hi, 2, min_pixels=1)
    bad_lo = torch.tensor([0, -2], dtype=torch.int64)  # < -1: out of range
    with pytest.raises(ValueError, match="mapping"):
        superob_with_mapping(pl, bad_lo, 2, min_pixels=1)


def test_superob_with_mapping_rejects_malformed_mapping_before_indexing():
    pl = _payload(lat=[35.0], lon=[125.0], bt_vals=[250.0])
    for bad in ([0], torch.tensor([[0]], dtype=torch.int64),
                torch.tensor([0.0], **_F64)):
        with pytest.raises(ValueError, match="mapping"):
            superob_with_mapping(pl, bad, 1, min_pixels=1)
    for bad_B in (True, 1.0, 0):
        with pytest.raises(ValueError, match="B"):
            superob_with_mapping(pl, torch.tensor([0], dtype=torch.int64),
                                  bad_B, min_pixels=1)


def test_superob_archive_schema_and_budget_validation(tmp_path):
    """Malformed archives fail at load before any consumer sees their tensors."""
    pl = _payload(lat=[35.0], lon=[125.0], bt_vals=[250.0])
    so = superob_to_model_grid(
        ObsPayload(bt=pl.bt, obs_quality=pl.obs_quality, lat=pl.lat,
                   lon=pl.lon, valid_time_utc="202507190000"),
        torch.tensor([35.0, 36.0], **_F64),
        torch.tensor([125.0, 125.0], **_F64), max_dist_km=4.0, min_pixels=1)
    base = dict(bt=so.bt, obs_quality=so.obs_quality, n_pixels=so.n_pixels,
                n_assigned_pixels=so.n_assigned_pixels, n_dropped_far=0,
                valid_time_utc=so.valid_time_utc)
    cases = []
    missing = dict(base); missing.pop("n_pixels"); cases.append((missing, "missing keys"))
    unknown = dict(base); unknown["unexpected"] = 1; cases.append((unknown, "unknown keys"))
    shape = dict(base); shape["obs_quality"] = so.obs_quality[:1]; cases.append((shape, "same .* shape"))
    nonfinite = dict(base); nonfinite["bt"] = so.bt.clone(); nonfinite["bt"][0, 0] = float("nan")
    cases.append((nonfinite, "usable bt contains non-finite"))
    quality = dict(base); quality["obs_quality"] = so.obs_quality.clone(); quality["obs_quality"][0, 0] = 2.0
    cases.append((quality, "obs_quality must contain only 0 or 1"))
    zero = dict(base); zero["n_pixels"] = so.n_pixels.clone(); zero["n_pixels"][0, 0] = 0.0
    cases.append((zero, "usable cells need n_pixels"))
    budget = dict(base); budget["n_pixels"] = so.n_pixels.clone(); budget["n_pixels"][0, 0] = 2.0
    cases.append((budget, "exceeds n_assigned_pixels"))
    for i, (archive, error) in enumerate(cases):
        path = tmp_path / f"bad-{i}.pt"
        torch.save(archive, path)
        with pytest.raises(ValueError, match=error):
            load_superobs(path)


def test_empty_all_unusable_superob_archive_roundtrip(tmp_path):
    """An empty input slot may legitimately produce an all-quality1 grid."""
    empty = ObsPayload(
        bt=torch.empty((0, 2), **_F64),
        obs_quality=torch.empty((0, 2), **_F64),
        lat=torch.empty((0,), **_F64), lon=torch.empty((0,), **_F64))
    so = superob_with_mapping(empty, torch.empty((0,), dtype=torch.int64), 2,
                              min_pixels=1)
    assert so.n_assigned_pixels == 0 and so.n_dropped_far == 0
    assert bool((so.obs_quality == 1.0).all())
    archive = tmp_path / "empty-superob.pt"
    save_superobs(so, archive)
    loaded = load_superobs(archive)
    assert loaded.n_assigned_pixels == 0
    assert torch.equal(loaded.obs_quality, so.obs_quality)


def test_superob_rejects_unconsumed_optional_payload_fields():
    pl = _payload(lat=[35.0], lon=[125.0], bt_vals=[250.0])
    pl = ObsPayload(bt=pl.bt, obs_quality=pl.obs_quality, lat=pl.lat, lon=pl.lon,
                    bias=torch.zeros_like(pl.bt))
    glat = torch.tensor([35.0, 36.0], **_F64)
    glon = torch.tensor([125.0, 125.0], **_F64)
    with pytest.raises(ValueError, match="bias/channel_gate"):
        superob_to_model_grid(pl, glat, glon, max_dist_km=4.0, min_pixels=1)


def test_superob_timestamp_roundtrip_and_legacy_archive(tmp_path):
    """The slot stamp survives both superob implementations and torch I/O."""
    pl0 = _payload(lat=[35.0], lon=[125.0], bt_vals=[250.0])
    pl = ObsPayload(bt=pl0.bt, obs_quality=pl0.obs_quality, lat=pl0.lat,
                    lon=pl0.lon, valid_time_utc="202507190000")
    glat = torch.tensor([35.0, 36.0], **_F64)
    glon = torch.tensor([125.0, 125.0], **_F64)

    so = superob_to_model_grid(pl, glat, glon, max_dist_km=4.0, min_pixels=1)
    assert so.valid_time_utc == "202507190000"
    mapped = superob_with_mapping(pl, torch.tensor([0], dtype=torch.int64), 1,
                                   min_pixels=1)
    assert mapped.valid_time_utc == so.valid_time_utc

    archive = tmp_path / "superob.pt"
    save_superobs(so, archive)
    assert load_superobs(archive).valid_time_utc == "202507190000"

    # A pre-timestamp archive remains explicitly untimed.  The primitive
    # archive contains tensors and scalar metadata only, so weights_only=True
    # remains the loading boundary (no object pickle fallback).
    legacy = tmp_path / "legacy-superob.pt"
    torch.save(dict(bt=so.bt, obs_quality=so.obs_quality, n_pixels=so.n_pixels,
                    n_assigned_pixels=so.n_assigned_pixels,
                    n_dropped_far=so.n_dropped_far), legacy)
    assert load_superobs(legacy).valid_time_utc is None


def test_legacy_superob_without_time_is_rejected_by_driver_date_guard(
        tmp_path, monkeypatch):
    """An untimed old archive cannot silently enter date-sensitive DA."""
    from types import SimpleNamespace
    import numpy as np
    import kdm6.da_fulldomain as da
    from kdm6.obs.obs_ingest import ColumnObs
    from kdm6.state import Forcing, State

    pl = _payload(lat=[35.0], lon=[125.0], bt_vals=[250.0])
    so = superob_to_model_grid(
        ObsPayload(bt=pl.bt, obs_quality=pl.obs_quality, lat=pl.lat,
                   lon=pl.lon, valid_time_utc="202507190000"),
        torch.tensor([35.0, 36.0], **_F64),
        torch.tensor([125.0, 125.0], **_F64), max_dist_km=4.0, min_pixels=1)
    legacy = tmp_path / "legacy-superob.pt"
    torch.save(dict(bt=so.bt, obs_quality=so.obs_quality, n_pixels=so.n_pixels,
                    n_assigned_pixels=so.n_assigned_pixels,
                    n_dropped_far=so.n_dropped_far), legacy)
    old = load_superobs(legacy)
    co = ColumnObs(bt=old.bt[:1], obs_quality=old.obs_quality[:1],
                   n_assigned=old.n_assigned_pixels,
                   n_dropped_far=old.n_dropped_far, n_dropped_collision=0,
                   col_of_obs=torch.tensor([0], dtype=torch.int64),
                   valid_time_utc=old.valid_time_utc)
    one = torch.ones((1, 1), **_F64)
    state = State(*(one.clone() for _ in State._fields))
    forcing = Forcing(*(one.clone() for _ in Forcing._fields))
    frame = SimpleNamespace(
        state=state, forcing=forcing, xland=torch.ones(1, **_F64),
        meta={"nx": 1, "ny": 1, "valid_time_utc": "2025-07-19_00:00:00"})
    # Stop before any RTTOV or filesystem work; this isolates the existing
    # driver date guard after it receives the archived timestamp value.
    monkeypatch.setattr(da, "select_membership",
                        lambda fr, co, boundary=10: torch.tensor([0]))
    import kdm6.obs.rttov_case_writer as case_writer
    monkeypatch.setattr(case_writer, "make_live_run_k",
                        lambda *a, **k: object())
    grids = {"p_lay": np.array([1000.0]), "p_half": np.array([1000.0, 900.0]),
             "t_ref": np.array([250.0]), "q_ref": np.array([1.0])}
    with pytest.raises(ValueError, match="valid_time_utc.*missing"):
        da.run_fulldomain_analysis(frame, co, grids, str(tmp_path), channels=())
