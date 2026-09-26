"""Fail-closed tests for the source-pinned S5 next-capture overlay plan."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import s5_g4_ww_probe_overlay as probe  # noqa: E402


def _anchor_fixture() -> str:
    return "".join((
        "SUBROUTINE calc_ww_cp ( u, v )\n",
        probe.DECL_ANCHOR,
        probe.BOUNDS_ANCHOR,
        "      DO j=jts,jtf\n      DO i=its,itf\n      ENDDO\n      ENDDO\n\n",
        "      DO j=jts,min(jte+1,jde)\n      DO i=its,itf\n",
        "        MUV(i,j) = 0.5*(MUP(i,j)+MUB(i,j)+MUP(i,j-1)+MUB(i,j-1))\n",
        probe.MU_ARRAYS_ANCHOR,
        "      DO j=jts,jtf\n",
        "        DO k=kts,ktf\n          divv(i,k) = source_terms\n",
        probe.DIVV_ANCHOR,
        "        DO k=2,ktf\n",
        probe.WW_ANCHOR,
        probe.CLOSE_ANCHOR,
        "END SUBROUTINE calc_ww_cp\n",
    ))


def test_guarded_overlay_strips_to_exact_input_bytes():
    source = _anchor_fixture()
    overlay = probe.render_overlay_text(source)

    assert probe.strip_guarded_blocks(overlay) == source
    assert overlay.count(f"#ifdef {probe.GUARD}") == 6
    assert "TRANSFER(ww(s5_i,s5_k,j),0)" in overlay
    assert "TRANSFER(divv(s5_i,s5_k),0)" in overlay
    assert "s5_tile_calls(s5_slot) <= 3" in overlay


def test_capture_mode_fails_closed_only_on_unplanned_tile_overflow():
    overlay = probe.render_overlay_text(_anchor_fixture())
    call_block = overlay.split("! S5_WW_PROBE_BEGIN:CALL\n", 1)[1].split(
        "! S5_WW_PROBE_END:CALL", 1
    )[0]

    assert "IF (s5_slot == 0) THEN" in call_block
    assert "S5_CAPTURE_TILE_OVERFLOW" in call_block
    assert "STOP 17" in call_block
    assert "s5_tile_calls(s5_slot) = s5_tile_calls(s5_slot) + 1" in call_block
    assert "IF (s5_tile_calls(s5_slot) <= 3) THEN" in call_block
    assert "STOP 18" not in call_block


def test_capture_blocks_follow_the_producer_assignments():
    overlay = probe.render_overlay_text(_anchor_fixture())

    assert overlay.index("MUV(i,j) =") < overlay.index("S5_WW_PROBE_BEGIN:MU_ARRAYS")
    assert overlay.index("S5_WW_PROBE_BEGIN:MU_ARRAYS") < overlay.index(
        "DO j=jts,jtf", overlay.index("S5_WW_PROBE_BEGIN:MU_ARRAYS")
    )
    assert overlay.index("divv(i,k) =") < overlay.index("S5_WW_PROBE_BEGIN:DIVV")
    assert overlay.index("S5_WW_PROBE_BEGIN:DIVV") < overlay.index("ww(i,k,j)=")
    assert overlay.index("ww(i,k,j)=") < overlay.index("S5_WW_PROBE_BEGIN:WW")
    assert overlay.index("S5_WW_PROBE_BEGIN:WW") < overlay.index("CLOSE(s5_unit)")


def test_overlay_refuses_missing_or_duplicated_source_anchors():
    with pytest.raises(ValueError, match="calc_ww_cp source routine"):
        probe.render_overlay_text("SUBROUTINE calc_ww_cp\n")

    fixture = _anchor_fixture()
    duplicated = fixture.replace(
        "END SUBROUTINE calc_ww_cp\n",
        probe.BOUNDS_ANCHOR + "END SUBROUTINE calc_ww_cp\n",
    )
    with pytest.raises(ValueError, match="computed call bounds occurs 2 times"):
        probe.render_overlay_text(duplicated)


def test_source_entrypoint_fails_closed_on_unpinned_source(tmp_path):
    source = tmp_path / "not-private-host-source.F"
    output = tmp_path / "overlay.F"
    source.write_text(_anchor_fixture(), encoding="ascii")

    with pytest.raises(ValueError, match="refuse source SHA-256"):
        probe.generate(source, output)
    assert not output.exists()


@pytest.mark.parametrize("layout,expected_header_count,expected_samples", [
    ("1x1", 6, 140_448),
    ("2x1", 12, 140_448),
])
def test_declared_schedule_has_complete_selected_cells(
    layout, expected_header_count, expected_samples
):
    headers = sorted(probe.expected_headers(layout))
    samples = sorted(probe.expected_sample_keys(layout))

    assert len(headers) == expected_header_count
    assert len(samples) == expected_samples
    probe.validate_declared_capture(layout, headers, samples)


@pytest.mark.parametrize("layout", ["1x1", "2x1"])
def test_declared_schedule_rejects_missing_duplicate_and_relocated_samples(layout):
    headers = sorted(probe.expected_headers(layout))
    samples = sorted(probe.expected_sample_keys(layout))

    with pytest.raises(ValueError, match="selected-cell schedule"):
        probe.validate_declared_capture(layout, headers, samples[:-1])

    with pytest.raises(ValueError, match="selected-cell schedule"):
        probe.validate_declared_capture(layout, headers, samples + [samples[0]])

    moved = list(samples)
    key = moved[0]
    moved[0] = (*key[:-2], key[-2] + 1, key[-1])
    with pytest.raises(ValueError, match="selected-cell schedule"):
        probe.validate_declared_capture(layout, headers, moved)


def test_declared_schedule_rejects_missing_or_extra_call_tile_header():
    headers = sorted(probe.expected_headers("2x1"))
    samples = sorted(probe.expected_sample_keys("2x1"))

    with pytest.raises(ValueError, match="tile/call schedule"):
        probe.validate_declared_capture("2x1", headers[:-1], samples)
    with pytest.raises(ValueError, match="tile/call schedule"):
        probe.validate_declared_capture(
            "2x1", headers + [headers[0]], samples
        )


def test_unknown_layout_is_not_inferred_from_received_records():
    with pytest.raises(ValueError, match="unsupported declared layout"):
        probe.expected_headers("3x1")


def test_capture_parser_keeps_raw_words_and_checks_expected_coordinates(tmp_path, monkeypatch):
    monkeypatch.setattr(probe, "CAPTURE_CALLS", (1,))
    monkeypatch.setattr(probe, "TILES", {"1x1": ((0, 1, 235, 1, 142),)})
    key = (1, 0, 1, 235, 1, 142, "WW", 117, 117, 1, 1)
    monkeypatch.setattr(probe, "expected_sample_keys", lambda _layout: {key})
    values = [1, 0, *probe.EXPECTED_GLOBAL_BOUNDS,
              *probe.EXPECTED_MEMORY_BOUNDS[("1x1", 0)],
              1, 235, 1, 142, 1, 40, 234, 142, 39, 32, 32]
    capture = tmp_path / "tile-call.txt"
    sample = "SAMPLE WW 1 117 117 1 1 -1234567\n"

    def write_header(header_values):
        capture.write_text(
            "CALL " + " ".join(map(str, header_values)) + "\n" + sample,
            encoding="ascii",
        )

    write_header(values)

    receipt, words = probe.parse_capture_files("1x1", [capture])

    assert receipt["global_bounds"] == {
        "i": [1, 235], "j": [1, 283], "k": [1, 40]
    }
    assert receipt["rank_memory_bounds"] == {
        "0": {"i": [-4, 240], "j": [-4, 288], "k": [1, 40]}
    }
    assert receipt["tile_calls"] == [{
        "call": 1,
        "rank": 0,
        "tile_i": [1, 235],
        "tile_j": [1, 142],
        "global_bounds": {"i": [1, 235], "j": [1, 283], "k": [1, 40]},
        "memory_bounds": {"i": [-4, 240], "j": [-4, 288], "k": [1, 40]},
        "derived_loop_bounds": {"itf": 234, "jtf": 142, "ktf": 39},
    }]
    assert receipt["selected_sample_count"] == 1
    assert words == {key: -1_234_567}

    for index, changed in (
        (2, 0), (3, 236), (4, 0), (5, 284), (6, 2), (7, 41)
    ):
        altered = list(values)
        altered[index] = changed
        write_header(altered)
        with pytest.raises(ValueError, match="global bounds differ"):
            probe.parse_capture_files("1x1", [capture])

    for index in (8, 9, 10, 11, 12, 13):
        altered = list(values)
        altered[index] = 999
        write_header(altered)
        with pytest.raises(ValueError, match="rank memory bounds differ"):
            probe.parse_capture_files("1x1", [capture])

    write_header(values)
    capture.write_text(
        capture.read_text(encoding="ascii").replace(
            "SAMPLE WW 1 117 117 1 1 -1234567",
            "SAMPLE WW 1 117 117 2 1 -1234567",
        ),
        encoding="ascii",
    )
    with pytest.raises(ValueError, match="selected-cell schedule"):
        probe.parse_capture_files("1x1", [capture])


def test_capture_parser_rejects_an_unexpected_fifth_tile(tmp_path, monkeypatch):
    monkeypatch.setattr(probe, "CAPTURE_CALLS", (1,))
    monkeypatch.setattr(probe, "TILES", {"2x1": ((0, 1, 117, 1, 142),)})
    monkeypatch.setattr(probe, "expected_sample_keys", lambda _layout: set())
    values = [1, 2, *probe.EXPECTED_GLOBAL_BOUNDS,
              *probe.EXPECTED_MEMORY_BOUNDS[("2x1", 0)],
              236, 353, 1, 142, 1, 40, 235, 142, 39, 32, 32]
    capture = tmp_path / "unexpected-tile.txt"
    capture.write_text("CALL " + " ".join(map(str, values)) + "\n", encoding="ascii")

    with pytest.raises(ValueError, match="unexpected tile metadata"):
        probe.parse_capture_files("2x1", [capture])
