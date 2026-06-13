"""M4/M5 gates for the out-of-process RTTOV runner (design 7, 14.2).

The runner's load-bearing, env-independent piece is the OUTPUT parser: it must
extract BT + the K-matrix + quality from the verified rttov_test ASCII output
with the correct profile-major/channel-minor orientation and the design's
[nprofiles, nchannels, nlayers] K shape. These tests parse the committed ami/501
fixture output (a prior verified RTTOV run) -- no live RTTOV invocation -- and
are skipped if AD_RTTOV_HOME is absent. The out-of-process subprocess path
(run_rttov_k) is exercised via its missing-script guard.
"""
from __future__ import annotations

import math

import pytest

from kdm6.obs.rttov_runner import (
    RttovKOutput,
    ad_rttov_home,
    parse_rttov_profiles_k,
    parse_rttov_radiance,
    parse_rttov_k_case,
    run_rttov_k,
)

_QUAL2 = "RADIANCE%QUALITY = (\n  0 0\n)\n"

AMI_NCHANNELS = 16
_FIX = ad_rttov_home() / "external/rttov14/src/rttov_test/tests.1.gfortran-openmp/ami/501/out"
_HAVE_FIX = (_FIX / "k" / "profiles_k.txt").is_file() and (_FIX / "direct" / "radiance.txt").is_file()
skip_no_fixture = pytest.mark.skipif(not _HAVE_FIX, reason=f"ami/501 fixture not found under {_FIX}")


@skip_no_fixture
def test_parse_radiance_bt_orientation():
    """BT reshapes [6, 16] with solar channels 0-5 == 0 and IR channels 6-15
    carrying brightness temperature -- proves profile-major orientation."""
    rad = parse_rttov_radiance(_FIX / "direct" / "radiance.txt", nchannels=AMI_NCHANNELS)
    bt = rad["bt"]
    assert rad["nprofiles"] == 6
    assert len(bt) == 6 and all(len(row) == 16 for row in bt)
    # profile 0: VIS/NIR (0-5) are 0 in BT space; IR (6-15) are physical BTs.
    assert all(bt[0][c] == 0.0 for c in range(6))
    assert all(150.0 < bt[0][c] < 350.0 for c in range(6, 16))
    assert math.isclose(bt[0][6], 308.183, abs_tol=1e-2)


@skip_no_fixture
def test_parse_radiance_quality_all_clear():
    rad = parse_rttov_radiance(_FIX / "direct" / "radiance.txt", nchannels=AMI_NCHANNELS)
    q = rad["rad_quality"]
    assert len(q) == 6 and all(len(row) == 16 for row in q)
    assert all(v == 0 for row in q for v in row)  # ami/501 is clear-sky clean


@skip_no_fixture
def test_parse_profiles_k_shape_and_finite():
    """K T-field reshapes to [nprofiles, nchannels, nlayers] = [6, 16, 69]."""
    k, nprofiles = parse_rttov_profiles_k(_FIX / "k" / "profiles_k.txt", nchannels=AMI_NCHANNELS)
    assert nprofiles == 6
    assert "T" in k and "Q" in k
    tk = k["T"]
    assert len(tk) == 6
    assert all(len(prof) == 16 for prof in tk)
    assert all(len(prof[ch]) == 69 for prof in tk for ch in range(16))
    # all finite
    assert all(math.isfinite(v) for prof in tk for ch in prof for v in ch)
    # P_HALF is on levels (70 = nlayers+1)
    assert "P_HALF" in k and len(k["P_HALF"][0][0]) == 70


@skip_no_fixture
def test_parse_rttov_k_case_assembles_output():
    out = parse_rttov_k_case(_FIX, nchannels=AMI_NCHANNELS, expected_nprofiles=6)
    assert isinstance(out, RttovKOutput)
    assert out.nprofiles == 6 and out.nchannels == 16
    assert len(out.bt) == 6 and len(out.bt[0]) == 16
    assert out.rad_quality is not None
    assert out.k["T"][0][6] is not None and len(out.k["T"][0][6]) == 69


@skip_no_fixture
def test_wrong_nchannels_rejected():
    # 96 values not divisible by 7 -> loud error, not a silent mis-reshape.
    with pytest.raises(ValueError, match="not divisible by nchannels"):
        parse_rttov_radiance(_FIX / "direct" / "radiance.txt", nchannels=7)


def test_missing_quality_block_raises(tmp_path):
    """RADIANCE%QUALITY is required: without it the design section-8 quality mask
    cannot be enforced, so the runner must raise (not silently return no quality)."""
    f = tmp_path / "radiance.txt"
    f.write_text("RADIANCE%BT = (\n  300.0 301.0\n)\n")  # BT present, QUALITY absent
    with pytest.raises(ValueError, match="no RADIANCE%QUALITY"):
        parse_rttov_radiance(f, nchannels=2)


def test_quality_bt_length_mismatch_raises(tmp_path):
    f = tmp_path / "radiance.txt"
    f.write_text("RADIANCE%BT = (\n  300.0 301.0\n)\nRADIANCE%QUALITY = (\n  0\n)\n")
    with pytest.raises(ValueError, match="QUALITY length"):
        parse_rttov_radiance(f, nchannels=2)


def test_run_rttov_k_missing_script_raises(tmp_path):
    """run_rttov_k requires a prepared case (run.sh); absence is a loud error,
    not a silent no-op. (Exercises the out-of-process entry without live RTTOV.)"""
    with pytest.raises(FileNotFoundError, match="run script not found"):
        run_rttov_k(tmp_path, nchannels=AMI_NCHANNELS, expected_nprofiles=6)


def test_run_rttov_k_requires_expected_nprofiles(tmp_path):
    """expected_nprofiles is required (no silent-truncation opt-out): omitting it
    is a TypeError, not a run with the guard disabled."""
    with pytest.raises(TypeError):
        run_rttov_k(tmp_path, nchannels=AMI_NCHANNELS)  # missing expected_nprofiles


# --- review fixes: truncation / empty-L / P_HALF / freshness -----------------

def test_expected_nprofiles_catches_uniform_truncation(tmp_path):
    """A uniformly-truncated case (48 chanprof @16ch -> 3 profiles) parses as a
    smaller valid case; parse_rttov_k_case must reject it against expected=6
    (raw parsers are pure/discovery; the guard lives at the case boundary)."""
    k = tmp_path / "k"
    k.mkdir()
    bt = " ".join(["0.0"] * 48)
    q = " ".join(["0"] * 48)
    (k / "radiance.txt").write_text(f"RADIANCE%BT = (\n {bt}\n)\nRADIANCE%QUALITY = (\n {q}\n)\n")
    pk = "".join(f"PROFILES_K( {i})%T = (\n 1.0\n)\n" for i in range(1, 49))
    (k / "profiles_k.txt").write_text(pk)
    # raw parser discovers 3 profiles (no guard at the pure-parser level):
    assert parse_rttov_radiance(k / "radiance.txt", nchannels=16)["nprofiles"] == 3
    # the case boundary rejects against the known expected count:
    with pytest.raises(ValueError, match="expected 6"):
        parse_rttov_k_case(tmp_path, nchannels=16, expected_nprofiles=6)


def test_empty_k_field_raises(tmp_path):
    f = tmp_path / "profiles_k.txt"
    f.write_text("PROFILES_K(   1)%T = (\n)\nPROFILES_K(   2)%T = (\n)\n")
    with pytest.raises(ValueError, match=r"is empty \(L=0\)"):
        parse_rttov_profiles_k(f, nchannels=2)


def test_non_finite_k_field_raises(tmp_path):
    f = tmp_path / "profiles_k.txt"
    f.write_text("PROFILES_K(   1)%T = (\n 1.0 NaN\n)\nPROFILES_K(   2)%T = (\n 3.0 4.0\n)\n")
    with pytest.raises(ValueError, match="non-finite marker"):
        parse_rttov_profiles_k(f, nchannels=2)


def test_uniform_nan_drop_in_k_rejected(tmp_path):
    """The real hole: a NaN at the SAME position in every row would drop
    uniformly -> rectangular-but-shorter K, passing ragged + isfinite. The raw
    non-finite token scan must reject it (Codex stop-review)."""
    f = tmp_path / "profiles_k.txt"
    f.write_text(
        "PROFILES_K(   1)%T = (\n 1.0 NaN 3.0\n)\n"
        "PROFILES_K(   2)%T = (\n 4.0 NaN 6.0\n)\n")  # uniform NaN column
    with pytest.raises(ValueError, match="non-finite marker"):
        parse_rttov_profiles_k(f, nchannels=2)


def test_bt_huge_exponent_inf_rejected(tmp_path):
    """A regex-matchable infinity (huge exponent) parses to inf and is caught by
    the math.isfinite check (the token scan does not see an 'inf' token here)."""
    f = tmp_path / "radiance.txt"
    f.write_text("RADIANCE%BT = (\n 1.0E+400 2.0\n)\n" + _QUAL2)
    with pytest.raises(ValueError, match="RADIANCE%BT has non-finite"):
        parse_rttov_radiance(f, nchannels=2)


def test_phalf_layer_mismatch_raises(tmp_path):
    f = tmp_path / "profiles_k.txt"
    f.write_text(
        "PROFILES_K(   1)%T = (\n 1.0 2.0 3.0\n)\n"
        "PROFILES_K(   2)%T = (\n 4.0 5.0 6.0\n)\n"
        "PROFILES_K(   1)%P_HALF = (\n 1.0 2.0 3.0\n)\n"   # 3 levels, needs 4
        "PROFILES_K(   2)%P_HALF = (\n 4.0 5.0 6.0\n)\n")
    with pytest.raises(ValueError, match="P_HALF has 3 levels but T has 3 layers"):
        parse_rttov_profiles_k(f, nchannels=2)


def test_run_rttov_k_clean_exit_without_output_raises(tmp_path):
    """A run.sh that exits 0 without rewriting k/ must raise (clean exit != valid
    output; the stale-output / libomp I/O-race class, review HIGH)."""
    k = tmp_path / "k"
    k.mkdir()
    (k / "radiance.txt").write_text("RADIANCE%BT = (\n 1 2\n)\n" + _QUAL2)   # stale
    (k / "profiles_k.txt").write_text("PROFILES_K(   1)%T = (\n 1\n)\n")     # stale
    (tmp_path / "run.sh").write_text("#!/bin/sh\nexit 0\n")                  # writes nothing
    with pytest.raises(RuntimeError, match="did not write"):
        run_rttov_k(tmp_path, nchannels=2, expected_nprofiles=1)
