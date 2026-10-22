"""Synthetic value-only tests of the composition verifier's acceptance gates.

These fixtures contain no native model, KDM or RTTOV execution evidence.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pytest

from harness import verify_microphysics_obs_ad as verify


def args(tmp_path, **updates):
    values = {name: tmp_path/name for name in (
        "trace", "checkpoint", "namelist", "library", "kernel_build_manifest",
        "observations", "template", "executable", "time_audit", "output", "workspace")}
    values.update(updates)
    return SimpleNamespace(**values)


@pytest.mark.parametrize("name", ("trace", "checkpoint", "namelist", "library", "kernel_build_manifest"))
def test_refuse_output_input_alias_before_library_loading(tmp_path, name):
    a = args(tmp_path)
    a.output = getattr(a, name)
    with pytest.raises(ValueError, match="output must be new"):
        verify.validate_paths(a)


def test_refuse_symlink_and_template_descendants(tmp_path):
    a = args(tmp_path)
    a.template.mkdir()
    a.output = a.template/"report.json"
    with pytest.raises(ValueError, match="template must be disjoint"):
        verify.validate_paths(a)
    a = args(tmp_path)
    a.workspace.symlink_to(tmp_path/"nonexistent")
    with pytest.raises(ValueError, match="workspace must be new"):
        verify.validate_paths(a)


def test_refuse_output_inside_workspace(tmp_path):
    a = args(tmp_path)
    a.output = a.workspace/"result.json"
    with pytest.raises(ValueError, match="output and workspace must be disjoint"):
        verify.validate_paths(a)


def test_optional_number_receipt_is_a_pinned_input_not_an_output(tmp_path):
    a = args(tmp_path)
    a.native_number_admission = tmp_path/"admission.json"
    a.output = a.native_number_admission
    with pytest.raises(ValueError, match="output must be new"):
        verify.validate_paths(a)


def test_fd_gate_checks_each_channel_and_cost_with_common_epsilon():
    # Opposite per-channel errors cancel in a BT sum; they must still fail.
    dbt = np.array([[1., 1.]])
    plus = {"bt": np.array([[1.001, .999]]), "cost": 2.}
    minus = {"bt": -plus["bt"], "cost": -2.}
    r = verify.fd_trial(1., dbt, 2., plus, minus, np.ones((1, 2)))
    assert r["cost_tolerance_ratio"] == 0
    assert r["max_tolerance_ratio"] > 1
    # A deliberately masked channel is excluded from this fixed-support gate.
    plus = {"bt": np.array([[1., 9.]]), "cost": 2.}
    minus = {"bt": -plus["bt"], "cost": -2.}
    r = verify.fd_trial(1., dbt, 2., plus, minus, np.array([[1., 0.]]))
    assert r["max_tolerance_ratio"] == 0


def test_observation_output_parsing_keeps_pressure_vector_and_interfaces():
    levels = 3
    y = np.arange(10*levels+1, dtype=np.float64)
    values = verify.observation_arrays(y, levels)
    assert [v.size for v in values] == [3, 3, 3, 4, 3, 3, 3, 3, 3, 3]
    np.testing.assert_array_equal(values[2], y[6:9])
    np.testing.assert_array_equal(values[3], y[9:13])
    np.testing.assert_array_equal(verify.pack(values), y)


def test_directions_leave_zero_reservoirs_zero_and_mix_live_geometry():
    levels = 3
    x = verify.pack_state((np.ones(levels), np.full(levels, .01), np.array(50000.), np.arange(levels+1)))
    rest = np.zeros((10, levels), dtype=np.float64)
    rest[2] = [0., 1e-5, 2e-5]
    ds = verify.directions(x, rest, levels)
    assert np.all(ds["cloud_mass"][1][rest == 0] == 0)
    parts = verify.unpack_state(ds["mu_total"][0], levels)
    assert parts[2] == 10.
    assert np.all(parts[3] == 0) and np.all(parts[0] == 0) and np.all(parts[1] == 0)
    parts = verify.unpack_state(ds["ph_interfaces"][0], levels)
    assert parts[2] == 0 and np.any(parts[3])
    np.testing.assert_allclose(ds["mixed"][0], sum(v[0] for k, v in ds.items() if k != "mixed"))


def test_kernel_build_library_and_required_sources_are_bound(tmp_path):
    root = tmp_path/"root"
    root.mkdir()
    library = tmp_path/"lib.dylib"
    library.write_bytes(b"synthetic library identity")
    names = ("libtorch/src/runtime.cpp", "libtorch/bridge/kdm6_c_api.cpp",
             "libtorch/include/kdm6/runtime.h", "harness/verify_state_forcing_ad.py")
    hashes = {}
    for name in names:
        path = root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name)
        hashes[name] = verify.sha(path)
    manifest = tmp_path/"manifest.json"
    data = {"library_sha256": verify.sha(library), "source_sha256": hashes}
    manifest.write_text(json.dumps(data))
    assert verify.verify_kernel_build(root, library, manifest) == hashes
    (root/names[0]).write_text("changed")
    with pytest.raises(ValueError, match="source differs from build"):
        verify.verify_kernel_build(root, library, manifest)
    data["source_sha256"] = {}
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="omits required"):
        verify.verify_kernel_build(root, library, manifest)
