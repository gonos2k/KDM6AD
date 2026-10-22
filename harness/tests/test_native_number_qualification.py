"""Fixed-baseline number-coordinate receipt validation tests."""
from __future__ import annotations

import copy
import hashlib
import json

import numpy as np
import pytest

from harness.native_number_qualification import (
    ADMISSION_SCHEMA,
    FIELD_UNITS,
    NUMBER_ROWS,
    ORIGIN,
    SCHEMA,
    apply_receipt,
    make_kernel_coordinate_receipt,
)


def inputs():
    levels = 3
    state = np.array([
        [300., 290., 280.],  # TH remains state row 0; it is never interpreted as density
        [.002, .003, .004], [1e-4, 2e-4, 3e-4], [2e-5, 3e-5, 4e-5],
        [5e-5, 6e-5, 7e-5], [8e-5, 9e-5, 1e-4], [1e-5, 2e-5, 3e-5],
        [80., 100., 120.], [200., 250., 300.], [30., 40., 50.], [400., 500., 600.],
        [1e-8, 2e-8, 3e-8],  # BG/QIB stays in its own volume-per-mass basis
    ], dtype=np.float64)
    forcing = np.array([
        [1.3, 1.1, 0.9],  # native dry DEN is forcing row 0 and differs clearly from TH
        [90000., 80000., 70000.], [0.98, 0.94, 0.90], [100., 200., 300.]
    ], dtype=np.float64)
    bindings = {
        "trace": "a" * 64,
        "namelist": "b" * 64,
        "checkpoint": "c" * 64,
        "step": 2,
        "i": 156,
        "j": 21,
        "levels": levels,
        "base_native_X_sha256": "d" * 64,
    }
    return state, forcing, bindings


def make(state=None, forcing=None, bindings=None):
    v, f, b = inputs()
    return make_kernel_coordinate_receipt(
        v if state is None else state,
        f if forcing is None else forcing,
        source_id="saved-kernel-volume-coordinate-case",
        source_sha256=(b if bindings is None else bindings)["trace"],
        source_bindings=b if bindings is None else bindings,
    )


def redigest(receipt):
    body = dict(receipt)
    body.pop("receipt_content_sha256", None)
    receipt["receipt_content_sha256"] = hashlib.sha256(json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")).hexdigest()


def test_receipt_converts_only_four_number_rows_and_admits_explicit_basis():
    state, forcing, bindings = inputs()
    receipt = make(state, forcing, bindings)
    dry, admission = apply_receipt(receipt, state, forcing, bindings, "f" * 64)

    expected = state.copy()
    expected[list(NUMBER_ROWS)] /= forcing[0][None, :]
    np.testing.assert_array_equal(dry, expected)
    np.testing.assert_array_equal(dry[:7], state[:7])
    np.testing.assert_array_equal(dry[11], state[11])
    np.testing.assert_array_equal(forcing, inputs()[1])
    assert receipt["schema"] == SCHEMA
    assert receipt["origin"] == ORIGIN == "derived_kernel_volume_coordinate"
    assert receipt["source_basis"] == "kernel_volume_operand"
    assert receipt["original_host_payload_basis"] == "unknown_not_migrated"
    assert receipt["original_host_basis_certified"] is False
    assert receipt["rho_source"]["forcing_row"] == 0
    assert receipt["rho_source"]["field"] == "DEN"
    assert all(item["max_ulp"] <= 2 for item in receipt["roundtrip_volume_coordinate"].values())
    assert admission.schema == ADMISSION_SCHEMA
    assert admission.origin == ORIGIN
    assert dict(admission.field_units) == FIELD_UNITS
    assert admission.receipt_sha256 == "f" * 64


@pytest.mark.parametrize("edit", ["state", "forcing", "bindings"])
def test_receipt_refuses_different_baseline_or_source_bindings(edit):
    state, forcing, bindings = inputs()
    receipt = make(state, forcing, bindings)
    if edit == "state":
        state[7, 0] = np.nextafter(state[7, 0], np.inf)
    elif edit == "forcing":
        forcing[0, 1] += 1e-12
    else:
        bindings = dict(bindings, step=1)
    with pytest.raises(ValueError, match="differ|match|bindings"):
        apply_receipt(receipt, state, forcing, bindings, "f" * 64)


def test_receipt_refuses_tampering_schema_digest_and_uncertified_claim_changes():
    state, forcing, bindings = inputs()
    receipt = make(state, forcing, bindings)
    for key, value, pattern in (
        ("source_sha256", "not-a-sha", "source_sha256"),
        ("receipt_content_sha256", "0" * 64, "content digest"),
        ("original_host_basis_certified", True, "must not claim"),
        ("origin", "registry_only", "schema or origin"),
    ):
        changed = copy.deepcopy(receipt)
        changed[key] = value
        with pytest.raises(ValueError, match=pattern):
            apply_receipt(changed, state, forcing, bindings, "f" * 64)
    with pytest.raises(ValueError, match="receipt_sha256"):
        apply_receipt(receipt, state, forcing, bindings, "registry-label-only")


@pytest.mark.parametrize("path,value", [
    (("field_map", "NN", "kernel_units"), "number_per_kg_dry_air"),
    (("field_map", "NC", "state_row"), 7),
    (("conversion",), "N_dry = N_volume / rho"),
    (("rho_source", "field"), "TH"),
    (("roundtrip_limit_ulp",), 99),
    (("roundtrip_volume_coordinate", "NN", "max_ulp"), 9),
])
def test_apply_checks_unit_contract_even_when_receipt_digest_is_recomputed(path, value):
    state, forcing, bindings = inputs()
    receipt = make(state, forcing, bindings)
    target = receipt
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    redigest(receipt)
    with pytest.raises(ValueError, match="field map|density source|conversion|ULP|roundtrip"):
        apply_receipt(receipt, state, forcing, bindings, "f" * 64)


@pytest.mark.parametrize("bad", ["wrong_dtype", "wrong_state_shape", "wrong_forcing_shape", "nonfinite", "negative_number", "nonpositive_density"])
def test_creation_rejects_malformed_or_nonphysical_arrays(bad):
    state, forcing, bindings = inputs()
    if bad == "wrong_dtype":
        state = state.astype(np.float32)
    elif bad == "wrong_state_shape":
        state = state[:-1]
    elif bad == "wrong_forcing_shape":
        forcing = forcing[:-1]
    elif bad == "nonfinite":
        forcing[2, 0] = np.nan
    elif bad == "negative_number":
        state[9, 1] = -1.
    else:
        forcing[0, 2] = 0.
    with pytest.raises((TypeError, ValueError)):
        make(state, forcing, bindings)


def test_creation_requires_complete_pinned_source_identity_and_matching_levels():
    state, forcing, bindings = inputs()
    for changed in ({k: v for k, v in bindings.items() if k != "checkpoint"},
                    dict(bindings, trace="unhashed"), dict(bindings, levels=4),
                    dict(bindings, step=0)):
        with pytest.raises(ValueError):
            make(state, forcing, changed)
    with pytest.raises(ValueError, match="pinned trace"):
        make_kernel_coordinate_receipt(
            state, forcing, source_id="case", source_sha256="9" * 64,
            source_bindings=bindings,
        )
