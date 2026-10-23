"""Mechanics/error-path tests for the native-finish composition verifier.

Fake KDM kernels in this file prove only Python chain-rule and refusal behavior;
they are not native-model or scientific evidence.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import harness.verify_native_finish_ad as verify_tool
from harness.native_finish_replay import replay_arm64_theta_m_finish
from harness.native_trace_records import TRACE_FIELDS, TRACE_MAGIC


def _hex32(value):
    return f"{int(np.asarray([value], dtype=np.float32).view(np.uint32)[0]):08X}"


def _write_record(stream, kind, step, i, j, values):
    fields = TRACE_FIELDS[kind]
    assert tuple(values) == fields
    stream.write(f"{kind} {step} {i} 1 {j} {len(fields)} " +
                 " ".join(_hex32(np.float32(values[name])) for name in fields) + "\n")


def _write_case(trace: Path, namelist: Path, *, bad_th_handoff=False):
    dt = np.float32(20.0)
    qv0, qv1 = np.float32(.01), np.float32(.011)
    qc0, qc1 = np.float32(2.0e-8), np.float32(4.0e-8)
    th0, th1 = np.float32(300.0), np.float32(300.1)
    pre = {
        "dt": dt, "H_PRE": th0, "QV_PRE": qv0,
        "TH_PLUS": th1, "QV_PLUS": qv1,
        "QVTEN": np.float32(qv1-qv0), "MP_RAW": np.float32(th1-th0),
        "MP_CLIPPED": np.float32(th1-th0), "T_NEW_PRE": np.float32(300.0),
        "T0": np.float32(300.0), "ALPHA": np.float32(1.6),
        "MP_TEND_LIM": np.float32(10.0),
    }
    replay = replay_arm64_theta_m_finish(pre)
    input_values = {
        "dt": dt, "TH": th0, "Q": qv0, "QC": qc0, "QR": 0.0,
        "QI": 0.0, "QS": 0.0, "QG": 0.0, "NN": 1.0e8,
        "NC": 0.0, "NI": 0.0, "NR": 0.0, "BG": 0.0,
        "DEN": 1.0, "PII": .95, "P": 80000.0, "DELZ": 300.0,
    }
    output_values = {
        "dt": dt, "TH": np.float32(th1 + (0.1 if bad_th_handoff else 0.0)),
        "Q": qv1, "QC": qc1, "QR": 0.0, "QI": 0.0, "QS": 0.0,
        "QG": 0.0, "NN": 1.0e8, "NC": 0.0, "NI": 0.0,
        "NR": 0.0, "BG": 0.0, "RHOG": 0.0,
    }
    post = {
        "dt": dt, "T_NEW_AFTER": replay["T_NEW_AFTER"], "T0": pre["T0"],
        "H_RATE": replay["H_RATE"], "QV_RATE": replay["QV_RATE"],
        "QC_RATE": np.float32((qc1-qc0)/dt),
        "TH_PHY_M_T0": replay["TH_PHY_M_T0"],
    }
    with trace.open("w", encoding="ascii") as stream:
        stream.write(TRACE_MAGIC + "\n")
        _write_record(stream, "MP_INPUT", 1, 2, 2, input_values)
        _write_record(stream, "MP_OUTPUT", 1, 2, 2, output_values)
        _write_record(stream, "FINISH_PRE", 1, 2, 2, pre)
        _write_record(stream, "FINISH_POST", 1, 2, 2, post)
    namelist.write_text(
        "&time_control\n time_step=20,\n time_step_fract_num=0,\n time_step_fract_den=1,\n/\n"
        "&domains\n e_we=4,\n e_sn=4,\n e_vert=2,\n/\n"
        "&physics\n mp_physics=137,\n no_mp_heating=0,\n use_theta_m=1,\n"
        " mp_zero_out=2,\n mp_zero_out_thresh=1.0e-8,\n mp_tend_lim=10,\n"
        " ncmin_land=10,\n ncmin_sea=10,\n/\n",
        encoding="ascii",
    )


def _zero_value(state, config):
    result = np.array(state, copy=True)
    if config.mode == 2:
        result[1] = np.maximum(result[1], 0.0)
    if config.mode != 0:
        result[2] = np.where(result[2] < config.threshold, 0.0, result[2])
    return result


def _zero_direction(raw, direction, config):
    if config.mode != 0 and config.threshold > 0 and np.any(raw[2] == config.threshold):
        raise ValueError("QC equals positive zero-out threshold; derivative is discontinuous")
    result = np.array(direction, copy=True)
    if config.mode == 2:
        result[1] *= (raw[1] > 0.0)
    if config.mode != 0:
        result[2] *= (raw[2] > config.threshold)
    return result


def _finish_value(before, after, config):
    dt = config.dt
    result = np.zeros((5, before.shape[1]), dtype=np.float64)
    result[0] = before[0] + after[0]
    result[1] = (after[0] - before[0]) / dt
    result[2] = (after[1] - before[1]) / dt
    result[3] = (after[2] - before[2]) / dt
    result[4] = after[0]
    return result


def _finish_jvp(before, after, d_before, d_after, config):
    return _finish_value(d_before, d_after, config)


def _finish_vjp(before, after, cotangent, config):
    dt = config.dt
    old = np.zeros_like(before)
    new = np.zeros_like(after)
    old[0] = cotangent[0] - cotangent[1] / dt
    new[0] = cotangent[0] + cotangent[1] / dt + cotangent[4]
    old[1] = -cotangent[2] / dt
    new[1] = cotangent[2] / dt
    old[2] = -cotangent[3] / dt
    new[2] = cotangent[3] / dt
    return old, new


class _IdentityKernel:
    def __init__(self, *args, levels=2):
        self.levels = levels

    def forward(self, state, forcing, *, record=False):
        return np.array(state, copy=True), (object() if record else None)

    def jvp(self, handle, ds, df):
        return np.array(ds, copy=True)

    def vjp(self, handle, cotangent):
        return np.array(cotangent, copy=True), np.zeros((4, cotangent.shape[1]))

    def close(self, handle):
        pass


class _BadOutputKernel(_IdentityKernel):
    def __init__(self, stage, kind, levels=2):
        self.levels = levels
        self.stage = stage
        self.kind = kind
        self.closed = False

    def _bad(self, value):
        if self.kind == "shape":
            return np.zeros((value.shape[0], self.levels + 1), dtype=np.float64)
        if self.kind == "dtype":
            return value.astype(np.float32)
        if self.kind == "finite":
            result = np.array(value, copy=True)
            result[0, 0] = np.nan
            return result
        raise AssertionError(f"unknown fake fault {self.kind}")

    def forward(self, state, forcing, *, record=False):
        out = np.array(state, copy=True)
        if self.stage == "forward":
            out = self._bad(out)
        return out, object()

    def jvp(self, handle, state_direction, forcing_direction):
        out = np.array(state_direction, copy=True)
        return self._bad(out) if self.stage == "jvp" else out

    def vjp(self, handle, cotangent):
        gs = np.array(cotangent, copy=True)
        gf = np.zeros((4, self.levels), dtype=np.float64)
        if self.stage == "vjp":
            if self.kind == "forcing_shape":
                gf = np.zeros((4, self.levels + 1), dtype=np.float64)
            elif self.kind == "forcing_dtype":
                gf = gf.astype(np.float32)
            elif self.kind == "forcing_finite":
                gf[0, 0] = np.nan
            else:
                gs = self._bad(gs)
        return gs, gf

    def close(self, handle):
        self.closed = True


def _install_analytic_composition(monkeypatch):
    monkeypatch.setattr(verify_tool, "_zero_value", _zero_value)
    monkeypatch.setattr(verify_tool, "_zero_jvp", _zero_direction)
    monkeypatch.setattr(verify_tool, "_zero_vjp", _zero_direction)
    monkeypatch.setattr(verify_tool, "finish_value", _finish_value)
    monkeypatch.setattr(verify_tool, "finish_jvp", _finish_jvp)
    monkeypatch.setattr(verify_tool, "finish_vjp", _finish_vjp)


def test_identity_kernel_qc_mask_keeps_direct_old_state_term(monkeypatch):
    """For QC>threshold, rates and tangent vanish; VJP needs R_s + Z_y K_s."""
    _install_analytic_composition(monkeypatch)
    config = SimpleNamespace(dt=10.0)
    zero = SimpleNamespace(mode=2, threshold=.5)
    adapter = verify_tool.KernelFinish(_IdentityKernel(levels=2), config, zero)
    state = np.zeros((12, 2), dtype=np.float64)
    state[0] = [290.0, 291.0]
    state[1] = [.01, .02]
    state[2] = [.25, .75]  # first cell is zeroed; second is strictly above threshold
    forcing = np.ones((4, 2), dtype=np.float64)
    value, handle, raw_after = adapter.forward(state, forcing, record=True)
    np.testing.assert_allclose(value[1:4, 1], 0.0, rtol=0, atol=0)
    np.testing.assert_allclose(value[3], [-.025, 0.0], rtol=0, atol=1e-15)

    ds = np.zeros_like(state)
    ds[0] = [.1, -.2]
    ds[1] = [.001, -.002]
    ds[2] = [.03, -.04]
    df = np.zeros_like(forcing)
    tangent = adapter.jvp(state, raw_after, handle, ds, df)
    np.testing.assert_allclose(tangent[1:3, :], 0.0, rtol=0, atol=0)
    assert tangent[3, 1] == 0.0  # QC above threshold follows identity K and Z
    assert tangent[3, 0] == pytest.approx(-ds[2, 0] / config.dt)

    cotangent = np.zeros((5, 2), dtype=np.float64)
    cotangent[3] = [1.0, 1.0]  # isolate QC_RATE's direct -I/dt term
    gs, gf, direct = adapter.vjp(state, raw_after, handle, cotangent)
    assert direct[2, 1] == pytest.approx(-1.0 / config.dt)
    assert (gs-direct)[2, 1] == pytest.approx(1.0 / config.dt)
    assert gs[2, 1] == pytest.approx(0.0, abs=1e-15)
    assert gs[2, 0] == pytest.approx(-1.0 / config.dt)
    assert np.all(gf == 0.0)
    adapter.kernel.close(handle)


def test_positive_qc_threshold_tie_refuses_composed_jvp_and_vjp(monkeypatch):
    _install_analytic_composition(monkeypatch)
    config = SimpleNamespace(dt=10.0)
    zero = SimpleNamespace(mode=2, threshold=.5)
    adapter = verify_tool.KernelFinish(_IdentityKernel(levels=1), config, zero)
    state = np.zeros((12, 1), dtype=np.float64)
    state[0] = 290.0
    state[1] = .01
    state[2] = .5
    forcing = np.zeros((4, 1), dtype=np.float64)
    _, handle, after = adapter.forward(state, forcing, record=True)
    direction = np.zeros_like(state)
    cotangent = np.zeros((5, 1), dtype=np.float64)
    with pytest.raises(ValueError, match="discontinuous"):
        adapter.jvp(state, after, handle, direction, np.zeros_like(forcing))
    with pytest.raises(ValueError, match="discontinuous"):
        adapter.vjp(state, after, handle, cotangent)
    adapter.kernel.close(handle)


@pytest.mark.parametrize(("stage", "kind", "message"), [
    ("forward", "dtype", "binary64"),
    ("jvp", "shape", "shape"),
    ("vjp", "forcing_finite", "finite"),
])
def test_kernel_finish_refuses_bad_kernel_result(monkeypatch, stage, kind, message):
    _install_analytic_composition(monkeypatch)
    config = SimpleNamespace(dt=10.0)
    zero = SimpleNamespace(mode=2, threshold=.5)
    kernel = _BadOutputKernel(stage, kind, levels=2)
    adapter = verify_tool.KernelFinish(kernel, config, zero)
    state = np.zeros((12, 2), dtype=np.float64)
    state[0] = 290.0
    state[1] = .01
    state[2] = .75
    forcing = np.zeros((4, 2), dtype=np.float64)
    if stage == "forward":
        with pytest.raises((ValueError, TypeError), match=message):
            adapter.forward(state, forcing, record=True)
        assert kernel.closed
    else:
        _, handle, after = adapter.forward(state, forcing, record=True)
        if stage == "jvp":
            with pytest.raises((ValueError, TypeError), match=message):
                adapter.jvp(state, after, handle, np.zeros_like(state), np.zeros_like(forcing))
        else:
            cotangent = np.zeros((5, 2), dtype=np.float64)
            with pytest.raises((ValueError, TypeError), match=message):
                adapter.vjp(state, after, handle, cotangent)
        adapter.kernel.close(handle)


def test_load_case_refuses_f32_finish_handoff_mismatch(tmp_path):
    trace, namelist = tmp_path/"trace.hex", tmp_path/"namelist.input"
    _write_case(trace, namelist)
    case = verify_tool.load_case(trace, namelist, step=1, i=2, j=2, levels=1)
    assert case.f32_replay["raw_bit_mismatches"] == 0
    assert case.f32_replay["checked_handoff_pairs"] == 4

    _write_case(trace, namelist, bad_th_handoff=True)
    with pytest.raises(ValueError, match="MP/finish handoff differs"):
        verify_tool.load_case(trace, namelist, step=1, i=2, j=2, levels=1)


def test_load_case_refuses_trace_timestep_mismatch(tmp_path):
    trace, namelist = tmp_path/"trace.hex", tmp_path/"namelist.input"
    _write_case(trace, namelist)
    text = namelist.read_text(encoding="ascii")
    namelist.write_text(text.replace("time_step=20", "time_step=40"), encoding="ascii")
    with pytest.raises(ValueError, match="time steps differ"):
        verify_tool.load_case(trace, namelist, step=1, i=2, j=2, levels=1)


def test_load_case_refuses_truncated_native_column(tmp_path):
    trace, namelist = tmp_path/"trace.hex", tmp_path/"namelist.input"
    _write_case(trace, namelist)
    text = namelist.read_text(encoding="ascii")
    namelist.write_text(text.replace("e_vert=2", "e_vert=3"), encoding="ascii")
    with pytest.raises(ValueError, match="complete native mass-level column"):
        verify_tool.load_case(trace, namelist, step=1, i=2, j=2, levels=1)


@pytest.mark.parametrize("alias", ["same_path", "symlink"])
def test_verifier_refuses_output_alias_before_source_reads(tmp_path, monkeypatch, alias):
    trace, namelist, library = (tmp_path/"trace", tmp_path/"namelist", tmp_path/"lib")
    for path, data in ((trace, b"trace bytes"), (namelist, b"namelist bytes"),
                       (library, b"library bytes")):
        path.write_bytes(data)
    fake_module = SimpleNamespace(__file__=str(tmp_path/"fake_finish_module.py"))
    fake_module_path = Path(fake_module.__file__)
    fake_module_path.write_bytes(b"synthetic module pin")
    monkeypatch.setattr(verify_tool, "_api", lambda: fake_module)
    output = trace if alias == "same_path" else tmp_path/"trace_alias"
    if alias == "symlink":
        output.symlink_to(trace)
    args = SimpleNamespace(trace=trace, namelist=namelist, library=library, output=output)
    before = {p: p.read_bytes() for p in (trace, namelist, library, fake_module_path)}
    with pytest.raises(ValueError, match="output must be new and distinct"):
        verify_tool.verify(args)
    assert {p: p.read_bytes() for p in before} == before
    if alias == "symlink":
        assert output.is_symlink()
