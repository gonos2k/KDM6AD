from __future__ import annotations

import json
import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import s15_face_cause_probe as probe


ROOT = Path(__file__).resolve().parents[2]
PROJECTION = ROOT / probe.PROJECTION_PATH
CONFIG = {"rk_order": 3, "adv_opt": "POSITIVEDEF"}


def _synthetic() -> tuple[list[dict], list[dict]]:
    coordinates = probe._projection(ROOT)
    producers: list[dict] = []
    consumers: list[dict] = []
    for schedule, coordinate in zip(probe.SCHEDULE, coordinates):
        i, j, k = coordinate
        identity = dict(zip(probe.KEY_FIELDS, [*schedule, i, j, k]))
        pd = schedule[1] == 3
        branch = "positive_definite" if pd else "ordinary"
        order = probe.PD_ORDER if pd else probe.ORDINARY_ORDER
        axes = {}
        acc = "00000000"
        prefixes = []
        for axis in order:
            faces = (
                {"minus": "00000000", "plus": "00000000"}
                if pd
                else {"minus": "BF800000", "plus": "3F800000"}
            )
            contribution = "00000000" if pd else "C0000000"
            axes[axis] = {
                "face_fluxes": faces,
                "metric_factor": "3F800000",
                "inverse_spacing": "3F800000",
                "flux_difference": "40000000" if not pd else "00000000",
                "directional_contribution": contribution,
                "tendency_prefix": (acc if pd else probe._sub(acc, "40000000")),
            }
            if not pd:
                acc = probe._sub(acc, "40000000")
            prefixes.append(acc)
        producer = {
            **identity,
            "branch": branch,
            "dispatch": {
                "rk_order": 3,
                "adv_opt": "POSITIVEDEF",
                "selected_branch": branch,
            },
            "tendency_order": list(order),
            "initial_tendency": "00000000",
            "axes": axes,
            "prefixes": prefixes,
            "advect_tend": acc,
        }
        if pd:
            producer.update(
                {
                    "pd_limiter_active": False,
                    "pd_flux_out": "00000000",
                    "pd_available_state": "3F800000",
                    "pd_low_order_fluxes": {
                        a: {"minus": "00000000", "plus": "00000000"} for a in probe.AXES
                    },
                    "pd_unlimited_high_order_fluxes": {
                        a: dict(axes[a]["face_fluxes"]) for a in probe.AXES
                    },
                    "pd_high_order_fluxes": {
                        a: dict(axes[a]["face_fluxes"]) for a in probe.AXES
                    },
                }
            )
        producers.append(producer)
        # The synthetic fixture selects values that keep every arithmetic
        # intermediate exactly representable in binary32.
        consumers.append(
            {
                **identity,
                "advect_tend": acc,
                "msfty": "3F800000",
                "sc_tend": "BF800000" if schedule[1] == 3 else "40A00000",
                "tendency": "BF800000",
                "before": "00000000",
                "after": "BF800000",
                "dt": "3F800000",
                "c1": "00000000",
                "c2": "3F800000",
                "muold": "3F800000",
                "munew": "3F800000",
            }
        )
    return producers, consumers


def test_exact_six_face_and_rk_rows_replay_from_raw_f32_words() -> None:
    producers, consumers = _synthetic()
    pairs = probe.validate_capture(producers, consumers, ROOT, CONFIG)
    assert len(pairs) == 6
    assert pairs[0][0]["axes"]["y"]["face_fluxes"]["minus"] == "BF800000"
    assert pairs[4][0]["branch"] == "positive_definite"

    # Discriminate the Fortran source's left-associated
    # high_plus-high_minus+low_plus-low_minus expression from grouped
    # (high_plus-high_minus)+(low_plus-low_minus) arithmetic.
    pd = producers[4]
    for axis in ("z", "y"):
        zero_faces = {"minus": "00000000", "plus": "00000000"}
        pd["pd_high_order_fluxes"][axis] = dict(zero_faces)
        pd["pd_low_order_fluxes"][axis] = dict(zero_faces)
        pd["axes"][axis].update(
            face_fluxes=dict(zero_faces),
            flux_difference="00000000",
            directional_contribution="00000000",
            tendency_prefix="00000000",
        )
    high_x = {"minus": "3F3FD48F", "plus": "3FF41F55"}
    low_x = {"minus": "3FA01BB4", "plus": "3F842B77"}
    grouped = probe._add(
        probe._sub(high_x["plus"], high_x["minus"]),
        probe._sub(low_x["plus"], low_x["minus"]),
    )
    assert grouped == "3F7089A2"
    assert (
        probe._sub(
            probe._add(
                probe._sub(high_x["plus"], high_x["minus"]),
                low_x["plus"],
            ),
            low_x["minus"],
        )
        == "3F7089A0"
    )
    pd["pd_high_order_fluxes"]["x"] = high_x
    pd["pd_unlimited_high_order_fluxes"]["x"] = high_x
    pd["pd_low_order_fluxes"]["x"] = low_x
    pd["axes"]["x"].update(
        face_fluxes=dict(high_x),
        flux_difference="3F7089A0",
        directional_contribution="BF7089A0",
        tendency_prefix="BF7089A0",
    )
    pd["axes"]["y"]["tendency_prefix"] = "BF7089A0"
    pd["prefixes"] = ["00000000", "BF7089A0", "BF7089A0"]
    pd["advect_tend"] = "BF7089A0"
    assert probe.replay_producer(pd, CONFIG)["advect_tend"] == "BF7089A0"

    active = _synthetic()[0][4]
    active.update(
        pd_limiter_active=True,
        pd_flux_out="40000000",
        pd_available_state="3F800000",
        pd_scale="3F000000",
        pd_eps="00000000",
    )
    raw = {
        "x": {"minus": "C0000000", "plus": "40800000"},
        "y": {"minus": "C0800000", "plus": "40C00000"},
        "z": {"minus": "40800000", "plus": "C0C00000"},
    }
    final = {
        "x": {"minus": "BF800000", "plus": "40000000"},
        "y": {"minus": "C0000000", "plus": "40400000"},
        "z": {"minus": "40000000", "plus": "C0400000"},
    }
    active["pd_unlimited_high_order_fluxes"] = raw
    active["pd_high_order_fluxes"] = final
    active["pd_low_order_fluxes"] = {
        "x": {"minus": "3F000000", "plus": "3F800000"},
        "y": {"minus": "3F800000", "plus": "3F000000"},
        "z": {"minus": "3F000000", "plus": "3F800000"},
    }
    for axis in probe.AXES:
        active["axes"][axis]["face_fluxes"] = dict(final[axis])
    probe._validate_pd(active)
    active["pd_scale"] = "00000000"
    with pytest.raises(probe.ProbeError, match="scale"):
        probe._validate_pd(active)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_consumer",
        "duplicate",
        "coordinate",
        "stage_mix",
        "branch",
        "signed_face",
        "prefix",
        "missing_sc_tend",
        "rk_store",
        "missing_pd",
        "pd_flag",
    ],
)
def test_fail_closed_replay_rejects_identity_face_stage_and_rk_mutations(
    mutation: str,
) -> None:
    producers, consumers = _synthetic()
    if mutation == "missing_consumer":
        consumers.pop()
    elif mutation == "duplicate":
        producers[-1] = dict(producers[0])
    elif mutation == "coordinate":
        producers[0]["i"] += 1
    elif mutation == "stage_mix":
        consumers[0]["rk"] = 2
    elif mutation == "branch":
        producers[-1]["branch"] = "ordinary"
    elif mutation == "signed_face":
        producers[0]["axes"]["y"]["face_fluxes"]["plus"] = "BF800000"
    elif mutation == "prefix":
        producers[0]["axes"]["y"]["tendency_prefix"] = "00000000"
    elif mutation == "missing_sc_tend":
        consumers[0].pop("sc_tend")
    elif mutation == "rk_store":
        consumers[0]["after"] = "40000000"
    elif mutation == "missing_pd":
        producers[4].pop("pd_low_order_fluxes")
    elif mutation == "pd_flag":
        producers[4]["pd_limiter_active"] = True
    with pytest.raises(probe.ProbeError):
        probe.validate_capture(producers, consumers, ROOT, CONFIG)


def test_projection_hash_and_independent_schedule_are_both_required(
    tmp_path: Path,
) -> None:
    source = PROJECTION
    projection = tmp_path / probe.PROJECTION_PATH
    projection.parent.mkdir(parents=True)
    projection.write_bytes(source.read_bytes() + b" ")
    witness = tmp_path / probe.WITNESS_PATH
    witness.parent.mkdir(parents=True, exist_ok=True)
    witness.write_bytes((ROOT / probe.WITNESS_PATH).read_bytes())
    with pytest.raises(probe.ProbeError, match="projection hash"):
        probe._projection(tmp_path)


def test_jsonl_parser_rejects_unknown_tags_and_wrong_cardinality(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text(json.dumps({"tag": "S15UNKNOWN"}) + "\n", encoding="utf-8")
    with pytest.raises(probe.ProbeError, match="unknown"):
        probe.read_jsonl(path)
    path.write_text('{"tag":"S15FACE","tag":"S15RK"}\n', encoding="utf-8")
    with pytest.raises(probe.ProbeError, match="duplicate JSON object key"):
        probe.read_jsonl(path)
    path.write_text(
        '{"tag":"S15FACE","outer":{"field":1,"field":2}}\n',
        encoding="utf-8",
    )
    with pytest.raises(probe.ProbeError, match="duplicate JSON object key"):
        probe.read_jsonl(path)


def test_source_pinned_recipe_copies_macro_off_inputs_byte_for_byte(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = tmp_path / "private-source"
    shadow_root = tmp_path / "shadow"
    fake_pins = {}
    for relative in probe.SOURCE_PINS:
        payload = ("fixture:" + relative).encode("ascii")
        target = source_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        fake_pins[relative] = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(probe, "SOURCE_PINS", fake_pins)
    recipe = probe.prepare_pinned_source_recipe(source_root, shadow_root, ROOT)
    assert probe.macro_off_equal(source_root, shadow_root)
    assert recipe["status"] == "source-pinned-recipe-only"
    assert len(recipe["schedule"]) == 6
    copied = shadow_root / "dyn_em/solve_em.F"
    copied.write_bytes(copied.read_bytes() + b"changed")
    with pytest.raises(probe.ProbeError, match="differs"):
        probe.macro_off_equal(source_root, shadow_root)


def test_raw_nonfinite_words_are_refused() -> None:
    for value in ("7F800000", "FF800000", "7FC00000"):
        with pytest.raises(probe.ProbeError, match="finite"):
            probe.word_value(value)
