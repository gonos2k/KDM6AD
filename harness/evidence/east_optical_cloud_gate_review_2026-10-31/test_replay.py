"""Checks for the saved cloud-fraction interpretation and its replay gate."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


PACKET = Path(__file__).resolve().parent
REPO = PACKET.parents[2]
WITNESS = PACKET.parent / "east_optical_witness_2026-10-31/witness.json"


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, PACKET / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def witness() -> dict:
    return json.loads(WITNESS.read_text())


def first_cloudy_row(data: dict) -> tuple[dict, int]:
    for profile in data["profiles"]:
        fractions = profile["optics"][1]["hydro_frac.txt"]["values"]
        for row in range(27, 66):
            if fractions[row] > 0:
                return profile, row
    raise AssertionError("fixture has no cloudy row")


def test_official_replay() -> None:
    run = subprocess.run(
        [sys.executable, str(PACKET / "replay.py")],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(run.stdout.splitlines()[-1])
    assert result["status"] == "REPLAY_PASSED"
    assert result["model_calls"] == 0


def test_cloudy_diameter_one_ulp_and_loss_denominators() -> None:
    result = load("analyze").analyze(witness())
    cloudy = result["strata"]["cloud_fraction_positive"]
    clear = result["strata"]["cloud_fraction_zero"]
    assert (cloudy["ice_changed"], clear["ice_changed"]) == (42, 40)
    assert (cloudy["diameter_changed"], clear["diameter_changed"]) == (1, 29)
    assert (
        cloudy["diameter_bound_category_changed"],
        clear["diameter_bound_category_changed"],
    ) == (0, 29)
    (event,) = result["cloudy_diameter_changes"]
    assert event["native_ijk"] == [234, 52, 25]
    assert event["delta_um"] == event["guard_float64_ulp_um"]
    assert event["same_float32"] is True
    assert result["bt_delta_K"]["negative"] == 70
    assert result["huber"]["fixed_m0_denominator"] == 377342
    assert result["huber"]["local_70_cell_mean_delta"] > 1.7


def test_reject_cloud_fraction_change() -> None:
    data = witness()
    profile, row = first_cloudy_row(data)
    profile["optics"][2]["hydro_frac.txt"]["values"][row] = 0.0
    with pytest.raises(ValueError, match="cloud fraction changed"):
        load("analyze").analyze(data)


def test_reject_cloudy_ratio_zero_denominator() -> None:
    data = witness()
    profile, row = first_cloudy_row(data)
    profile["optics"][1]["hydro.txt"]["values"][row] = 0.0
    with pytest.raises(ValueError, match="zero guard denominator"):
        load("analyze").analyze(data)


def test_reject_huber_mismatch() -> None:
    data = witness()
    data["profiles"][0]["huber"][2][0] += 1.0
    with pytest.raises(ValueError, match="Huber losses differ"):
        load("analyze").analyze(data)


def test_changed_source_pin_rejected(tmp_path: Path) -> None:
    replay = load("replay")
    source = PACKET / "analyze.py"
    copied = tmp_path / "analyze.py"
    copied.write_bytes(source.read_bytes())
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    replay.check_pins(tmp_path, {"analyze.py": digest}, {"analyze.py"})
    copied.write_bytes(copied.read_bytes() + b"\n# changed\n")
    with pytest.raises(ValueError, match="pinned file changed"):
        replay.check_pins(tmp_path, {"analyze.py": digest}, {"analyze.py"})


def test_optimized_python_still_rejects_fraction_change() -> None:
    script = """
import importlib.util, json, sys
s = importlib.util.spec_from_file_location('review', sys.argv[1])
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
x = json.load(open(sys.argv[2]))
for p in x['profiles']:
    for i, f in enumerate(p['optics'][1]['hydro_frac.txt']['values']):
        if i >= 27 and f > 0:
            p['optics'][2]['hydro_frac.txt']['values'][i] = 0.0
            m.analyze(x)
            raise SystemExit(0)
raise SystemExit(2)
"""
    run = subprocess.run(
        [sys.executable, "-O", "-c", script, str(PACKET / "analyze.py"), str(WITNESS)],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert run.returncode != 0
    assert "ValueError" in run.stderr
