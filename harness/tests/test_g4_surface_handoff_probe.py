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
    for sample, _, _ in surface_probe.PROFILES:
        for event in surface_probe.event_schedule(config):
            for field, levels in surface_probe.EVENT_FIELDS[event].items():
                for level in levels:
                    yield surface_probe.CaptureRow(
                        arm=arm,
                        sample=sample,
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
        arm="continuous", sample="clear", event="sfclay_pre",
        field="UNPLANNED", level=0, word="3F800000",
    )

    with pytest.raises(surface_probe.SurfaceProbeError, match="out-of-plan"):
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
        "sample": "clear", "field": "UST", "level": 0,
        "continuous_word": "3F800000", "restart_word": "3F800001",
    }]


def test_cardinality_replacement_by_extra_event_cannot_pass() -> None:
    config = _config()
    rows = list(_rows("continuous", config))
    victim = next(i for i, row in enumerate(rows)
                  if row.sample == "clear" and row.event == "sfclay_pre"
                  and row.field == "UST" and row.level == 0)
    rows.pop(victim)
    rows.append(surface_probe.CaptureRow(
        arm="continuous", sample="clear", event="unplanned_stage9",
        field="UST", level=0, word="3F800000",
    ))

    with pytest.raises(surface_probe.SurfaceProbeError, match="out-of-plan"):
        surface_probe.validate_capture(rows, arm="continuous", config=config)
