import hashlib
import ctypes as ct
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from harness.native_fp64_value_only_boundary import (
    BatchInput,
    IN_HEADER,
    REQUEST_MAGIC,
    REFERENCE_HEADER,
    REFERENCE_MAGIC,
    batch_to_fortran_fields,
    fortran_fields_to_batch,
    batch_xland_to_fortran,
    encode_batch_request,
    load_full_f64_reference,
    make_nonsquare_probe_case,
    make_dt0_roundtrip_case,
    float32_storage_roundtrip_probe,
    water_roundoff_bound,
    run_precision_case,
    _pack_field_major_fortran,
    _fp64_ad_signature,
    _call_fp64_ad,
    _call_with_attempt,
    FLOAT_PTR,
    DOUBLE_PTR,
    HANDLE_PTR,
    _fp_environment_roundoff_compatible,
    _persist_case_capture_metadata,
)


def _batch(batch=8, levels=3, *, dt=20.0):
    state = np.arange(12 * batch * levels, dtype=np.float64).reshape(12, batch, levels) / 100.0
    forcing = np.ones((4, batch, levels), dtype=np.float64)
    xland = np.array([1.0, 2.0] * (batch // 2), dtype=np.float64)
    return BatchInput(state, forcing, xland, dt, 10.0, 10.0, "test", "")


def test_fortran_field_and_xland_layout_roundtrip_nonsquare():
    im, kme, jme = 2, 3, 4
    batch = im * jme
    fields = np.empty((12, batch, kme), dtype=np.float32)
    for field in range(12):
        for b in range(batch):
            for k in range(kme):
                fields[field, b, k] = field * 10000 + b * 100 + k
    packed = batch_to_fortran_fields(fields, im=im, kme=kme, jme=jme, dtype=np.float32)
    assert all(value.flags.f_contiguous for value in packed)
    restored = fortran_fields_to_batch(packed, im=im, kme=kme, jme=jme, dtype=np.float32)
    np.testing.assert_array_equal(restored, fields)
    xland = np.array([1, 2, 2, 1, 1, 2, 2, 1], dtype=np.float32)
    xland_f = batch_xland_to_fortran(xland, im=im, jme=jme)
    for i in range(im):
        for j in range(jme):
            assert xland_f[i, j] == xland[i * jme + j]


def test_fp64_ad_reference_uses_field_major_packed_fortran_buffers():
    im, kme, jme = 2, 3, 4
    batch = im * jme
    fields = np.empty((12, batch, kme), dtype=np.float64)
    for n in range(12):
        for b in range(batch):
            for k in range(kme):
                fields[n, b, k] = n * 10000 + b * 100 + k
    packed_fields = batch_to_fortran_fields(fields, im=im, kme=kme, jme=jme, dtype=np.float64)
    packed = _pack_field_major_fortran(packed_fields)
    assert packed.shape == (12 * im * kme * jme,)
    for n in range(12):
        decoded = packed[n * batch * kme:(n + 1) * batch * kme]
        decoded = decoded.reshape((im, kme, jme), order="F")
        restored = fortran_fields_to_batch([np.array(decoded, order="F")],
                                            im=im, kme=kme, jme=jme, dtype=np.float64)[0]
        np.testing.assert_array_equal(restored, fields[n])


def test_fp64_ad_c_header_signature_two_packed_inputs_and_all_arguments():
    im, kme, jme = 2, 3, 4
    batch = im * jme
    state = np.arange(12 * batch * kme, dtype=np.float64).reshape(12, batch, kme)
    forcing = (1000.0 + np.arange(4 * batch * kme, dtype=np.float64)).reshape(4, batch, kme)
    xland_flat = np.array([1, 2, 1, 2, 2, 1, 2, 1], dtype=np.float32)
    xland = np.empty((im, jme), dtype=np.float32, order="F")
    for i in range(im):
        for j in range(jme):
            xland[i, j] = xland_flat[i * jme + j]
    signature = _fp64_ad_signature()
    assert signature == [DOUBLE_PTR, DOUBLE_PTR, ct.c_int, ct.c_int, ct.c_int,
                         ct.c_double, ct.c_int, DOUBLE_PTR, HANDLE_PTR,
                         FLOAT_PTR, ct.c_double, ct.c_double]
    seen = {}

    def reference(state_ptr, forcing_ptr, got_im, got_kme, got_jme, dt, value_only,
                  output_ptr, handle_ptr, xland_ptr, ncmin_land, ncmin_sea):
        assert (got_im, got_kme, got_jme, dt, value_only) == (im, kme, jme, 20.0, 1)
        nstate, nforcing = 12 * im * kme * jme, 4 * im * kme * jme
        state_values = np.ctypeslib.as_array(state_ptr, shape=(nstate,)).copy()
        forcing_values = np.ctypeslib.as_array(forcing_ptr, shape=(nforcing,)).copy()
        xland_values = np.ctypeslib.as_array(xland_ptr, shape=(im * jme,)).copy()
        seen.update(state=state_values, forcing=forcing_values, xland=xland_values,
                    ncmin_land=ncmin_land, ncmin_sea=ncmin_sea)
        np.ctypeslib.as_array(output_ptr, shape=(nstate,))[:] = state_values
        handle_ptr[0] = None
        return 0

    callback = ct.CFUNCTYPE(ct.c_int, *signature)(reference)
    fake_lib = SimpleNamespace(kdm6_step_ad_c=callback)
    rc, handle, output = _call_fp64_ad(fake_lib, state, forcing, xland,
                                       im=im, kme=kme, jme=jme, dt=20.0,
                                       ncmin_land=10.0, ncmin_sea=20.0)
    assert rc == 0 and handle is None
    np.testing.assert_array_equal(seen["state"], _pack_field_major_fortran(
        batch_to_fortran_fields(state, im=im, kme=kme, jme=jme, dtype=np.float64)))
    np.testing.assert_array_equal(seen["forcing"], _pack_field_major_fortran(
        batch_to_fortran_fields(forcing, im=im, kme=kme, jme=jme, dtype=np.float64)))
    np.testing.assert_array_equal(seen["xland"], xland.ravel(order="F"))
    assert seen["ncmin_land"] == 10.0 and seen["ncmin_sea"] == 20.0
    np.testing.assert_array_equal(output, state)


def test_attempt_ledger_accepts_tuple_result_without_native_call(tmp_path):
    im, kme, jme = 2, 3, 4
    case = _batch(batch=im * jme, levels=kme)
    dso = tmp_path / "pinned-placeholder.dylib"
    dso.write_bytes(b"fixture only; no library loaded")
    attempt = tmp_path / "attempts.jsonl"
    attempt.write_bytes(b"")
    xland = np.empty((im, jme), dtype=np.float32, order="F")
    xland[:] = np.array([1.0, 2.0, 1.0, 2.0, 2.0, 1.0, 2.0, 1.0], dtype=np.float32).reshape(im, jme)

    def mock_ad(state_ptr, forcing_ptr, got_im, got_kme, got_jme, dt, value_only,
                output_ptr, handle_ptr, xland_ptr, ncmin_land, ncmin_sea):
        assert (got_im, got_kme, got_jme, dt, value_only) == (im, kme, jme, 20.0, 1)
        n = 12 * im * kme * jme
        np.ctypeslib.as_array(output_ptr, shape=(n,))[:] = np.ctypeslib.as_array(state_ptr, shape=(n,))
        handle_ptr[0] = None
        return 0

    callback = ct.CFUNCTYPE(ct.c_int, *_fp64_ad_signature())(mock_ad)
    mock_lib = SimpleNamespace(kdm6_step_ad_c=callback)
    result = _call_with_attempt(
        attempt, case, "tuple_value_result", dso, "kdm6_step_ad_c",
        lambda: _call_fp64_ad(mock_lib, case.state, case.forcing, xland,
                              im=im, kme=kme, jme=jme, dt=20.0,
                              ncmin_land=case.ncmin_land, ncmin_sea=case.ncmin_sea),
        dt=20.0,
    )
    assert result[0] == 0 and result[1] is None
    np.testing.assert_array_equal(result[2], case.state)
    lines = [json.loads(line) for line in attempt.read_text().splitlines()]
    assert [line["event"] for line in lines] == ["C_API_CALL_START", "C_API_CALL_COMPLETE"]
    assert lines[-1]["KDM6_forward_completed"] is True


def test_batch_request_encoding_preserves_field_order_and_metadata():
    case = _batch()
    payload = encode_batch_request(case)
    magic, version, batch, levels, dt, ncmin_land, ncmin_sea = IN_HEADER.unpack_from(payload)
    assert (magic, version, batch, levels, dt, ncmin_land, ncmin_sea) == (
        REQUEST_MAGIC, 1, 8, 3, 20.0, 10.0, 10.0
    )
    offset = IN_HEADER.size
    decoded = np.frombuffer(payload, dtype="<f8", offset=offset)
    np.testing.assert_array_equal(decoded[: case.state.size], case.state.ravel())
    np.testing.assert_array_equal(decoded[case.state.size : case.state.size + case.forcing.size], case.forcing.ravel())
    np.testing.assert_array_equal(decoded[-8:], case.xland)


def test_nonsquare_probe_selects_both_native_land_sea_classes_and_binds_bytes():
    source = _batch(batch=12, levels=3)
    source = source._replace(xland=np.array([1] * 6 + [2] * 6, dtype=np.float64))
    probe = make_nonsquare_probe_case(source)
    assert probe.state.shape == (12, 8, 3)
    assert probe.xland.tolist() == [1, 2, 1, 2, 1, 2, 1, 2]
    assert hashlib.sha256(encode_batch_request(probe)).hexdigest() == probe.input_sha256


def test_dt0_roundtrip_fixture_contains_subnormals_and_signed_zero():
    probe = make_dt0_roundtrip_case()
    assert probe.dt == 0.0 and probe.state.shape == (12, 8, 3)
    result = float32_storage_roundtrip_probe()
    assert result["all_bits_preserved"]
    assert result["subnormal_bits_preserved"]
    assert result["signed_zero_preserved"]


@pytest.mark.parametrize("fpcr, compatible", [((1 << 64) - 1, False), (0, True),
                                             (1 << 22, False), (1 << 24, False)])
def test_direct_runtime_reference_format_binds_widened_inputs_and_fpcr(tmp_path, fpcr, compatible):
    case = _batch(batch=8, levels=3)
    input_sha = hashlib.sha256(encode_batch_request(case)).hexdigest()
    case = case._replace(input_sha256=input_sha)
    state32w = case.state.astype(np.float32).astype(np.float64)
    force32w = case.forcing.astype(np.float32).astype(np.float64)
    x32w = case.xland.astype(np.float32).astype(np.float64)
    state_out = state32w + 0.125
    precip = np.full((3, 8), 0.25, dtype=np.float64)
    rhog = np.full((8, 3), 1.0, dtype=np.float64)
    header = REFERENCE_HEADER.pack(REFERENCE_MAGIC, 1, 8, 3, 20.0, 10.0, 10.0,
                                  input_sha.encode("ascii"), fpcr, fpcr, 0, 0, 0)
    payload = np.concatenate((state32w.ravel(), force32w.ravel(), x32w.ravel(),
                              state_out.ravel(), precip.ravel(), rhog.ravel())).astype("<f8").tobytes()
    path = tmp_path / "reference.bin"
    path.write_bytes(header + payload)
    ref = load_full_f64_reference(path, case)
    np.testing.assert_array_equal(ref.widened_state, state32w)
    np.testing.assert_array_equal(ref.widened_forcing, force32w)
    np.testing.assert_array_equal(ref.state_out, state_out)
    assert ref.fp_env_before["raw_fpcr_available"] is (fpcr != (1 << 64) - 1)
    assert _fp_environment_roundoff_compatible(ref.fp_env_before) is compatible
    assert not _fp_environment_roundoff_compatible({**ref.fp_env_before, "fe_round_to_nearest": False})


@pytest.mark.parametrize("field", ["fe_round_to_nearest", "raw_fpcr_available",
                                   "fpcr_rounding_mode_bits", "fpcr_fz_bit24"])
@pytest.mark.parametrize("unknown", [None, "missing"])
def test_roundoff_environment_requires_each_measured_control(field, unknown):
    snapshot = {"fe_round_to_nearest": True, "raw_fpcr_available": True,
                "fpcr_rounding_mode_bits": 0, "fpcr_fz_bit24": False}
    if unknown == "missing":
        snapshot.pop(field)
    else:
        snapshot[field] = unknown
    assert not _fp_environment_roundoff_compatible(snapshot)


def test_roundoff_environment_rejects_conflicting_probe_evidence():
    snapshot = {"fe_round_to_nearest": True, "raw_fpcr_available": True,
                "fpcr_rounding_mode_bits": 0, "fpcr_fz_bit24": False}
    assert _fp_environment_roundoff_compatible(snapshot)
    assert not _fp_environment_roundoff_compatible({**snapshot, "fpcr_round_to_nearest": False})
    assert not _fp_environment_roundoff_compatible({**snapshot, "fpcr_rounding_mode_bits": False})
    assert not _fp_environment_roundoff_compatible({**snapshot, "float32_roundtrip": {}})
    assert not _fp_environment_roundoff_compatible({**snapshot, "float32_roundtrip": []})
    assert not _fp_environment_roundoff_compatible(
        {**snapshot, "float32_roundtrip": {"all_bits_preserved": False}})


def test_case_capture_metadata_is_durable_and_receipt_bound(tmp_path):
    case = _batch(batch=8, levels=3)
    attempt = tmp_path / "attempts.jsonl"
    attempt.write_bytes(b"")
    capture_dir = tmp_path / "captures"
    capture_dir.mkdir()
    capture = {"schema": "kdm6.native_fp64_value_only_case_capture.v1",
               "block_id": case.block_id, "request_sha256": "1" * 64,
               "fp_environment": {"before": {"fe_round_to_nearest": True}},
               "forward_output_artifacts": [], "refusal_probes": {},
               "capture_complete_before_comparison": True}
    receipt = _persist_case_capture_metadata(capture_dir, case, attempt, capture)
    target = capture_dir / receipt["path"]
    assert hashlib.sha256(target.read_bytes()).hexdigest() == receipt["sha256"]
    assert json.loads(target.read_text()) == capture
    assert json.loads(attempt.read_text().splitlines()[-1])["event"] == "CASE_CAPTURE_METADATA_SAVED"


def test_storage_half_ulp_bound_is_not_a_physical_closure_claim():
    case = _batch(batch=8, levels=3)
    ref_state = np.abs(case.state) + 0.001
    ref_precip = np.ones((3, 8), dtype=np.float64) / 7.0
    forcing = case.forcing.copy()
    forcing[0] *= 0.8
    forcing[3] *= 125.0
    report = water_roundoff_bound(ref_state, ref_precip, forcing)
    cast_state = ref_state.astype(np.float32).astype(np.float64)
    cast_precip = ref_precip.astype(np.float32).astype(np.float64)
    weights = forcing[0] * forcing[3]
    error = sum(float(np.sum(weights * np.abs(cast_state[row] - ref_state[row])))
                for row in (1, 2, 3, 4, 5, 6))
    error += float(np.sum(np.abs(cast_precip - ref_precip)))
    assert error <= report["combined_output_storage_roundoff_bound_kg_m2"]
    assert "not physical closure" in report["scope"]


def test_boundary_harness_requires_root_approval_before_any_dso_access():
    case = _batch()
    with pytest.raises(PermissionError, match="explicit root approval"):
        run_precision_case(case, Path("/missing/legacy"), Path("/missing/new"),
                           new_dso_sha256="0" * 64,
                           full_f64_reference=None, im=1, kme=3, jme=8)
