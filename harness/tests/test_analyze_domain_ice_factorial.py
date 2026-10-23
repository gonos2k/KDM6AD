import hashlib
import json
from fractions import Fraction

import numpy as np
import pytest

from harness.analyze_domain_ice_factorial import admit_chunk, columns, distribution
from harness.ice_factorial_batch import OUT_HEADER, pack_request
from harness.run_domain_ice_factorial import GuardError, _expected_receipt


def test_columns_preserves_column_field_level_identity_and_exact_rounded_products():
    values = np.array(
        [[[1e16, 1.0, -1e16], [2.0, 3.0, 4.0]], [[2.0, 3.0, 4.0], [0.25, 0.5, 1.0]]]
    )
    weights = np.array([[1.0, 1.0, 1.0], [2.0, 3.0, 5.0]])
    actual = columns(values, weights)
    expected = []
    for b in range(2):
        terms = [
            Fraction.from_float(float(values[field, b, k]) * float(weights[b, k]))
            for field in range(2)
            for k in range(3)
        ]
        expected.append(float(sum(terms, Fraction())))
    np.testing.assert_array_equal(actual, expected)
    assert actual[0] == 10.0


def test_two_dimensional_column_sum_never_broadcasts_another_columns_profile():
    with pytest.raises(ValueError):
        columns(np.ones((1, 3)), np.ones((2, 3)))
    np.testing.assert_array_equal(
        columns(np.array([[1e16, 1.0, -1e16]]), np.ones((1, 3))), [1.0]
    )


def test_spatial_statistic_is_unweighted_fsum_and_rank_not_interpolated_quantile():
    stat = distribution([6.0, 0.0, 4.0, 2.0])
    assert stat["unweighted_column_mean"] == 3.0
    assert stat["rank_p50"] == 2.0
    assert stat["min"] == 0.0 and stat["max"] == 6.0
    assert distribution([1e16, 1.0, -1e16])["unweighted_column_mean"] == 1 / 3


@pytest.mark.parametrize("value", [[], [np.inf], [np.nan]])
def test_invalid_statistics_are_refused(value):
    with pytest.raises(ValueError):
        distribution(value)


def admitted_files(tmp_path):
    b, levels, start = 512, 39, 0
    state = np.zeros((12, b, levels), dtype=np.float64)
    forcing = np.ones((4, b, levels), dtype=np.float64)
    xland = np.resize(np.array([1.0, 2.0]), b)
    flat = np.arange(start, start + b, dtype=np.int32)
    source = tmp_path / "chunk.npz"
    np.savez(
        source,
        state=state,
        forcing=forcing,
        xland=xland,
        flat_indices=flat,
        i=flat % 234,
        j=flat // 234,
    )
    source_bytes = source.read_bytes()
    tool = tmp_path / "tool"
    tool.write_bytes(b"tool")
    task = {
        "index": 0,
        "start": start,
        "end": start + b,
        "B": b,
        "L": levels,
        "source_path": str(source),
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "manifest_sha256": "a" * 64,
        "tool_sha256": hashlib.sha256(tool.read_bytes()).hexdigest(),
        "mode": "raw_cap",
        "dt_seconds": 20.0,
        "ncmin_land": 10.0,
        "ncmin_sea": 10.0,
    }
    request = pack_request(state, forcing, xland, 20.0, 10.0, 10.0)
    run = tmp_path / "run"
    run.mkdir()
    stem = "chunk-00000"
    request_path = run / f"{stem}.request.bin"
    request_path.write_bytes(request)
    state_bytes, forcing_bytes = state.tobytes(), forcing.tobytes()
    response = (
        OUT_HEADER.pack(b"K6BATO1\0", 1, b, levels)
        + state_bytes
        + forcing_bytes
        + state_bytes
        + bytes(3 * b * 8)
    )
    response_path = run / f"{stem}.response.bin"
    response_path.write_bytes(response)
    receipt_path = run / f"{stem}.receipt.json"
    gate = _expected_receipt(
        task,
        hashlib.sha256(request).hexdigest(),
        hashlib.sha256(state_bytes + forcing_bytes + xland.tobytes()).hexdigest(),
    )
    receipt = dict(
        gate,
        status="complete",
        response_sha256=hashlib.sha256(response).hexdigest(),
        tool_sha256_after=task["tool_sha256"],
        resources={
            "wall": 0.1,
            "user": 0.05,
            "system": 0.02,
            "wall_seconds_measured": 0.1,
            "peak_rss_bytes": 1024,
        },
    )
    receipt_path.write_text(json.dumps(receipt))
    return task, receipt_path, request_path, response_path, receipt_path


def test_admission_checks_full_receipt_gate_and_returns_verified_echo(tmp_path):
    task, receipt, _, _, _ = admitted_files(tmp_path)
    decoded = admit_chunk(task, receipt)
    assert decoded["B"] == 512 and decoded["L"] == 39


def test_admission_rejects_receipt_gate_mismatch(tmp_path):
    task, _, _, _, receipt_path = admitted_files(tmp_path)
    receipt = json.loads(receipt_path.read_text())
    receipt["manifest_sha256"] = "f" * 64
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(
        GuardError, match="receipt admission mismatch for manifest_sha256"
    ):
        admit_chunk(task, receipt_path)


def test_admission_rejects_saved_request_that_differs_from_verified_source(tmp_path):
    task, receipt, request_path, _, _ = admitted_files(tmp_path)
    request_path.write_bytes(request_path.read_bytes() + b"bad")
    with pytest.raises(GuardError, match="saved request differs"):
        admit_chunk(task, receipt)


def test_admission_rejects_response_echo_even_when_response_hash_is_updated(tmp_path):
    task, receipt_path, _, response_path, _ = admitted_files(tmp_path)
    raw = bytearray(response_path.read_bytes())
    header = OUT_HEADER.size
    raw[header] ^= 1
    response_path.write_bytes(raw)
    receipt = json.loads(receipt_path.read_text())
    receipt["response_sha256"] = hashlib.sha256(raw).hexdigest()
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(GuardError, match="response echo differs"):
        admit_chunk(task, receipt_path)


def test_admission_rejects_incomplete_receipt_before_using_arrays(tmp_path):
    task, receipt_path, _, _, _ = admitted_files(tmp_path)
    receipt = json.loads(receipt_path.read_text())
    receipt["status"] = "failed"
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(GuardError, match="not complete"):
        admit_chunk(task, receipt_path)
