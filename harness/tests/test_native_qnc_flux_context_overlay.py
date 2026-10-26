from __future__ import annotations

import hashlib
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))
import native_qnc_flux_context_overlay as overlay  # noqa: E402


def _fixture(path: Path) -> bytes:
    groups = (
        overlay._ADVECT_USE_ANCHOR,
        overlay._STATE_USE_ANCHOR,
        overlay._PD_CALL,
        overlay._GENERIC_CALL,
    )
    text = "\n\n".join("\n".join(group) for group in groups) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text.encode("utf-8")


def test_public_pin_is_saved_v3_module_em_f90():
    assert overlay.SOURCE_RELATIVE_PATH == "dyn_em/module_em.f90"
    assert overlay.BASE_SOURCE_SHA256 == "53207a03dba5b3a42edb43891368f09318a59d44ced480f8ef982184a9e0034e"


def test_default_plan_is_read_only_and_context_brackets_only_two_advect_sites(tmp_path, monkeypatch):
    source = tmp_path / "source/dyn_em/module_em.f90"
    original = _fixture(source)
    monkeypatch.setattr(overlay, "BASE_SOURCE_SHA256", hashlib.sha256(original).hexdigest())

    report = overlay.build_overlay_plan(source)
    assert report["status"] == "ready"
    assert source.read_bytes() == original

    output = tmp_path / "overlay/module_em.f90"
    applied = overlay.apply_overlay(source, output_path=output)
    assert applied["status"] == "applied"
    updated = output.read_text(encoding="utf-8")
    assert updated.count("CALL qnc_flux_trace_set_context(im, P_QNC, rk_step, dt_step, moist_step)") == 2
    assert updated.count("CALL qnc_flux_trace_set_context(0, P_QNC, 0, 0.0, .TRUE.)") == 2
    pd = updated.index("CALL advect_scalar_pd")
    generic = updated.index("CALL advect_scalar     ")
    setter = "CALL qnc_flux_trace_set_context(im, P_QNC, rk_step, dt_step, moist_step)"
    reset = "CALL qnc_flux_trace_set_context(0, P_QNC, 0, 0.0, .TRUE.)"
    pd_set = updated.rfind(setter, 0, pd)
    pd_reset = updated.index(reset, pd)
    generic_set = updated.rfind(setter, 0, generic)
    generic_reset = updated.index(reset, generic)
    assert pd_set < pd < pd_reset < generic_set < generic < generic_reset
    assert "USE module_state_description, ONLY: P_QNC" in updated
    assert "module_em.f90" not in updated
    assert source.read_bytes() == original


@pytest.mark.parametrize("mutate", ("missing_pd", "duplicate_generic"))
def test_ambiguous_target_call_refuses_without_output(tmp_path, monkeypatch, mutate):
    source = tmp_path / "source/dyn_em/module_em.f90"
    original = _fixture(source).decode("utf-8")
    if mutate == "missing_pd":
        changed = original.replace("\n".join(overlay._PD_CALL), "", 1)
    else:
        block = "\n".join(overlay._GENERIC_CALL)
        changed = original.replace(block, block + "\n" + block, 1)
    source.write_text(changed, encoding="utf-8")
    monkeypatch.setattr(overlay, "BASE_SOURCE_SHA256", hashlib.sha256(changed.encode()).hexdigest())
    output = tmp_path / "overlay/module_em.f90"
    report = overlay.apply_overlay(source, output_path=output)
    assert report["status"] == "blocked"
    assert not output.exists()
    assert source.read_text(encoding="utf-8") == changed
