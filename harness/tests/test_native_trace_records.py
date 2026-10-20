from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from harness.native_trace_records import (
    TRACE_FIELDS,
    TRACE_MAGIC,
    read_native_trace,
    validate_step_trace,
    validate_window_trace,
)


def _row(kind: str, step: int, i: int, k: int, j: int, values: list[str]) -> str:
    return f"{kind} {step} {i} {k} {j} {len(values)} " + " ".join(values)


def _trace(path: Path, rows: list[str]) -> Path:
    path.write_text(
        TRACE_MAGIC + " kind step i k j count values_ieee754_binary32_hex\n"
        + "\n".join(rows) + "\n",
        encoding="ascii",
    )
    return path


def _complete_rows(*, step=7, i=156, j=21, levels=2, dt_hex="41A00000") -> list[str]:
    rows = []
    for kind, fields in TRACE_FIELDS.items():
        values = [dt_hex] + ["3F800000"] * (len(fields) - 1)
        for k in range(1, levels + 1):
            rows.append(_row(kind, step, i, k, j, values))
    return rows


def _complete_window_rows(*, steps=(7, 8), i=156, j=21, levels=2, dt_hex="41A00000"):
    return [
        row
        for step in steps
        for row in _complete_rows(step=step, i=i, j=j, levels=levels, dt_hex=dt_hex)
    ]


def test_reader_preserves_exact_float32_bits_including_negative_zero(tmp_path):
    bits = ["3F800000", "80000000", "3F800001"] + ["00000000"] * 14
    trace = _trace(tmp_path / "known.hex", [_row("MP_INPUT", 3, 156, 2, 21, bits)])

    records = read_native_trace(trace)

    record = records[("MP_INPUT", 3, 156, 2, 21)]
    assert record.fields == TRACE_FIELDS["MP_INPUT"]
    assert record.bits == tuple(int(value, 16) for value in bits)
    assert record.values.dtype == np.dtype(np.float32)
    assert record.values.view(np.uint32).tolist() == [int(value, 16) for value in bits]
    assert np.signbit(record.value("TH"))
    assert record.value("Q") == np.nextafter(np.float32(1.0), np.float32(2.0))


def test_validate_requires_every_kind_and_vertical_level_with_exact_dt(tmp_path):
    trace = _trace(tmp_path / "complete.hex", _complete_rows())

    records = validate_step_trace(trace, step=7, i=156, j=21, levels=2, dt=20)

    assert len(records) == 4 * 2
    assert set(records) == {
        (kind, 7, 156, k, 21)
        for kind in TRACE_FIELDS
        for k in (1, 2)
    }


def test_window_validator_accepts_exact_consecutive_steps_and_single_step_api_stays_strict(tmp_path):
    trace = _trace(tmp_path / "window.hex", _complete_window_rows())

    records = validate_window_trace(trace, steps=(7, 8), i=156, j=21, levels=2, dt=20)

    assert len(records) == 4 * 2 * 2
    assert {key[1] for key in records} == {7, 8}
    with pytest.raises(ValueError, match="inventory mismatch"):
        validate_step_trace(trace, step=8, i=156, j=21, levels=2, dt=20)


@pytest.mark.parametrize("failure", ["missing", "extra", "wrong_dt"])
def test_window_validator_rejects_incomplete_or_unexpected_steps(tmp_path, failure):
    rows = _complete_window_rows()
    if failure == "missing":
        rows.pop()  # Missing the final FINISH_POST level in step 8.
    elif failure == "extra":
        rows.append(_row("MP_INPUT", 9, 156, 1, 21, ["41A00000"] + ["3F800000"] * 16))
    else:
        old = _row("FINISH_PRE", 8, 156, 2, 21, ["41A00000"] + ["3F800000"] * 11)
        new = _row("FINISH_PRE", 8, 156, 2, 21, ["41A00001"] + ["3F800000"] * 11)
        rows[rows.index(old)] = new
    trace = _trace(tmp_path / f"{failure}.hex", rows)
    message = "dt bits differ" if failure == "wrong_dt" else "inventory mismatch"
    with pytest.raises(ValueError, match=message):
        validate_window_trace(trace, steps=(7, 8), i=156, j=21, levels=2, dt=20)


@pytest.mark.parametrize(
    "content, message",
    [
        ("", "header"),
        (TRACE_MAGIC + "\n", "no records"),
        (TRACE_MAGIC + "0 kind step i k j count values\n", "header"),
        (TRACE_MAGIC + "\nUNKNOWN 1 1 1 1 1 3F800000\n", "unknown trace kind"),
        (TRACE_MAGIC + "\nMP_INPUT 1 1 1 1 17 3F800000\n", "requires 17 values"),
        (TRACE_MAGIC + "\nMP_INPUT 1 1 1 1 17 " + " ".join(["3F80000"] + ["00000000"] * 16) + "\n", "eight hex digits"),
        (TRACE_MAGIC + "\nMP_INPUT 0 1 1 1 17 " + " ".join(["00000000"] * 17) + "\n", "must be positive"),
        (TRACE_MAGIC + "\nMP_INPUT 1 1 1 1 17 " + " ".join(["7F800000"] + ["00000000"] * 16) + "\n", "nonfinite"),
    ],
)
def test_reader_rejects_malformed_or_nonfinite_records(tmp_path, content, message):
    path = tmp_path / "bad.hex"
    path.write_text(content, encoding="ascii")
    with pytest.raises(ValueError, match=message):
        read_native_trace(path)


def test_reader_rejects_duplicate_keys(tmp_path):
    row = _row("FINISH_POST", 7, 156, 1, 21, ["41A00000"] + ["3F800000"] * 6)
    trace = _trace(tmp_path / "duplicate.hex", [row, row])
    with pytest.raises(ValueError, match="duplicate trace key"):
        read_native_trace(trace)


@pytest.mark.parametrize(
    "rows, message",
    [
        (_complete_rows()[:-1], "inventory mismatch"),  # missing one FINISH_POST level
        (_complete_rows() + [_row("MP_INPUT", 7, 157, 1, 21, ["41A00000"] + ["3F800000"] * 16)], "inventory mismatch"),
        (_complete_rows(dt_hex="41A00001"), "dt bits differ"),
    ],
)
def test_step_validation_rejects_missing_unexpected_or_wrong_dt(tmp_path, rows, message):
    trace = _trace(tmp_path / "wrong-step.hex", rows)
    with pytest.raises(ValueError, match=message):
        validate_step_trace(trace, step=7, i=156, j=21, levels=2, dt=20)


def test_step_validation_rejects_wrong_step_and_column(tmp_path):
    rows = [
        _row(kind, 8, 156, 1, 21, ["41A00000"] + ["3F800000"] * (len(fields) - 1))
        for kind, fields in TRACE_FIELDS.items()
    ]
    trace = _trace(tmp_path / "wrong-step-column.hex", rows)
    with pytest.raises(ValueError, match="inventory mismatch"):
        validate_step_trace(trace, step=7, i=156, j=21, levels=1, dt=20)


@pytest.mark.parametrize("dt", [0, -1, -0.0, 1.0e-50])
def test_step_validation_requires_positive_float32_dt(tmp_path, dt):
    trace = _trace(tmp_path / "nonpositive-dt.hex", _complete_rows(levels=1))
    with pytest.raises(ValueError, match="dt must .*positive"):
        validate_step_trace(trace, step=7, i=156, j=21, levels=1, dt=dt)
