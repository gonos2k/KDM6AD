"""Mock-only tests for the selected-row native observation batch adapter."""
# Imports after importorskip are intentional so Torch remains an optional dependency.
# ruff: noqa: E402
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch", reason="native profile/RTTOV autograd boundary needs Torch")

import harness.native_observation_batch as adapter_module
from harness.native_batch_microphysics import (
    CloudProfile,
    NativeBatchOutput,
    NativeProfile,
)
from harness.native_observation_batch import (
    CHANNELS,
    RTTOV_QMIN_PPMV_DRY,
    _rttov_qmin_error,
    _optical_cloud_state,
    evaluate_observation_batch,
    profile_jvp,
)
from oracle.kdm6.obs.model_profile_builder import RttovProfileTensors
from oracle.kdm6.obs.native_cloud_profile import NativeCloudState


DTYPE = torch.float64


def _surface():
    return {
        "skin": {
            "surftype": 0,
            "watertype": 1,
            "t": 300.0,
            "salinity": 35.0,
            "foam_fraction": 0.0,
            "snow_fraction": 0.0,
            "fastem": [3.0, 5.0, 15.0, 0.1, 0.3],
        },
        "near_surface": {
            "t2m": 300.0,
            "q2m": 1000.0,
            "wind_u10m": 1.0,
            "wind_v10m": 2.0,
            "wind_fetch": 0.0,
        },
    }


def _block(batch=4):
    geometry = {
        name: np.full(batch, value, dtype=np.float64)
        for name, value in (
            ("zenangle", 40.0), ("azangle", 0.0), ("sunzenangle", 0.0),
            ("sunazangle", 0.0), ("latitude", 37.0), ("longitude", 127.0),
            ("elevation", 0.2),
        )
    }
    admission = np.ones(batch, dtype=bool)
    negative_nc = np.zeros(batch, dtype=bool)
    negative_ni = np.zeros(batch, dtype=bool)
    admission[1] = False
    negative_nc[1] = True
    reasons = np.full(batch, "", dtype="U32")
    reasons[1] = "negative_nc"
    dqf = np.zeros((batch, 7), dtype=np.uint8)
    dqf[3, 0] = 1
    qc_raw = np.zeros((batch, 7), dtype=np.float64)
    qc_raw[3, 2] = 1.0
    qc_codes = qc_raw.astype(np.int32)
    return {
        "flat_indices": np.arange(batch, dtype=np.int32),
        "B": batch,
        "L": 3,
        "obs_bt": np.full((batch, 7), 280.0, dtype=np.float64),
        "obs_dqf": dqf,
        "obs_qc_raw": qc_raw,
        "obs_qc_codes": qc_codes,
        "initial_admission": {
            "cost_eligible": admission,
            "negative_nc": negative_nc,
            "negative_ni": negative_ni,
            "reasons": reasons,
        },
        "xland": np.array([1.0, 1.0, 2.0, 2.0], dtype=np.float64),
        "fnm": np.full(3, 0.5, dtype=np.float64),
        "fnp": np.full(3, 0.5, dtype=np.float64),
        "reference": {
            "p_lay_hpa": np.array([1.0, 5.0, 20.0, 60.0]),
            "p_half_hpa": np.array([0.0, 2.0, 10.0, 30.0, 100.0]),
            "t_k": np.array([295.0, 250.0, 220.0, 190.0]),
            "q_ppmv": np.array([1000.0, 500.0, 100.0, 10.0]),
            "fixed_upper_count": 2,
        },
        "rttov_geometry": geometry,
        "surface_profiles": [_surface() for _ in range(batch)],
        "rest": np.arange(10 * batch * 3, dtype=np.float64).reshape(10, batch, 3),
    }


def _output(block):
    batch = block["B"]
    theta = torch.zeros((batch, 3), dtype=DTYPE, requires_grad=True)
    qv = torch.full((batch, 3), 0.008, dtype=DTYPE, requires_grad=True)
    p_center = torch.tensor(
        [[100000.0, 10000.0, 1500.0]] * batch, dtype=DTYPE, requires_grad=True)
    phi = torch.tensor(
        [[0.0, 9810.0, 19620.0, 29430.0]] * batch, dtype=DTYPE, requires_grad=True)
    qc = torch.full((batch, 3), 1.0e-4, dtype=DTYPE, requires_grad=True)
    qi = torch.full((batch, 3), 2.0e-5, dtype=DTYPE, requires_grad=True)
    qs = torch.full((batch, 3), 3.0e-5, dtype=DTYPE, requires_grad=True)
    nc = torch.full((batch, 3), 1.0e7, dtype=DTYPE, requires_grad=True)
    ni = torch.full((batch, 3), 5.0e6, dtype=DTYPE, requires_grad=True)
    # One initially admitted row fails the post-microphysics active-mass/moment
    # check. It must receive a row reason without dropping its valid neighbors.
    nc.data[2] = 0.0
    rho_d = torch.tensor(
        [[2.0, 4.0, 5.0]] * batch, dtype=DTYPE, requires_grad=True)
    native = NativeProfile(theta, qv, p_center, phi)
    cloud = CloudProfile(
        qc, torch.zeros_like(qc), qi, qs, torch.zeros_like(qc),
        torch.zeros_like(qc), nc, ni, torch.zeros_like(qc), torch.zeros_like(qc))
    return NativeBatchOutput(native, cloud, rho_d, None)


def _config(tmp_path):
    template = tmp_path / "template"
    template.mkdir()
    (template / "out").mkdir()
    (template / "out" / "rttov_test.txt").write_text(
        "&rttov_test_nml\n  defn%do_k = .TRUE.\n  defn%do_direct = .TRUE.\n/\n")
    return {
        "paths": {"template": str(template)},
        "prep_configuration": {
            "alpha": 1.6083624362945557,
            "t0": 300.0,
            "kappa": 0.2857142984867096,
            "p0": 100000.0,
            "g": 9.8100004196167,
        },
        "experiment": {"ncmin_land": 10.0, "ncmin_sea": 10.0},
        "rttov_timeout_seconds": 30.0,
    }


def _fake_k(profile_calls, *, bad_quality=None):
    def build(case_dir, *, fixture_case_dir, timeout, ami_kma_bt):
        assert ami_kma_bt is True
        assert timeout == 30.0

        def run(rin):
            profile_calls.append(rin)
            nprof = rin.nprofiles
            nlay = rin.profile["T"].shape[1]
            nlev = rin.profile["P_HALF"].shape[1]
            assert rin.config.pressure_gradients is True
            assert isinstance(rin.config.surface, list) and len(rin.config.surface) == nprof
            bt = np.full((nprof, 7), 281.0, dtype=np.float64)
            quality = np.zeros((nprof, 7), dtype=np.int32)
            if bad_quality is not None:
                quality[0, bad_quality] = 1
            k = {
                "T": np.ones((nprof, 7, nlay), dtype=np.float64),
                "Q": np.ones((nprof, 7, nlay), dtype=np.float64) * 2.0,
                "P": np.ones((nprof, 7, nlay), dtype=np.float64) * 3.0,
                "P_HALF": np.ones((nprof, 7, nlev), dtype=np.float64) * 4.0,
                "HYDRO6": np.ones((nprof, 7, nlay), dtype=np.float64) * 5.0,
                "HYDRO7": np.ones((nprof, 7, nlay), dtype=np.float64) * 6.0,
                "HYDRO_DEFF6": np.ones((nprof, 7, nlay), dtype=np.float64) * 7.0,
                "HYDRO_DEFF7": np.ones((nprof, 7, nlay), dtype=np.float64) * 8.0,
            }
            return bt, k, quality

        return run
    return build


def test_batch_observation_keeps_full_rows_and_records_per_row_reasons(tmp_path, monkeypatch):
    from oracle.kdm6.obs import rttov_case_writer

    block = _block()
    output = _output(block)
    before_rest = block["rest"].copy()
    config = _config(tmp_path)
    coef = tmp_path / "fake-coef.dat"
    coef.write_text("fixed coef identity\n")
    monkeypatch.setattr(rttov_case_writer, "_resolve_coef_path", lambda _: coef)
    calls = []
    original_namelist = Path(config["paths"]["template"]) / "out" / "rttov_test.txt"
    original_text = original_namelist.read_text()
    seen = {}
    fake_build = _fake_k(calls, bad_quality=1)

    def capture_k_template(case_dir, *, fixture_case_dir, timeout, ami_kma_bt):
        seen["k_template"] = fixture_case_dir
        return fake_build(case_dir, fixture_case_dir=fixture_case_dir,
                          timeout=timeout, ami_kma_bt=ami_kma_bt)

    monkeypatch.setattr(rttov_case_writer, "make_live_run_k", capture_k_template)

    result = evaluate_observation_batch(block, output, config, tmp_path / "workspace", with_k=True)

    assert len(calls) == 1
    assert calls[0].nprofiles == 2
    assert result["rows"].tolist() == [0, 3]
    assert result["profile_valid"].tolist() == [True, False, False, True]
    assert result["bt"].shape == (4, 7) and result["bt"].requires_grad
    assert torch.isnan(result["bt"][1]).all() and torch.isnan(result["bt"][2]).all()
    assert result["quality"].shape == (4, 7)
    assert np.all(result["quality"][1:3] == -1)
    assert result["baseline_valid_mask"].shape == (4, 7)
    assert not result["baseline_valid_mask"][0, 1]  # strict RTTOV quality==0
    assert not result["baseline_valid_mask"][3, 0]  # strict source DQF==0
    assert not result["baseline_valid_mask"][3, 2]
    assert result["baseline_valid_mask"][3, 1] and result["baseline_valid_mask"][3, 3:].all()
    assert "negative_initial_nc" in result["reasons"][1]
    assert "post_microphysics_profile_invalid" in result["reasons"][2]
    assert "rttov_quality_nonzero_channels0=[1]" in result["reasons"][0]
    assert "source_dqf_nonzero_channels0=[0]" in result["reasons"][3]
    assert "source_qc_nonzero_channels0=[2]" in result["reasons"][3]
    assert result["k"]["P_HALF"].shape == (2, 7, 6)
    assert result["profile_arrays"]["P"].shape == (2, 5)
    np.testing.assert_array_equal(block["rest"], before_rest)  # raw KDM rest is not rewritten
    assert result["receipt"]["K_calls"] == 1 and result["receipt"]["direct_calls"] == 0
    k_namelist = tmp_path / "workspace" / "template_k" / "out" / "rttov_test.txt"
    assert seen["k_template"] == k_namelist.parents[1]
    assert "defn%do_k = .TRUE." in k_namelist.read_text()
    assert "defn%do_direct = .FALSE." in k_namelist.read_text()
    assert original_namelist.read_text() == original_text
    assert result["receipt"]["driver_flags"] == {
        "template_do_k": True,
        "template_do_direct": True,
        "K_template_do_k": True,
        "K_template_do_direct": False,
    }


def test_rttov_qmin_uses_dry_air_conversion_and_strict_boundary():
    q_wet = torch.tensor(
        [0.0, RTTOV_QMIN_PPMV_DRY, 2.0 * RTTOV_QMIN_PPMV_DRY],
        dtype=DTYPE,
        requires_grad=True,
    )
    before = q_wet.clone()
    error = _rttov_qmin_error(q_wet)
    assert error is not None and "RTTOV hard Q minimum" in error
    assert torch.equal(q_wet, before)
    assert q_wet.requires_grad

    at_minimum = torch.tensor([RTTOV_QMIN_PPMV_DRY], dtype=DTYPE)
    above_minimum = torch.tensor([2.0 * RTTOV_QMIN_PPMV_DRY], dtype=DTYPE)
    assert _rttov_qmin_error(at_minimum) is None
    assert _rttov_qmin_error(above_minimum) is None
    assert "invalid denominator" in _rttov_qmin_error(torch.tensor([1.0e6], dtype=DTYPE))
    with pytest.raises(TypeError, match="float64"):
        _rttov_qmin_error(torch.tensor([0.0], dtype=torch.float32))


def test_hard_qmin_row_is_excluded_before_direct_call_without_q_rewrite(tmp_path, monkeypatch):
    from oracle.kdm6.obs import rttov_case_writer

    block = _block()
    output = _output(block)
    qv = torch.cat(
        (torch.zeros_like(output.native_profile.qv[:1]), output.native_profile.qv[1:]),
        dim=0,
    )
    output = output._replace(
        native_profile=output.native_profile._replace(qv=qv)
    )
    qv_before = output.native_profile.qv.detach().clone()
    config = _config(tmp_path)
    coef = tmp_path / "fake-coef.dat"
    coef.write_text("fixed coef identity\n")
    monkeypatch.setattr(rttov_case_writer, "_resolve_coef_path", lambda _: coef)
    case_dir = tmp_path / "workspace" / "case_direct"
    case_out = case_dir / "out"
    case_out.mkdir(parents=True)
    (case_out / "rttov_test.txt").write_text("&rttov_test_nml\n  defn%do_k = .TRUE.\n/\n")
    seen = {}

    def write_case(rin, out, **kwargs):
        seen["nprofiles"] = rin.nprofiles
        return case_out

    def direct(case, nprofiles, *, channels, timeout, kma_bt):
        seen["direct_nprofiles"] = nprofiles
        return np.full((nprofiles, 7), 275.0), np.zeros((nprofiles, 7)), {
            "bt_coordinate": "kma_v3_0"
        }

    monkeypatch.setattr(rttov_case_writer, "write_rttov_case", write_case)
    monkeypatch.setattr(adapter_module, "_case_direct_radiance", direct)
    monkeypatch.setattr(
        rttov_case_writer,
        "make_live_run_k",
        lambda *args, **kwargs: pytest.fail("direct-value trial must not request K"),
    )

    result = evaluate_observation_batch(
        block, output, config, tmp_path / "workspace", with_k=False
    )

    assert result["rows"].tolist() == [3]
    assert seen == {"nprofiles": 1, "direct_nprofiles": 1}
    assert "rttov_hard_qmin_invalid" in result["reasons"][0]
    assert "below 9.9999999999999994e-12 ppmv" in result["reasons"][0]
    assert torch.equal(output.native_profile.qv, qv_before)
    assert result["receipt"]["direct_calls"] == 1
    assert result["receipt"]["K_calls"] == 0


def test_optical_number_quotient_and_profile_jvp_use_same_live_density(tmp_path, monkeypatch):
    import harness.native_observation_batch as adapter

    raw_nc = torch.tensor([10.0, 20.0, 30.0], dtype=DTYPE, requires_grad=True)
    raw_ni = torch.tensor([4.0, 8.0, 10.0], dtype=DTYPE, requires_grad=True)
    rho = torch.tensor([2.0, 4.0, 5.0], dtype=DTYPE, requires_grad=True)
    raw = NativeCloudState(torch.ones(3, dtype=DTYPE), torch.ones(3, dtype=DTYPE),
                           torch.ones(3, dtype=DTYPE), raw_nc, raw_ni)
    optical = _optical_cloud_state(raw, rho)
    torch.testing.assert_close(optical.nc, raw_nc / rho, rtol=0, atol=0)
    torch.testing.assert_close(optical.ni, raw_ni / rho, rtol=0, atol=0)

    block = _block()
    primal = _output(block)
    # Give the selected row nonconstant raw number and density profiles so the
    # quotient JVP has a nonzero live-density contribution.
    primal.cloud_state.nc.data[0] = raw_nc.detach()
    primal.cloud_state.ni.data[0] = raw_ni.detach()
    primal.rho_d.data[0] = rho.detach()
    tangent_native = NativeProfile(
        torch.zeros_like(primal.native_profile.thm_pert),
        torch.zeros_like(primal.native_profile.qv),
        torch.zeros_like(primal.native_profile.p_center_Pa),
        torch.zeros_like(primal.native_profile.phi_interfaces),
    )
    tangent_cloud = CloudProfile(
        torch.zeros_like(primal.cloud_state.qc), torch.zeros_like(primal.cloud_state.qr),
        torch.zeros_like(primal.cloud_state.qi), torch.zeros_like(primal.cloud_state.qs),
        torch.zeros_like(primal.cloud_state.qg), torch.zeros_like(primal.cloud_state.nn),
        torch.zeros_like(primal.cloud_state.nc), torch.zeros_like(primal.cloud_state.ni),
        torch.zeros_like(primal.cloud_state.nr), torch.zeros_like(primal.cloud_state.bg))
    tangent_cloud.nc[0] = torch.tensor([1.0, 2.0, 4.0], dtype=DTYPE)
    tangent_cloud.ni[0] = torch.tensor([0.4, 1.0, 1.0], dtype=DTYPE)
    tangent_rho = torch.zeros_like(primal.rho_d)
    tangent_rho[0] = torch.tensor([0.1, 0.5, 1.0], dtype=DTYPE)
    tangent = NativeBatchOutput(tangent_native, tangent_cloud, tangent_rho, None)

    def fake_profile_batch(native, cloud, geometry, config, upper, *, rho_d,
                           xland, ncmin_land, ncmin_sea):
        del geometry, config, upper, rho_d, xland, ncmin_land, ncmin_sea
        return RttovProfileTensors(
            native.thm_pert, native.qv, native.p_center_Pa, native.phi_interfaces,
            cloud.nc, cloud.ni, 2.0 * cloud.nc, 3.0 * cloud.ni,
            torch.zeros_like(cloud.qc))

    monkeypatch.setattr(adapter, "native_to_rttov_cloud_profile_batch", fake_profile_batch)
    profile_tangent = profile_jvp(block, primal, tangent, _config(tmp_path), np.array([0]))
    expected_nc_tangent = (torch.tensor([1.0, 2.0, 4.0], dtype=DTYPE) / rho.detach()
                           - raw_nc.detach() * torch.tensor([0.1, 0.5, 1.0], dtype=DTYPE)
                           / rho.detach().square())
    expected_ni_tangent = (torch.tensor([0.4, 1.0, 1.0], dtype=DTYPE) / rho.detach()
                           - raw_ni.detach() * torch.tensor([0.1, 0.5, 1.0], dtype=DTYPE)
                           / rho.detach().square())
    np.testing.assert_allclose(profile_tangent["HYDRO6"][0], expected_nc_tangent.numpy())
    np.testing.assert_allclose(profile_tangent["HYDRO7"][0], expected_ni_tangent.numpy())
    np.testing.assert_allclose(profile_tangent["HYDRO_DEFF6"][0], (2 * expected_nc_tangent).numpy())
    np.testing.assert_allclose(profile_tangent["HYDRO_DEFF7"][0], (3 * expected_ni_tangent).numpy())


def test_direct_trial_disables_only_k_and_records_actual_call_mode(tmp_path, monkeypatch):
    from oracle.kdm6.obs import rttov_case_writer

    block = _block()
    output = _output(block)
    config = _config(tmp_path)
    coef = tmp_path / "fake-coef.dat"
    coef.write_text("fixed coef identity\n")
    monkeypatch.setattr(rttov_case_writer, "_resolve_coef_path", lambda _: coef)
    case_dir = tmp_path / "workspace" / "case_direct"
    case_out = case_dir / "out"
    case_out.mkdir(parents=True)
    namelist = case_out / "rttov_test.txt"
    namelist.write_text("&rttov_test_nml\n  defn%do_k = .TRUE.\n/\n")
    seen = {}

    def write_case(rin, out, **kwargs):
        seen["nprofiles"] = rin.nprofiles
        return case_out

    def direct(case, nprofiles, *, channels, timeout, kma_bt):
        seen["direct_args"] = (case, nprofiles, tuple(channels), timeout, kma_bt)
        return np.full((nprofiles, 7), 275.0), np.zeros((nprofiles, 7)), {
            "bt_coordinate": "kma_v3_0"
        }

    monkeypatch.setattr(rttov_case_writer, "write_rttov_case", write_case)
    monkeypatch.setattr(adapter_module, "_case_direct_radiance", direct)
    monkeypatch.setattr(
        rttov_case_writer, "make_live_run_k",
        lambda *args, **kwargs: pytest.fail("direct-value trial must not request K"))

    result = evaluate_observation_batch(
        block, output, config, tmp_path / "workspace", with_k=False)
    text = namelist.read_text()
    assert "defn%do_k = .FALSE." in text
    assert "defn%do_direct = .TRUE." in text
    assert seen["nprofiles"] == 2
    assert seen["direct_args"][1:] == (2, CHANNELS, 30.0, True)
    assert result["receipt"]["K_calls"] == 0
    assert result["receipt"]["direct_calls"] == 1
    assert result["k"] == {}
    assert result["bt"].shape == (4, 7) and not result["bt"].requires_grad
