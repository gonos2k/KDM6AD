"""What the 9-15% is a percentage OF (owner §11).

R/F_surface is the right denominator for "is the transport accounting closed" and
the wrong one for nearly every sentence a reader writes next. These pin the
distinction so a future edit cannot quietly collapse it back to one number.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import g33_defect_magnitude as dm  # noqa: E402
from test_g33_dual_ledger import _stream  # noqa: E402

QV = [0.001] * 4


#: nonzero qr so a mean particle mass q/N exists at all.
QR = 1.0e-3


def _row():
    return dm.analysis(_stream(QV, QR))["rows"]["main/nr/1"]


def test_every_denominator_is_reported_not_just_the_surface_flux():
    """One denominator invites the reader to supply their own."""
    r = _row()
    assert {"of_surface_flux", "of_initial_inventory", "of_summed_call_starts",
            "of_interface_throughput"} <= set(r)


def test_the_column_fraction_is_far_smaller_than_the_flux_fraction():
    """The whole point: the same residual is a large fraction of what LEFT and a
    small fraction of what is THERE. Quoting the first as the second is the
    misreading this module exists to prevent."""
    r = _row()
    assert abs(r["of_initial_inventory"]) < abs(r["of_surface_flux"])


def test_the_defect_size_effect_is_separated_from_real_size_sorting():
    """Sedimentation genuinely size-sorts -- large particles fall faster -- so the
    TOTAL change in q/N is mostly physics. Attributing it to the defect would be
    exactly the overreach §11 warns about."""
    r = _row()
    assert "mean_particle_mass_change_total" in r
    assert "defect_mean_mass_bias_frozen" in r
    assert abs(r["defect_mean_mass_bias_frozen"]) < abs(r["mean_particle_mass_change_total"])


def test_a_diameter_bias_is_a_CUBE_ROOT_of_the_number_bias():
    """This is why a 15%-sounding number is not a 3-5% diameter change: a
    characteristic diameter goes as (q/N)^(1/3)."""
    r = _row()
    eps = r["spurious_fraction_of_segment_endpoint"]
    assert r["defect_diameter_bias_frozen"] == pytest.approx(
        (1 + eps) ** (-1 / 3) - 1, rel=1e-9)
    assert abs(r["defect_diameter_bias_frozen"]) < abs(r["defect_mean_mass_bias_frozen"])


def test_the_artifact_says_what_the_number_is_NOT():
    """A caveat in prose gets separated from the table the moment it is copied."""
    note = dm.analysis(_stream(QV, QR))["note"]
    for word in ("column", "diameter", "reflectivity", "precipitation"):
        assert word in note


def test_an_unusable_row_carries_no_magnitudes_at_all():
    """A row whose mass control failed must not offer a tidy set of percentages
    to copy."""
    rows = dm.analysis(_stream(QV, QR))["rows"]
    for r in rows.values():
        if not r["usable"]:
            assert "of_surface_flux" not in r
