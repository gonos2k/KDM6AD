"""Observer source guards; native noninterference is separate run evidence."""
import difflib
from pathlib import Path

import pytest

from harness.make_activation_trace_overlay import instrument_coordinator, main

SOURCE = Path(__file__).resolve().parents[2] / "libtorch/src/coordinator.cpp"


def test_observer_only_inserts_source_and_labels_value_only_diagnostics():
    original = SOURCE.read_text()
    rendered = instrument_coordinator(original)
    changes = difflib.SequenceMatcher(None, original.splitlines(), rendered.splitlines())
    assert all(tag in ("equal", "insert") for tag, *_ in changes.get_opcodes())
    assert 'torch::NoGradGuard guard;' in rendered
    assert 'value.scalar_type() == torch::kBool ? "bool" : "f64"' in rendered
    for flag in ("reservoir_tie", "qv_cap_tie", "nc_at_absolute_max", "nccn_at_max"):
        assert '{"' + flag + '"' in rendered
    assert 'trace_activation_schedule(mstep_col_main, mstepmax_main' in rendered


def test_observer_refuses_a_second_instrumentation():
    with pytest.raises(ValueError, match="already present"):
        instrument_coordinator(instrument_coordinator(SOURCE.read_text()))


def test_cli_rejects_unpinned_source_without_creating_output(tmp_path):
    output = tmp_path / "observer"
    with pytest.raises(ValueError, match="receipt-pinned"):
        main(["--coordinator", str(SOURCE), "--output-dir", str(output)])
    assert not output.exists()


def test_cli_checks_existing_output_before_reading_source(tmp_path):
    output = tmp_path / "observer"
    output.mkdir()
    (output / "keep").write_bytes(b"unchanged")
    with pytest.raises(FileExistsError, match="must be new"):
        main(["--coordinator", str(tmp_path / "missing.cpp"), "--output-dir", str(output)])
    assert (output / "keep").read_bytes() == b"unchanged"
    assert list(output.iterdir()) == [output / "keep"]
