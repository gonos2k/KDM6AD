"""Small boundary witnesses for the review-208 transport fixes.

These tests keep the transport and experiment claims independently
discriminating: a numerically equal value with a different f32 word is still a
different input, and a metric-aware prediction must use the metric the call
declared.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import g33_factorial as fc  # noqa: E402
import g33_ncmin_locality as nl  # noqa: E402
import g33_number_transport as nt  # noqa: E402
import g33_qr_process_ledger as ql  # noqa: E402
import g33_real_column_batch as batch  # noqa: E402
import g33_refine_analyze as ra  # noqa: E402
import g33_refine_experiment as xp  # noqa: E402
from test_g33_number_transport import _call, _stream  # noqa: E402


def _window_from_stream(stream: str) -> dict:
    """Build the window duplicate from the parsed stream, by field and word."""
    run = {}
    for call in nt.calls(stream):
        for (loop, col, level), record in call["outer_pre_sed"].items():
            run[("forcing", "rho", col, level)] = record["rho"]
            run[("forcing", "delz", col, level)] = record["delz"]
            if call["split"] == 1 and loop == 1:
                for field in ("qv", "nr", "ni", "qr", "qi"):
                    run[("initial", field, col, level)] = record[field]
    return run


def test_review208_initial_transport_binding_refuses_signed_zero_change():
    """G33P INITIAL qv is part of the same run, even when values compare equal."""
    stream = _stream(_call(1, cols=(1,), ks=2))
    stream = stream.replace(
        "G33F STAGE 1 - outer_pre_sed 0 qv 1 0 f32 3F800000",
        "G33F STAGE 1 - outer_pre_sed 0 qv 1 0 f32 00000000", 1)
    run = _window_from_stream(stream)
    run[("initial", "qv", 1, 0)] = -0.0
    with pytest.raises(nt.StreamError, match="initial qv differs"):
        nt.require_window_forcing(list(nt.calls(stream)), run, 4)


def test_review208_metric_predicted_residual_uses_declared_weight():
    """For moist-layer mass, the predicted identity closes at the actual zero."""
    pre, post = {}, {}
    for level, rho, value, value_post in (
            (0, 1.0, 4.0, 3.0), (1, 2.0, 0.0, 1.0)):
        pre[(1, 1, level)] = {"rho": rho, "delz": 1.0, "qv": 0.0,
                              "nr": value}
        post[(1, 1, level)] = {"nr": value_post}
    call = {
        "loops": {1},
        "mstep": {(1, "main", 1): 1},
        "outer_pre_sed": pre,
        "outer_post_sed": post,
        "algorithm": "nmass",
        "declared_metric": "moist_layer_mass",
        "flux": {(1, 1): {"bottom_falln_nr": 0.0, "nflux_dtcld": 1.0}},
    }
    got = nt.column(call, 1, "nr")
    assert got["residual"] == pytest.approx(0.0)
    assert got["predicted_residual"] == pytest.approx(0.0)
    # The stale thickness-only expression would have returned this nonzero
    # density-contrast term for the same recovered transfer.
    assert ((2.0 - 1.0) * 1.0 * 1.0) == pytest.approx(1.0)


def test_review208_qr_weight_comparison_preserves_signed_zero():
    base = {
        ("forcing", "rho", 1, 0): 0.0,
        ("forcing", "delz", 1, 0): 1.0,
        ("initial", "qv", 1, 0): 1.0,
    }
    got = dict(base)
    got[("forcing", "rho", 1, 0)] = -0.0
    with pytest.raises(ra.RefineError, match="disagree on rho"):
        ql._require_same_weights(base, got)


def test_review208_qr_analysis_forwards_carry_profile_and_width(monkeypatch):
    seen = []

    # Keep the actual `gated_text` signature.  A fake that accepted the old
    # nonexistent `mode=` keyword let the analysis test pass while the real
    # runner raised before either QR leg executed.
    def gated(driver, fixture, tiles, nsplit=1, carry="rezero",
              rho="as-is", algo=None, contract=None):
        seen.append((tuple(tiles), nsplit, carry, rho, algo, contract))
        return f"stream-{len(seen)}"

    monkeypatch.setattr(nl, "gated_text", gated)
    monkeypatch.setattr(ql.ra, "read_text", lambda text: {})
    monkeypatch.setattr(ql, "decompose", lambda *args: {"columns": {}})
    contract = SimpleNamespace(columns=7, mode="carry", rho_profile="uniform")
    got = ql.analysis("driver", "fixture", algo="legacy", contract=contract)
    assert seen == [((1,) * 7, 1, "carry", "uniform", "legacy", contract),
                    ((7,), 1, "carry", "uniform", "legacy", contract)]
    assert got["ran"] == {
        "nsplit": 1, "carry": "carry", "rho": "uniform", "width": 7,
        "decompositions": [[1] * 7, [7]],
    }


def test_review208_qr_direct_boundary_rejects_unvalidated_streams():
    with pytest.raises(ra.RefineError, match="G33N"):
        ql.decompose("not a G33N stream", "not a G33N stream", 1, {})


def test_review208_qr_binds_g33r_algorithm_metadata_to_g33n():
    lines = ["G33R BEGIN nsplit 1 rezero conservative delt 100.000000 loops 1 "
             "dtcld 100.000000"]
    for field in ra.STATE_FIELDS:
        for level in (0, 1):
            lines.append(f"G33R STATE {field} 1 {level} 3F800000")
    for species in (1, 2, 3):
        lines.append(f"G33R PREC {species} 1 3F800000")
    lines.append("G33R END")
    stream = _stream(_call(1, cols=(1,), ks=2)) + "\n".join(lines) + "\n"
    with pytest.raises(ra.RefineError, match="G33R algorithm"):
        ql._validated_window(stream, "algorithm-mismatch")


def test_review208_factorial_partition_keeps_signed_zero_distinct(monkeypatch):
    single = {(1, 1, 0): (("qv", 0.0),)}
    split = {(1, 1, 0): (("qv", -0.0),)}
    final_single = {("qv", 1, 0): 0.0}
    final_split = {("qv", 1, 0): -0.0}
    monkeypatch.setattr(fc, "_segment_states", lambda text:
                        single if text == "single" else split)
    monkeypatch.setattr(fc, "_window_final", lambda text:
                        final_single if text == "single" else final_split)
    got = fc._partition("single", "split")
    assert got["partition_first_components"] == 1.0
    assert got["partition_path_components"] == 1.0
    assert got["partition_window_final_components"] == 1.0


def test_review208_factorial_binding_requires_initial_state(monkeypatch):
    rid = {"real_bytes": 4}
    run = {("forcing", "rho", 1, 0): 1.0,
           ("forcing", "delz", 1, 0): 1.0}
    monkeypatch.setattr(nt, "validated_run_identity",
                        lambda text, with_calls=True: (rid, []))
    monkeypatch.setattr(ra, "read_text", lambda text: run)
    with pytest.raises(fc.FactorialError, match="no INITIAL state"):
        fc._bound_window_identity("synthetic")


def test_review208_factorial_response_refuses_absent_initial_inventory():
    lines = ["G33R BEGIN nsplit 1 rezero legacy delt 100.000000 loops 1 "
             "dtcld 100.000000", "G33R FIXTURE synthetic"]
    for field in ra.STATE_FIELDS:
        for level in (0, 1):
            lines.append(f"G33R STATE {field} 1 {level} 3F800000")
    for species in (1, 2, 3):
        lines.append(f"G33R PREC {species} 1 3F800000")
    for name in ("rho", "delz"):
        for level in (0, 1):
            lines.append(f"G33R FORCING {name} 1 {level} 3F800000")
    lines.append("G33R END")
    stream = _stream(_call(1, cols=(1,), ks=2)) + "\n".join(lines) + "\n"
    with pytest.raises(fc.FactorialError, match="no INITIAL state"):
        fc.responses(stream, stream)


def test_review208_factorial_response_checks_pair_identity_inside_api(monkeypatch):
    fields = {
        "algorithm": "legacy", "number_transfer_metric": "thickness",
        "nsplit": 1, "carry": "rezero", "rho": "as-is", "width": 3,
        "levels": 2, "delt": 100.0, "dtcld": 100.0, "loops": 1,
        "ntile": 2,
    }
    other = dict(fields, carry="carry")
    monkeypatch.setattr(fc, "_bound_window_identity",
                        lambda text: fields if text == "single" else other)
    with pytest.raises(fc.FactorialError, match="differ in carry"):
        fc.responses("single", "split")


def test_review208_batch_empty_fraction_population_is_explicit():
    rows = [{"fraction_left": None, "fraction_left_xfer": None},
            {"fraction_left": None, "fraction_left_xfer": None}]
    summary, fractions, transfers = batch._fraction_summary(rows)
    assert fractions == [] and transfers == []
    assert summary["columns"] == 0
    assert summary["columns_unavailable"] == 2
    assert summary["summary_unavailable"] is True
    assert summary["median"] is None and summary["max"] is None
    assert batch._display(None, ".4%") == "n/a"


def test_review208_frozen_fixture_source_uses_staged_build_bytes(tmp_path):
    fixture = "g33_fixture_multisubcycle_v1"
    current = (xp.HERE / "g33_fortran" / f"{fixture}.f90").resolve()
    payload = b"! bytes staged for this build\n"
    staged = tmp_path / f"{hashlib.sha256(payload).hexdigest()}-staged.f90"
    staged.write_bytes(payload)
    (tmp_path / "staged-map.txt").write_text(f"{staged}\t{current}\n")
    assert xp._frozen_fixture_source(tmp_path, fixture) == payload.decode()


def test_review208_frozen_fixture_source_refuses_post_build_mutation(tmp_path):
    fixture = "g33_fixture_multisubcycle_v1"
    current = (xp.HERE / "g33_fortran" / f"{fixture}.f90").resolve()
    original = b"! bytes staged for this build\n"
    staged = tmp_path / f"{hashlib.sha256(original).hexdigest()}-staged.f90"
    staged.write_bytes(original)
    (tmp_path / "staged-map.txt").write_text(f"{staged}\t{current}\n")
    staged.write_bytes(b"! mutated after build verification\n")
    with pytest.raises(SystemExit, match="claims"):
        xp._frozen_fixture_source(tmp_path, fixture)


def test_review208_invalid_factorial_null_keeps_valid_coefficient_contract():
    from test_g33_factorial import _table

    beta = fc.coefficients(_table(lambda n, c, l: 2.0))['R_ni']
    assert beta["_valid"] is True
    assert beta[""] == pytest.approx(2.0)


def test_review208_locality_contract_uses_frozen_fixture_authority(monkeypatch):
    fixture = "g33_fixture_multisubcycle_v1"
    source = (xp.HERE / "g33_fortran" / f"{fixture}.f90").read_text()
    source = source.replace(
        "int(z'3F800000', int32), int(z'3F800000', int32), int(z'3F800000', int32)",
        "int(z'3F800000', int32), int(z'40000000', int32), int(z'3F800000', int32)")
    source = source.replace("NCMIN_SEA_BITS = int(z'41200000'",
                            "NCMIN_SEA_BITS = int(z'42C80000'")
    contract = SimpleNamespace(columns=3, levels=4, fixture_source=source)
    monkeypatch.setattr(nl, "fixture_dims", lambda *_: pytest.fail("tree read"))
    monkeypatch.setattr(nl, "fixture_xland", lambda *_: pytest.fail("tree read"))
    monkeypatch.setattr(nl, "fixture_ncmin", lambda *_: pytest.fail("tree read"))
    width, levels, xland, ncmin, held = nl._fixture_authority(fixture, contract)
    assert (width, levels) == (3, 4)
    assert xland == {1: 1.0, 2: 2.0, 3: 1.0}
    assert ncmin == (10.0, 100.0)
    assert held == source


def test_review208_locality_contract_without_source_refuses_tree_fallback():
    fixture = "g33_fixture_multisubcycle_v1"
    contract = SimpleNamespace(columns=3, levels=4, fixture_source="")
    # These two helpers construct threshold classes from fixture bytes. Their
    # contract path must refuse a missing source rather than reread the tree.
    for helper in (nl.class_law, nl.control_replication):
        with pytest.raises(ra.RefineError, match="fixture_source"):
            helper("driver", fixture, contract=contract)
