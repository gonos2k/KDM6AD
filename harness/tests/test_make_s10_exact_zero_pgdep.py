from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import make_s10_exact_zero_pgdep as guard  # noqa: E402
import make_s10_stage2_pair as pair  # noqa: E402
import make_progb_validity_capture as validity  # noqa: E402


def pair_overlay_fixture() -> str:
    return (
        "module module_mp_kdm6_cons\n"
        + guard.USE_ANCHOR
        + "contains\nsubroutine kdm62d\n"
        + pair._DECL_ANCHOR
        + guard.BRS_MIN_ANCHOR
        + pair.COLD_BRS_ANCHOR
        + "end subroutine\nend module\n"
    )


def test_stage2_guard_is_exact_zero_only_preserves_other_terms_and_fail_closes():
    base = pair_overlay_fixture()
    guarded = guard.inject_guard(base)
    assert guard.strip_guard(guarded) == base
    block = guarded[guarded.index("! S10_EXACT_ZERO_BEGIN:stage2_pgdep_guard"):
                    guarded.index("! S10_EXACT_ZERO_END:stage2_pgdep_guard")]
    zero, nonzero = block.split("            else\n", 1)
    assert "pgdep(i,k).eq.0." in zero
    assert "pgdep(i,k)+biacr(i,k)" in zero
    assert pair.COLD_BRS_ANCHOR not in zero
    assert all(name in zero for name in pair.BRS_RATES)
    assert "rhox" not in zero
    assert "qrs(i,k,3).eq.0." not in block
    assert pair.COLD_BRS_ANCHOR in nonzero
    checks = [nonzero.index(item) for item in (
        "capture_last_site.ne.5", ".not.capture_rhox_assigned(i,k)",
        ".not.ieee_is_finite(rhox(i,k))", "rhox(i,k).le.0.",
        "pgdep(i,k)/rhox(i,k)",
    )]
    assert checks == sorted(checks)
    assert "KDM6_PROGB_POLICY_MIDPOINT" not in guarded
    assert guard.BRS_MIN_ANCHOR in guarded

    unassigned = nonzero.split("else if (.not.capture_rhox_assigned(i,k)) then", 1)[1]
    zf = unassigned[:unassigned.index("call wrf_error_fatal('S10 nonzero pgdep has unassigned rhox')")]
    assert "'S10ZF'" in zf
    assert "capture_enabled" not in zf and "lat.eq.2" not in zf and "i.eq.142" not in zf
    assert "capture_step,lat,capture_last_site" in zf
    assert "capture_last_substep,i,k,2,0" in zf
    assert "transfer(qcrmin,0_s10_pgdep_word_kind)" in zf
    assert "transfer(1.e-15,0_s10_pgdep_word_kind)" in zf
    assert zf.index("transfer(1.e-15,0_s10_pgdep_word_kind)") < zf.index("flush(6)")
    assert unassigned.index("flush(6)") < unassigned.index(
        "call wrf_error_fatal('S10 nonzero pgdep has unassigned rhox')"
    )
    assert "ifsat" not in zf
    assert "rhox" not in zf

    log = guarded[guarded.index("'S10ZG'") - 300:guarded.index("'S10ZG'") + 500]
    assert "s10_pgdep_action" in log
    assert "transfer(pgdep(i,k),0_s10_pgdep_word_kind)" in log
    assert "s10_pgdep_density_valid" in log
    assert "'S10ZG'" in log and "rhox," not in log


def test_builder_reuses_pair_overlay_and_combined_strip_restores_source(tmp_path, monkeypatch):
    source = tmp_path / "module_mp_kdm6_cons.F"
    base = pair_overlay_fixture()
    source.write_text(base)
    seen = {}

    def fake_pair_build(given_source, output, manifest):
        seen["source"] = given_source
        output.write_text(base)
        manifest.write_text("{}\n")
        return {
            "canonical_source_sha256": "canonical-pin",
            "pair_overlay_sha256": "pair-pin",
        }

    monkeypatch.setattr(guard.pair, "build", fake_pair_build)
    output = tmp_path / "guarded.F"
    manifest = tmp_path / "guarded.json"
    record = guard.build(source, output, manifest)
    generated = output.read_text()
    pair_base = pair.strip_pair(guard.strip_guard(generated))
    assert seen["source"] == source
    assert pair_base == base
    assert validity.strip_capture(pair_base) == source.read_text()
    assert record["canonical_source_sha256"] == "canonical-pin"
    assert record["midpoint_fallback"] is False
    assert record["macro_off_matches_s10pair_overlay"] is True
    assert record["other_rhox_consumers_changed"] is False
    assert record["native_build_or_run"] is False
    assert manifest.exists()
    with pytest.raises(ValueError, match="paths must be distinct"):
        guard.build(source, output, source)
