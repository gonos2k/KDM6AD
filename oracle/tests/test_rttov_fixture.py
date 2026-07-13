"""P2-1 (external review): the RTTOV ami/501 fixture accessors are a PACKAGE
module, so the production evidence runner no longer imports them from the test
tree (a test refactor must not be able to change a production evidence run)."""
from __future__ import annotations

from pathlib import Path


def test_rttov_fixture_is_a_package_module():
    from kdm6.obs.rttov_fixture import (CHANNELS, fixture_case_dir,
                                        fixture_nlayers, fixture_p_half,
                                        fixture_tq)
    assert CHANNELS == tuple(range(1, 17))            # ami/501: 16 AMI channels
    assert callable(fixture_case_dir)
    assert all(callable(f) for f in (fixture_tq, fixture_p_half,
                                     fixture_nlayers))


def test_runner_does_not_depend_on_the_test_tree():
    """Production must not consume tests (reviewer P2-1): the runner sources
    its fixtures from the package, not from test_rttov_case_writer, and does
    not put oracle/tests on sys.path."""
    src = (Path(__file__).resolve().parents[1]
           / "scripts" / "run_fulldomain_lc05.py").read_text()
    assert "test_rttov_case_writer" not in src
    assert 'str(_ORACLE / "tests")' not in src


def test_test_module_reexports_match_the_package():
    """The test module keeps its _CHANNELS/_fixture_* names (its other
    consumers are unchanged), now sourced from the package."""
    import test_rttov_case_writer as t
    from kdm6.obs import rttov_fixture as pkg
    assert t._CHANNELS == pkg.CHANNELS
    assert t._fixture_tq is pkg.fixture_tq
    assert t._fixture_p_half is pkg.fixture_p_half
