"""Exact AD-product comparison must retain signed zeros and reject bad products."""
import numpy as np
import pytest
import json
from pathlib import Path

from harness.verify_ice_trace_ad_noninterference import PRODUCTS, compare_products, sha


def values():
    return {key: np.arange(6., dtype=np.float64).reshape(2, 3) for key in PRODUCTS}


def test_exact_comparison_covers_every_product():
    result = compare_products(values(), values())
    assert all(p["raw_bit_equal"] and p["finite"] and p["count"] == 6 for p in result.values())


@pytest.mark.parametrize("change", ["ulp", "signed_zero", "nan", "shape", "dtype"])
def test_noninterference_comparison_refuses_any_changed_product(change):
    reference, altered = values(), values()
    if change == "ulp":
        altered["jvp"][0, 1] = np.nextafter(1., 2.)
    elif change == "signed_zero":
        altered["jvp"][0, 0] = -0.
    elif change == "nan":
        altered["jvp"][0, 1] = np.nan
    elif change == "shape":
        altered["jvp"] = altered["jvp"].reshape(3, 2)
    else:
        altered["jvp"] = altered["jvp"].astype(np.float32)
    result = compare_products(reference, altered)
    assert not result["jvp"]["raw_bit_equal"]
    assert all(result[key]["raw_bit_equal"] for key in PRODUCTS if key != "jvp")


def test_public_native_product_arrays_match_exactly_without_private_libraries():
    directory = Path(__file__).parents[1]/"evidence/ice_boundary_attribution_2026-10-23"
    saved = json.loads((directory/"native39_ad_noninterference.json").read_text())
    data = {}
    for mode, metadata in saved["products"].items():
        path = directory/"ad_products"/(mode+".npz")
        assert sha(path) == metadata["products_sha256"]
        with np.load(path, allow_pickle=False) as npz:
            data[mode] = {key: npz[key].copy() for key in npz.files}
    for mode in ("instrumented_off", "instrumented_on"):
        assert compare_products(data["control"], data[mode]) == saved["comparisons"][mode]
        for seed in ("state_direction", "forcing_direction", "cotangent", "finish_cotangent"):
            assert data[mode][seed].tobytes() == data["control"][seed].tobytes()
    source = json.loads((directory.parent/"same_call_water_budget_2026-10-22/native39_same_call.json").read_text())
    expected = np.asarray(source["same_call"]["state_out"], dtype=np.float64)
    assert data["control"]["state"].tobytes() == expected.tobytes()
    prior = json.loads((directory.parent/"native_number_boundary_2026-10-22/native39_dry_boundary_cost.json").read_text())
    fields = ("T_NEW_AFTER", "H_RATE", "QV_RATE", "QC_RATE", "TH_PHY_M_T0")
    expected_finish = np.asarray([prior["applied_finish"][k] for k in fields], dtype=np.float64)
    assert data["control"]["applied_finish"].tobytes() == expected_finish.tobytes()
