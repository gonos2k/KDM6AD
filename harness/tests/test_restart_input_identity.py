"""Restart-aware active-input identity, without launching WRF."""
from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest


HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))


def _load():
    spec = importlib.util.spec_from_file_location(
        "run_ss_case_restart_identity", HARNESS / "run_ss_case.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _restart_namelist(*, extra: str = "") -> str:
    return f"""&time_control
 restart = .true.,
 start_year = 2025,
 start_month = 7,
 start_day = 19,
 start_hour = 0,
 start_minute = 0,
 start_second = 20,
 input_inname = "wrfinput_d<domain>",
 bdy_inname = "wrfbdy_d<domain>",
 auxinput24_interval_s = 60,
 auxinput24_inname = "wrfchainp_d<domain>",
 {extra}
/
&domains
 max_dom = 1,
/
"""


def test_restart_uses_exact_date_restart_and_keeps_boundary_aux_envelope():
    runner = _load()
    specs = runner.resolve_active_namelist_inputs(_restart_namelist())

    assert [(x["kind"], x["domain"], x["name"]) for x in specs] == [
        ("restart", "d01", "wrfrst_d01_2025-07-19_00:00:20"),
        ("boundary", "d01", "wrfbdy_d01"),
        ("auxinput24", "d01", "wrfchainp_d01"),
    ]


def test_registry_restart_pattern_is_used_when_restart_template_is_omitted():
    runner = _load()
    specs = runner.resolve_active_namelist_inputs(_restart_namelist())

    assert specs[0]["kind"] == "restart"
    assert specs[0]["name"] == "wrfrst_d01_2025-07-19_00:00:20"


def test_nocolons_hashes_the_exact_filename_wrf_will_open(tmp_path):
    runner = _load()
    text = _restart_namelist(extra="nocolons = .true.,")
    specs = runner.resolve_active_namelist_inputs(text)
    restart_spec = next(spec for spec in specs if spec["kind"] == "restart")
    assert restart_spec["name"] == "wrfrst_d01_2025-07-19_00_00_20"

    # A stale colon file must not satisfy identity for the underscore path WRF
    # computes after maybe_remove_colons().
    stale = tmp_path / "wrfrst_d01_2025-07-19_00:00:20"
    actual = tmp_path / restart_spec["name"]
    stale.write_bytes(b"stale colon-name file")
    actual.write_bytes(b"current underscore-name checkpoint")
    identity = runner.hash_resolved_inputs(tmp_path, specs)
    record = next(row for row in identity["records"] if row["kind"] == "restart")
    assert record["resolved_path"] == str(actual.resolve())
    assert record["sha256_before"] == hashlib.sha256(actual.read_bytes()).hexdigest()
    assert record["sha256_before"] != hashlib.sha256(stale.read_bytes()).hexdigest()


@pytest.mark.parametrize("io_form", [100, 102, 199])
def test_rank_split_restart_formats_refuse_single_file_identity(io_form):
    runner = _load()
    text = _restart_namelist(extra=f"io_form_restart = {io_form},")

    with pytest.raises(runner.NamelistInputError, match="rank-specific restart identities"):
        runner.resolve_active_namelist_inputs(text)


@pytest.mark.parametrize("io_form", [2, 4, 202])
def test_supported_single_file_restart_forms_keep_the_same_path(io_form):
    runner = _load()
    text = _restart_namelist(extra=f"io_form_restart = {io_form},")

    specs = runner.resolve_active_namelist_inputs(text)

    assert specs[0]["name"] == "wrfrst_d01_2025-07-19_00:00:20"


def test_malformed_nocolons_logical_is_rejected():
    runner = _load()
    text = _restart_namelist(extra="nocolons = yes,")

    with pytest.raises(runner.NamelistInputError, match="nocolons must be"):
        runner.resolve_active_namelist_inputs(text)


def test_explicit_literal_restart_filename_is_hashed_without_renaming():
    runner = _load()
    text = _restart_namelist(
        extra='rst_inname = "checkpoint_from_scheduler.nc",'
    )

    specs = runner.resolve_active_namelist_inputs(text)

    assert specs[0] == {
        "kind": "restart",
        "domain": "d01",
        "name": "checkpoint_from_scheduler.nc",
    }


def test_per_domain_dates_and_explicit_restart_names_are_resolved_exactly():
    runner = _load()
    text = """&time_control
 restart = .true.,
 start_year = 2025, 2025,
 start_month = 7, 7,
 start_day = 19, 19,
 start_hour = 0, 0,
 start_minute = 0, 0,
 start_second = 20, 40,
 rst_inname = "checkpoint_d01_<date>", "checkpoint_d02_<date>",
 bdy_inname = "wrfbdy_d<domain>",
/
&domains
 max_dom = 2,
/
"""

    specs = runner.resolve_active_namelist_inputs(text)

    assert [(x["kind"], x["domain"], x["name"]) for x in specs] == [
        ("restart", "d01", "checkpoint_d01_2025-07-19_00:00:20"),
        ("restart", "d02", "checkpoint_d02_2025-07-19_00:00:40"),
        ("boundary", "d01", "wrfbdy_d01"),
        ("boundary", "d02", "wrfbdy_d02"),
    ]


def test_nonrestart_initial_identity_is_unchanged_and_ignores_restart_template():
    runner = _load()
    text = """&time_control
 restart = .false.,
 input_inname = "wrfinput_d<domain>",
 bdy_inname = "wrfbdy_d<domain>",
 rst_inname = "wrfrst_d<domain>_<unsupported>",
/
&domains
 max_dom = 1,
/
"""

    specs = runner.resolve_active_namelist_inputs(text)

    assert [(x["kind"], x["name"]) for x in specs] == [
        ("init", "wrfinput_d01"),
        ("boundary", "wrfbdy_d01"),
    ]


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("invalid_date", "invalid restart start date"),
        ("missing_start", "requires explicit start components"),
        ("unsupported_token", "unsupported token"),
        ("wildcard", "wildcard"),
    ],
)
def test_restart_inputs_fail_closed_for_invalid_or_ambiguous_identity(case, message):
    runner = _load()
    text = _restart_namelist()
    if case == "invalid_date":
        text = text.replace(" start_month = 7,", " start_month = 2,")
        text = text.replace(" start_day = 19,", " start_day = 30,")
    elif case == "missing_start":
        text = text.replace(" start_minute = 0,\n", "")
    else:
        value = {
            "unsupported_token": "wrfrst_d<domain>_<hour>",
            "wildcard": "wrfrst_d<domain>_*",
        }[case]
        text = text.replace(
            ' auxinput24_inname = "wrfchainp_d<domain>",\n',
            f' auxinput24_inname = "wrfchainp_d<domain>",\n'
            f' rst_inname = "{value}",\n',
        )

    with pytest.raises(runner.NamelistInputError, match=message):
        runner.resolve_active_namelist_inputs(text)


def test_restart_input_hash_is_sealed_before_and_after_the_run(tmp_path):
    runner = _load()
    restart = tmp_path / "wrfrst_d01_2025-07-19_00:00:20"
    boundary = tmp_path / "wrfbdy_d01"
    restart.write_bytes(b"restart checkpoint at 20s")
    boundary.write_bytes(b"boundary history 0..40s")
    (tmp_path / "wrfchainp_d01").write_bytes(b"active auxiliary input")
    specs = runner.resolve_active_namelist_inputs(_restart_namelist())

    identity = runner.hash_resolved_inputs(tmp_path, specs)
    restart_record = next(r for r in identity["records"] if r["kind"] == "restart")
    assert restart_record["sha256_before"] == hashlib.sha256(restart.read_bytes()).hexdigest()
    runner.refresh_input_hashes(identity)
    assert identity["complete"] is True
    assert restart_record["sha256_after"] == restart_record["sha256_before"]
    assert restart_record["stable"] is True

    restart.write_bytes(b"different checkpoint")
    runner.refresh_input_hashes(identity)
    assert identity["complete"] is False
    assert restart_record["sha256_after"] != restart_record["sha256_before"]
    assert restart_record["stable"] is False
