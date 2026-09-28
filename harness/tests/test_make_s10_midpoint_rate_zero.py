from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import make_s10_midpoint_rate_zero as hybrid  # noqa: E402


def test_four_rate_guards_restore_midpoint_source_when_disabled():
    base = hybrid.USE_ANCHOR + hybrid.DECL_ANCHOR + "".join(
        site[2] for site in hybrid.SITES
    )
    generated = hybrid.inject_hybrid(base)
    assert hybrid.strip_hybrid(generated) == base
    assert generated.count("S10_HYBRID_BEGIN:") == 6
    assert generated.count("S10HYFAIL") == 8
    assert "qrs(i,k,3).eq.0." not in generated
    for consumer_id, rate, original, zero in hybrid.SITES:
        start = generated.index(f"! S10_HYBRID_BEGIN:{consumer_id}")
        end = generated.index(f"! S10_HYBRID_END:{consumer_id}", start)
        block = generated[start:end]
        zero_arm, nonzero_arm = block.split("            else\n", 1)
        assert zero_arm.index(f"ieee_is_finite({rate})") < zero_arm.index(f"if ({rate}.eq.0.)")
        assert f"if ({rate}.eq.0.)" in zero_arm
        assert zero in zero_arm
        assert "rhox(i,k)" not in zero_arm
        assert original in nonzero_arm
        checks = [nonzero_arm.index(value) for value in (
            "capture_rhox_assigned(i,k)",
            "ieee_is_finite(rhox(i,k))",
            "rhox(i,k).gt.0.",
            "if (.not.s10_hybrid_density_valid)",
            original,
        )]
        assert checks == sorted(checks)
        assert f"transfer({rate},0_s10_hybrid_word_kind)" in nonzero_arm
