"""Reject crossed artifact identities; these tests do not execute a host model."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import replay_native_host_mass_reference as replay
from replay_native_host_mass_reference import STATE_FIELDS, validate_pair


def pair():
    state = np.arange(12 * 39, dtype=np.float64).reshape(12, 39)
    fields = {f"xb_{name}": state[k:k+1].copy() for k, name in enumerate(STATE_FIELDS)}
    fields.update(nx=np.array(234), ny=np.array(282), sub_idx=np.array([36576]))
    selected = dict(i_1based=73, j_1based=157, flat_b=36576)
    return state, fields, selected


def test_matching_pair():
    validate_pair(*pair())


@pytest.mark.parametrize("key,value", [("nx", 235), ("ny", 281), ("nx", [234]), ("sub_idx", [36575])])
def test_crossed_grid_or_column(key, value):
    state, fields, selected = pair()
    fields[key] = np.array(value)
    with pytest.raises(ValueError):
        validate_pair(state, fields, selected)


@pytest.mark.parametrize("name", STATE_FIELDS)
def test_crossed_background_component(name):
    state, fields, selected = pair()
    fields[f"xb_{name}"][0, 0] += 0.01
    with pytest.raises(ValueError, match="background"):
        validate_pair(state, fields, selected)


def test_numeric_equality_does_not_hide_signed_zero_change():
    state, fields, selected = pair()
    fields["xb_th"][0, 0] = -0.0
    with pytest.raises(ValueError, match="background"):
        validate_pair(state, fields, selected)


def test_receipt_column_disagrees():
    state, fields, selected = pair()
    selected["flat_b"] -= 1
    with pytest.raises(ValueError, match="column"):
        validate_pair(state, fields, selected)


def test_edited_source_and_matching_self_declared_hash_are_rejected(tmp_path, monkeypatch):
    import hashlib
    import json

    original = replay.EVIDENCE / "NATIVE_host_mass_reference_source_2026-10-06.py"
    altered = original.read_text().replace("gravity = 9.81", "gravity = 9.8")
    assert altered != original.read_text()
    source = tmp_path / original.name
    source.write_text(altered)
    (tmp_path / "NATIVE_host_mass_reference_result_2026-10-06.json").write_text(
        json.dumps({"source_sha256": hashlib.sha256(source.read_bytes()).hexdigest()}))
    monkeypatch.setattr(replay, "EVIDENCE", tmp_path)
    with pytest.raises(ValueError, match="pinned executed bytes"):
        replay.main()
