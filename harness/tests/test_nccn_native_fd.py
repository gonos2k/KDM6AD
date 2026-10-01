import gzip
import subprocess
import sys
from pathlib import Path

import pytest

from harness.replay_nccn_native_fd import DEFAULT_TRACE, TraceError, parse_trace, replay


def _lines():
    with gzip.open(DEFAULT_TRACE, "rt", encoding="ascii") as stream:
        return stream.read().splitlines()


def _write_trace(path: Path, lines):
    with gzip.open(path, "wt", encoding="ascii", newline="\n") as stream:
        stream.write("\n".join(lines) + "\n")
    return path


def test_actual_native_trace_replays_numerically_but_is_not_admitted():
    result = replay(DEFAULT_TRACE)
    assert result["compressed_sha256"] == "d46746a88225529c81902b0ec927b7b421f1f6dbe898887303d94c19144d9bc6"
    assert result["trace_sha256"] == "82f5173f022d9bc4bb708224ed799d18c4d779b99c696769c4a872254cd5ce59"
    assert result["numerical_pass"] is True
    assert result["supported"] is False
    assert result["accepted"] is False
    assert result["status"] == "NUMERICAL_PASS_UNADMITTED_STATE"
    assert result["worst_field"] == 8
    assert 0.0 <= result["duality_relative"] <= result["duality_threshold"] == 1e-12
    assert len(result["field_metrics"]) == 12
    parsed = parse_trace(DEFAULT_TRACE)
    assert set(parsed["arrays"]) == {
        "STATE_IN", "STATE_PLUS", "STATE_MINUS", "OUT_BASE", "OUT_PLUS", "OUT_MINUS",
        "V", "JV", "JTU", "FD", "FORCING", "XLAND",
    }
    assert all(result["array_shapes"][tag] == [12, 39] for tag in (
        "STATE_IN", "STATE_PLUS", "STATE_MINUS", "OUT_BASE", "OUT_PLUS", "OUT_MINUS", "V", "JV", "JTU", "FD"
    ))
    assert result["array_shapes"]["FORCING"] == [4, 39]
    assert result["array_shapes"]["XLAND"] == [1, 1]
    assert result["moment_admission"]["input_one_sided_pair_level_counts"] == {
        "qc/nc": 31, "qr/nr": 17, "qi/ni": 32, "qg/bg": 0,
    }
    assert result["moment_admission"]["baseline_output_one_sided_pair_level_counts"] == {
        "qc/nc": 5, "qr/nr": 8, "qi/ni": 0, "qg/bg": 4,
    }
    assert result["physical_moment_admission"] is False
    assert result["operational_approval"] is False
    assert result["accepted_observation_cost"] is False

    command = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parents[1] / "replay_nccn_native_fd.py"), str(DEFAULT_TRACE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert command.returncode == 1
    assert '"status": "NUMERICAL_PASS_UNADMITTED_STATE"' in command.stdout


def test_missing_array_record_is_rejected(tmp_path):
    lines = _lines()
    del lines[next(i for i, line in enumerate(lines) if line.startswith("STATE_IN 12 39 "))]
    with pytest.raises(TraceError, match="STATE_IN coverage incomplete"):
        parse_trace(_write_trace(tmp_path / "missing.tsv.gz", lines))


def test_duplicate_array_record_is_rejected(tmp_path):
    lines = _lines()
    row = next(line for line in lines if line.startswith("V 1 1 "))
    index = next(i for i, line in enumerate(lines) if line.startswith("FD_PASS_WORST_FIELD "))
    lines.insert(index, row)
    with pytest.raises(TraceError, match="duplicate V index"):
        parse_trace(_write_trace(tmp_path / "duplicate.tsv.gz", lines))


def test_changed_endpoint_is_rejected_by_recomputed_fd(tmp_path):
    lines = _lines()
    index = next(i for i, line in enumerate(lines) if line.startswith("OUT_PLUS 1 1 "))
    parts = lines[index].split()
    parts[-1] = "9.99900000000000000E+002"
    lines[index] = " ".join(parts)
    with pytest.raises(TraceError, match="stored FD differs"):
        replay(_write_trace(tmp_path / "endpoint.tsv.gz", lines))


def test_nonfinite_and_schema_mismatch_are_rejected(tmp_path):
    lines = _lines()
    index = next(i for i, line in enumerate(lines) if line.startswith("JTU 1 1 "))
    parts = lines[index].split()
    parts[-1] = "nan"
    lines[index] = " ".join(parts)
    with pytest.raises(TraceError, match="nonfinite"):
        parse_trace(_write_trace(tmp_path / "nonfinite.tsv.gz", lines))

    lines = _lines()
    index = next(i for i, line in enumerate(lines) if line.startswith("STATE_SHAPE "))
    lines[index] = "STATE_SHAPE 1 38 1 12"
    with pytest.raises(TraceError, match="STATE_SHAPE"):
        parse_trace(_write_trace(tmp_path / "schema.tsv.gz", lines))

    with pytest.raises(TraceError, match="truncated trace metadata"):
        parse_trace(_write_trace(tmp_path / "truncated.tsv.gz", ["KDM6_NCCN_ZERO_FD_TRACE_V1"]))


def test_inconsistent_reported_fd_pass_is_rejected(tmp_path):
    lines = _lines()
    index = next(i for i, line in enumerate(lines) if line.startswith("FD_PASS_WORST_FIELD "))
    lines[index] = "FD_PASS_WORST_FIELD 0 8"
    with pytest.raises(TraceError, match="does not match recomputed pass/worst field"):
        replay(_write_trace(tmp_path / "bad-pass.tsv.gz", lines))
