"""Portable checks of the policy passed by actual LC05 initialization callers."""
from pathlib import Path

import pytest


@pytest.mark.parametrize("caller", ["runner", "conserving_runner", "real_fixture",
                                    "smoke", "conserving_smoke", "regime2"])
def test_lc05_initialization_callers_request_the_profile(caller, monkeypatch, tmp_path):
    import test_da_fulldomain as full
    import test_da_regime2 as regime
    import test_real_innovation_lc05 as real
    import test_rttov_case_writer as fixtures
    from kdm6.io import frame_reader
    from kdm6.obs import gk2a_l1b

    class ReadObserved(Exception):
        pass

    calls = []

    def reader(path, time_idx=0, nccn_policy="as_stored"):
        calls.append((time_idx, nccn_policy))
        # Stop at the real call boundary, before NetCDF, GK2A or RTTOV execution.
        raise ReadObserved

    monkeypatch.setattr(frame_reader, "read_wrfout_frame", reader)
    monkeypatch.setattr(fixtures, "_HAVE_CLOUD_EXE", True)
    monkeypatch.setattr(gk2a_l1b, "slot_files", lambda *a, **k: [])
    monkeypatch.setattr(regime, "_lc05_gate", lambda: (Path("wrfinput"), Path("obs"), Path("cal")))
    with pytest.raises(ReadObserved):
        if caller in ("runner", "conserving_runner"):
            runner = full._load_runner()
            monkeypatch.setattr(runner, "snapshot_provenance", lambda *a, **k: {"rttov": {}})
            runner.main(str(tmp_path / "out.json"), str(tmp_path / "case"),
                        conserving=caller == "conserving_runner")
        elif caller == "real_fixture":
            real.lc05_collocated.__wrapped__()
        elif caller == "smoke":
            full.test_fulldomain_smoke_capped(tmp_path)
        elif caller == "conserving_smoke":
            full.test_fulldomain_smoke_conserving_capped(tmp_path)
        else:
            regime.test_regime2_live_bootstrap_lc05(tmp_path)
    assert calls == [(0, "init_profile")]
