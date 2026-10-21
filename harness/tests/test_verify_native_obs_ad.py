"""NumPy-only refusal and snapshot-reader tests for verify_native_obs_ad.

All profiles/observations below are synthetic parser fixtures. They are not
model output, RTTOV evidence, or scientific forward results.
"""
from __future__ import annotations

import builtins
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from harness import verify_native_obs_ad as verifier


NOBS = 234 * 282
EXPECTED = "2025-07-19_00:00:00"
SLOT = "202507190000"


def _args(tmp_path, **updates):
    values = dict(
        checkpoint=tmp_path / "checkpoint.nc",
        observations=tmp_path / "obs.npz",
        template=tmp_path / "template",
        executable=tmp_path / "rttov_test.exe",
        time_audit=tmp_path / "time_audit.json",
        namelist=tmp_path / "namelist.output",
        workspace=tmp_path / "workspace",
        output=tmp_path / "result.json",
        i=156, j=21, levels=39, upper_layers=27,
        model_time=EXPECTED, nominal_time=EXPECTED, all_sky=False,
        sigma=1.0, huber_delta=1.0, timeout=1.0,
    )
    values.update(updates)
    return SimpleNamespace(**values)


def _assert_refusal_before_expensive_work(monkeypatch):
    imported = []
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "torch":
            imported.append(name)
            raise AssertionError("Torch must not load before input-path refusals")
        return original_import(name, *args, **kwargs)

    hashed = []

    def guarded_sha(path):
        hashed.append(path)
        raise AssertionError("input hashes must not be read before path refusals")

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(verifier, "sha", guarded_sha)
    return imported, hashed


def test_output_equal_to_input_refuses_before_torch_or_hashes(tmp_path, monkeypatch):
    args = _args(tmp_path)
    args.output = args.checkpoint
    imported, hashed = _assert_refusal_before_expensive_work(monkeypatch)
    with pytest.raises(ValueError, match="output must be new and distinct"):
        verifier.verify(args)
    assert imported == [] and hashed == []


def test_symlink_output_alias_to_input_refuses_early(tmp_path, monkeypatch):
    args = _args(tmp_path)
    args.checkpoint.write_bytes(b"synthetic placeholder")
    args.output.symlink_to(args.checkpoint)
    imported, hashed = _assert_refusal_before_expensive_work(monkeypatch)
    with pytest.raises(ValueError, match="output must be new and distinct"):
        verifier.verify(args)
    assert imported == [] and hashed == []


def test_output_nested_under_template_refuses_before_expensive_work(tmp_path, monkeypatch):
    args = _args(tmp_path)
    args.template.mkdir()
    args.output = args.template / "result.json"
    imported, hashed = _assert_refusal_before_expensive_work(monkeypatch)
    with pytest.raises(ValueError, match="output.*template|template.*output"):
        verifier.verify(args)
    assert imported == [] and hashed == []


def test_workspace_overlapping_template_refuses_before_expensive_work(tmp_path, monkeypatch):
    args = _args(tmp_path)
    args.template.mkdir()
    args.workspace = args.template / "workspace"
    imported, hashed = _assert_refusal_before_expensive_work(monkeypatch)
    with pytest.raises(ValueError, match="workspace and input template must be disjoint"):
        verifier.verify(args)
    assert imported == [] and hashed == []


@pytest.mark.parametrize(
    ("source", "target"),
    [("template", "template/child"), ("template/child", "template")],
)
def test_clear_template_refuses_ancestor_or_descendant_paths(tmp_path, source, target):
    root = tmp_path / "tree"
    (root / "template").mkdir(parents=True)
    source_path = root / source
    target_path = root / target
    # Existing ancestor targets are refused by the new-target guard first; a
    # not-yet-created child still exercises the explicit containment check.
    with pytest.raises(ValueError):
        verifier.clear_template(source_path, target_path)


def test_clear_template_refuses_broken_symlink_target_before_resolve(tmp_path):
    source = tmp_path / "template"
    source.mkdir()
    target = tmp_path / "broken-target"
    target.symlink_to(tmp_path / "missing-target")
    with pytest.raises(ValueError, match="target must be new"):
        verifier.clear_template(source, target)


def _clear_template_source(root: Path, *, duplicate_key: bool = False):
    out = root / "out"
    atm = root / "in" / "profiles" / "001" / "atm"
    (out / "direct").mkdir(parents=True)
    (out / "k").mkdir()
    atm.mkdir(parents=True)
    (out / "run.sh").write_text("#!/bin/sh\n")
    (out / "env.sh").write_text("export RTTOV=1\n")
    nml = "defn%f_hydro = 'hydro.txt'\ndefn%f_hydro_frac = 'frac.txt'\n"
    (out / "rttov_test.txt").write_text(nml)
    (out / "direct" / "stale.txt").write_text("stale direct output\n")
    (out / "k" / "stale.txt").write_text("stale K output\n")
    (out / "old.log").write_text("stale log\n")
    coef = "defn%f_hydrotable = 'hydrotable.dat'\n"
    if duplicate_key:
        coef += "defn%f_hydrotable = 'duplicate.dat'\n"
    (root / "in" / "coef.txt").write_text(coef)
    (atm / "simple_cloud.txt").write_text("cfraction = 0.7\n")
    return root


def test_clear_template_retains_empty_rttov_output_directories(tmp_path):
    source = _clear_template_source(tmp_path / "template")
    before = {p.relative_to(source): p.read_bytes()
              for p in source.rglob("*") if p.is_file()}
    target = tmp_path / "clear"
    verifier.clear_template(source, target)
    assert (target / "out" / "direct").is_dir()
    assert (target / "out" / "k").is_dir()
    assert list((target / "out" / "direct").iterdir()) == []
    assert list((target / "out" / "k").iterdir()) == []
    assert not (target / "out" / "old.log").exists()
    assert _tree_bytes(source) == before


def _tree_bytes(root: Path):
    return {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_clear_template_duplicate_disable_key_fails_without_source_changes(tmp_path):
    source = _clear_template_source(tmp_path / "template", duplicate_key=True)
    before = _tree_bytes(source)
    with pytest.raises(ValueError, match="expected one f_hydrotable"):
        verifier.clear_template(source, tmp_path / "clear")
    assert _tree_bytes(source) == before


class _Dim:
    def __init__(self, size):
        self.size = size

    def __len__(self):
        return self.size


class _Var:
    def __init__(self, value, dimensions):
        self.value = np.asarray(value)
        self.dimensions = tuple(dimensions)
        self.dtype = self.value.dtype
        self.attrs = {}
        self.shape = self.value.shape

    def __getitem__(self, _index):
        # Loader tests only need selected vectors, not a full 234x282 field.
        return self.value

    def ncattrs(self):
        return []


class _Dataset:
    def __init__(self, variables, sizes, *, mp_physics=137, use_theta_m=1):
        self.variables = variables
        self.dimensions = {name: _Dim(size) for name, size in sizes.items()}
        self.MP_PHYSICS = mp_physics
        self.USE_THETA_M = use_theta_m

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def set_auto_maskandscale(self, _value):
        pass


def _char_time(stamp):
    return np.asarray(list(stamp), dtype="S1").reshape(1, 19)


def _install_fake_netcdf(monkeypatch, *, times=EXPECTED, numeric_times=False,
                         bottom_top=39, all_sky=False, mp_physics=137,
                         use_theta_m=1):
    dt = np.int32 if numeric_times else "S1"
    times_data = np.arange(19, dtype=dt).reshape(1, 19) if numeric_times else _char_time(times)
    variables = {
        "Times": _Var(times_data, ("Time", "DateStrLen")),
        "THM_2": _Var(np.linspace(1.0, 39.0, 39, dtype=np.float32),
                       ("Time", "bottom_top", "south_north", "west_east")),
        "QVAPOR": _Var(np.full(39, 0.004, dtype=np.float32),
                        ("Time", "bottom_top", "south_north", "west_east")),
        "P": _Var(np.full(39, 100.0, dtype=np.float32),
                  ("Time", "bottom_top", "south_north", "west_east")),
        "PB": _Var(np.full(39, 90000.0, dtype=np.float32),
                   ("Time", "bottom_top", "south_north", "west_east")),
        "PH_2": _Var(np.linspace(0.0, 390000.0, 40, dtype=np.float32),
                     ("Time", "bottom_top_stag", "south_north", "west_east")),
        "PHB": _Var(np.zeros(40, dtype=np.float32),
                    ("Time", "bottom_top_stag", "south_north", "west_east")),
        "FNM": _Var(np.full(39, 0.5, dtype=np.float32), ("Time", "bottom_top")),
        "FNP": _Var(np.full(39, 0.5, dtype=np.float32), ("Time", "bottom_top")),
    }
    if all_sky:
        for name, value in {
            "QCLOUD": 1.2e-3, "QICE": 8.0e-4, "QSNOW": 3.0e-5,
            "QNCLOUD": 6.0e7, "QNICE": 5.0e5, "AL": 0.5, "ALB": 0.5,
        }.items():
            variables[name] = _Var(np.full(39, value, dtype=np.float32),
                                   ("Time", "bottom_top", "south_north", "west_east"))
        variables["XLAND"] = _Var(np.asarray(2.0, dtype=np.float32),
                                  ("Time", "south_north", "west_east"))
    sizes = {"Time": 1, "DateStrLen": 19, "west_east": 234,
             "south_north": 282, "bottom_top": bottom_top, "bottom_top_stag": 40}
    module = ModuleType("netCDF4")
    module.Dataset = lambda _path: _Dataset(
        variables, sizes, mp_physics=mp_physics, use_theta_m=use_theta_m)
    monkeypatch.setitem(sys.modules, "netCDF4", module)


def _write_time_audit(path, slot=SLOT):
    path.write_text(json.dumps({
        "status": "nominal_slot_only",
        "KO_original_files": [{"filename_nominal_slot": slot}],
    }))


def _write_observations(path, *, stamp=EXPECTED, scalar_time=False, multi_time=False):
    history_time = np.asarray(stamp, dtype="U32") if scalar_time else _char_time(stamp)
    if multi_time:
        history_time = np.concatenate([history_time, history_time], axis=0)
    np.savez_compressed(
        path,
        history__Times=history_time,
        ko_channel_ids_1based=np.asarray(verifier.CHANNELS, dtype=np.int16),
        obs_bt=np.zeros((NOBS, 7), dtype=np.float32),
        obs_dqf=np.zeros((NOBS, 7), dtype=np.uint8),
        obs_qc=np.zeros((NOBS, 7), dtype=np.uint8),
        rttov_reference__p_lay_hPa=np.linspace(10.0, 900.0, 39),
        rttov_reference__p_half_hPa=np.linspace(0.0, 1000.0, 40),
        rttov_reference__t_K=np.full(39, 270.0),
        rttov_reference__q_ppmv=np.full(39, 1000.0),
    )


def _load_with_fake_inputs(tmp_path, monkeypatch, *, times=EXPECTED,
                           numeric_times=False, bottom_top=39, audit_slot=SLOT,
                           model_time=EXPECTED, nominal_time=EXPECTED, all_sky=False,
                           mp_physics=137, use_theta_m=1):
    _install_fake_netcdf(monkeypatch, times=times, numeric_times=numeric_times,
                         bottom_top=bottom_top, all_sky=all_sky,
                         mp_physics=mp_physics, use_theta_m=use_theta_m)
    observations = tmp_path / "observations.npz"
    _write_observations(observations)
    audit = tmp_path / "time_audit.json"
    _write_time_audit(audit, audit_slot)
    nml = tmp_path / "namelist.output"
    nml.write_text("&physics\nmp_physics = 137\nuse_theta_m = 1\nncmin_land = 1.0E8\nncmin_sea = 1.0E7\n/\n")
    return verifier.load_snapshot(tmp_path / "fake.nc", observations, i=156, j=21,
                                  expected_time=model_time,
                                  nominal_time=nominal_time, time_audit=audit,
                                  namelist=nml if all_sky else None,
                                  all_sky=all_sky, levels=39)


def test_load_snapshot_accepts_native_char_time_and_39_40_dimensions(tmp_path, monkeypatch):
    snapshot = _load_with_fake_inputs(tmp_path, monkeypatch)
    assert snapshot.x.shape == (4*39+1,)
    assert snapshot.provenance["checkpoint_time"] == EXPECTED
    assert snapshot.provenance["native_levels"] == 39
    assert snapshot.provenance["native_interfaces"] == 40
    assert snapshot.provenance["pixel_acquisition_time_verified"] is False


def test_load_snapshot_rejects_numeric_or_wrong_character_times(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="Times must be a Time-indexed character"):
        _load_with_fake_inputs(tmp_path, monkeypatch, numeric_times=True)


def test_load_snapshot_rejects_wrong_character_times(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="checkpoint Times .* != requested model boundary"):
        _load_with_fake_inputs(tmp_path, monkeypatch, times="2025-07-19_00:01:00")


def test_load_snapshot_accepts_scalar_unicode_npz_time_and_rejects_multi_time(
        tmp_path, monkeypatch):
    _install_fake_netcdf(monkeypatch)
    obs = tmp_path / "scalar.npz"
    _write_observations(obs, scalar_time=True)
    audit = tmp_path / "scalar-audit.json"
    _write_time_audit(audit)
    snapshot = verifier.load_snapshot(tmp_path / "fake.nc", obs, i=156, j=21,
                                      expected_time=EXPECTED, time_audit=audit)
    assert snapshot.provenance["checkpoint_time"] == EXPECTED

    obs_multi = tmp_path / "multi.npz"
    _write_observations(obs_multi, multi_time=True)
    with pytest.raises(ValueError, match="observation bundle background time differs from its nominal KO slot"):
        verifier.load_snapshot(tmp_path / "fake.nc", obs_multi, i=156, j=21,
                               expected_time=EXPECTED, time_audit=audit)


def test_cloud_snapshot_accepts_model_boundary_20s_after_nominal_ko_slot(
        tmp_path, monkeypatch):
    model_time = "2025-07-19_00:00:20"
    snapshot = _load_with_fake_inputs(
        tmp_path, monkeypatch, times=model_time, model_time=model_time,
        nominal_time=EXPECTED, audit_slot=SLOT, all_sky=True)
    assert snapshot.provenance["checkpoint_time"] == model_time
    assert snapshot.provenance["nominal_KO_slot"] == EXPECTED
    assert snapshot.provenance["model_minus_nominal_slot_seconds"] == 20.0
    assert snapshot.provenance["pixel_acquisition_time_verified"] is False
    assert snapshot.cloud is not None and set(snapshot.cloud) == {"qc", "qi", "qs", "nc", "ni"}
    assert snapshot.rho_d is not None and np.all(snapshot.rho_d > 0.0)
    assert snapshot.ncmin == (1.0e8, 1.0e7)
    assert snapshot.xland == 2.0


def test_cloud_snapshot_rejects_checkpoint_global_physics_mismatch(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="checkpoint physics/thermodynamic coordinate"):
        _load_with_fake_inputs(
            tmp_path, monkeypatch, all_sky=True,
            mp_physics=37, use_theta_m=1)


def test_load_snapshot_rejects_non_native_vertical_dimension(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="bottom_top dimension differs"):
        _load_with_fake_inputs(tmp_path, monkeypatch, bottom_top=38)


def test_load_snapshot_rejects_ko_audit_nominal_slot_mismatch_before_netcdf_open(
        tmp_path, monkeypatch):
    module = ModuleType("netCDF4")
    module.Dataset = lambda _path: (_ for _ in ()).throw(AssertionError("dataset should not open"))
    monkeypatch.setitem(sys.modules, "netCDF4", module)
    observations = tmp_path / "observations.npz"
    _write_observations(observations)
    audit = tmp_path / "time_audit.json"
    _write_time_audit(audit, "202507190005")
    with pytest.raises(ValueError, match="KO source nominal slot differs"):
        verifier.load_snapshot(tmp_path / "not-opened.nc", observations, i=156, j=21,
                               expected_time=EXPECTED, time_audit=audit, levels=39)
