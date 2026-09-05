"""Focused regressions for the G33F/G33R generator contracts.

These checks stay at the parser and producer-contract boundary.  The refinement
CLI leg is optional because a public checkout may not have a Torch build; when a
driver is supplied, it exercises the emitted header and runtime validation.
"""
from pathlib import Path
import math
import os
import re
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "harness" / "g33_fortran"))

import g33_fixture_v1 as fixtures  # noqa: E402
import g33_fortran_dump as dump   # noqa: E402


SAMPLE = ROOT / "harness" / "tests" / "data" / "g33_conservative_sample.g33f"


def _parse(text):
    _, authority = fixtures.load_fixture(fixtures.DEFAULT_FIXTURE_ID)
    return dump.parse_fortran_run(text, "conservative", authority["K"], authority["B"])


def test_future_g33f_versions_are_rejected_before_grammar_dispatch():
    raw = SAMPLE.read_text(encoding="utf-8")
    for version in (15, 999):
        future = raw.replace("BEGIN v14", f"BEGIN v{version}")
        future = future.replace("END v14", f"END v{version}")
        with pytest.raises(dump.FortranRunError, match="unsupported G33F protocol version"):
            _parse(future)


def test_g33f_duplicate_init_metadata_is_rejected():
    lines = SAMPLE.read_text(encoding="utf-8").splitlines()
    init = next(i for i, line in enumerate(lines) if line.startswith("G33F INIT "))
    lines.insert(init + 1, lines[init])
    with pytest.raises(dump.FortranRunError, match=r"INIT: 1 duplicate key"):
        _parse("\n".join(lines) + "\n")


def test_current_g33f_version_still_parses_with_unique_init_records():
    parsed = _parse(SAMPLE.read_text(encoding="utf-8"))
    assert parsed.protocol_version == 14
    assert set(parsed.init_params) == set(dump._INIT_ARGS)


def test_all_five_public_fixture_aliases_resolve_to_the_declared_build_selector():
    assert len(fixtures.FIXTURES) == 5
    for fixture_id, spec in fixtures.FIXTURES.items():
        assert fixtures.canonical_id(fixture_id) == fixture_id
        assert fixtures.canonical_id(spec.fortran_module.stem) == fixture_id
        assert fixtures.canonical_id(spec.cpp_header.stem) == fixture_id
        assert spec.fortran_build_name == spec.fortran_module.stem


def test_cpp_refinement_custom_schedule_cli_contract_when_driver_is_available():
    """Exercise the real C++ producer when a configured build exposes it.

    CI's public checkout does not carry a Torch build, so this remains an optional
    integration leg.  ``KDM6_G33_REFINE_DRIVER`` makes the executable under test
    explicit; the segment vector defaults to the 20-second default fixture and can
    be changed for a different built fixture with ``KDM6_G33_REFINE_SEGMENTS``.
    """
    configured = os.environ.get("KDM6_G33_REFINE_DRIVER")
    candidates = [
        Path(configured) if configured else None,
        ROOT / "libtorch" / "build" / "g33_refine_driver",
    ]
    driver = next((p for p in candidates if p is not None and p.is_file()), None)
    if driver is None:
        pytest.skip("no configured C++ refinement driver; set KDM6_G33_REFINE_DRIVER")

    segments = os.environ.get("KDM6_G33_REFINE_SEGMENTS", "10,10")
    values = [float(token) for token in segments.split(",")]
    assert values and all(math.isfinite(value) and value > 0 for value in values)
    assert len(set(values)) == 1

    def run(spec):
        return subprocess.run(
            [str(driver), "--algo=legacy", f"--segments={spec}"],
            cwd=ROOT, capture_output=True, text=True,
        )

    def run_nsplit(spec):
        return subprocess.run(
            [str(driver), "--algo=legacy", f"--nsplit={spec}"],
            cwd=ROOT, capture_output=True, text=True,
        )

    for spec, expected in (
        ("100,", "empty duration"),
        ("100x,100", "malformed duration"),
        ("-100,200,200", "finite and strictly positive"),
        ("nan,150,150", "finite and strictly positive"),
        ("250,50", "equal durations"),
    ):
        result = run(spec)
        assert result.returncode != 0, result.stdout
        assert expected in result.stderr

    for spec, expected in (
        ("3x", "positive decimal integer"),
        (" 3", "positive decimal integer"),
        ("3 ", "positive decimal integer"),
        ("+3", "positive decimal integer"),
        ("3.0", "positive decimal integer"),
        ("0", "positive decimal integer"),
        ("2147483648", "out of range"),
    ):
        result = run_nsplit(spec)
        assert result.returncode != 0, result.stdout
        assert expected in result.stderr

    nsplit_result = run_nsplit("3")
    assert nsplit_result.returncode == 0, nsplit_result.stderr
    nsplit_header = re.search(
        r"^G33R BEGIN nsplit (\d+) \S+ \S+ delt (\S+) loops (\d+) dtcld (\S+)$",
        nsplit_result.stdout, re.MULTILINE,
    )
    assert nsplit_header, nsplit_result.stdout[:1000]
    assert int(nsplit_header.group(1)) == 3
    assert int(nsplit_header.group(3)) >= 1

    result = run(segments)
    assert result.returncode == 0, result.stderr
    header = re.search(
        r"^G33R BEGIN nsplit (\d+) \S+ \S+ delt (\S+) loops (\d+) dtcld (\S+)$",
        result.stdout, re.MULTILINE,
    )
    assert header, result.stdout[:1000]
    nsplit, delt, loops, dtcld = int(header.group(1)), float(header.group(2)), int(header.group(3)), float(header.group(4))
    assert nsplit == len(values)
    assert math.isclose(delt * nsplit, sum(values), rel_tol=0.0, abs_tol=1e-6)
    assert math.isclose(dtcld, delt, rel_tol=0.0, abs_tol=1e-6)
    assert loops >= 1


@pytest.mark.parametrize("fixture_id", sorted(fixtures.FIXTURES))
def test_each_registry_cpp_fixture_has_driver_and_build_selector(fixture_id):
    spec = fixtures.spec(fixture_id)
    if not spec.cpp_define:
        return
    macro = "KDM6_G33_FIXTURE_" + spec.cpp_define.upper()
    header = spec.cpp_header.name
    for source_name in ("abc_driver.cpp", "g33_refine_driver.cpp"):
        source = (ROOT / "harness" / "g33_overlay" / source_name).read_text()
        assert macro in source
        assert header in source
    for script_name in ("selfcheck_build.sh", "refine_build_cpp.sh"):
        script = (ROOT / "harness" / "g33_overlay" / script_name).read_text()
        assert f"--fixture={spec.cpp_define}" in script
