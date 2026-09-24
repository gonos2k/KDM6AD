import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from native_input_selection import CATEGORIES, select_columns  # noqa:E402


def test_predeclared_classes_keep_native_layers_and_unique_cells():
    qc, qr, qi, qs, qg = [np.zeros((2, 5, 7)) for _ in range(5)]
    temp = np.full_like(qc, 280.0)
    qc[0, 2, 2] = 2e-5
    qc[1, 2, 3] = 2e-5
    temp[1, 2, 3] = 260.0
    qi[1, 2, 3] = 2e-6
    qi[1, 2, 4] = 2e-5
    temp[1, 2, 4] = 240.0
    qr[0, 2, 5] = 2e-5
    out = select_columns(qc, qr, qi, qs, qg, temp, margin=1, excluded=())
    assert tuple(x["category"] for x in out) == CATEGORIES
    expected = {
        "warm_liquid": (3, 3),
        "mixed_column": (3, 4),
        "ice": (3, 5),
        "rain": (3, 6),
    }
    for x in out:
        if x["category"] in expected:
            assert (x["selected"]["j"], x["selected"]["i"]) == expected[x["category"]]
    assert len({tuple(x["selected"].values()) for x in out}) == 5
    assert out == select_columns(qc, qr, qi, qs, qg, temp, margin=1, excluded=())


def test_missing_category_is_not_replaced_with_a_passing_case():
    zero = np.zeros((1, 5, 5))
    t = np.full_like(zero, 280.0)
    out = select_columns(zero, zero, zero, zero, zero, t, margin=1, excluded=((3, 3),))
    assert out[0]["selected"] != {"j": 3, "i": 3}
    assert all(x["selected"] is None and x["candidate_count"] == 0 for x in out[1:])


def test_invalid_model_array_rejected():
    zero = np.zeros((1, 5, 5))
    bad = zero.copy()
    bad[0, 2, 2] = np.nan
    with pytest.raises(ValueError):
        select_columns(bad, zero, zero, zero, zero, zero)


def test_masked_cell_cannot_be_selected_as_clear_from_its_hidden_storage():
    zero = np.zeros((1, 5, 5))
    unknown = np.ma.array(zero, mask=False)
    unknown.mask[0, 2, 2] = True
    with pytest.raises(ValueError, match="masked native input"):
        select_columns(
            unknown,
            zero,
            zero,
            zero,
            zero,
            np.full_like(zero, 280.0),
            margin=1,
            excluded=(),
        )
