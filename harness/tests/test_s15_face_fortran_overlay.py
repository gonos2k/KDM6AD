from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
import s15_face_cause_probe as replay
import s15_face_fortran_overlay as overlay
from test_s15_face_cause_probe import _synthetic


ROOT = Path(__file__).resolve().parents[2]
CONFIG = {"rk_order": 3, "adv_opt": "POSITIVEDEF"}


def _raw_stream() -> str:
    producers, consumers = _synthetic()
    coordinates = replay._projection(ROOT)
    rows: list[str] = []
    for slot, (producer, coordinate) in enumerate(zip(producers, coordinates)):
        identity = [
            producer["step"],
            producer["rk"],
            producer["owner"],
            slot % 2 + 1,
            producer["tile_i0"],
            producer["tile_i1"],
            producer["tile_j0"],
            producer["tile_j1"],
            *coordinate,
        ]
        branch_id = 2 if producer["branch"] == "positive_definite" else 1
        order = producer["tendency_order"]
        before = producer["initial_tendency"]
        for axis in order:
            part = producer["axes"][axis]
            faces = part["face_fluxes"]
            low = (
                producer["pd_low_order_fluxes"][axis]
                if branch_id == 2
                else {"minus": "00000000", "plus": "00000000"}
            )
            words = [
                faces["minus"],
                faces["plus"],
                low["minus"],
                low["plus"],
                part["metric_factor"],
                part["inverse_spacing"],
                before,
                part["tendency_prefix"],
            ]
            axis_id = {"y": 1, "x": 2, "z": 3}[axis]
            rows.append(
                "S15AX " + " ".join(map(str, identity + [axis_id, branch_id] + words))
            )
            before = part["tendency_prefix"]
        if branch_id == 2:
            low = producer["pd_low_order_fluxes"]
            pre = producer["pd_unlimited_high_order_fluxes"]
            post = producer["pd_high_order_fluxes"]
            words = [
                producer["pd_flux_out"],
                producer["pd_available_state"],
                "00000000",
                "00000000",
                *[low[a][s] for a in ("x", "y", "z") for s in ("minus", "plus")],
                *[pre[a][s] for a in ("x", "y", "z") for s in ("minus", "plus")],
                *[post[a][s] for a in ("x", "y", "z") for s in ("minus", "plus")],
            ]
            rows.append("S15PD " + " ".join(map(str, identity + [0] + words)))

    for slot, (consumer, coordinate) in enumerate(zip(consumers, coordinates)):
        identity = [
            consumer["step"],
            consumer["rk"],
            consumer["owner"],
            slot % 2 + 1,
            consumer["tile_i0"],
            consumer["tile_i1"],
            consumer["tile_j0"],
            consumer["tile_j1"],
            *coordinate,
        ]
        words = [
            consumer["advect_tend"],
            consumer["msfty"],
            consumer["sc_tend"],
            consumer["tendency"],
            consumer["before"],
            consumer["dt"],
            consumer["c1"],
            consumer["c2"],
            consumer["muold"],
            consumer["munew"],
            consumer["after"],
        ]
        rows.append("S15RK " + " ".join(map(str, identity + words)))
    return "\n".join(rows) + "\n"


def test_source_pins_and_both_owner_call_anchors_are_independent() -> None:
    assert overlay.SOURCE_PINS == {
        "dyn_em/solve_em.F": "d66e9db1bba8f37e3f46d30c2fd74bdf8def411adf233376a69e0b401c6d3d1f",
        "dyn_em/module_em.F": "7695bfb05a7f99763334a6e69523bbcc1de0f2c659177a18c10a6e1cf530a0c7",
        "dyn_em/module_advect_em.F": "58253bdbeb188dd47ed0579fcd2891086be1889b75c0c7d3696c9ad1d213559d",
    }
    assert overlay.PRODUCER_ANCHOR == ("scalar_tile_loop_1", "rk_scalar_tend")
    assert overlay.CONSUMER_ANCHOR == ("scalar_tile_loop_2", "rk_update_scalar")
    source = """scalar_tile_loop_1: DO ij=1,n
 CALL rk_scalar_tend(x)
ENDDO scalar_tile_loop_1
scalar_tile_loop_2: DO ij=1,n
 CALL rk_update_scalar(x)
ENDDO scalar_tile_loop_2
"""
    anchors = overlay.find_dual_owner_calls(source)
    assert anchors["producer"] != anchors["consumer"]
    patched = overlay._patch_solve(source)
    assert patched.count("s15_step=grid%itimestep") == 2
    assert overlay.strip_capture_macro(patched) == source
    with pytest.raises(overlay.OverlayError, match="rk_scalar_tend call"):
        overlay.find_dual_owner_calls(
            source.replace("CALL rk_scalar_tend(x)", "CALL other_tend(x)")
        )


def test_macro_off_call_rewrite_preserves_the_original_closing_line() -> None:
    original = "                                  kts=k_start, kte=k_end )"
    guarded = overlay._wrap_closing_line(
        original,
        ["s15_step=grid%itimestep", "s15_rk=rk_step", "s15_owner=5", "s15_tile=ij"],
    )
    assert overlay.strip_capture_macro("\n".join(guarded)) == original + "\n"


def test_synthetic_s15_records_parse_and_join_to_the_six_pinned_slots() -> None:
    stream = _raw_stream()
    producers, consumers = overlay.parse_fortran_capture(stream, ROOT, CONFIG)
    assert len(producers) == len(consumers) == 6
    assert producers[4]["pd_limiter_active"] is False
    assert producers[4]["tendency_order"] == ["z", "x", "y"]


@pytest.mark.parametrize(
    "mutation,match",
    [
        ("drop_axis", "exactly Y/X/Z"),
        ("duplicate_axis", "duplicate .* face record"),
        ("unknown", "unknown S15 record tag"),
        ("wrong_tile", "tile slot or coordinate"),
        ("wrong_branch", "source branch does not match"),
        ("duplicate_json_shape", "duplicate RK consumer"),
    ],
)
def test_raw_fortran_parser_fails_closed(mutation: str, match: str) -> None:
    rows = _raw_stream().splitlines()
    if mutation == "drop_axis":
        rows.remove(next(row for row in rows if row.startswith("S15AX ")))
    elif mutation == "duplicate_axis":
        event = next(row for row in rows if row.startswith("S15AX "))
        rows.append(event)
    elif mutation == "unknown":
        rows.append("S15FUTURE 2")
    elif mutation == "wrong_tile":
        index = next(i for i, row in enumerate(rows) if row.startswith("S15RK "))
        parts = rows[index].split()
        parts[4] = "2"
        rows[index] = " ".join(parts)
    elif mutation == "wrong_branch":
        index = next(
            i
            for i, row in enumerate(rows)
            if row.startswith("S15AX ") and " 3 2 " in row
        )
        parts = rows[index].split()
        parts[13] = "1"
        rows[index] = " ".join(parts)
    elif mutation == "duplicate_json_shape":
        index = next(i for i, row in enumerate(rows) if row.startswith("S15RK "))
        rows.append(rows[index])
    with pytest.raises(overlay.OverlayError, match=match):
        overlay.parse_fortran_capture("\n".join(rows) + "\n", ROOT, CONFIG)
