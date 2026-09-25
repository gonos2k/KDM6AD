from __future__ import annotations

import gzip
import sys
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parents[1]
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import g4_restart_probe as probe  # noqa: E402


def _write_trace(path: Path, *, omit: tuple[int, str] | None = None,
                 changed: tuple[int, str] | None = None) -> None:
    lines: list[str] = []
    stages = probe.EXPECTED_STAGES
    for stage in stages:
        for name, j, i in probe.PROBE_COORDINATES:
            lines.append(
                f"SAMPLE {stage} 2 1 {name} {j} {i} 1 39 1 40 7 6 4"
            )
            fields: list[tuple[int, str]] = []
            fields.extend((0, field) for field in probe.SURFACE_FIELDS)
            fields.extend((k, field) for field in probe.MASS_FIELDS for k in range(1, 40))
            fields.extend((k, field) for field in probe.INTERFACE_FIELDS for k in range(1, 41))
            fields.extend((k, field) for field in probe.SOIL_FIELDS for k in range(1, 5))
            fields.extend((k, f"MOIST{m}") for m in range(1, 8) for k in range(1, 40))
            fields.extend((k, f"SCALAR{m}") for m in range(1, 7) for k in range(1, 40))
            for k, field in fields:
                if omit == (stage, field):
                    continue
                word = "3F800000"
                if changed == (stage, field):
                    word = "3F800001"
                lines.append(f"{stage} 2 1 {j} {i} {k} {name} {field} {word}")
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def test_exact_probe_plan_compares_raw_words_and_finds_first_stage(tmp_path: Path) -> None:
    continuous = tmp_path / "continuous.log"
    restart = tmp_path / "restart.log"
    _write_trace(continuous)
    _write_trace(restart, changed=(3, "HFX"))

    result = probe.compare_traces(continuous, restart)

    assert result["records_compared"] > 30_000
    assert result["raw_word_equal"] is False
    assert result["first_differing_stage"] == 3
    assert {item["field"] for item in result["differences"]} == {"HFX"}


def test_same_missing_stage_in_both_arms_is_rejected(tmp_path: Path) -> None:
    continuous = tmp_path / "continuous.log"
    restart = tmp_path / "restart.log"
    _write_trace(continuous)
    _write_trace(restart)
    for path in (continuous, restart):
        lines = [line for line in path.read_text().splitlines()
                 if not line.startswith("SAMPLE 8 ")
                 and not line.startswith("8 ")]
        path.write_text("\n".join(lines) + "\n")

    with pytest.raises(probe.ProbeError, match="sample plan incomplete"):
        probe.compare_traces(continuous, restart)


def test_same_missing_operand_in_both_arms_is_rejected(tmp_path: Path) -> None:
    continuous = tmp_path / "continuous.log"
    restart = tmp_path / "restart.log"
    _write_trace(continuous, omit=(2, "RTHRATEN"))
    _write_trace(restart, omit=(2, "RTHRATEN"))

    with pytest.raises(probe.ProbeError, match="field/level coverage incomplete"):
        probe.compare_traces(continuous, restart)


def test_wrong_level_plan_is_rejected(tmp_path: Path) -> None:
    trace = tmp_path / "continuous.log"
    _write_trace(trace)
    trace.write_text(
        trace.read_text().replace(
            " 1 39 1 40 7 6 4\n", " 1 38 1 40 7 6 4\n", 1
        )
    )

    with pytest.raises(probe.ProbeError, match="fixed vertical/species plan changed"):
        probe.parse_trace(trace)


def test_shrunk_species_declaration_and_rows_are_rejected(tmp_path: Path) -> None:
    trace = tmp_path / "shrunk.log"
    _write_trace(trace)
    lines = []
    removed_rows = 0
    for line in trace.read_text().splitlines():
        parts = line.split()
        if parts[0] == "SAMPLE":
            parts[11:13] = ["6", "5"]
            line = " ".join(parts)
        elif parts[7] in {"MOIST7", "SCALAR6"}:
            removed_rows += 1
            continue
        lines.append(line)
    assert removed_rows == 3_120
    for sample, j, i in probe.PROBE_COORDINATES:
        for index in range(624):
            lines.append(f"9 2 1 {j} {i} {index} {sample} EXTRA 3F800000")
    assert sum(not line.startswith("SAMPLE ") for line in lines) == 48_120
    trace.write_text("\n".join(lines) + "\n", encoding="ascii")

    with pytest.raises(probe.ProbeError, match="fixed vertical/species plan changed"):
        probe.parse_trace(trace)


def test_out_of_plan_stage_records_are_rejected(tmp_path: Path) -> None:
    trace = tmp_path / "extra-stage.log"
    _write_trace(trace)
    with trace.open("a", encoding="ascii") as stream:
        stream.write("9 2 1 145 11 0 clear HFX 3F800000\n")

    with pytest.raises(probe.ProbeError, match="global record universe incomplete"):
        probe.parse_trace(trace)


def test_shifted_mass_and_interface_level_bounds_are_rejected(tmp_path: Path) -> None:
    trace = tmp_path / "shifted.log"
    _write_trace(trace)
    lines = []
    for line in trace.read_text().splitlines():
        parts = line.split()
        if parts[0] == "SAMPLE":
            parts[7:11] = ["2", "40", "2", "41"]
            line = " ".join(parts)
        elif parts[7] in probe.MASS_FIELDS:
            parts[5] = str(int(parts[5]) + 1)
            line = " ".join(parts)
        elif parts[7] in probe.INTERFACE_FIELDS:
            parts[5] = str(int(parts[5]) + 1)
            line = " ".join(parts)
        lines.append(line)
    trace.write_text("\n".join(lines) + "\n", encoding="ascii")

    with pytest.raises(probe.ProbeError, match="fixed vertical/species plan changed"):
        probe.parse_trace(trace)


def test_compressed_trace_uses_the_same_complete_plan(tmp_path: Path) -> None:
    plain = tmp_path / "trace.log"
    compressed = tmp_path / "trace.log.gz"
    _write_trace(plain)
    with plain.open("rb") as source, gzip.open(compressed, "wb", compresslevel=9) as dest:
        dest.write(source.read())

    assert probe.parse_trace(compressed) == probe.parse_trace(plain)
