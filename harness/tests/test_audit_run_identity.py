"""Focused counterexamples for run identity and evidence boundaries.

These tests use only temporary files.  They do not invoke WRF, MPI, or a host
build; the purpose is to pin the producer/consumer metadata contract.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


HARNESS = Path(__file__).resolve().parents[1]


def _load(name: str, filename: str | None = None):
    spec = importlib.util.spec_from_file_location(
        name, HARNESS / f"{filename or name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_run(root: Path, *, requested: str, actual: str,
               nml: str = "&domains\n/\n", inputs: dict[str, bytes] | None = None):
    root.mkdir()
    exe = "a" * 64
    runner = "b" * 64
    (root / "wrf_exe_sha256").write_text(f"{exe}\n")
    (root / "runner_sha256").write_text(f"runner {runner}\n")
    (root / "proc_grid").write_text(
        f"requested {requested}\nactual {actual}\nmatches "
        f"{'yes' if requested == actual else 'NO -- mismatch'}\n")
    (root / "namelist.input").write_text(nml)
    if inputs is not None:
        records = []
        for name, payload in inputs.items():
            path = root / name
            path.write_bytes(payload)
            digest = hashlib.sha256(payload).hexdigest()
            records.append({"kind": "init" if "input" in name else "boundary",
                            "domain": "d01", "name": name,
                            "sha256": digest, "sha256_before": digest,
                            "sha256_after": digest, "status": "ok",
                            "stable": True})
        (root / "input_sha256.json").write_text(json.dumps({
            "schema": 1, "declared": True, "complete": True,
            "records": records,
        }))
    return root


def test_active_resolver_includes_boundary_and_active_aux_per_domain():
    runner = _load("run_ss_case")
    text = """&domains
 max_dom = 2,
 input_inname = "wrfinput_d<domain>",
 bdy_inname = "wrfbdy_d<domain>",
 auxinput24_interval = 0, 60,
 auxinput24_inname = "unused_d<domain>", "wrfchainp_d<domain>",
/
"""
    specs = runner.resolve_active_namelist_inputs(text)
    assert [(s["kind"], s["domain"], s["name"]) for s in specs] == [
        ("init", "d01", "wrfinput_d01"),
        ("init", "d02", "wrfinput_d02"),
        ("boundary", "d01", "wrfbdy_d01"),
        ("boundary", "d02", "wrfbdy_d02"),
        ("auxinput24", "d02", "wrfchainp_d02"),
    ]


def test_active_input_hashes_record_each_resolved_file(tmp_path):
    runner = _load("run_ss_case_hash", "run_ss_case")
    (tmp_path / "wrfinput_d01").write_bytes(b"initial")
    (tmp_path / "wrfbdy_d01").write_bytes(b"boundary")
    specs = [{"kind": "init", "domain": "d01", "name": "wrfinput_d01"},
             {"kind": "boundary", "domain": "d01", "name": "wrfbdy_d01"}]
    identity = runner.hash_resolved_inputs(tmp_path, specs)
    assert identity["complete"] is True
    assert {r["kind"] for r in identity["records"]} == {"init", "boundary"}
    assert all(len(r["sha256_before"]) == 64 for r in identity["records"])


def test_decomposition_rejects_equal_actual_grid_with_different_requests(tmp_path):
    mpi = _load("g33_mpi_divergence_equal_actual", "g33_mpi_divergence")
    nml = "&domains\n/\n"
    a = _write_run(tmp_path / "a", requested="2x2", actual="1x1", nml=nml)
    b = _write_run(tmp_path / "b", requested="4x1", actual="1x1", nml=nml)
    with pytest.raises(SystemExit, match="requested 2x2"):
        mpi.same_experiment(a, b, expect="decomposition")


def test_decomposition_requires_matching_request_and_actual(tmp_path):
    mpi = _load("g33_mpi_divergence_mismatch", "g33_mpi_divergence")
    nml = "&domains\n/\n"
    a = _write_run(tmp_path / "a", requested="2x2", actual="1x1", nml=nml)
    b = _write_run(tmp_path / "b", requested="4x1", actual="4x1", nml=nml)
    with pytest.raises(SystemExit, match="requested 2x2"):
        mpi.same_experiment(a, b, expect="decomposition")


def test_decomposition_requires_all_declared_input_hashes(tmp_path):
    mpi = _load("g33_mpi_divergence_inputs", "g33_mpi_divergence")
    nml = """&domains
 max_dom = 1,
 input_inname = "wrfinput_d<domain>",
 bdy_inname = "wrfbdy_d<domain>",
/
"""
    a = _write_run(tmp_path / "a", requested="2x2", actual="2x2", nml=nml,
                   inputs={"wrfinput_d01": b"same", "wrfbdy_d01": b"same"})
    b = _write_run(tmp_path / "b", requested="4x1", actual="4x1", nml=nml)
    with pytest.raises(SystemExit, match="input_sha256"):
        mpi.same_experiment(a, b, expect="decomposition")


def test_decomposition_rejects_differing_boundary_hash(tmp_path):
    mpi = _load("g33_mpi_divergence_boundary", "g33_mpi_divergence")
    nml = """&domains
 max_dom = 1,
 input_inname = "wrfinput_d<domain>",
 bdy_inname = "wrfbdy_d<domain>",
/
"""
    a = _write_run(tmp_path / "a", requested="2x2", actual="2x2", nml=nml,
                   inputs={"wrfinput_d01": b"same", "wrfbdy_d01": b"A"})
    b = _write_run(tmp_path / "b", requested="4x1", actual="4x1", nml=nml,
                   inputs={"wrfinput_d01": b"same", "wrfbdy_d01": b"B"})
    with pytest.raises(SystemExit, match="input_sha256"):
        mpi.same_experiment(a, b, expect="decomposition")


def test_decomposition_consumes_invalid_producer_status(tmp_path):
    mpi = _load("g33_mpi_divergence_invalid_producer", "g33_mpi_divergence")
    a = _write_run(tmp_path / "a", requested="2x2", actual="2x2")
    b = _write_run(tmp_path / "b", requested="4x1", actual="4x1")
    for run in (a, b):
        (run / "wrf_exe_sha256").write_text(
            "a" * 64 + "\n"
            "stable NO -- the binary changed during the run\n")
        (run / "experiment_valid.json").write_text(json.dumps({
            "experiment_valid": False,
            "invalid_reasons": ["binary_changed_during_run"],
        }))
    with pytest.raises(SystemExit, match="experiment_valid=false"):
        mpi.same_experiment(a, b, expect="decomposition")


def test_stable_no_is_rejected_even_without_legacy_verdict_file(tmp_path):
    mpi = _load("g33_mpi_divergence_stable_no", "g33_mpi_divergence")
    a = _write_run(tmp_path / "a", requested="2x2", actual="2x2")
    b = _write_run(tmp_path / "b", requested="4x1", actual="4x1")
    (a / "wrf_exe_sha256").write_text("a" * 64 + "\nstable NO\n")
    with pytest.raises(SystemExit, match="stable NO"):
        mpi.same_experiment(a, b, expect="decomposition")


def test_standard_namelist_omitted_wr_defaults_refuse_attribution(tmp_path):
    mpi = _load("g33_mpi_divergence_wr_defaults", "g33_mpi_divergence")
    nml = "&domains\n max_dom = 1,\n/\n"
    a = _write_run(tmp_path / "a", requested="2x2", actual="2x2", nml=nml)
    b = _write_run(tmp_path / "b", requested="4x1", actual="4x1", nml=nml)
    with pytest.raises(SystemExit, match="defaults.*unsupported"):
        mpi.same_experiment(a, b, expect="decomposition")


def test_fractional_max_dom_is_not_truncated():
    runner = _load("run_ss_case_fractional_maxdom", "run_ss_case")
    nml = """&domains
 max_dom = 1.5,
 input_inname = "wrfinput_d<domain>",
 bdy_inname = "wrfbdy_d<domain>",
/
"""
    with pytest.raises(runner.NamelistInputError, match="fractional"):
        runner.resolve_active_namelist_inputs(nml)


def test_aux_name_without_explicit_interval_is_unsupported():
    runner = _load("run_ss_case_aux_default", "run_ss_case")
    nml = """&domains
 max_dom = 1,
 input_inname = "wrfinput_d<domain>",
 bdy_inname = "wrfbdy_d<domain>",
 auxinput24_inname = "wrfchainp_d<domain>",
/
"""
    with pytest.raises(runner.NamelistInputError, match="explicit interval"):
        runner.resolve_active_namelist_inputs(nml)


def test_canonical_input_record_seal_is_validated(tmp_path):
    runner = _load("run_ss_case_canonical", "run_ss_case")
    mpi = _load("g33_mpi_divergence_canonical", "g33_mpi_divergence")
    nml = """&domains
 max_dom = 1,
 input_inname = "wrfinput_d<domain>",
 bdy_inname = "wrfbdy_d<domain>",
/
"""
    a = _write_run(tmp_path / "a", requested="2x2", actual="2x2", nml=nml,
                   inputs={"wrfinput_d01": b"same", "wrfbdy_d01": b"same"})
    b = _write_run(tmp_path / "b", requested="4x1", actual="4x1", nml=nml,
                   inputs={"wrfinput_d01": b"same", "wrfbdy_d01": b"same"})
    for run in (a, b):
        identity = json.loads((run / "input_sha256.json").read_text())
        identity["canonical_sha256"] = runner.canonical_input_sha256(identity)
        (run / "input_sha256.json").write_text(json.dumps(identity))
    identity = json.loads((a / "input_sha256.json").read_text())
    identity["records"][0]["sha256_before"] = "0" * 64
    (a / "input_sha256.json").write_text(json.dumps(identity))
    with pytest.raises(SystemExit, match="canonical input identity hash"):
        mpi.same_experiment(a, b, expect="decomposition")


def test_comparable_rejects_dimension_order_mismatch():
    np = pytest.importorskip("numpy")
    mpi = _load("g33_mpi_divergence_dimensions", "g33_mpi_divergence")

    class Var:
        def __init__(self, array, dimensions):
            self.array = np.asarray(array)
            self.dimensions = dimensions
            self.shape = self.array.shape
            self.dtype = self.array.dtype
            self.ndim = self.array.ndim

        def __getitem__(self, index):
            return self.array[index]

    class Dataset:
        def __init__(self, variables):
            self.variables = variables

        def __getitem__(self, name):
            return self.variables[name]

    times = Var(np.zeros((1, 1), dtype="S1"), ("Time", "DateStrLen"))
    values = np.ones((1, 2, 3), dtype="f4")
    a = Dataset({"Times": times,
                 "T": Var(values, ("Time", "south_north", "west_east"))})
    b = Dataset({"Times": times,
                 "T": Var(values, ("Time", "west_east", "south_north"))})
    with pytest.raises(SystemExit, match="dimension order"):
        mpi.comparable(a, b)


def test_recert_rejects_an_unclaimed_second_forecast(tmp_path):
    if importlib.util.find_spec("netCDF4") is None:
        pytest.skip("netCDF4 is unavailable")
    c4 = _load("build_c4_evidence_extra_output", "build_c4_evidence")
    run = tmp_path / "run"
    run.mkdir()
    (run / "exit_code").write_text("0\n")
    for rank in range(4):
        (run / f"rsl.error.{rank:04d}").write_text(
            "2025-07-19_12:00:00 wrf: SUCCESS COMPLETE WRF\n")
    # The exact output count is checked before a NetCDF comparison, so these
    # placeholders are sufficient to exercise the scope refusal.
    (run / "klfs_lc05_fcst.aaa").write_bytes(b"first")
    (run / "klfs_lc05_fcst.zzz").write_bytes(b"second")
    result = c4.verify_recert_run(run, np=4)
    assert result["verified"] is False
    assert result["output_files_ok"] is False
    assert len(result["forecast_files"]) == 2


def test_recert_rejects_a_directory_named_like_forecast_output(tmp_path):
    if importlib.util.find_spec("netCDF4") is None:
        pytest.skip("netCDF4 is unavailable")
    c4 = _load("build_c4_evidence_directory_output", "build_c4_evidence")
    run = tmp_path / "run"
    run.mkdir()
    (run / "exit_code").write_text("0\n")
    for rank in range(4):
        (run / f"rsl.error.{rank:04d}").write_text(
            "2025-07-19_12:00:00 wrf: SUCCESS COMPLETE WRF\n")
    (run / "wrfout_d01_fake").mkdir()
    result = c4.verify_recert_run(run, np=4)
    assert result["verified"] is False
    assert result["output_files_ok"] is False
    assert "regular file" in result["output_error"]


def test_recert_reports_a_non_netcdf_history_file_as_invalid(tmp_path):
    if importlib.util.find_spec("netCDF4") is None:
        pytest.skip("netCDF4 is unavailable")
    c4 = _load("build_c4_evidence_bad_output", "build_c4_evidence")
    run = tmp_path / "run"
    run.mkdir()
    (run / "exit_code").write_text("0\n")
    for rank in range(4):
        (run / f"rsl.error.{rank:04d}").write_text(
            "2025-07-19_12:00:00 wrf: SUCCESS COMPLETE WRF\n")
    (run / "wrfout_d01_fake").write_bytes(b"not netcdf")
    result = c4.verify_recert_run(run, np=4)
    assert result["verified"] is False
    assert result["output_files_ok"] is False
    assert "readable NetCDF" in result["output_error"]
