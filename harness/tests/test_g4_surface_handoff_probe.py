from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parents[1]
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import g4_restart_probe as restart_probe  # noqa: E402
import g4_surface_handoff_probe as surface_probe  # noqa: E402


def _config(*, fractional_seaice: int | None = 0) -> surface_probe.G4SurfaceConfig:
    return surface_probe.G4SurfaceConfig(
        timestep=2,
        sf_sfclay_physics=1,
        sf_surface_physics=2,
        sf_urban_physics=1,
        isfflx=1,
        bldt_minutes=0,
        adaptive_timestep=False,
        fractional_seaice=fractional_seaice,
    )


def _rows(arm: str, config: surface_probe.G4SurfaceConfig):
    for sample, j, i in surface_probe.PROFILES:
        for event in surface_probe.event_schedule(config):
            for field, levels in surface_probe.EVENT_FIELDS[event].items():
                for level in levels:
                    yield surface_probe.CaptureRow(
                        arm=arm,
                        sample=sample,
                        j_fortran_1based=j,
                        i_fortran_1based=i,
                        event=event,
                        field=field,
                        level=level,
                        word="3F800000",
                    )


def test_event_schedule_comes_from_declared_config_not_received_events() -> None:
    no_fractional_ice = surface_probe.event_schedule(_config(fractional_seaice=0))
    fractional_ice = surface_probe.event_schedule(_config(fractional_seaice=1))

    assert no_fractional_ice == (
        "surface_call_pre", "sfclay_pre", "sfclay_post",
        "noahmp_dispatch_entry", "noahmp_pre",
        "noahmp_post", "noahmp_urban_pre", "noahmp_urban_post",
        "surface_return",
    )
    assert fractional_ice == (
        "surface_call_pre", "sfclay_pre", "sfclay_post",
        "noahmp_dispatch_entry", "seaice_adjustment_post",
        "noahmp_pre", "noahmp_post",
        "noahmp_urban_pre", "noahmp_urban_post", "surface_return",
    )
    with pytest.raises(surface_probe.SurfaceProbeError, match="must be declared"):
        surface_probe.event_schedule(_config(fractional_seaice=None))
    with pytest.raises(surface_probe.SurfaceProbeError, match="pinned G4 surface path"):
        surface_probe.event_schedule(surface_probe.G4SurfaceConfig(
            timestep=2, sf_sfclay_physics=1, sf_surface_physics=2,
            sf_urban_physics=2, isfflx=1, bldt_minutes=0,
            adaptive_timestep=False, fractional_seaice=0,
        ))


def test_operand_contract_matches_independent_golden_schema() -> None:
    # Independently pinned in review; it does not derive from EVENT_FIELDS.
    assert {
        event: sum(len(levels) for levels in fields.values())
        for event, fields in surface_probe.EVENT_FIELDS.items()
    } == {
        "surface_call_pre": 27, "sfclay_pre": 271, "sfclay_post": 17,
        "noahmp_dispatch_entry": 11, "seaice_adjustment_post": 9,
        "noahmp_pre": 285, "noahmp_post": 30, "noahmp_urban_pre": 11,
        "noahmp_urban_post": 9, "surface_return": 7,
    }
    canonical = __import__("json").dumps(
        {event: {field: list(levels) for field, levels in fields.items()}
         for event, fields in surface_probe.EVENT_FIELDS.items()},
        sort_keys=True, separators=(",", ":"),
    )
    assert hashlib.sha256(canonical.encode()).hexdigest() == (
        "895d77cb90772ce79179ebafb04b5e9a15395c252e2480ac323f9d35e6264026"
    )
    assert surface_probe.EVENT_FIELDS["noahmp_pre"]["P8W"] == tuple(range(1, 41))


def test_source_audit_requires_pins_and_unique_anchors(monkeypatch: pytest.MonkeyPatch) -> None:
    sources = {"callsite": "source call anchor\n", "consumer": "consumer anchor\n"}
    pins = {name: hashlib.sha256(text.encode()).hexdigest()
            for name, text in sources.items()}
    anchors = {
        "callsite": {"call": ("source call anchor", 1)},
        "consumer": {"call": ("consumer anchor", 1)},
    }

    receipt = surface_probe.audit_sources(sources, pins=pins, anchors=anchors)
    assert receipt["sources"]["callsite"]["anchor_counts"] == {"call": 1}

    with pytest.raises(surface_probe.SurfaceProbeError, match="anchor count"):
        surface_probe.audit_sources(
            {**sources, "consumer": "consumer anchor\nconsumer anchor\n"},
            pins={**pins, "consumer": hashlib.sha256(
                b"consumer anchor\nconsumer anchor\n").hexdigest()},
            anchors=anchors,
        )


def test_existing_first_rk_overlay_preserves_exact_source() -> None:
    source = "\n".join(
        [anchor for _, anchor, _ in restart_probe.FIRST_RK_ANCHORS]
        + ["END MODULE module_first_rk_step_part1", ""]
    )
    original_pin = restart_probe.FIRST_RK_PIN
    restart_probe.FIRST_RK_PIN = hashlib.sha256(source.encode()).hexdigest()
    try:
        overlay = restart_probe.build_first_rk_overlay(source)
        assert restart_probe.strip_first_rk_overlay(overlay) == source
    finally:
        restart_probe.FIRST_RK_PIN = original_pin


def test_capture_validator_rejects_same_missing_operand_in_both_arms() -> None:
    config = _config()
    required = list(_rows("continuous", config))
    omitted_key = next(
        row for row in required
        if row.event == "sfclay_pre" and row.field == "UST" and row.sample == "clear"
    )
    for arm in ("continuous", "restart"):
        rows = [row for row in _rows(arm, config)
                if not (row.sample == omitted_key.sample
                        and row.event == omitted_key.event
                        and row.field == omitted_key.field
                        and row.level == omitted_key.level)]
        with pytest.raises(surface_probe.SurfaceProbeError, match="key universe incomplete"):
            surface_probe.validate_capture(rows, arm=arm, config=config)


def test_capture_validator_rejects_cardinality_preserving_substitution() -> None:
    config = _config()
    rows = list(_rows("continuous", config))
    target = next(i for i, row in enumerate(rows)
                  if row.sample == "clear" and row.event == "sfclay_pre"
                  and row.field == "UST" and row.level == 0)
    rows[target] = surface_probe.CaptureRow(
        arm="continuous", sample="clear", j_fortran_1based=145,
        i_fortran_1based=11, event="sfclay_pre",
        field="UNPLANNED", level=0, word="3F800000",
    )

    with pytest.raises(surface_probe.SurfaceProbeError, match="out-of-plan"):
        surface_probe.validate_capture(rows, arm="continuous", config=config)


def test_capture_validator_binds_sample_name_to_fixed_coordinates() -> None:
    config = _config()
    rows = list(_rows("continuous", config))
    target = next(i for i, row in enumerate(rows)
                  if row.sample == "clear" and row.event == "surface_call_pre")
    row = rows[target]
    rows[target] = surface_probe.CaptureRow(
        arm=row.arm, sample=row.sample, j_fortran_1based=12,
        i_fortran_1based=row.i_fortran_1based, event=row.event,
        field=row.field, level=row.level, word=row.word,
    )
    with pytest.raises(surface_probe.SurfaceProbeError, match="coordinates"):
        surface_probe.validate_capture(rows, arm="continuous", config=config)


def test_classifier_reports_earliest_boundary_without_claiming_cause() -> None:
    config = _config()
    continuous = surface_probe.validate_capture(
        _rows("continuous", config), arm="continuous", config=config
    )
    restart_rows = list(_rows("restart", config))
    for i, row in enumerate(restart_rows):
        if row.sample == "clear" and row.event == "sfclay_post" and row.field == "UST":
            restart_rows[i] = surface_probe.CaptureRow(
                arm="restart", sample=row.sample, event=row.event,
                j_fortran_1based=row.j_fortran_1based,
                i_fortran_1based=row.i_fortran_1based,
                field=row.field, level=row.level, word="3F800001",
            )
            break
    restart = surface_probe.validate_capture(
        restart_rows, arm="restart", config=config
    )

    result = surface_probe.classify_pair(continuous, restart, config=config)

    assert result["first_differing_event"] == "sfclay_post"
    assert result["classification"] == "producer_output_or_unobserved_dependency_difference"
    assert result["cause_established"] is False
    assert result["mismatches"] == [{
        "sample": "clear", "j_fortran_1based": 145,
        "i_fortran_1based": 11, "field": "UST", "level": 0,
        "continuous_word": "3F800000", "restart_word": "3F800001",
    }]


def test_classifier_fails_closed_on_incomplete_or_malformed_maps() -> None:
    config = _config()
    complete = surface_probe.validate_capture(
        _rows("continuous", config), arm="continuous", config=config
    )
    with pytest.raises(surface_probe.SurfaceProbeError, match="incomplete or extra"):
        surface_probe.classify_pair(complete, {}, config=config)
    malformed = dict(complete)
    key = next(iter(malformed))
    malformed[key] = "3f800000"
    with pytest.raises(surface_probe.SurfaceProbeError, match="invalid raw"):
        surface_probe.classify_pair(complete, malformed, config=config)


def test_plan_does_not_claim_profile_branch_activity() -> None:
    branch_activity = surface_probe.g4_source_plan()["profile_branch_activity"]
    assert branch_activity["status"] == "not_observed_by_this_plan"
    assert set(branch_activity["profiles"]) == {
        name for name, _, _ in surface_probe.PROFILES
    }
    assert all(all(value is None for value in outcomes.values())
               for outcomes in branch_activity["profiles"].values())


def test_cardinality_replacement_by_extra_event_cannot_pass() -> None:
    config = _config()
    rows = list(_rows("continuous", config))
    victim = next(i for i, row in enumerate(rows)
                  if row.sample == "clear" and row.event == "sfclay_pre"
                  and row.field == "UST" and row.level == 0)
    rows.pop(victim)
    rows.append(surface_probe.CaptureRow(
        arm="continuous", sample="clear", j_fortran_1based=145,
        i_fortran_1based=11, event="unplanned_stage9",
        field="UST", level=0, word="3F800000",
    ))

    with pytest.raises(surface_probe.SurfaceProbeError, match="out-of-plan"):
        surface_probe.validate_capture(rows, arm="continuous", config=config)
