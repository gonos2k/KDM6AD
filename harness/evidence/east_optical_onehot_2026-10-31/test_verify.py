"""Adversarial offline replay checks."""

import importlib.util
import json
import math
import re
import shutil
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("onehot_verify", HERE / "verify.py")
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


def test_mutated_parser_source_rejected(tmp_path):
    for name in ("verify.py", "test_verify.py", "README.md", "source_manifest.json"):
        shutil.copy2(HERE / name, tmp_path / name)
    with (tmp_path / "verify.py").open("a") as stream:
        stream.write("\n# mutated parser\n")
    with pytest.raises(ValueError, match="source hash: verify.py"):
        verify.verify_sources(tmp_path)


def test_product_alternate_rounding():
    # A one-ULP difference is portable; a much larger corruption is not.
    k, direction = 1.234567890123, 0.00045368468747598384
    product = k * direction
    k_layers = np.zeros(40)
    direction_layers = np.zeros(40)
    k_layers[39] = k
    direction_layers[39] = direction
    alternate_reduction = np.dot(k_layers, direction_layers)
    verify.check_product(k, direction, alternate_reduction, product)
    alternate_rounding = math.nextafter(float(alternate_reduction), math.inf)
    verify.check_product(k, direction, alternate_rounding, product)
    with pytest.raises(ValueError, match="product roundoff"):
        verify.check_product(k, direction, product + 1e-10, product)


def test_rehashed_corrupt_saved_product_rejected(tmp_path, monkeypatch):
    packet = tmp_path / "packet"
    shutil.copytree(HERE / "packet", packet)
    summary_path = packet / "summary.json"
    summary = json.loads(summary_path.read_text())
    summary["results"]["GG"]["0.0001"]["k_v"][0][0] += 1e-5
    summary_path.write_text(json.dumps(summary))
    manifest_path = packet / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"]["summary.json"] = verify.sha(summary_path)
    manifest_path.write_text(json.dumps(manifest))
    # Simulate accepting a newly authenticated, rehashed capture manifest.
    monkeypatch.setattr(verify, "P", packet)
    monkeypatch.setattr(verify, "PACKET_SHA", verify.sha(manifest_path))
    with pytest.raises(ValueError, match="product roundoff"):
        verify.main()


def test_rehashed_raw_total_does_not_match_saved_kma_bt(tmp_path, monkeypatch):
    packet = tmp_path / "packet"
    shutil.copytree(HERE / "packet", packet)
    name = "GG_0_plus/direct_radiance.txt"
    raw_path = packet / name
    raw = raw_path.read_text()
    pattern = r"(RADIANCE%TOTAL\s*=\s*\(\s*)([-+0-9.EeDd]+)"
    match = re.search(pattern, raw)
    assert match is not None
    changed_token = f"{float(match.group(2).replace('D', 'E')) * 1.01:.17E}"
    raw_path.write_text(raw[: match.start(2)] + changed_token + raw[match.end(2) :])
    manifest_path = packet / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"][name] = verify.sha(raw_path)
    manifest_path.write_text(json.dumps(manifest))
    monkeypatch.setattr(verify, "P", packet)
    monkeypatch.setattr(verify, "PACKET_SHA", verify.sha(manifest_path))
    with pytest.raises(ValueError, match="raw TOTAL to KMA BT differs"):
        verify.main()
