from __future__ import annotations

from pathlib import Path
import sys
import struct

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from s10_progb_zero_qg_guard import (  # noqa: E402
    f32,
    sum32,
    brs_volume_stage2,
    guarded_rate_over_density,
    heat_stage1,
    heat_stage2,
)


def test_only_exact_zero_qg_and_zero_rate_take_guard_bypass():
    action, contribution = guarded_rate_over_density(0.0, 0.0, 0.0)
    assert action == 0
    assert contribution == f32(0.0)

    # A nonzero process rate is never suppressed solely because qg is zero.
    action, contribution = guarded_rate_over_density(0.0, -2.0e-7, 400.0)
    assert action == 1
    assert contribution == f32(f32(-2.0e-7) / f32(400.0))

    # qg positive with a zero rate is not the exact-zero-qg bypass case.
    with pytest.raises(ZeroDivisionError, match="requires finite positive rhox"):
        guarded_rate_over_density(1.0e-9, 0.0, 0.0)
    with pytest.raises(ZeroDivisionError, match="requires finite positive rhox"):
        guarded_rate_over_density(0.0, 1.0e-12, 0.0)


def test_source_ordered_sum_keeps_signed_zero_entry():
    total = sum32((-0.0, -0.0, -0.0))
    assert total == 0.0
    assert struct.unpack(">I", struct.pack(">f", total))[0] == 0x80000000


def test_guard_bypass_keeps_non_density_volume_transfers_in_source_order():
    action, pgdep_volume = guarded_rate_over_density(0.0, 0.0, 0.0)
    assert action == 0 and pgdep_volume == 0.0
    before = f32(2.0e-6)
    others = [f32(1.0e-8), f32(-2.0e-9), f32(3.0e-9)]
    result = brs_volume_stage2(before, pgdep_volume=pgdep_volume,
                               other_rates=others, dtcld=20.0)
    unchanged = brs_volume_stage2(before, pgdep_volume=0.0,
                                  other_rates=others, dtcld=20.0)
    assert result == unchanged
    assert result != before


def test_nonzero_density_transfer_is_applied_with_f32_volume_update():
    action, quotient = guarded_rate_over_density(0.0, 8.0e-7, 400.0)
    assert action == 1
    result = brs_volume_stage2(1.0e-8, pgdep_volume=quotient,
                               other_rates=[2.0e-9, -1.0e-9], dtcld=20.0)
    source = f32(f32(f32(quotient) + f32(2.0e-9)) + f32(-1.0e-9))
    expected = f32(f32(f32(1.0e-8) + f32(source * f32(20.0))))
    assert result == max(expected, f32(0.0))


def test_latent_and_heat_updates_are_not_gated_by_zero_qg():
    # C changes only the zero quotient. A nonzero qg melt rate still reaches
    # the original heat operation; exact zero rate contributes exactly zero.
    zero_heat = heat_stage1(260.0, xlf=3.34e5, cpm=1004.0, pgmlt=0.0)
    nonzero_heat = heat_stage1(260.0, xlf=3.34e5, cpm=1004.0, pgmlt=-1.0e-7)
    assert zero_heat == f32(260.0)
    assert nonzero_heat != zero_heat

    unchanged_heat = heat_stage2(260.0, xlwork2=0.0, cpm=1004.0, dtcld=20.0)
    assert unchanged_heat == f32(260.0)
    applied_heat = heat_stage2(260.0, xlwork2=1.5e-2, cpm=1004.0, dtcld=20.0)
    assert applied_heat != unchanged_heat
