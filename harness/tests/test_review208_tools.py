"""Focused PR208 regressions for the public tooling boundaries.

These tests use temporary NetCDF/binary metadata only.  They never launch WRF,
MPI, or a host build and do not modify committed evidence.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import struct
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

HARNESS = Path(__file__).resolve().parents[1]
# The production comparator intentionally supports direct-script execution and
# uses the neighboring runner module for producer identity helpers.  Keep the
# documented root pytest invocation equivalent to ``PYTHONPATH=harness``.
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HARNESS / filename)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _nc_pair(tmp_path: Path, *, nonleading: bool = False):
    nc = pytest.importorskip("netCDF4")
    left, right = tmp_path / "left.nc", tmp_path / "right.nc"
    for path in (left, right):
        with nc.Dataset(path, "w") as ds:
            ds.createDimension("x", 2)
            ds.createDimension("Time", 2)
            ds.createDimension("y", 1)
            ds.createDimension("DateStrLen", 4)
            dims = ("x", "Time", "y") if nonleading else ("Time", "x", "y")
            v = ds.createVariable("T", "f4", dims)
            values = np.arange(4, dtype="f4").reshape(2, 2, 1)
            v[:] = values if nonleading else values.transpose(1, 0, 2)
            times = ds.createVariable("Times", "S1", ("Time", "DateStrLen"))
            times[:] = np.array([[b"0", b"0", b"0", b"0"],
                                 [b"0", b"0", b"0", b"1"]])
    return left, right


def test_review208_strict_uses_named_time_axis(tmp_path):
    left, right = _nc_pair(tmp_path, nonleading=True)
    tool = HARNESS / "strict_bitwise_nc.py"
    clean = subprocess.run([sys.executable, str(tool), str(left), str(right), "0"],
                           capture_output=True, text=True)
    assert clean.returncode == 0, clean.stdout + clean.stderr
    nc = pytest.importorskip("netCDF4")
    with nc.Dataset(right, "a") as ds:
        value = ds.variables["T"][:]
        value[0, 1, 0] += np.float32(1)
        ds.variables["T"][:] = value
    selected = subprocess.run([sys.executable, str(tool), str(left), str(right), "1"],
                              capture_output=True, text=True)
    assert selected.returncode == 1
    assert "DIVERGES" in selected.stdout


def test_review208_strict_times_only_is_insufficient(tmp_path):
    nc = pytest.importorskip("netCDF4")
    files = []
    for i in range(2):
        p = tmp_path / f"times{i}.nc"
        with nc.Dataset(p, "w") as ds:
            ds.createDimension("Time", 1)
            ds.createDimension("s", 1)
            ds.createVariable("Times", "S1", ("Time", "s"))[:] = [[b"0"]]
        files.append(p)
    result = subprocess.run([sys.executable, str(HARNESS / "strict_bitwise_nc.py"),
                             *(str(p) for p in files)], capture_output=True, text=True)
    assert result.returncode == 1
    assert "INSUFFICIENT" in result.stdout


def _run_dir(path: Path, *, proc: str = "1x1") -> Path:
    path.mkdir()
    digest = "a" * 64
    (path / "wrf_exe_sha256").write_text(
        f"{digest}\nbefore {digest}\nafter {digest}\nstable yes\n")
    (path / "runner_sha256").write_text(f"runner {'b' * 64}\n")
    (path / "proc_grid").write_text(
        f"requested {proc}\nactual {proc}\nmatches yes\nnp 1\n")
    (path / "namelist.input").write_text("&domains\n/\n")
    return path


def test_review208_perturbation_requires_valid_equal_actual_grids(tmp_path):
    mpi = _load("review208_mpi_grid", "g33_mpi_divergence.py")
    a, b = _run_dir(tmp_path / "a"), _run_dir(tmp_path / "b")
    bad = "requested opaque\nactual opaque\nmatches yes\nnp 1\n"
    (a / "proc_grid").write_text(bad)
    (b / "proc_grid").write_text(bad)
    with pytest.raises(SystemExit, match="valid actual processor grids"):
        mpi.same_experiment(a, b, expect="perturbation")


def test_review208_input_stability_is_derived_from_before_after(tmp_path):
    mpi = _load("review208_mpi_input", "g33_mpi_divergence.py")
    run = _run_dir(tmp_path / "run")
    (run / "namelist.input").write_text(
        "&domains\nmax_dom = 1,\ninput_inname = 'x',\n"
        "bdy_inname = 'y',\n/\n")
    records = []
    for name in ("x", "y"):
        records.append({"kind": "init" if name == "x" else "boundary",
                        "domain": "d01", "name": name,
                        "sha256_before": "a" * 64,
                        "sha256_after": "b" * 64,
                        "sha256": "a" * 64, "status": "ok", "stable": True})
    (run / "input_sha256.json").write_text(json.dumps({
        "declared": True, "complete": True,
        "records": records,
    }))
    with pytest.raises(SystemExit, match="contradictory stable"):
        mpi._input_identity(run)


def test_review208_producer_success_cannot_contain_failed_exit(tmp_path):
    mpi = _load("review208_producer", "g33_mpi_divergence.py")
    run = _run_dir(tmp_path / "run")
    (run / "experiment_valid.json").write_text(json.dumps({
        "experiment_valid": True, "invalid_reasons": [],
        "exit_code": 1, "model_completed": False,
    }))
    with pytest.raises(SystemExit, match="exit_code"):
        mpi._validate_producer_status(run)


def test_review208_mapfac_requires_hash_and_positive_finite_values(tmp_path):
    nc = pytest.importorskip("netCDF4")
    mpi = _load("review208_mapfac", "g33_mpi_divergence.py")
    map_path = tmp_path / "wrfinput_d01"
    with nc.Dataset(map_path, "w") as ds:
        ds.createDimension("x", 2)
        ds.createDimension("y", 2)
        ds.createVariable("MAPFAC_M", "f4", ("x", "y"))[:] = 0
        ds.DX, ds.DY = 9000.0, 9000.0
    with nc.Dataset(tmp_path / "forecast.nc", "w") as ds:
        ds.createDimension("Time", 1)
        ds.createDimension("x", 2)
        ds.createDimension("y", 2)
        ds.createVariable("T", "f4", ("Time", "x", "y"))[:] = 1
        ds.createVariable("Times", "S1", ("Time",))[:] = [b"0"]
    with nc.Dataset(tmp_path / "forecast.nc") as forecast:
        with pytest.raises(SystemExit, match="provenance"):
            mpi.cell_area(map_path, forecast)
        digest = hashlib.sha256(map_path.read_bytes()).hexdigest()
        with pytest.raises(SystemExit, match="strictly positive"):
            mpi.cell_area(map_path, forecast, expected_sha256=digest)


def test_review208_fixed_mask_frame_is_checked_against_both_files(tmp_path):
    nc = pytest.importorskip("netCDF4")
    paths = []
    for i in range(2):
        path = tmp_path / f"one{i}.nc"
        with nc.Dataset(path, "w") as ds:
            ds.createDimension("Time", 1)
            ds.createDimension("x", 1)
            ds.createDimension("y", 1)
            ds.createDimension("s", 1)
            ds.createVariable("T", "f4", ("Time", "x", "y"))[:] = [[[1]]]
            ds.createVariable("Times", "S1", ("Time", "s"))[:] = [[b"0"]]
        paths.append(path)
    result = subprocess.run([
        sys.executable, str(HARNESS / "g33_mpi_divergence.py"),
        *(str(p) for p in paths), "--frames", "0"],
        capture_output=True, text=True)
    assert result.returncode != 0
    assert "fixed-mask-frame" in (result.stdout + result.stderr)
    assert "Traceback" not in result.stderr


def test_review208_c4_schema_is_sealed_and_exact(tmp_path):
    c4 = _load("review208_c4", "build_c4_evidence.py")
    nc = pytest.importorskip("netCDF4")
    paths = [tmp_path / "a.nc", tmp_path / "b.nc"]
    for path in paths:
        with nc.Dataset(path, "w") as ds:
            ds.createDimension("Time", 1)
            ds.createDimension("x", 2)
            ds.createDimension("s", 1)
            ds.createVariable("T", "f4", ("Time", "x"))[:] = [[1, 2]]
            ds.createVariable("Times", "S1", ("Time", "s"))[:] = [[b"0"]]
    variables = {
        "T": {"dimensions": ["Time", "x"], "dtype": "f4"},
        "Times": {"dimensions": ["Time", "s"], "dtype": "S1"},
    }
    expected = {"schema_id": "review208-small", "variables": variables}
    expected["schema_sha256"] = c4.schema_digest(variables)
    result = c4.strict_bitwise_all_frames(str(paths[0]), str(paths[1]),
                                          expected_schema=expected)
    assert result["strict_bitwise"] is True
    assert result["schema_provenance"]["required"] is True
    expected["schema_sha256"] = "0" * 64
    with pytest.raises(SystemExit, match="digest"):
        c4.strict_bitwise_all_frames(str(paths[0]), str(paths[1]),
                                     expected_schema=expected)


def test_review208_c4_pair_identity_must_be_shared_and_two_arm(tmp_path):
    c4 = _load("review208_c4_pair", "build_c4_evidence.py")
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    controls = {"label": "review208", "runner_sha256": "b" * 64}
    campaign = c4._producer_campaign_id(controls)
    (a / "run_identity.json").write_text(json.dumps({
        "schema": 1, "campaign_id": campaign, "scheme": "37", "controls": controls,
        "experiment_valid": True, "exit_code": 0}))
    (b / "run_identity.json").write_text(json.dumps({
        "schema": 1, "campaign_id": campaign, "scheme": "137", "controls": controls,
        "experiment_valid": True, "exit_code": 0}))
    pair = c4._require_pair_identity(a, b)
    assert pair["campaign_id"] == campaign
    (b / "run_identity.json").write_text(json.dumps({
        "schema": 1, "campaign_id": "d" * 64, "scheme": "137", "controls": controls,
        "experiment_valid": True, "exit_code": 0}))
    with pytest.raises(SystemExit, match="campaign_id"):
        c4._require_pair_identity(a, b)


def test_review208_rate_nonfinite_is_insufficient(tmp_path):
    tool = HARNESS / "compare_rate_dump.py"
    fort = tmp_path / "fort_x.bin"
    cpp = tmp_path / "cpp_x.bin"
    fort.write_bytes(struct.pack(">5i", 1, 1, 1, 1, 1)
                     + struct.pack(">f", float("nan")))
    cpp.write_bytes(struct.pack(">2i", 1, 1) + struct.pack(">f", float("nan")))
    result = subprocess.run([sys.executable, str(tool), str(fort), str(cpp),
                             "--k-order", "same"], capture_output=True, text=True)
    assert result.returncode == 2
    assert "INSUFFICIENT" in result.stdout


def test_review208_dyn_nonfinite_halo_is_not_a_clean_match(tmp_path):
    dyn = _load("review208_dyn_finite", "g33_dyn_probe.py")

    def record(owned: bool, value: float) -> bytes:
        header = (31, 2, 60, 60, 0, 0, 0, 0,
                  60 if owned else 61, 60 if owned else 61)
        values = []
        for _name, kind, _orientation in dyn.GROUPS[2]:
            values.extend([value] * (2 if kind == "Z" else 1))
        return (struct.pack(">10i", *header)
                + struct.pack(f">{len(values)}f", *values))

    (tmp_path / "g33dyn_owner.bin").write_bytes(record(True, 1.0))
    (tmp_path / "g33dyn_halo.bin").write_bytes(record(False, float("nan")))
    rows = dyn.halo_content(tmp_path)
    assert any(row["status"] == "INSUFFICIENT_NONFINITE"
               for row in rows if row["columns"])


def test_review208_stage_orientation_is_a_required_argument():
    source = (HARNESS / "compare_substep_stage.py").read_text()
    assert 'ap.add_argument("--k-order", required=True' in source
    assert "chosen: fewer diffs" not in source
    assert 'GROUPS = {' in (HARNESS / "g33_dyn_probe.py").read_text()
    dyn = _load("review208_dyn", "g33_dyn_probe.py")
    assert any(name == "muu" and kind == "S"
               for name, kind, _orientation in dyn.GROUPS[4])


def test_review208_runner_rejects_nonpositive_grid_before_case_access(tmp_path):
    tool = HARNESS / "run_ss_case.py"
    result = subprocess.run([sys.executable, str(tool), "--mp", "37",
                             "--np", "4", "--proc-grid=-1x4",
                             "--case", str(tmp_path / "does-not-exist")],
                            capture_output=True, text=True)
    assert result.returncode != 0
    assert "factors must be >= 1" in result.stderr


def test_review208_grid_rejects_explicit_malformed_facts_in_both_modes(tmp_path):
    mpi = _load("review208_mpi_malformed_grid", "g33_mpi_divergence.py")
    for mode in ("decomposition", "perturbation"):
        a, b = _run_dir(tmp_path / f"a_{mode}"), _run_dir(tmp_path / f"b_{mode}")
        malformed = "requested 1x1\nactual 1x1\nmatches ???\nnp nonsense\n"
        (a / "proc_grid").write_text(malformed)
        (b / "proc_grid").write_text(malformed)
        with pytest.raises(SystemExit):
            mpi.same_experiment(a, b, expect=mode)


def test_review208_executable_digest_record_is_cross_checked(tmp_path):
    mpi = _load("review208_mpi_executable", "g33_mpi_divergence.py")
    run = _run_dir(tmp_path / "run")
    (run / "wrf_exe_sha256").write_text(
        "a" * 64 + "\n"
        "before " + "b" * 64 + "\n"
        "after  " + "a" * 64 + "\n"
        "stable yes\n")
    with pytest.raises(SystemExit, match="contradict"):
        mpi._validate_producer_status(run)


def test_review208_duplicate_active_input_identity_is_refused(tmp_path):
    mpi = _load("review208_mpi_duplicate_input", "g33_mpi_divergence.py")
    run = _run_dir(tmp_path / "run")
    (run / "namelist.input").write_text(
        "&domains\nmax_dom = 1,\ninput_inname = 'x',\n"
        "bdy_inname = 'y',\n/\n")
    digest = "a" * 64
    rec = {"kind": "init", "domain": "d01", "name": "x",
           "sha256_before": digest, "sha256_after": digest,
           "status": "ok", "stable": True}
    boundary = {"kind": "boundary", "domain": "d01", "name": "y",
                "sha256_before": digest, "sha256_after": digest,
                "status": "ok", "stable": True}
    (run / "input_sha256.json").write_text(json.dumps({
        "declared": True, "complete": True,
        "records": [rec, dict(rec), boundary],
    }))
    with pytest.raises(SystemExit, match="duplicate active input"):
        mpi._input_identity(run)


def test_review208_missing_times_is_typed_insufficiency(tmp_path):
    nc = pytest.importorskip("netCDF4")
    paths = []
    for i in range(2):
        path = tmp_path / f"missing_times{i}.nc"
        with nc.Dataset(path, "w") as ds:
            ds.createDimension("Time", 1)
            ds.createDimension("x", 1)
            ds.createDimension("y", 1)
            ds.createVariable("T", "f4", ("Time", "x", "y"))[:] = [[[1]]]
        paths.append(path)
    result = subprocess.run([
        sys.executable, str(HARNESS / "g33_mpi_divergence.py"),
        *(str(p) for p in paths), "--frames", "0"],
        capture_output=True, text=True)
    assert result.returncode != 0
    assert "INSUFFICIENT" in result.stderr
    assert "Traceback" not in result.stderr


def test_review208_zero_cell_arrays_are_insufficient_for_all_numeric_census(tmp_path):
    nc = pytest.importorskip("netCDF4")
    paths = []
    for i in range(2):
        path = tmp_path / f"empty{i}.nc"
        with nc.Dataset(path, "w") as ds:
            ds.createDimension("Time", 1)
            ds.createDimension("x", 0)
            ds.createDimension("y", 1)
            ds.createDimension("s", 1)
            ds.createVariable("T", "f4", ("Time", "x", "y"))[:] = np.empty((1, 0, 1), dtype="f4")
            ds.createVariable("Times", "S1", ("Time", "s"))[:] = [[b"0"]]
        paths.append(path)

    strict = subprocess.run([
        sys.executable, str(HARNESS / "strict_bitwise_nc.py"),
        *(str(p) for p in paths)], capture_output=True, text=True)
    assert strict.returncode == 1 and "INSUFFICIENT" in strict.stdout

    mpi = _load("review208_mpi_empty_cells", "g33_mpi_divergence.py")
    with nc.Dataset(paths[0]) as a, nc.Dataset(paths[1]) as b:
        with pytest.raises(SystemExit, match="INSUFFICIENT"):
            mpi.comparable(a, b)

    c4 = _load("review208_c4_empty_cells", "build_c4_evidence.py")
    variables = {
        "T": {"dimensions": ["Time", "x", "y"], "dtype": "f4"},
        "Times": {"dimensions": ["Time", "s"], "dtype": "S1"},
    }
    schema = {"schema_id": "empty", "variables": variables}
    schema["schema_sha256"] = c4.schema_digest(variables)
    result = c4.strict_bitwise_all_frames(str(paths[0]), str(paths[1]),
                                          expected_schema=schema)
    assert result["strict_bitwise"] is False
    assert result["insufficient"] is True


def test_review208_c4_identity_recomputes_controls_and_checks_schema_binding(tmp_path):
    c4 = _load("review208_c4_internal_identity", "build_c4_evidence.py")
    controls = {"label": "review208", "runner_sha256": "b" * 64}
    campaign = c4._producer_campaign_id(controls)
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    for path, scheme in ((a, "37"), (b, "137")):
        (path / "run_identity.json").write_text(json.dumps({
            "schema": 1, "campaign_id": campaign, "scheme": scheme,
            "controls": controls, "experiment_valid": True, "exit_code": 0,
        }))
    wrong = {"schema_id": "requested", "schema_sha256": "a" * 64,
             "campaign_id": "d" * 64}
    with pytest.raises(SystemExit, match="schema.*campaign"):
        c4._require_pair_identity(a, b, expected_schemes=("37", "137"),
                                  expected_schema=wrong)
    with pytest.raises(SystemExit, match="intended scheme"):
        (b / "run_identity.json").write_text(json.dumps({
            "schema": 1, "campaign_id": campaign, "scheme": "other",
            "controls": controls, "experiment_valid": True, "exit_code": 0,
        }))
        c4._require_pair_identity(a, b, expected_schemes=("37", "137"))


def test_review208_c4_pair_cross_checks_producer_status_sibling(tmp_path):
    c4 = _load("review208_c4_status_sibling", "build_c4_evidence.py")
    controls = {"label": "review208", "runner_sha256": "b" * 64}
    campaign = c4._producer_campaign_id(controls)
    runs = []
    for i, scheme in enumerate(("37", "137")):
        run = _run_dir(tmp_path / f"run{i}", proc="1x1")
        (run / "run_identity.json").write_text(json.dumps({
            "schema": 1, "campaign_id": campaign, "scheme": scheme,
            "controls": controls, "requested_proc_grid": "1x1",
            "actual_proc_grid": "1x1", "experiment_valid": True, "exit_code": 0,
        }))
        (run / "experiment_valid.json").write_text(json.dumps({
            "experiment_valid": True, "invalid_reasons": [],
            "requested_proc_grid": "1x1", "actual_proc_grid": "1x1",
            "exit_code": 0, "model_completed": True,
        }))
        runs.append(run)
    assert c4._require_pair_identity(
        runs[0], runs[1], expected_schemes=("37", "137"), require_status=True)
    (runs[1] / "experiment_valid.json").write_text(json.dumps({
        "experiment_valid": False, "invalid_reasons": ["failed"],
        "requested_proc_grid": "1x1", "actual_proc_grid": "1x1",
        "exit_code": 1, "model_completed": False,
    }))
    with pytest.raises(SystemExit, match="producer marked experiment_valid=false"):
        c4._require_pair_identity(
            runs[0], runs[1], expected_schemes=("37", "137"), require_status=True)
