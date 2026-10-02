import gzip
import subprocess
import sys
from pathlib import Path

import pytest

from harness.replay_supported_native_nccn import (
    DEFAULT_MASKS,
    DEFAULT_TRACE,
    TraceError,
    parse_masks,
    parse_trace,
    replay,
)


def _read(path):
    with gzip.open(path, "rt", encoding="ascii") as stream:
        return stream.read().splitlines()


def _write(path, lines):
    with gzip.open(path, "wt", encoding="ascii", newline="\n") as stream:
        stream.write("\n".join(lines) + "\n")
    return path


def test_actual_two_direction_trace_recomputes_outputs_masks_and_supported_gate():
    result = replay()
    assert result["trace_sha256"] == "ef6f6127a96124734b5cc08c9cff1222f0abd9fe32aa87a292558d60624d88fc"
    assert result["mask_trace_sha256"] == "e4eacccd11f691272cba43a12b7229fca439af846a924413bafdab05d46d79c5"
    assert result["numerical_pass"] is True
    assert all(result["strict_pair_admitted"].values())
    assert all(result["runner_preconditions_passed"].values())
    assert result["return_reconstruction_bitwise_equal"] is True
    assert result["return_branch_local"] is True
    assert result["branch_crossing"] is False
    assert result["supported_diagnostic_pass"] is True
    assert result["physical_number_basis_resolved"] is False
    assert result["physical_nccn_process_approved"] is False
    assert result["observational_admission"] is False
    assert result["direct_return_mismatch_count"] == 8
    assert result["raw_masks_identical_across_calls"] is True
    assert result["raw_mask_zero_count_per_call"] == {str(i): 18 for i in range(1, 6)}
    assert result["raw_mask_changed_count_per_call"] == {str(i): 21 for i in range(1, 6)}
    assert result["duality"]["mix"]["relative"] <= 1e-12
    assert result["duality"]["nn"]["relative"] <= 1e-12
    assert all(v["relative"] <= 1e-5 for d in result["field_relative"].values() for v in d.values())

    command = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parents[1] / "replay_supported_native_nccn.py")],
        capture_output=True, text=True, check=False,
    )
    assert command.returncode == 0
    assert '"status": "SUPPORTED_NATIVE_DIAGNOSTIC_PASS"' in command.stdout
    assert '"observational_admission": false' in command.stdout


def test_missing_main_array_level_is_rejected(tmp_path):
    lines = _read(DEFAULT_TRACE)
    del lines[next(i for i, line in enumerate(lines) if line.startswith("NN_OUT_MINUS 12 39 "))]
    with pytest.raises(TraceError, match="incomplete NN_OUT_MINUS coverage"):
        parse_trace(_write(tmp_path / "missing-level.tsv.gz", lines))


def test_missing_raw_mask_row_is_rejected(tmp_path):
    lines = _read(DEFAULT_MASKS)
    del lines[next(i for i, line in enumerate(lines) if line.startswith("5 39 "))]
    with pytest.raises(TraceError, match="5 calls x 39 levels"):
        parse_masks(_write(tmp_path / "missing-mask.tsv.gz", lines))


def test_mask_bit_that_disagrees_with_raw_delta_is_rejected(tmp_path):
    lines = _read(DEFAULT_MASKS)
    index = next(i for i, line in enumerate(lines) if line.startswith("1 1 "))
    parts = lines[index].split()
    parts[-1] = "0"  # raw DeltaVol is exactly zero at this cell
    lines[index] = " ".join(parts)
    with pytest.raises(TraceError, match="mask disagrees with raw DeltaVol"):
        parse_masks(_write(tmp_path / "mutated-branch.tsv.gz", lines))


def test_mutated_nccn_endpoint_fails_raw_return_reconstruction(tmp_path):
    lines = _read(DEFAULT_TRACE)
    index = next(i for i, line in enumerate(lines) if line.startswith("BASE_OUT 8 1 "))
    parts = lines[index].split()
    parts[-1] = "1.00000000000000000E+009"
    lines[index] = " ".join(parts)
    with pytest.raises(TraceError, match="raw return branch does not reproduce"):
        replay(_write(tmp_path / "mutated-endpoint.tsv.gz", lines), DEFAULT_MASKS)


def test_nonfinite_trace_value_is_rejected(tmp_path):
    lines = _read(DEFAULT_TRACE)
    index = next(i for i, line in enumerate(lines) if line.startswith("JV_NN 1 1 "))
    parts = lines[index].split()
    parts[-1] = "nan"
    lines[index] = " ".join(parts)
    with pytest.raises(TraceError, match="nonfinite"):
        parse_trace(_write(tmp_path / "nonfinite.tsv.gz", lines))
