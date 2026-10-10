"""Contract checks for the bounded PR401 saved-K response helper."""
from __future__ import annotations

import pytest
import numpy as np

from k_response_audit import (
    CHANNEL_IDS,
    CHANNEL_NAMES,
    build_log_pressure_interpolation_matrix,
    contract_held_endpoint_k,
    contract_reference_k,
    validate_run_contract,
)


def test_log_pressure_matrix_reproduces_interpolation_and_six_endpoint_holds():
    source_p = np.geomspace(0.5, 1000.0, 69)
    active_p = np.r_[np.geomspace(0.1, 800.0, 58), [902.57162, 926.73796],
                     np.geomspace(1100.0, 1600.0, 6)]
    matrix = build_log_pressure_interpolation_matrix(source_p, active_p)
    beta = np.linspace(2.0, 6.0, source_p.size)

    assert matrix.shape == (66, 69)
    assert np.all(matrix >= 0.0)
    np.testing.assert_allclose(matrix.sum(axis=1), 1.0, rtol=0.0, atol=1e-15)
    np.testing.assert_allclose(
        matrix @ beta,
        np.interp(np.log(active_p), np.log(source_p), beta),
        rtol=0.0,
        atol=2e-15,
    )
    held = np.flatnonzero(active_p > source_p[-1])
    assert held.size == 6
    np.testing.assert_array_equal(matrix[held, -1], np.ones(6))
    np.testing.assert_array_equal(matrix[held, :-1], np.zeros((6, 68)))
    partial = np.flatnonzero((matrix[:, -1] > 0.0) & (matrix[:, -1] < 1.0))
    assert partial.size == 2


def test_reference_k_contraction_and_correlated_endpoint_sum():
    source_p = np.geomspace(0.5, 1000.0, 69)
    active_p = np.r_[np.geomspace(0.1, 800.0, 58), [902.57162, 926.73796],
                     np.geomspace(1100.0, 1600.0, 6)]
    matrix = build_log_pressure_interpolation_matrix(source_p, active_p)
    k_active = np.arange(7 * 66, dtype=np.float64).reshape(7, 66) - 220.0
    beta = np.linspace(0.1, 6.9, 69) * 0.01
    held = np.flatnonzero(active_p > source_p[-1])

    active_delta, direct, source_contracted = contract_reference_k(
        k_active, matrix, beta
    )
    aggregate, held_contribution = contract_held_endpoint_k(
        k_active, matrix, beta, held, 68
    )

    np.testing.assert_allclose(direct, source_contracted, rtol=0.0, atol=2e-12)
    np.testing.assert_allclose(aggregate, k_active[:, held].sum(axis=1), rtol=0.0, atol=0.0)
    np.testing.assert_allclose(
        held_contribution,
        (k_active[:, held] @ matrix[held, :])[:, -1] * beta[-1],
        rtol=0.0,
        atol=2e-12,
    )
    partial = np.flatnonzero((matrix[:, -1] > 0.0) & (matrix[:, -1] < 1.0))
    partial_contribution = np.sum(
        k_active[:, partial] * matrix[partial, -1][None, :], axis=1
    ) * beta[-1]
    np.testing.assert_allclose(
        held_contribution + partial_contribution,
        (k_active @ matrix)[:, -1] * beta[-1],
        rtol=0.0,
        atol=2e-12,
    )
    assert np.all(active_delta[held] == beta[-1])


def test_contract_rejects_misaligned_source_dimensions():
    with pytest.raises(ValueError, match="dimensions do not align"):
        contract_reference_k(np.ones((7, 65)), np.ones((66, 69)), np.ones(69))


def test_run_contract_accepts_saved_channels_adk_and_gas_units_two():
    settings = {
        "defn%opts%config%adk_bt": ".TRUE.",
        "defn%opts%rt_all%use_q2m": ".TRUE.",
        "defn%run_gas_units": "2",
        "defn%do_direct": ".TRUE.",
        "defn%do_k": ".TRUE.",
    }
    assert validate_run_contract(
        list(CHANNEL_IDS), CHANNEL_NAMES, "&units\n gas_units = 2\n/", settings
    ) == 2


@pytest.mark.parametrize(
    "channels,names,gas_text,settings,match",
    [
        (list(reversed(CHANNEL_IDS)), CHANNEL_NAMES, "gas_units = 2", {
            "defn%opts%config%adk_bt": ".TRUE.", "defn%run_gas_units": "2",
            "defn%opts%rt_all%use_q2m": ".TRUE.",
            "defn%do_direct": ".TRUE.", "defn%do_k": ".TRUE.",
        }, "channels.txt"),
        (list(CHANNEL_IDS), CHANNEL_NAMES, "gas_units = 1", {
            "defn%opts%config%adk_bt": ".TRUE.", "defn%run_gas_units": "2",
            "defn%opts%rt_all%use_q2m": ".TRUE.",
            "defn%do_direct": ".TRUE.", "defn%do_k": ".TRUE.",
        }, "gas_units.txt"),
        (list(CHANNEL_IDS), CHANNEL_NAMES, "gas_units = 2", {
            "defn%opts%config%adk_bt": ".FALSE.", "defn%run_gas_units": "2",
            "defn%opts%rt_all%use_q2m": ".TRUE.",
            "defn%do_direct": ".TRUE.", "defn%do_k": ".TRUE.",
        }, "adk_bt"),
        (list(CHANNEL_IDS), CHANNEL_NAMES, "gas_units = 2", {
            "defn%opts%config%adk_bt": ".TRUE.", "defn%run_gas_units": "2",
            "defn%opts%rt_all%use_q2m": ".FALSE.",
            "defn%do_direct": ".TRUE.", "defn%do_k": ".TRUE.",
        }, "use_q2m"),
    ],
)
def test_run_contract_rejects_wrong_order_units_or_non_adk_bt(
    channels, names, gas_text, settings, match
):
    with pytest.raises(ValueError, match=match):
        validate_run_contract(channels, names, gas_text, settings)
