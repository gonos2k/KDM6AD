"""RTTOV ami/501 fixture accessors — the reference T/Q/p_half profile grids the
clear-sky evidence path rides.

These read the on-disk AD-RTTOV fixture case (resolved by rttov_case_writer,
runtime bundle first then AD_RTTOV_HOME). They used to live in
tests/test_rttov_case_writer.py, which coupled the PRODUCTION evidence runner
to the test tree — a test refactor could then silently change an evidence run
(external review P2-1). They are package data accessors, not test logic, so
they live here; the test module re-exports them for its own consumers.

Importing this module is side-effect-free (only a path is resolved); calling
an accessor requires the fixture files to exist on disk.
"""
from __future__ import annotations

import numpy as np

from .rttov_case_writer import default_fixture_case_dir

CHANNELS = tuple(range(1, 17))            # ami/501: 16 AMI channels


def fixture_case_dir():
    """The resolved ami/501 clear-sky fixture case directory."""
    return default_fixture_case_dir()


def fixture_nlayers(profile: str = "001") -> int:
    atm = default_fixture_case_dir() / "in" / "profiles" / profile / "atm"
    return len(np.loadtxt(atm / "t.txt"))


def fixture_tq(profile: str = "001"):
    """The fixture profile's T (K) and Q (ppmv moist) vectors."""
    atm = default_fixture_case_dir() / "in" / "profiles" / profile / "atm"
    return np.loadtxt(atm / "t.txt"), np.loadtxt(atm / "q.txt")


def fixture_p_half(profile: str = "001"):
    """The fixture profile's p_half grid (the grid the run uses; model T/Q ride it)."""
    atm = default_fixture_case_dir() / "in" / "profiles" / profile / "atm"
    return np.loadtxt(atm / "p_half.txt")
