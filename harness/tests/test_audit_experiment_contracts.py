"""Focused regressions for the independent experiment contracts."""
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import g33_expectation as expectation  # noqa: E402
import g33_factorial as factorial  # noqa: E402
import g33_ncmin_locality as ncmin  # noqa: E402
import g33_refine_analyze as analyze  # noqa: E402
from g33_refine_experiment import RunContract  # noqa: E402


def _stream(*, fixture=None, mode="rezero", algo="legacy", nsplit=3,
            columns=(1, 2)):
    lines = [f"G33R BEGIN nsplit {nsplit} {mode} {algo} "
             f"delt {300 / nsplit:.6f} loops 1 dtcld {300 / nsplit:.6f}"]
    if fixture is not None:
        lines.append(f"G33R FIXTURE {fixture}")
    for field in analyze.STATE_FIELDS:
        for col in columns:
            for level in (0, 1):
                lines.append(f"G33R STATE {field} {col} {level} 3F800000")
    for species in (1, 2, 3):
        for col in columns:
            lines.append(f"G33R PREC {species} {col} 3F800000")
    lines.append("G33R END")
    return "\n".join(lines) + "\n"


def _with_inputs(text, names=("rho", "delz"), *, initial=False):
    lines = text.splitlines()
    end = lines.pop()
    if initial:
        lines.extend(
            f"G33R INITIAL {p[2]} {p[3]} {p[4]} 3F800000"
            for p in (ln.split() for ln in lines)
            if p[:2] == ["G33R", "STATE"])
    for name in names:
        columns = sorted({int(p[3]) for p in (ln.split() for ln in lines)
                          if p[:2] == ["G33R", "STATE"]})
        levels = sorted({int(p[4]) for p in (ln.split() for ln in lines)
                         if p[:2] == ["G33R", "STATE"]})
        lines.extend(
            f"G33R FORCING {name} {col} {level} 3F800000"
            for col in columns for level in levels)
    lines.append(end)
    return "\n".join(lines) + "\n"


def test_refinement_parser_rejects_duplicate_fixture_metadata():
    text = _stream().replace(
        "G33R END", "G33R FIXTURE first\nG33R FIXTURE second\nG33R END")
    with pytest.raises(analyze.RefineError, match="duplicate"):
        analyze.read_text(text, nsplit=3)


def test_refinement_members_require_same_atmosphere_words():
    first = analyze.read_text(_with_inputs(_stream()), nsplit=3)
    changed = _with_inputs(_stream()).replace(
        "G33R FORCING rho 1 0 3F800000",
        "G33R FORCING rho 1 0 40000000")
    second = analyze.read_text(changed, nsplit=3)
    with pytest.raises(analyze.RefineError, match="raw input"):
        analyze.require_same_universe({3: first, 6: second})


def test_refinement_members_require_same_fixture_identity():
    first = analyze.read_text(_stream(fixture="fixture_a"), nsplit=3)
    second = analyze.read_text(_stream(fixture="fixture_b"), nsplit=3)
    with pytest.raises(analyze.RefineError, match="fixed run condition `fixture`"):
        analyze.require_same_universe({3: first, 6: second})


def test_pii_only_stream_reports_unavailable_rho_dz_measurements(capsys):
    run = analyze.read_text(
        _with_inputs(_stream(), ("pii",), initial=True), nsplit=3)
    assert analyze.column_budgets(run) == {
        "available": False,
        "reason": "rho*dz column budget requires both `rho` and `delz` forcing",
    }
    assert analyze.water_residual(run, 1) == {
        "available": False,
        "reason": "water residual requires both `rho` and `delz` forcing",
    }
    assert analyze.enthalpy_ledger(run) == {
        "available": False,
        "reason": "enthalpy ledger requires `rho`, `delz`, and `pii` forcing",
    }
    analyze.budget_report({3: run, 6: run})
    analyze.water_residual_report({3: run, 6: run})
    analyze.ledger_report({3: run, 6: run})
    analyze.diagnostic_budget_consistency_report({3: run, 6: run})
    assert capsys.readouterr().out.count("unavailable") >= 3


def test_xland_only_column_budget_is_explicitly_unavailable():
    run = analyze.read_text(_with_inputs(_stream(), ("xland",)), nsplit=3)
    result = analyze.column_budgets(run)
    assert result["available"] is False
    assert "rho" in result["reason"] and "delz" in result["reason"]


def _table():
    return {
        arm: {
            response: {"value": 1.0, "valid": True, "reason": "",
                       "screening_bound": 1.0}
            for response in factorial.RESPONSES}
        for arm in factorial.ALGO_FACTORS
    }


def test_factorial_coefficients_apply_and_validate_external_screens():
    table = _table()
    screens = {arm: {response: 0.0 for response in factorial.RESPONSES}
               for arm in factorial.ALGO_FACTORS}
    assert factorial.coefficients(table, screens)["R_qr"]["_bound"] == 0.0
    screens["legacy"]["R_qr"] = -1.0
    with pytest.raises(factorial.FactorialError, match="finite non-negative"):
        factorial.coefficients(table, screens)


def test_stage_registry_follows_call_input_then_init_then_clamp():
    major = expectation.stage_major()
    assert [name for name, _ in sorted(major.items(), key=lambda x: x[1])][:3] == [
        "kernel_call_input", "kernel_init_constants", "kernel_after_entry_clamp"]


def _ncmin_contract():
    return RunContract(
        fixture="fake-fixture", columns=3, levels=2, horizon=300.0,
        dtcldcr=120.0, algorithm="conservative", precision="f32",
        mode="carry", rho_profile="uniform", tiles=(3,))


def _ncmin_stream(contract):
    return _with_inputs(
        _stream(mode=contract.mode, algo=contract.algorithm, nsplit=1,
                columns=(1, 2, 3)),
        ("rho", "delz"), initial=True)


def test_ncmin_analysis_forwards_contract_to_every_stream_boundary(monkeypatch):
    """Run both analysis legs and observe the arguments at their stream seam.

    A source-string assertion would pass if a call to ``gated_text`` remained
    while its keywords were dropped.  This fake requires the complete frozen
    contract and returns a strict-parser-valid G33R stream, so the real analysis
    and local-oracle loops execute against the observed boundary.
    """
    contract = _ncmin_contract()
    text = _ncmin_stream(contract)
    calls = []

    def gate(driver, fixture, tiles, nsplit=1, carry="rezero", rho="as-is",
             *, algo=None, contract=None):
        calls.append((driver, fixture, tuple(tiles), nsplit, carry, rho,
                      algo, contract))
        assert algo == "conservative"
        assert contract is expected
        assert (nsplit, carry, rho) == (1, "carry", "uniform")
        return text

    expected = contract
    monkeypatch.setattr(ncmin, "gated_text", gate)
    # If the implementation regresses to direct run(), keep this test portable
    # and make the missing seam observable through the empty call list.
    monkeypatch.setattr(ncmin, "run", lambda *args, **kwargs: text)
    monkeypatch.setattr(ncmin, "_expect_tiles_are_live", lambda *args, **kwargs: None)
    monkeypatch.setattr(ncmin, "fixture_xland",
                        lambda fixture: {1: 1.0, 2: 1.0, 3: 1.0})
    monkeypatch.setattr(ncmin, "fixture_ncmin", lambda fixture: (1.0, 1.0))

    result = ncmin.analysis("fake-driver", "fake-fixture",
                            algo="conservative", contract=contract)

    assert result["ran"] == {
        "nsplit": 1, "carry": "carry", "rho": "uniform", "width": 3,
        "decompositions": [[1, 1, 1], [1, 2], [2, 1], [3]],
    }
    # One analysis baseline plus three partitions, and the local-oracle baseline
    # plus four decompositions.  Every
    # one must have crossed the same validated contract seam.
    assert len(calls) == 9
    assert all(call[6] == "conservative" and call[7] is expected
               for call in calls)


def test_ncmin_analysis_rejects_changed_forcing_at_partition_boundary(monkeypatch):
    """A changed forcing stream cannot be relabelled as an ncmin effect."""
    contract = _ncmin_contract()
    text = _ncmin_stream(contract)
    changed = text.replace(
        "G33R FORCING rho 1 0 3F800000",
        "G33R FORCING rho 1 0 40000000")

    def gate(driver, fixture, tiles, nsplit=1, carry="rezero", rho="as-is",
             *, algo=None, contract=None):
        assert algo == "conservative" and contract is expected
        return changed if tuple(tiles) == (1, 2) else text

    expected = contract
    monkeypatch.setattr(ncmin, "gated_text", gate)
    monkeypatch.setattr(ncmin, "run", lambda *args, **kwargs: text)
    monkeypatch.setattr(ncmin, "_expect_tiles_are_live", lambda *args, **kwargs: None)
    monkeypatch.setattr(ncmin, "fixture_xland",
                        lambda fixture: {1: 1.0, 2: 1.0, 3: 1.0})
    monkeypatch.setattr(ncmin, "fixture_ncmin", lambda fixture: (1.0, 1.0))

    with pytest.raises(analyze.RefineError, match="did not receive the same atmosphere"):
        ncmin.analysis("fake-driver", "fake-fixture",
                       algo="conservative", contract=contract)


def test_signed_zero_inputs_are_distinct_in_both_standalone_consumers():
    import g33_number_budget as budget
    a = _with_inputs(_stream(), initial=True).replace(
        'G33R INITIAL qv 1 0 3F800000', 'G33R INITIAL qv 1 0 00000000')
    b = a.replace('G33R INITIAL qv 1 0 00000000', 'G33R INITIAL qv 1 0 80000000')
    with pytest.raises(factorial.FactorialError, match='different inputs'):
        factorial.same_input('legacy', a, b)
    with pytest.raises(factorial.FactorialError, match='same atmosphere'):
        factorial.same_atmosphere({'a': a, 'b': b})
    with pytest.raises(analyze.RefineError, match='shared initial value'):
        budget._validate_pair(analyze.read_text(a), analyze.read_text(
            b.replace('rezero legacy', 'rezero conservative')), Path('a'), Path('b'))


def test_legacy_geometry_cli_refuses_cleanly(tmp_path, capsys):
    for n in (3, 6):
        text = _with_inputs(_stream(nsplit=n), initial=True)
        text = text.replace(text.splitlines()[0], f'G33R BEGIN nsplit {n} rezero legacy')
        (tmp_path / f'n{n}.rezero.txt').write_text(text)
    assert analyze.main([str(tmp_path)]) == 2
    out = capsys.readouterr()
    assert 'geometry unavailable' in out.err
    assert 'Reporting only' not in out.out


def test_standalone_factorial_binds_actual_stream_forcing():
    from test_g33_number_transport import _call, _stream as number_stream
    window = _with_inputs(_stream(nsplit=1, columns=(1,)), initial=True)
    raw = number_stream(_call(1)) + window
    assert factorial._bound_window_identity(raw)['real_bytes'] == 4
    # Change only the upper-layer transfer metric, leaving the independently
    # parsed G33R forcing and bottom NFLUX duplicate intact.
    bad = raw.replace('outer_pre_sed 0 rho 1 0 f32 3F800000',
                      'outer_pre_sed 0 rho 1 0 f32 40000000')
    with pytest.raises(factorial.FactorialError, match='window forcing'):
        factorial._bound_window_identity(bad)
    with pytest.raises(factorial.FactorialError, match='window forcing'):
        factorial.responses(bad, raw)
