from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from replay_s10_progb_czero_guard import (  # noqa: E402
    _eq32,
    _replay_event_rows,
    event_log_sha256,
)
from s10_progb_zero_qg_guard import (  # noqa: E402
    brs_volume_stage1,
    brs_volume_stage2,
    brs_volume_stage3,
    f32,
    guarded_rate_over_density,
    heat_stage1,
    heat_stage2,
    qg_mass_stage1,
    qg_mass_stage2,
    qg_mass_stage3,
    xlwork2_stage2,
    xlwork2_stage3,
)

CALL = (1, 73, 3, 1, 0, 113, 1)
CALL3 = (1, 73, 4, 1, 0, 113, 2)
EXPECTED_STAGE1_KEYS = {(*CALL, 1)}

def _record(tag, ints, reals):
    return " ".join([tag, *(str(x) for x in ints), *(format(f32(x), ".17e") for x in reals)])


def _valid_event_rows():
    step1_qg = f32(1.0e-9)
    pgmlt = f32(-step1_qg)
    step1_qg_after = qg_mass_stage1(step1_qg, pgmlt)
    rain_before = f32(2.0e-6)
    rain_after = f32(rain_before - pgmlt)
    step1_brs_before = f32(1.0e-9)
    action, div_pgmlt = guarded_rate_over_density(step1_qg_after, pgmlt, 400.0)
    step1_brs_after = brs_volume_stage1(step1_brs_before, div_pgmlt)
    step1_t_before = f32(260.0)
    step1_t_after = heat_stage1(step1_t_before, xlf=3.34e5, cpm=1004.0, pgmlt=pgmlt)

    stage2_terms = dict(pgdep=0.0, pgaut=0.0, piacr=0.0, delta3=0.0,
                        praci=0.0, psacr=0.0, delta2=0.0, pracs=0.0,
                        pgaci=0.0, paacw=0.0, pgacr=0.0, pgacs=0.0, dtcld=20.0)
    stage2_qg_after = qg_mass_stage2(0.0, **stage2_terms)
    action2, div_pgdep = guarded_rate_over_density(stage2_qg_after, 0.0, 0.0)
    other_volume = [1.0e-8, -2.0e-9, 3.0e-9, 0.0, 0.0, 0.0, 0.0]
    stage2_brs_before = step1_brs_after
    stage2_brs_after = brs_volume_stage2(stage2_brs_before,
        pgdep_volume=div_pgdep, other_rates=other_volume, dtcld=20.0)
    stage2_heat_args = dict(xls=2.0e5, xl=3.0e5, xlf=1.0e5,
        psdep=0.0, pgdep=0.0, pidep=0.0, pinud=0.0,
        prevp=1.0e-8, piacr=0.0, paacw=0.0, pmulcs=0.0,
        pmulcg=0.0, pmulrs=0.0, pmulrg=0.0, piacw=0.0,
        pgacr=0.0, psacr=0.0)
    stage2_xlwork = xlwork2_stage2(**stage2_heat_args)
    stage2_t_before = step1_t_after
    stage2_t_after = heat_stage2(stage2_t_before, xlwork2=stage2_xlwork,
                                 cpm=1004.0, dtcld=20.0)

    stage3_qg_before = f32(1.0e-8)
    stage3_pgevp = f32(-1.0e-8)
    stage3_pgeml = f32(0.0)
    stage3_qg_after = qg_mass_stage3(stage3_qg_before, pgacs=0.0,
        pgevp=stage3_pgevp, pgeml=stage3_pgeml, dtcld=20.0)
    action_evap, div_evap = guarded_rate_over_density(stage3_qg_before,
                                                       stage3_pgevp, 400.0)
    action_melt, div_melt = guarded_rate_over_density(stage3_qg_before,
                                                       stage3_pgeml, 400.0)
    stage3_brs_before = stage2_brs_after
    stage3_brs_after = brs_volume_stage3(stage3_brs_before,
        bgevp=div_evap, bgeml=div_melt, dtcld=20.0)
    stage3_heat_args = dict(xl=3.0e5, xlf=1.0e5, prevp=0.0,
        psevp=2.0e-7, pgevp=stage3_pgevp, pseml=0.0, pgeml=stage3_pgeml)
    stage3_xlwork = xlwork2_stage3(**stage3_heat_args)
    stage3_t_after = heat_stage2(stage2_t_after, xlwork2=stage3_xlwork,
                                 cpm=1004.0, dtcld=20.0)

    events = []
    key = (*CALL, 1)
    events += [
        _record("S10ZG", (*CALL, 1418, action),
                (step1_qg_after, pgmlt, 400.0)),
        _record("S10MASS", key,
                (step1_qg, pgmlt, step1_qg_after, rain_before, rain_after)),
        _record("S10VOLUME", key,
                (step1_qg_after, pgmlt, 400.0, div_pgmlt,
                 step1_brs_before, step1_brs_after)),
        _record("S10HEAT", key,
                (step1_qg, pgmlt, step1_qg_after, 3.34e5, 1004.0,
                 step1_t_before, step1_t_after)),
    ]
    key = (*CALL, 2)
    events += [
        _record("S10ZG", (*CALL, 2824, action2), (stage2_qg_after, 0.0, 0.0)),
        _record("S10MASS", key, (0.0, *(stage2_terms[name] for name in
            ("pgdep", "pgaut", "piacr", "delta3", "praci", "psacr", "delta2",
             "pracs", "pgaci", "paacw", "pgacr", "pgacs", "dtcld")), stage2_qg_after)),
        _record("S10VOLUME", key, (stage2_qg_after, stage2_brs_before,
            0.0, 0.0, div_pgdep, *other_volume, 20.0, stage2_brs_after)),
        _record("S10HEAT", key, (stage2_heat_args["psdep"], stage2_heat_args["pgdep"],
            stage2_heat_args["pidep"], stage2_heat_args["pinud"], stage2_heat_args["prevp"],
            stage2_heat_args["piacr"], stage2_heat_args["paacw"], stage2_heat_args["pmulcs"],
            stage2_heat_args["pmulcg"], stage2_heat_args["pmulrs"], stage2_heat_args["pmulrg"],
            stage2_heat_args["piacw"], stage2_heat_args["pgacr"], stage2_heat_args["psacr"],
            stage2_heat_args["xls"], stage2_heat_args["xl"], stage2_heat_args["xlf"],
            stage2_xlwork, 20.0, 1004.0, stage2_t_before, stage2_t_after)),
    ]
    key = (*CALL3, 3)
    events += [
        _record("S10ZG", (*CALL3, 2915, action_evap),
                (stage3_qg_before, stage3_pgevp, 400.0)),
        _record("S10ZG", (*CALL3, 2916, action_melt),
                (stage3_qg_before, stage3_pgeml, 400.0)),
        _record("S10MASS", key, (stage3_qg_before, 0.0, stage3_pgevp,
                                  stage3_pgeml, 20.0, stage3_qg_after)),
        _record("S10VOLUME", key, (stage3_qg_before, stage3_qg_after,
                                     stage3_pgevp, 400.0, div_evap,
                                     stage3_pgeml, 400.0, div_melt, 20.0,
                                     stage3_brs_before, stage3_brs_after)),
        _record("S10HEAT", key, (0.0, stage3_heat_args["psevp"], stage3_pgevp, 0.0, stage3_pgeml,
            stage3_heat_args["xl"], stage3_heat_args["xlf"], stage3_xlwork,
            20.0, 1004.0, stage2_t_after, stage3_t_after)),
    ]
    events += [
        _record("S10MELTGATE", (*CALL, 1), (step1_qg, 280.0, 273.15)),
        _record("S10PHASE", (*CALL, 1), (-1.0, step1_qg_after, 20.0)),
        _record("S10MELTGATE", (*CALL3, 0), (0.0, 260.0, 273.15)),
        _record("S10PHASE", (*CALL3, 0), (1.0, 0.0, 20.0)),
    ]
    return events


def _replay(rows, *, expected_gate_keys=None, expected_log_sha256=None):
    return _replay_event_rows(
        rows,
        expected_log_sha256=expected_log_sha256 or event_log_sha256(rows),
        expected_stage1_keys=EXPECTED_STAGE1_KEYS,
        expected_gate_keys=expected_gate_keys,
    )


def test_replay_keeps_non_density_volume_and_heat_when_zero_division_is_skipped():
    result = _replay(_valid_event_rows(),
        expected_gate_keys={CALL, CALL3})
    assert result["nonzero_rate_suppressed"] is False
    assert result["guard_action_counts"] == {"0": 1, "1": 3}
    assert result["source_ordered_f32_budgets_passed"]


def test_replay_rejects_zero_guard_action_on_a_nonzero_rate():
    rows = _valid_event_rows()
    for index, line in enumerate(rows):
        if line.startswith("S10ZG ") and " 2824 " in line:
            fields = line.split()
            fields[9] = "1"  # illegal bypass->divide action for the exact-zero case
            rows[index] = " ".join(fields)
            break
    with pytest.raises(ValueError, match="guard action mismatch"):
        _replay(rows, expected_gate_keys={CALL, CALL3})


def test_replay_rejects_incomplete_or_nonfinite_guard_events():
    rows = _valid_event_rows()
    rows = [line for line in rows if not (line.startswith("S10ZG ") and " 2824 " in line)]
    with pytest.raises(ValueError, match="missing one|guard and budget"):
        _replay(rows, expected_gate_keys={CALL, CALL3})

    rows = _valid_event_rows()
    for index, line in enumerate(rows):
        if line.startswith("S10ZG ") and " 2824 " in line:
            fields = line.split()
            fields[-1] = "NaN"
            rows[index] = " ".join(fields)
            break
    with pytest.raises(ValueError, match="non-finite"):
        _replay(rows, expected_gate_keys={CALL, CALL3})


def test_stage2_zg_operands_must_match_mass_and_volume_ledger():
    rows = _valid_event_rows()
    for index, line in enumerate(rows):
        fields = line.split()
        if fields[0] == "S10ZG" and fields[8] == "2824":
            # A valid positive density/rate pair still cannot be relocated to
            # a call whose mass ledger records qg=0 and pgdep=0.
            fields[9:13] = ["1", "1.0e-8", "2.0e-9", "400.0"]
            rows[index] = " ".join(fields)
            break
    with pytest.raises(ValueError, match="stage-2 ZG qg operand"):
        _replay(rows, expected_gate_keys={CALL, CALL3})


def test_stage3_zg_operands_must_match_mass_ledger():
    rows = _valid_event_rows()
    for index, line in enumerate(rows):
        fields = line.split()
        if fields[0] == "S10ZG" and fields[8] == "2915":
            fields[9:13] = ["1", "1.0e-8", "2.0e-9", "400.0"]
            rows[index] = " ".join(fields)
            break
    with pytest.raises(ValueError, match="stage-3 ZG 2915 (qg|rate)"):
        _replay(rows, expected_gate_keys={CALL, CALL3})


def test_stage3_zg_uses_preupdate_qg_not_postmass_qg():
    rows = _valid_event_rows()
    for index, line in enumerate(rows):
        fields = line.split()
        if fields[0] == "S10ZG" and fields[8] == "2915":
            fields[10] = "0.0"  # stage-3 MASS qg_after; divider is before that update
            rows[index] = " ".join(fields)
            break
    with pytest.raises(ValueError, match="stage-3 ZG 2915 qg"):
        _replay(rows, expected_gate_keys={CALL, CALL3})


def test_default_replay_uses_code_fixed_gate_schedule_not_received_rows():
    # The two-row synthetic census cannot define its own expected universe.
    with pytest.raises(ValueError, match="independent melt/phase gate census"):
        _replay(_valid_event_rows())


def test_replay_rejects_gate_and_ledger_shrink_against_trusted_run_digest():
    rows = _valid_event_rows()
    trusted_digest = event_log_sha256(rows)
    mutated = []
    for line in rows:
        fields = line.split()
        if fields[0] == "S10MELTGATE" and fields[1:8] == [str(x) for x in CALL]:
            fields[9] = "0.0"  # qg gate no longer expects stage 1
            line = " ".join(fields)
        if fields[0] in {"S10ZG", "S10MASS", "S10VOLUME", "S10HEAT"} and (
            fields[1:8] == [str(x) for x in CALL]
            and (fields[0] != "S10ZG" or fields[8] == "1418")
            and (fields[0] == "S10ZG" or fields[8] == "1")
        ):
            continue
        mutated.append(line)
    with pytest.raises(ValueError, match="trusted event-log SHA-256"):
        _replay(mutated, expected_gate_keys={CALL, CALL3},
                expected_log_sha256=trusted_digest)
    with pytest.raises(ValueError, match="stage-1 source gate keys"):
        _replay(mutated, expected_gate_keys={CALL, CALL3})


def test_production_replay_requires_predeclared_stage1_census():
    rows = _valid_event_rows()
    with pytest.raises(TypeError, match="expected_stage1_keys"):
        _replay_event_rows(rows, expected_log_sha256=event_log_sha256(rows))


def test_f32_comparison_distinguishes_signed_zero_words():
    with pytest.raises(ValueError, match="source-order f32 mismatch"):
        _eq32(0.0, -0.0, "signed zero")
