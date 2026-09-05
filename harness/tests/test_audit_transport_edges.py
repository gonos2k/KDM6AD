"""Focused regressions for transport evidence boundary contracts.

These tests use synthetic netCDF/binary records and monkeypatch only the
mutable fixture path where the real-column producer writes a compile-time
manifest. Expectations are calculated from the independent input values.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import g33_defect_magnitude as dm  # noqa: E402
import g33_dual_ledger as dl  # noqa: E402
import g33_dyn_probe as dyn  # noqa: E402
import g33_number_basis as nb  # noqa: E402
import g33_number_transport as nt  # noqa: E402
import g33_real_column_batch as batch  # noqa: E402
import g33_real_column_density as density  # noqa: E402
from test_g33_number_transport import _call, _stream  # noqa: E402

np = pytest.importorskip("numpy")
netCDF4 = pytest.importorskip("netCDF4")


def _state_with_frames(path: Path, pressure_frames) -> Path:
    """Write a minimal WRF-shaped pressure/moisture state."""
    pressure_frames = np.asarray(pressure_frames, dtype="f8")
    ntime, levels = pressure_frames.shape
    with netCDF4.Dataset(str(path), "w") as d:
        d.createDimension("Time", ntime)
        d.createDimension("bottom_top", levels)
        d.createDimension("south_north", 1)
        d.createDimension("west_east", 1)
        dims = ("Time", "bottom_top", "south_north", "west_east")
        for name, values in (("P", pressure_frames),
                             ("PB", np.zeros_like(pressure_frames)),
                             ("T", np.zeros_like(pressure_frames)),
                             ("QVAPOR", np.zeros_like(pressure_frames))):
            v = d.createVariable(name, "f8", dims)
            v[:, :, 0, 0] = values
    return path


def _full_batch_state(path: Path, *, masked_name: str | None = None) -> Path:
    """Write the fields consumed by ``write_manifest`` for one column."""
    with netCDF4.Dataset(str(path), "w") as d:
        d.createDimension("Time", 1)
        d.createDimension("bottom_top", 3)
        d.createDimension("bottom_top_stag", 4)
        d.createDimension("south_north", 1)
        d.createDimension("west_east", 1)
        lev = ("Time", "bottom_top", "south_north", "west_east")
        stag = ("Time", "bottom_top_stag", "south_north", "west_east")
        p = np.array([100000.0, 80000.0, 60000.0])[None, :, None, None]
        for name, values in (("P", p), ("PB", np.zeros_like(p)),
                             ("T", np.zeros_like(p)),
                             ("QVAPOR", np.full_like(p, 1.0e-3))):
            v = d.createVariable(name, "f8", lev)
            v[:] = values
        ph = np.array([0.0, 100.0, 200.0, 300.0])[None, :, None, None]
        for name, values in (("PH", ph), ("PHB", np.zeros_like(ph))):
            v = d.createVariable(name, "f8", stag)
            v[:] = values
        mu = d.createVariable("MU", "f8", ("Time", "south_north", "west_east"))
        mub = d.createVariable("MUB", "f8", ("Time", "south_north", "west_east"))
        mu[:] = 100.0
        mub[:] = 0.0
        dnw = d.createVariable("DNW", "f8", ("Time", "bottom_top"))
        dnw[:] = 1.0
        for name in ("QCLOUD", "QRAIN", "QICE", "QSNOW", "QGRAUP",
                     "QNCCN", "QNCLOUD", "QNICE", "QNRAIN"):
            v = d.createVariable(name, "f8", lev, fill_value=9999.0)
            v[:] = 1.0
            if name == masked_name:
                values = np.ma.array(np.ones((1, 3, 1, 1)),
                                     mask=np.zeros((1, 3, 1, 1), dtype=bool))
                values.mask[0, 1, 0, 0] = True
                v[:] = values
        xland = d.createVariable("XLAND", "f8",
                                 ("Time", "south_north", "west_east"))
        xland[:] = 1.0
    return path


def test_real_column_batch_rejects_masked_selection_and_manifest_inputs(tmp_path,
                                                                          monkeypatch):
    path = _full_batch_state(tmp_path / "masked.nc", masked_name="QNRAIN")
    with pytest.raises(ValueError, match="QNRAIN.*masked"):
        batch.candidates(path, want=1, levels=1)

    # Exercise the storage path with a different masked field. The committed
    # manifest is copied to a temporary path; no tracked fixture is rewritten.
    path = _full_batch_state(tmp_path / "masked_qr.nc", masked_name="QRAIN")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(batch.MANIFEST.read_text())
    monkeypatch.setattr(batch, "MANIFEST", manifest)
    with pytest.raises(ValueError, match="QRAIN.*masked"):
        batch.write_manifest(path, 0, 0)


def test_g33n_rejects_nonphysical_upper_layer_measures():
    original = _stream(_call(1))
    for field, value, expected in (("rho", "BF800000", "rho"),
                                   ("delz", "00000000", "delz")):
        needle = f"G33F STAGE 1 - outer_pre_sed 0 {field} 1 0 f32 3F800000"
        bad = original.replace(needle, needle.replace("3F800000", value), 1)
        with pytest.raises(nt.StreamError, match=expected):
            nt.calls(bad)


def test_number_basis_refuses_multicall_endpoint_recovery(monkeypatch):
    # Parsing accepts the two calls; the endpoint helper must refuse their
    # non-unique combined trajectory before it reads a surface transfer.
    with pytest.raises(nt.StreamError, match="exactly one external call"):
        nb.from_stream(_stream(_call(1), _call(2)), "nr")


def test_number_basis_refuses_multisubstep_endpoint_recovery():
    stream = _stream(_call(1).replace(
        "G33F MSTEP 1 main 1 i32 00000001",
        "G33F MSTEP 1 main 1 i32 00000002", 1))
    with pytest.raises(nt.StreamError, match="multi-substep"):
        nb.from_stream(stream, "nr")


def test_defect_magnitude_uses_statistical_even_median(monkeypatch):
    mass = {"start": 1.0, "final": 1.0}
    number = {
        "residual": 4.0, "out": 1.0, "start": 10.0, "final": 100.0,
        "calls": 2,
        "per_call": [{"start": 10.0, "residual": 1.0},
                      {"start": 10.0, "residual": 3.0}],
    }
    acc = {("main", "qr", 1): mass, ("main", "nr", 1): number}
    monkeypatch.setattr(dm.mc, "closures", lambda *a, **k: acc)
    monkeypatch.setattr(dm.mc, "usable", lambda d: (True, ""))
    monkeypatch.setattr(dm.mc, "endpoints", lambda d: {
        "first_segment_pre_inventory": 10.0,
        "last_segment_post_inventory": 100.0,
        "calls": 2,
    })
    monkeypatch.setattr(dm.mc, "window_inventories", lambda *a, **k: {})
    monkeypatch.setattr(dm.ci, "interfaces", lambda *a, **k: {
        ("main", 1): {"number_transported": 1.0}})
    got = dm.analysis("")["rows"]["main/nr/1"]
    assert got["per_call_fraction_median"] == pytest.approx(0.2)


def test_dual_ledger_prints_one_unavailable_basis(capsys, monkeypatch):
    monkeypatch.setattr(dl, "analysis", lambda _stream: {
        "rows": {"main/nr/1": {
            "operator": {"ratio": None},
            "physical": {"ratio": 0.25},
            "ratio_divergence": None}},
        "humidity": {},
    })
    dl.report("")
    out = capsys.readouterr().out
    assert "-" in out and "25.0000%" in out


def test_number_basis_report_marks_empty_ratio_population(tmp_path):
    path = _state_with_frames(tmp_path / "flat.nc",
                              [[100000.0, 100000.0, 100000.0]])
    got = nb.report(path, "exact")
    ratio = got["armn_residual_fraction"]
    assert ratio["interfaces"] == 0
    assert ratio["empty_ratio"] is True
    assert ratio["median"] is None
    assert ratio["p90"] is None
    assert ratio["max"] is None
    assert got["composition_max_abs_error"] == pytest.approx(0.0)


def test_density_proxy_has_explicit_compatible_default_and_frame_selection(tmp_path):
    path = _state_with_frames(tmp_path / "frames.nc", [
        [100000.0, 100000.0, 100000.0],
        [100000.0, 80000.0, 60000.0],
    ])
    first_profile = density.profile(path)
    first = density.report(path)
    terminal_profile = density.profile(path, frame=-1)
    terminal = density.report(path, frame=-1)
    assert first["frame_index"] == 0
    assert first["frame_policy"].startswith("explicit")
    assert np.allclose(first_profile["eps"], 0.0)
    assert terminal["frame_index"] == 1
    assert terminal["frame_request"] == -1
    expected = (100000.0 / 80000.0) ** (1.0 - density.RD / density.CP) - 1.0
    assert terminal_profile["eps"][0, 0, 0] == pytest.approx(expected)
    assert terminal["eps_median"] > 0.15
    with pytest.raises(ValueError, match="outside.*Time"):
        density.profile(path, frame=2)


def _dyn_record(*, owned: bool, value: float = 1.0) -> bytes:
    """One valid group-2 stage31 record for a single global column."""
    header = (31, 2, 60, 60, 0, 0, 0, 0, 60 if owned else 61,
              60 if owned else 61)
    values = []
    for _name, kind, _ in dyn.GROUPS[2]:
        values.extend([value] * (2 if kind == "Z" else 1))
    return (struct.pack(">10i", *header)
            + struct.pack(f">{len(values)}f", *values))


def _write_dyn_record(path: Path, *, owned: bool, value: float = 1.0):
    path.write_bytes(_dyn_record(owned=owned, value=value))


def test_halo_content_keeps_repeated_rank_copies_and_rejects_empty(tmp_path):
    _write_dyn_record(tmp_path / "g33dyn_owner.bin", owned=True)
    _write_dyn_record(tmp_path / "g33dyn_a.bin", owned=False, value=2.0)
    _write_dyn_record(tmp_path / "g33dyn_b.bin", owned=False)
    rows = dyn.halo_content(tmp_path)
    assert {row["rank"] for row in rows} == {"a", "b"}
    assert any(row["rank"] == "a" and row["columns"] for row in rows)
    assert all(not row["columns"] for row in rows if row["rank"] == "b")

    empty = tmp_path / "empty"
    empty.mkdir()
    _write_dyn_record(empty / "g33dyn_owner.bin", owned=True)
    with pytest.raises(SystemExit, match="no halo records"):
        dyn.halo_content(empty)


def test_dyn_read_rejects_duplicate_identity_within_one_rank_file(tmp_path):
    path = tmp_path / "g33dyn_bad.bin"
    path.write_bytes(_dyn_record(owned=False, value=2.0)
                     + _dyn_record(owned=False, value=1.0))
    with pytest.raises(dyn.DynDumpError, match="duplicate record"):
        dyn.read_dump(path)


def test_dyn_read_normalizes_truncated_payload(tmp_path):
    path = tmp_path / "g33dyn_truncated.bin"
    path.write_bytes(_dyn_record(owned=False)[:-1])
    with pytest.raises(dyn.DynDumpError, match="truncated .*payload"):
        dyn.read_dump(path)


@pytest.mark.parametrize('pressure', [0.0, -1.0, float('nan'), float('inf')])
def test_density_reports_refuse_invalid_pressure(tmp_path, pressure):
    path = _state_with_frames(tmp_path / 'invalid_pressure.nc',
                              [[100000.0, pressure, 50000.0]])
    for reader in (lambda p: nb.report(p, 'exact'), density.report):
        with pytest.raises(ValueError, match='pressure|nonfinite'):
            reader(path)


@pytest.mark.parametrize('field,value', [('PH', 0.0), ('MU', 0.0), ('DNW', 0.0),
                                         ('P', 0.0), ('XLAND', 3.0)])
def test_batch_refuses_derived_invalid_forcing_before_replacing_manifest(
        tmp_path, monkeypatch, field, value):
    path = _full_batch_state(tmp_path / 'invalid_forcing.nc')
    with netCDF4.Dataset(str(path), 'a') as d:
        d[field][:] = value
    manifest = tmp_path / 'manifest.json'
    original = batch.MANIFEST.read_bytes()
    manifest.write_bytes(original)
    monkeypatch.setattr(batch, 'MANIFEST', manifest)
    with pytest.raises(ValueError):
        batch.write_manifest(path, 0, 0)
    assert manifest.read_bytes() == original


@pytest.mark.parametrize('field,word', [('rho', '7f800000'), ('p', '00000000'),
                                        ('delz', 'bf800000'), ('qv', '7fc00000')])
def test_fixture_refuses_nonfinite_or_nonpositive_metrics(tmp_path, field, word):
    import json
    import g33_fixture_v1 as fx
    data = json.loads(fx.MANIFEST.read_text())
    data['fields'][field][0] = word
    target = tmp_path / 'invalid.json'
    target.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='finite|positive'):
        fx.load_manifest(target)
