#!/usr/bin/env python3
"""False-pass guards of the 12h-recert evidence ingester (build_c4_evidence.py).

Codex stop-review: a fail-closed recertifier must NEVER pass incomplete or
malformed evidence. These tests construct synthetic run dirs + NetCDF history
files and assert the ingester's negative paths.

Runs under pytest OR directly (`python3 test_recert_ingest.py`). Skips cleanly
if netCDF4 is unavailable.
"""
import importlib.util
import pathlib
import sys
import tempfile

HARNESS = pathlib.Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "bce", HARNESS / "build_c4_evidence.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


try:
    import netCDF4 as nc
    import numpy as np
    _HAVE = True
except Exception:
    _HAVE = False


def _mk_fcst(path, nframes=12, nvars=253, seed=0, tweak=None):
    """Write a synthetic klfs_lc05_fcst with `nvars` numeric vars over
    `nframes` frames. `tweak(ds)` may mutate before close (e.g. flip a bit)."""
    rng = np.random.default_rng(seed)
    d = nc.Dataset(str(path), "w")
    d.createDimension("Time", nframes)
    d.createDimension("x", 4)
    for i in range(nvars):
        v = d.createVariable(f"V{i}", "f4", ("Time", "x"))
        v[:] = rng.standard_normal((nframes, 4)).astype("f4")
    # a non-numeric var (Times) to exercise the skip path
    d.createDimension("s", 3)
    tv = d.createVariable("Times", "S1", ("Time", "s"))
    tv[:] = np.array([[b"a", b"b", b"c"]] * nframes)
    if tweak:
        tweak(d)
    d.close()


def _mk_rundir(tmp, name, ranks=4, exit_code="0", success=True,
               reached_full=True, fatal=False):
    d = tmp / name
    d.mkdir()
    (d / "exit_code").write_text((exit_code or "") + "\n")
    for r in range(ranks):
        body = ""
        if reached_full:
            body += "d01 2025-07-19_12:00:00 wrf: SUCCESS COMPLETE WRF\n"
        elif success:
            body += "d01 2025-07-19_06:00:00 wrf: SUCCESS COMPLETE WRF\n"
        if fatal and r == 0:
            body += "[node:00000] *** MPI_ABORT\n"
        (d / f"rsl.error.{r:04d}").write_text(body or "running\n")
    return d


def test_verify_rejects_bad_and_accepts_good():
    if not _HAVE:
        print("  SKIP (no netCDF4)"); return
    m = _load()
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        # good run
        good = _mk_rundir(tmp, "mp37_good")
        _mk_fcst(good / "klfs_lc05_fcst.x", nframes=12)
        assert m.verify_recert_run(good, np=4)["verified"] is True
        # wrong rank count (3 of 4)
        r3 = _mk_rundir(tmp, "mp37_r3", ranks=3)
        _mk_fcst(r3 / "klfs_lc05_fcst.x")
        assert m.verify_recert_run(r3, np=4)["verified"] is False
        # exit_code != 0
        bad_ec = _mk_rundir(tmp, "mp37_ec", exit_code="14")
        _mk_fcst(bad_ec / "klfs_lc05_fcst.x")
        assert m.verify_recert_run(bad_ec, np=4)["verified"] is False
        # did not reach 12:00:00
        early = _mk_rundir(tmp, "mp37_early", reached_full=False)
        _mk_fcst(early / "klfs_lc05_fcst.x")
        assert m.verify_recert_run(early, np=4)["verified"] is False
        # fatal marker
        fat = _mk_rundir(tmp, "mp37_fatal", fatal=True)
        _mk_fcst(fat / "klfs_lc05_fcst.x")
        assert m.verify_recert_run(fat, np=4)["verified"] is False
        # no history file
        nofc = _mk_rundir(tmp, "mp37_nofc")
        assert m.verify_recert_run(nofc, np=4)["verified"] is False
        # WRONG rank identities: 4 logs but ranks {0,1,2,5} — rank 3 missing,
        # a stale 0005 present. Count==4 & all SUCCESS, but identities wrong.
        wid = _mk_rundir(tmp, "mp37_wid", ranks=3)   # 0000..0002
        (wid / "rsl.error.0005").write_text(
            "d01 2025-07-19_12:00:00 wrf: SUCCESS COMPLETE WRF\n")
        _mk_fcst(wid / "klfs_lc05_fcst.x")
        v = m.verify_recert_run(wid, np=4)
        assert v["verified"] is False and v["missing_ranks"] == ["rsl.error.0003"]
        # EXTRA rank log beyond np: 0000..0004 for np=4 (stale np5 decomposition)
        ext = _mk_rundir(tmp, "mp37_ext", ranks=5)
        _mk_fcst(ext / "klfs_lc05_fcst.x")
        v = m.verify_recert_run(ext, np=4)
        assert v["verified"] is False and v["extra_rank_logs"] == ["rsl.error.0004"]


def test_strict_bitwise_fail_closed():
    if not _HAVE:
        print("  SKIP (no netCDF4)"); return
    m = _load()
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        a = tmp / "a.nc"; b = tmp / "b.nc"
        # identical, enough numeric vars -> PASS
        _mk_fcst(a, nframes=12, nvars=253, seed=1)
        _mk_fcst(b, nframes=12, nvars=253, seed=1)
        assert m.strict_bitwise_all_frames(str(a), str(b))["strict_bitwise"] is True
        # too few common numeric vars -> FAIL (malformed/degenerate)
        c = tmp / "c.nc"; dd = tmp / "d.nc"
        _mk_fcst(c, nframes=12, nvars=5, seed=2)
        _mk_fcst(dd, nframes=12, nvars=5, seed=2)
        assert m.strict_bitwise_all_frames(str(c), str(dd))["strict_bitwise"] is False
        # one bit flipped -> FAIL
        e = tmp / "e.nc"; f = tmp / "f.nc"
        _mk_fcst(e, nframes=12, nvars=253, seed=3)

        def flip(ds):
            arr = ds.variables["V0"][:]
            arr[0, 0] = arr[0, 0] + np.float32(1e-3)
            ds.variables["V0"][:] = arr
        _mk_fcst(f, nframes=12, nvars=253, seed=3, tweak=flip)
        assert m.strict_bitwise_all_frames(str(e), str(f))["strict_bitwise"] is False
        # mismatched frame counts -> FAIL
        g = tmp / "g.nc"; h = tmp / "h.nc"
        _mk_fcst(g, nframes=12, nvars=253, seed=4)
        _mk_fcst(h, nframes=11, nvars=253, seed=4)
        assert m.strict_bitwise_all_frames(str(g), str(h))["strict_bitwise"] is False
        # mismatched variable sets -> FAIL
        i = tmp / "i.nc"; j = tmp / "j.nc"
        _mk_fcst(i, nframes=12, nvars=253, seed=5)
        _mk_fcst(j, nframes=12, nvars=252, seed=5)
        assert m.strict_bitwise_all_frames(str(i), str(j))["strict_bitwise"] is False


def _selftest():
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  PASS {name}")
            except AssertionError as e:
                print(f"  FAIL {name}: {e}"); fails += 1
    return fails


if __name__ == "__main__":
    sys.exit(1 if _selftest() else 0)
