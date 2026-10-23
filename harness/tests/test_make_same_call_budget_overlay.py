"""Fail-closed checks for the private fp64 runtime trace overlay generator."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

from harness import make_same_call_budget_overlay as generator


def source_runtime():
    return Path(__file__).parents[2] / "libtorch/src/runtime.cpp"


def test_generator_instruments_pinned_runtime_only_and_records_its_hash(tmp_path, monkeypatch):
    source = source_runtime()
    before = generator.sha256(source)
    assert before == generator.EXPECTED_RUNTIME_SHA256
    out = tmp_path / "overlay"
    monkeypatch.setattr(sys, "argv", [
        "make_same_call_budget_overlay.py", "--libtorch-source", str(source.parents[1]),
        "--output", str(out),
    ])
    assert generator.main() == 0
    generated = out / "runtime.cpp"
    manifest = json.loads((out / "source_sha256.json").read_text())
    text = generated.read_text()
    assert manifest["input_runtime_sha256"] == before
    assert manifest["overlay_runtime_sha256"] == generator.sha256(generated)
    assert manifest["instrumented_stages"] == ["entry", "pre_sed", "post_sed", "post_micro", "exit"]
    for stage in manifest["instrumented_stages"]:
        assert text.count(f'trace_same_call_water("{stage}"') == 1
    assert "record=level" in text and "DEN_kg_m3=" in text and "DELZ_m=" in text
    assert "waters[n]->scalar_type() == torch::kFloat64" in text
    assert "f.den.scalar_type() == torch::kFloat64" in text
    assert generator.sha256(source) == before  # source tree was not edited


def test_generator_refuses_duplicate_or_missing_source_anchors():
    source = source_runtime().read_text()
    with pytest.raises(RuntimeError, match="already contains"):
        generator.instrument(source + "\n" + generator.MARKER)
    with pytest.raises(RuntimeError, match="entry trace call anchor"):
        generator.instrument(source.replace("auto cur = cs;", "auto current = cs;", 1))


def test_cli_fails_closed_when_runtime_source_hash_is_unreviewed(tmp_path, monkeypatch):
    stale = tmp_path / "stale-lib"
    (stale / "src").mkdir(parents=True)
    (stale / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.20)\n")
    (stale / "src/runtime.cpp").write_text("// changed source\n")
    output = tmp_path / "out"
    monkeypatch.setattr(sys, "argv", [
        "make_same_call_budget_overlay.py", "--libtorch-source", str(stale),
        "--output", str(output),
    ])
    with pytest.raises(SystemExit) as err:
        generator.main()
    assert err.value.code == 2
    assert not output.exists()


def test_replace_once_requires_one_and_only_one_anchor():
    with pytest.raises(RuntimeError, match="found 0"):
        generator.replace_once("none", "anchor", "replacement", "test")
    with pytest.raises(RuntimeError, match="found 2"):
        generator.replace_once("anchor anchor", "anchor", "replacement", "test")
