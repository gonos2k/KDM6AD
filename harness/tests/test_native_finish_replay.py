from fractions import Fraction

import numpy as np
import pytest

from harness.native_finish_replay import _round_f32, fma_f32_exact, replay_arm64_theta_m_finish


def _bits(value):
    return int(np.asarray([value], dtype=np.float32).view(np.uint32)[0])


def test_fma_preserves_cancellation_which_separate_operations_lose():
    a, b = np.float32(1 + 2**-23), np.float32(1 - 2**-23)
    assert np.float32(np.float32(a * b) - np.float32(1)) == 0
    assert _bits(fma_f32_exact(a, b, np.float32(-1))) == _bits(np.float32(-2**-46))


def test_exact_rounding_uses_even_ties_and_preserves_zero_sign():
    assert _bits(_round_f32(Fraction(1) + Fraction(1, 2**24))) == _bits(np.float32(1))
    assert _bits(_round_f32(Fraction(1) + Fraction(3, 2**24))) == _bits(np.float32(1 + 2**-22))
    assert _bits(_round_f32(Fraction(-1, 2**150))) == 0x80000000
    assert _bits(fma_f32_exact(np.float32(-0.0), 1, np.float32(-0.0))) == 0x80000000
    assert _bits(fma_f32_exact(1, 1, -1)) == 0


def test_identity_and_applied_limiter_have_independent_expected_heating():
    pre = dict(dt=20, H_PRE=300, QV_PRE=0, TH_PLUS=300, QV_PLUS=0,
               T0=300, ALPHA=1, MP_TEND_LIM=0.02)
    identity = replay_arm64_theta_m_finish(pre)
    assert _bits(identity["H_RATE"]) == 0
    assert identity["T_NEW_AFTER"] == 0
    limited = replay_arm64_theta_m_finish({**pre, "TH_PLUS": 301})
    assert limited["MP_RAW"] == 1
    assert _bits(limited["MP_CLIPPED"]) == _bits(np.float32(0.02) * np.float32(20))
    assert _bits(limited["H_RATE"]) == _bits(np.float32(0.02))
    stored_increment = np.float32(np.float32(300) + limited["MP_CLIPPED"]) - np.float32(300)
    assert _bits(limited["T_NEW_AFTER"]) == _bits(stored_increment)


def test_replay_refuses_invalid_value_boundary():
    with pytest.raises(ValueError, match="finite"):
        fma_f32_exact(np.nan, 1, 1)
