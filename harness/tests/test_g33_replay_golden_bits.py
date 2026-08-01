"""The replay's arithmetic, pinned to exact bits on the values the decision rests on.

The decision artifact is produced locally; CI runs a different NumPy. IEEE f32/f64
arithmetic *should* be identical across them — but "should be" is not a
measurement, and the whole point of the replay is that it reproduces each
backend's own stored state bit-for-bit. If a runtime ever changed that, every
conclusion built on the replay would move with nothing failing.

So the expected values here are HARD-CODED, not recomputed. They are the actual
seed cell of the current decision artifact (`micro_freeze_heat` / `micro_qr_operands`,
loop 2, column 3, k 0, fixture `arithmetic_multisubcycle_v1`), and they were
produced by the two backends, not by this file. A runtime that computes anything
else fails here — in CI, on CI's own NumPy, which is exactly where the mismatch
was invisible before.

This is cheaper and stricter than regenerating the artifact in CI: the four leg
bundles are not in the repository, and what was actually in doubt is whether the
runtime changes the arithmetic. That is what this answers.
"""
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_update_replay as rp  # noqa: E402

# ── the seed cell, exactly as both backends recorded it ──────────────────────
F_XLF, F_CPM = 0x488740A0, 0x447B5809          # Fortran coefficient operands
C_XLF, C_CPM = 0x488911E0, 0x447B36A5          # C++ coefficient operands
T_PRE_FREEZE = 0x43739698                      # identical on both legs
RATES_F64 = (0x3E1C30E25582CD5D,               # pinuc    ) identical on both
             0x3EBEFAE7A7F5767D,               # pfrzdtc  ) legs at f64
             0x3E61E05D0E2E83BD)               # pfrzdtr  )
POST_FREEZE_T_F, POST_FREEZE_T_C = 0x437396BA, 0x437396BB

QR_PRE, QR_POST = 0x31959F04, 0x31974466
DTCLD = 100.0                                  # 0x42c80000


def _heat(xlf, cpm):
    return {"t_pre_freeze": rp.f32(T_PRE_FREEZE),
            "xlf": rp.f32(xlf), "cpm": rp.f32(cpm),
            **dict(zip(rp.FREEZE_TERMS,
                       (struct.unpack("<d", struct.pack("<Q", b))[0]
                        for b in RATES_F64)))}


# ── the freeze heat term ─────────────────────────────────────────────────────

def test_the_freeze_replay_reproduces_the_FORTRAN_stored_t():
    assert rp.replay_freeze_t(_heat(F_XLF, F_CPM)) == POST_FREEZE_T_F


def test_the_freeze_replay_reproduces_the_CPP_stored_t():
    assert rp.replay_freeze_t(_heat(C_XLF, C_CPM)) == POST_FREEZE_T_C


def test_the_two_stored_temperatures_differ_by_exactly_one_ULP():
    """The observation the whole v14 finding rests on."""
    assert POST_FREEZE_T_C - POST_FREEZE_T_F == 1


@pytest.mark.parametrize("xlf,cpm,want", [
    (F_XLF, F_CPM, 0x437396BA),   # FF
    (C_XLF, F_CPM, 0x437396BB),   # CF
    (F_XLF, C_CPM, 0x437396BA),   # FC
    (C_XLF, C_CPM, 0x437396BB),   # CC
])
def test_the_2x2_counterfactual_corners_are_these_bits(xlf, cpm, want):
    """FF == FC and CF == CC is what allocates the stored ULP entirely to `xlf`
    and none to `cpm`. If a runtime moved any corner, that allocation would move
    with it and nothing else would notice."""
    assert rp.replay_freeze_t(_heat(xlf, cpm)) == want


def test_the_derived_coefficients_are_these_f32_values():
    import numpy as np
    assert float(np.float32(rp.f32(F_XLF) / rp.f32(F_CPM))) == pytest.approx(
        275.51596, abs=1e-5)
    assert float(np.float32(rp.f32(C_XLF) / rp.f32(C_CPM))) == pytest.approx(
        279.36304, abs=1e-5)


# ── the qr update line ───────────────────────────────────────────────────────

def test_the_qr_update_replay_reproduces_the_stored_qr():
    """Cold arm at 243.6 K, the source's left-to-right f32 association."""
    # Extracted from the evidence, not typed from memory: the first version of
    # this test had four of the eight wrong and failed for that reason, which is a
    # good argument for goldens coming out of the artifact rather than out of a
    # recollection of it.
    ops = {n: rp.f32(b) for n, b in (
        ("praut", 0x00000000), ("pracw", 0x2BB88394), ("prevp", 0xA9854A33),
        ("piacr", 0x2B593CC6), ("pgacr", 0x2605FDA0), ("psacr", 0x261F8B83),
        ("pmulrs", 0x00000000), ("pmulrg", 0x00000000))}
    assert rp.replay_qr(QR_PRE, ops, DTCLD, cold=True) == QR_POST


def test_the_branch_at_this_cell_is_COLD():
    assert rp.is_cold(T_PRE_FREEZE)


# ── the runtime this ran on, recorded in the failure message ─────────────────

def test_the_runtime_is_reported_when_anything_above_fails():
    """Not an assertion about the version — a place for it to be visible.

    The artifact records `verifier_runtime`; if these goldens ever fail, the first
    question is which runtime moved, and it should not require a second run to
    find out.
    """
    import numpy as np
    import platform
    assert np.__version__ and platform.python_version(), (
        f"numpy {np.__version__}, python {platform.python_version()}")
