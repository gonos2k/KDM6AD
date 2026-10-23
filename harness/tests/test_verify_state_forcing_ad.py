"""Unit tests for the local trace-to-joint-AD verification harness.

The fake kernel below tests harness bookkeeping and verdict propagation only;
it is not model or science evidence.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pytest

import harness.verify_state_forcing_ad as verify_tool
from harness.native_trace_records import TRACE_MAGIC, TRACE_FIELDS


def _f32_hex(value: float) -> str:
    return f"{int(np.asarray([np.float32(value)], dtype=np.float32).view(np.uint32)[0]):08X}"


def _trace(path, *, dt=np.float32(20.0)):
    values = {
        "dt": dt, "TH": 300.0, "Q": .01, "QC": .0004, "QR": .0002,
        "QI": .0003, "QS": .0001, "QG": .00002, "NN": 1.2e8,
        "NC": 7.0e7, "NI": 2.0e6, "NR": 1.5e6, "BG": 2.0e-8,
        "DEN": 1.0, "PII": .95, "P": 80000.0, "DELZ": 300.0,
    }
    fields = TRACE_FIELDS["MP_INPUT"]
    record = "MP_INPUT 1 1 1 1 " + str(len(fields)) + " " + " ".join(
        _f32_hex(values[name]) for name in fields)
    path.write_text(TRACE_MAGIC + "\n" + record + "\n", encoding="ascii")


class _LinearKernel:
    """Small analytic map used only to test verifier direction/FD wiring."""
    def __init__(self, library, levels, dt, xland, ncmin_land, ncmin_sea, *, wrong_jvp=False):
        self.dt = dt
        self.wrong_jvp = wrong_jvp

    def forward(self, state, forcing, *, joint=True, record=False):
        out = np.zeros_like(state)
        out[0] = state[0] + 2.0 * state[1] + 3.0 * forcing[0] + .5 * forcing[1]
        out[1] = .5 * state[1] + 1.0e-5 * forcing[2] + .1 * forcing[3]
        out[2:] = state[2:]
        return out, (object() if record else None)

    def jvp(self, handle, state_direction, forcing_direction):
        out = np.zeros_like(state_direction)
        out[0] = state_direction[0] + 2.0 * state_direction[1] + 3.0 * forcing_direction[0] + .5 * forcing_direction[1]
        out[1] = .5 * state_direction[1] + 1.0e-5 * forcing_direction[2] + .1 * forcing_direction[3]
        out[2:] = state_direction[2:]
        if self.wrong_jvp:
            out[0] += 1.0
        return out

    def vjp(self, handle, cotangent):
        gs = np.zeros_like(cotangent)
        gf = np.zeros((4, cotangent.shape[1]), dtype=np.float64)
        gs[0] = cotangent[0]
        gs[1] = 2.0 * cotangent[0] + .5 * cotangent[1]
        gs[2:] = cotangent[2:]
        gf[0] = 3.0 * cotangent[0]
        gf[1] = .5 * cotangent[0]
        gf[2] = 1.0e-5 * cotangent[1]
        gf[3] = .1 * cotangent[1]
        return gs, gf

    def close(self, handle):
        pass


def _args(tmp_path, *, output=None):
    trace = tmp_path / "native_trace.hex"
    library = tmp_path / "libkdm6_c.dylib"
    _trace(trace)
    library.write_bytes(b"synthetic library pin for harness test\n")
    return SimpleNamespace(
        trace=trace, library=library, step=1, i=1, j=1, levels=1,
        xland=2.0, ncmin_land=10.0, ncmin_sea=10.0,
        output=output if output is not None else tmp_path / "report.json",
    )


def test_float32_trace_dt_is_json_serialized_as_builtin_float(tmp_path, monkeypatch):
    args = _args(tmp_path)
    monkeypatch.setattr(verify_tool, "Kernel", _LinearKernel)
    verify_tool.verify(args)
    report = json.loads(args.output.read_text())
    assert report["source"]["dt"] == 20.0
    assert type(report["source"]["dt"]) is float
    assert report["passed"] is True


@pytest.mark.parametrize("alias_kind", ["existing", "trace_symlink", "library_symlink"])
def test_output_alias_refused_without_modifying_inputs(tmp_path, monkeypatch, alias_kind):
    args = _args(tmp_path)
    trace_before = args.trace.read_bytes()
    library_before = args.library.read_bytes()
    if alias_kind == "existing":
        args.output.write_bytes(b"preserve existing report\n")
        expected = args.output.read_bytes()
    elif alias_kind == "trace_symlink":
        args.output.symlink_to(args.trace)
        expected = trace_before
    else:
        args.output.symlink_to(args.library)
        expected = library_before

    class MustNotLoadKernel:
        def __init__(self, *args, **kwargs):
            raise AssertionError("verification must reject output aliases before loading the kernel")

    monkeypatch.setattr(verify_tool, "Kernel", MustNotLoadKernel)
    with pytest.raises(ValueError, match="output must be a new file"):
        verify_tool.verify(args)

    if alias_kind == "existing":
        assert args.output.read_bytes() == expected
    else:
        assert args.output.is_symlink()
        assert args.output.resolve() in (args.trace.resolve(), args.library.resolve())
    assert args.trace.read_bytes() == trace_before
    assert args.library.read_bytes() == library_before


def test_verifier_rejects_analytic_fake_with_wrong_jvp_and_records_failure(tmp_path, monkeypatch):
    args = _args(tmp_path)

    class WrongKernel(_LinearKernel):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs, wrong_jvp=True)

    monkeypatch.setattr(verify_tool, "Kernel", WrongKernel)
    with pytest.raises(SystemExit) as exc:
        verify_tool.verify(args)
    assert exc.value.code == 1
    report = json.loads(args.output.read_text())
    assert report["passed"] is False
    assert any(not direction["passed"] for direction in report["directions"].values())
