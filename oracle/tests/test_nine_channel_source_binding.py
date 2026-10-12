"""Synthetic checks for PR418 analysis source provenance, without RTTOV/H/M."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
DRIVER_PATH = ROOT / "harness/evidence/pr418_nine_channels_2026-10-12/run_case_analysis_nine.py"
SPEC = importlib.util.spec_from_file_location("pr418_source_binding_driver", DRIVER_PATH)
driver = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(driver)


class _FakeCapture:
    def __init__(self, on_run=None):
        self.on_run = on_run
        self.calls = 0

    def _source_snapshot(self):
        return {"capture_stub": "unchanged"}

    def run_capture(self, **kwargs):
        self.calls += 1
        if self.on_run is not None:
            self.on_run()
        return {"status": "RETURNED_DIAGNOSTIC_ONLY"}


class _FakePool:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _FakeContext:
    def Pool(self, _workers):
        return _FakePool()


def _setup(monkeypatch, tmp_path, *, build_mutation=None, run_mutation=None):
    template = tmp_path / "template"
    template.mkdir()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{}\n")
    npz_path = tmp_path / "intake.npz"
    npz_path.write_bytes(b"synthetic intake")

    capture_source = tmp_path / "capture_tq_state_capture.py"
    capture_source.write_text("capture stub\n")
    geometry_reader = tmp_path / "native_reader.py"
    geometry_reader.write_text("geometry reader v1\n")
    coefficient = tmp_path / "coef.dat"
    coefficient.write_text("coefficient fixture\n")
    executable = tmp_path / "rttov_test.exe"
    executable.write_text("executable fixture\n")

    def prepare_fixture(_source, out, _arrays):
        relpaths = (
            "in/profiles/001/atm/p.txt", "in/profiles/001/atm/p_half.txt",
            "in/profiles/001/atm/t.txt", "in/profiles/001/atm/q.txt",
            "in/channels.txt", "in/profiles/001/atm/o3.txt",
            "in/profiles/001/atm/co2.txt", "in/profiles/001/atm/simple_cloud.txt",
            "in/profiles/001/atm/hydro.txt", "in/profiles/001/atm/hydro_frac.txt",
            "in/profiles/001/sfc/01/skin.txt", "out/rttov_test.txt",
            "out/run.sh", "out/env.sh",
        )
        for relpath in relpaths:
            path = out / relpath
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(relpath + "\n")
        return {
            "ami_coefficient": {"path": str(coefficient)},
            "rttov_executable": {"path": str(executable)},
        }

    legacy = SimpleNamespace(
        TEMPLATE_FIXTURE=template,
        CAPTURE_HELPER=capture_source,
        NATIVE_READER=geometry_reader,
        _prepare_fixture_copy=prepare_fixture,
    )
    intake = SimpleNamespace(
        load_bound_intake=lambda *_args: ({"case_id": "synthetic-source-guard"}, {})
    )

    def load_module(path, _name):
        return legacy if Path(path) == driver.LEGACY_DRIVER else intake

    capture_callback = (
        None if run_mutation is None else lambda: run_mutation(geometry_reader)
    )
    capture = _FakeCapture(on_run=capture_callback)
    monkeypatch.setattr(driver, "load_module", load_module)
    monkeypatch.setattr(driver, "_prepare_capture_module", lambda: capture)
    monkeypatch.setattr(driver.mp, "get_context", lambda _method: _FakeContext())
    monkeypatch.setattr(
        driver,
        "_audit_initial_objectives_selected",
        lambda *_args, **_kwargs: {"status": "CROSSCHECKED"},
    )

    def build_inputs(*_args, **_kwargs):
        # Reading this temporary file stands in for consuming ami_geometry.
        consumed = geometry_reader.read_text()
        if build_mutation is not None:
            build_mutation(geometry_reader)
        return {
            "xb": None, "forcing": None, "y_bt": None, "y_rq": None,
            "xland": None, "clear_cfg": None, "rttov_cfg": None,
            "window_config": None, "run_manifest": {},
            "geometry_reader_content_consumed": consumed,
        }

    monkeypatch.setattr(driver, "build_inputs", build_inputs)
    return {
        "template": template,
        "manifest": manifest_path,
        "npz": npz_path,
        "reader": geometry_reader,
        "capture": capture,
        "execute": lambda out: driver.execute(
            manifest_path, npz_path, out, template, channels=tuple(range(8, 17))
        ),
    }


def test_geometry_reader_is_in_analysis_source_bindings(monkeypatch, tmp_path):
    probe = _setup(monkeypatch, tmp_path)
    result = probe["execute"](tmp_path / "output")

    reader_key = str(probe["reader"].resolve())
    preflight = json.loads((tmp_path / "output/PREFLIGHT.json").read_text())
    assert reader_key in preflight["source_bindings"]
    assert reader_key in result["case_sources"]
    assert result["status"] == "RETURNED_CASE_DIAGNOSTIC"


def test_geometry_reader_change_after_use_is_rejected_before_capture(
        monkeypatch, tmp_path):
    def mutate(reader):
        reader.write_text("geometry reader changed after use\n")

    probe = _setup(monkeypatch, tmp_path, build_mutation=mutate)
    out = tmp_path / "output"

    with pytest.raises(ValueError, match="case sources changed during preparation"):
        probe["execute"](out)

    assert probe["capture"].calls == 0
    assert not (out / "RUN_STARTED_ONCE.json").exists()
    assert not (out / "PREFLIGHT.json").exists()


def test_geometry_reader_change_during_capture_fails_final_source_audit(
        monkeypatch, tmp_path):
    def mutate(reader):
        reader.write_text("geometry reader changed during capture\n")

    probe = _setup(monkeypatch, tmp_path, run_mutation=mutate)
    out = tmp_path / "output"
    result = probe["execute"](out)

    reader_key = str(probe["reader"].resolve())
    assert result["status"] == "FAILED_CASE_AUDIT"
    assert result["case_sources"][reader_key] != driver.sha(probe["reader"])
    assert probe["capture"].calls == 1
