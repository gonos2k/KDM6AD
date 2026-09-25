"""Paired energy, material law and passive direction are independent gates."""

from dataclasses import replace
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from material_interface_contract import (  # noqa: E402
    IntegratedHeatFace, SeriesMaterial, ThermalCells, advance_declared_heat,
    check_heat_face_budget, check_passive_entropy, check_series_face_law,
    series_resistance_flux,
)


def _case():
    return (ThermalCells(310., 300., 10000., 10000.),
            SeriesMaterial(1., 100., .5, .5))


def test_series_resistance_flux_and_paired_heat_both_pass():
    before, material = _case()
    flux = series_resistance_flux(before, material)
    assert flux == pytest.approx(19.801980198019802)
    event = IntegratedHeatFace(flux, 1.)
    after = advance_declared_heat(before, event)
    assert abs(check_heat_face_budget(before, after, event).total_residual_j_m2) < 1e-8
    assert check_series_face_law(before, material, event) == pytest.approx(flux)
    assert check_passive_entropy(before, after, event) > 0


def test_arithmetic_mean_conserves_but_violates_material_interface_law():
    before, material = _case()
    arithmetic_flux = ((material.left_conductivity_w_m_k
                        + material.right_conductivity_w_m_k) / 2
                       * (before.left_temperature_k - before.right_temperature_k)
                       / (material.left_center_to_face_m
                          + material.right_center_to_face_m))
    correct = series_resistance_flux(before, material)
    assert arithmetic_flux / correct == pytest.approx(25.5025)
    event = IntegratedHeatFace(arithmetic_flux, 1.)
    after = advance_declared_heat(before, event)
    check_heat_face_budget(before, after, event)
    assert check_passive_entropy(before, after, event) > 0
    with pytest.raises(ValueError, match="series-resistance law"):
        check_series_face_law(before, material, event)


def test_reversed_heat_can_conserve_energy_while_entropy_decreases():
    before, material = _case()
    event = IntegratedHeatFace(-10., 1.)
    after = advance_declared_heat(before, event)
    check_heat_face_budget(before, after, event)
    with pytest.raises(ValueError, match="entropy"):
        check_passive_entropy(before, after, event)
    with pytest.raises(ValueError, match="reverses"):
        check_series_face_law(before, material, event)


def test_equal_temperature_has_zero_flux_and_no_spurious_entropy():
    _, material = _case()
    before = ThermalCells(300., 300., 10000., 10000.)
    event = IntegratedHeatFace(0., 1.)
    after = advance_declared_heat(before, event)
    assert after == before
    assert series_resistance_flux(before, material) == 0.
    assert check_series_face_law(before, material, event) == 0.
    assert check_passive_entropy(before, after, event) == 0.
    with pytest.raises(ValueError, match="equilibrium"):
        check_series_face_law(before, material, IntegratedHeatFace(1e-10, 1.))


def test_tiny_opposite_flux_cannot_hide_inside_absolute_tolerance():
    _, material = _case()
    before = ThermalCells(300. + 1e-9, 300., 10000., 10000.)
    expected = series_resistance_flux(before, material)
    assert 0 < expected < 1e-8
    with pytest.raises(ValueError, match="reverses"):
        check_series_face_law(before, material, IntegratedHeatFace(-expected, 1.))
    with pytest.raises(ValueError, match="series-resistance law"):
        check_series_face_law(before, material, IntegratedHeatFace(expected * .01, 1.))
    with pytest.raises(ValueError, match="series-resistance law"):
        check_series_face_law(before, material, IntegratedHeatFace(0., 1.))


def test_invalid_material_state_and_unpaired_face_are_rejected():
    before, material = _case()
    event = IntegratedHeatFace(10., 1.)
    after = advance_declared_heat(before, event)
    with pytest.raises(ValueError, match="energy changes"):
        check_heat_face_budget(before, replace(after, left_temperature_k=309.), event)
    with pytest.raises(ValueError, match="changing heat capacity"):
        check_heat_face_budget(before, replace(after, left_heat_capacity_j_m2_k=9000.), event)
    with pytest.raises(ValueError, match="must be positive"):
        series_resistance_flux(before, replace(material, left_conductivity_w_m_k=0.))
    with pytest.raises(ValueError, match="positive"):
        advance_declared_heat(replace(before, left_temperature_k=-1.), event)
    with pytest.raises(ValueError, match="finite real"):
        check_series_face_law(before, material, IntegratedHeatFace(math.nan, 1.))
