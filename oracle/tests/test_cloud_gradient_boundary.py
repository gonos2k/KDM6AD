"""Portable checks for the bounded all-sky quality diagnosis."""
from __future__ import annotations

from scripts.diagnose_cloud_gradient_boundary import decode_quality_bits, _bt_resolution


def test_quality_bit15_is_decoded_without_changing_mask_semantics():
    report = decode_quality_bits([[0, 32768, 32769]])
    assert report["bit15_value"] == 32768
    assert report["delta_eddington_extinction_limit"] == [32768, 32769]
    assert report["unique_values"] == [0, 32768, 32769]


def test_bt_resolution_reads_emitted_block_quantum(tmp_path):
    path = tmp_path / "radiance.txt"
    path.write_text("RADIANCE%BT = ( 300.123 0.12345 )\n")
    report = _bt_resolution(path)
    assert report["bt_values"] == 2
    assert report["bt_quantum_upper_bound"] == 1.0e-3
