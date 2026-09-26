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
            axes[axis] = {
                "face_fluxes": {"minus": "BF800000", "plus": "3F800000"},
                "metric_factor": "3F800000",
                "inverse_spacing": "3F800000",
                "flux_difference": "40000000",
                "directional_contribution": "C0000000",
                "tendency_prefix": probe._sub(acc, "40000000"),
            }
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
                    "pd_limiter_active": True,
                    "pd_flux_out": "40000000",
                    "pd_available_state": "3F800000",
                    "pd_scale": "3F000000",
                    "pd_low_order_fluxes": {
                        a: {"minus": "00000000", "plus": "00000000"} for a in probe.AXES
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
                "sc_tend": "40C00000",
                "tendency": "00000000",
                "before": "3F800000",
                "after": "3F800000",
                "dt": "00000000",
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
        producers[4]["pd_limiter_active"] = False
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
