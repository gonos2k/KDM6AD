#!/usr/bin/env python3
"""Replay a real native column's optical JVP without host or RTTOV calls."""

import contextlib
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path

import numpy as np
import torch

from harness.native_checkpoint_observation import (
    CheckpointCloudState,
    CheckpointNativeProfile,
    NativeCheckpointOutput,
    _f32_sum,
    _rho_d_from_al,
    _tensor64,
)
from harness.native_observation_batch import PROFILE_FIELDS, _selected_profile_context, profile_jvp

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
PARENT = ROOT.parent / "interior_qi_ni_checkpoint_2026-10-31"
FIXTURE = ROOT / "native_column.npz"
METADATA = ROOT / "native_column.json"
FIXTURE_SHA = "602f2713549ac99ee2272db74245aca65ad28511f087dac7f2ec985300a54be1"
METADATA_SHA = "dc15b4cab2a9c4e5e4be8cbae908f63e5787db8185a8f85adbd2574bbe11a761"
SOURCE_ROOT = "/private/tmp/KDM6AD-east-ice-radius-floor/"
CASE_FIELDS = (
    "THM_2", "QVAPOR", "QCLOUD", "QICE", "QSNOW", "QNCLOUD",
    "QNICE", "QRAIN", "QGRAUP", "QNCCN", "QNRAIN", "QIB",
    "P", "PB", "AL", "ALB", "PH_2", "PHB", "FNM", "FNP", "XLAND",
)
REF_FIELDS = ("p_lay_hpa", "p_half_hpa", "t_k", "q_ppmv")
SOURCE_EXPONENT = float(np.float32(1.0 / np.float32(3.0)))
TARGET_K = 20
TARGET_ROW = 45
HS = (1e-4, 2e-4, 4e-4, 8e-4)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def close(actual, expected, label, *, atol=1e-13, rtol=2e-12):
    require(math.isfinite(actual) and math.isfinite(expected), label + " nonfinite")
    require(math.isclose(actual, expected, rel_tol=rtol, abs_tol=atol), label)


def parent_replay():
    spec = importlib.util.spec_from_file_location("interior_qi_ni_parent_verify", PARENT / "verify_packet.py")
    parent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parent)
    with contextlib.redirect_stdout(io.StringIO()):
        parent.main()
    return json.loads((PARENT / "packet/prepared/pins.json").read_bytes())


def verify_executed_sources(pins):
    sources = pins["source_files"]
    require(len(sources) == 519, "executed source inventory")
    for original, expected in sources.items():
        require(original.startswith(SOURCE_ROOT), "executed source path")
        relative = original[len(SOURCE_ROOT):]
        require(relative.startswith(("harness/", "oracle/")), "executed source scope")
        local = REPO / relative
        require(local.is_file() and digest(local.read_bytes()) == expected, "executed source " + relative)


def load_fixture():
    raw = FIXTURE.read_bytes()
    require(digest(raw) == FIXTURE_SHA, "native fixture digest")
    meta_raw = METADATA.read_bytes()
    require(digest(meta_raw) == METADATA_SHA, "native metadata digest")
    meta = json.loads(meta_raw)
    require(meta["fixture_sha256"] == FIXTURE_SHA, "metadata fixture binding")
    require(meta["exporter_sha256"] == digest((ROOT / "export_private.py").read_bytes()), "exporter digest")
    require(meta["native_ijk_1based"] == [164, 242, 21], "native coordinate")
    require(meta["flat_index_0based"] == 56557 and meta["rttov_row_0based"] == TARGET_ROW, "profile coordinate")
    require(meta["fixed_upper_count"] == 27 and meta["raw_number_unit_certified"] is False, "fixture contract")
    require(meta["checkpoint_unit_labels"] == {
        "AL": "m3 kg-1", "ALB": "m3 kg-1", "QICE": "kg kg-1", "QNICE": "  kg-1",
    }, "checkpoint unit labels")
    require(meta["source_sha256"] == {
        "checkpoint": "950bc5d67dc8cf4980091ecac19a9b7b1ba94756e83d9bd101180e55863c0bb6",
        "observation_inputs": "c9df709fe00578b4468187cb782006da105cce28c3666d26de5e03c6c4bd461b",
        "case_manifest": "58d23f72be7ae717b20d0d60b53f908c2ecf28bd1c973756a1d4c7e4f0ec7c8d",
    }, "private source pins")
    with np.load(io.BytesIO(raw), allow_pickle=False) as stored:
        require(set(stored.files) == set(CASE_FIELDS) | {"reference__" + name for name in REF_FIELDS}, "fixture inventory")
        data = {name: stored[name].copy() for name in stored.files}
    for name in CASE_FIELDS:
        shape = () if name == "XLAND" else ((40,) if name in ("PH_2", "PHB") else (39,))
        require(data[name].shape == shape and data[name].dtype == np.float32, "native field " + name)
    for name in REF_FIELDS:
        values = data["reference__" + name]
        require(values.shape == ((70,) if name == "p_half_hpa" else (69,)) and values.dtype == np.float64,
                "reference field " + name)
    require(all(np.isfinite(values).all() for values in data.values()), "fixture finite")
    return meta, data


def build_inputs(meta, data):
    def tensor(name):
        return _tensor64(data[name][None, :])

    native = CheckpointNativeProfile(
        tensor("THM_2"), tensor("QVAPOR"),
        _tensor64(_f32_sum(data["P"], data["PB"])[None, :]),
        _tensor64(_f32_sum(data["PH_2"], data["PHB"])[None, :]),
    )
    cloud = CheckpointCloudState(*(tensor(name) for name in (
        "QCLOUD", "QICE", "QSNOW", "QNCLOUD", "QNICE",
        "QRAIN", "QGRAUP", "QNCCN", "QNRAIN", "QIB",
    )))
    rho = _tensor64(_rho_d_from_al(data["AL"], data["ALB"])[None, :])
    output = NativeCheckpointOutput(native, cloud, rho)
    block = {
        "xland": np.array([data["XLAND"]], dtype=np.float64),
        "fnm": data["FNM"].astype(np.float64),
        "fnp": data["FNP"].astype(np.float64),
        "reference": {name: data["reference__" + name] for name in REF_FIELDS}
        | {"fixed_upper_count": meta["fixed_upper_count"]},
    }
    config = {"prep_configuration": meta["prep_configuration"], "experiment": meta["experiment"]}
    return block, output, config


def change(output, *, qi=None, ni=None, rho=None):
    cloud = output.cloud_state
    q = cloud.qi.clone()
    n = cloud.ni.clone()
    r = output.rho_d.clone()
    if qi is not None:
        q[0, TARGET_K] = qi
    if ni is not None:
        n[0, TARGET_K] = ni
    if rho is not None:
        r[0, TARGET_K] = rho
    return output._replace(cloud_state=cloud._replace(qi=q, ni=n), rho_d=r)


def tangent_output(output, dq, dn, dr):
    native = type(output.native_profile)(*(torch.zeros_like(value) for value in output.native_profile))
    cloud = type(output.cloud_state)(*(torch.zeros_like(value) for value in output.cloud_state))
    qi = cloud.qi.clone()
    ni = cloud.ni.clone()
    rho = torch.zeros_like(output.rho_d)
    qi[0, TARGET_K], ni[0, TARGET_K], rho[0, TARGET_K] = dq, dn, dr
    return NativeCheckpointOutput(native, cloud._replace(qi=qi, ni=ni), rho)


def profile(block, output, config):
    return _selected_profile_context(block, output, np.array([0], dtype=np.int64), config)


def components(result):
    return {name: getattr(result, attr).detach().numpy()[0].copy() for name, attr in (
        ("T", "t_lay"), ("Q", "q_lay"), ("P", "p_lay"), ("P_HALF", "p_half"),
        ("HYDRO6", "clw"), ("HYDRO7", "ciw"),
        ("HYDRO_DEFF6", "deff_liq"), ("HYDRO_DEFF7", "deff_ice"),
    )}


def only_target(values, label):
    require(set(values) == set(PROFILE_FIELDS), label + " field inventory")
    for name, row in values.items():
        expected = 67 if name == "P_HALF" else 66
        require(row.shape == (1, expected) and np.isfinite(row).all(), label + " shape " + name)
        row = row[0].copy()
        if name in ("HYDRO7", "HYDRO_DEFF7"):
            row[TARGET_ROW] = 0.0
        require(np.count_nonzero(row) == 0, label + " off-target " + name)


def analytic(h0, d0, qi, ni, rho, dq, dn, dr):
    return (
        1000.0 * (rho * dq + qi * dr),
        SOURCE_EXPONENT * d0 * (dq / qi + dr / rho - dn / ni),
    )


def scalar_endpoint(d0, qi, ni, rho, dq, dn, dr, t):
    q, n, r = qi + t * dq, ni + t * dn, rho + t * dr
    require(q > 0 and n > 0 and r > 0, "scalar endpoint domain")
    ratio = (q / qi) * (r / rho) / (n / ni)
    return 1000.0 * r * q, d0 * math.exp(SOURCE_EXPONENT * math.log(ratio))


def check_vjp(block, output, config, h0, d0, qi, ni, rho):
    cloud = output.cloud_state
    q = cloud.qi.clone().detach().requires_grad_(True)
    n = cloud.ni.clone().detach().requires_grad_(True)
    r = output.rho_d.clone().detach().requires_grad_(True)
    result = profile(block, output._replace(cloud_state=cloud._replace(qi=q, ni=n), rho_d=r), config)
    scalar = result.ciw[0, TARGET_ROW] / h0 + result.deff_ice[0, TARGET_ROW] / d0
    gradients = torch.autograd.grad(scalar, (q, n, r))
    expected = ((1.0 + SOURCE_EXPONENT) / qi, -SOURCE_EXPONENT / ni,
                (1.0 + SOURCE_EXPONENT) / rho)
    for name, grad, want in zip(("QI", "raw NI", "rho"), gradients, expected):
        values = grad.detach().numpy()[0]
        close(float(values[TARGET_K]), want, "VJP " + name, atol=1e-12, rtol=2e-12)
        values = values.copy()
        values[TARGET_K] = 0.0
        require(np.count_nonzero(values) == 0, "VJP off-target " + name)
    return [float(grad[0, TARGET_K]) for grad in gradients]


def main():
    torch.set_num_threads(1)
    pins = parent_replay()
    verify_executed_sources(pins)
    meta, data = load_fixture()
    block, output, config = build_inputs(meta, data)
    baseline = profile(block, output, config)
    base = components(baseline)
    optical_dir = PARENT / "packet/results/baseline/in/profiles/001/atm"
    for field, path, slot in (
        ("HYDRO6", "hydro.txt", 5), ("HYDRO7", "hydro.txt", 6),
        ("HYDRO_DEFF6", "hydro_deff.txt", 5),
        ("HYDRO_DEFF7", "hydro_deff.txt", 6),
    ):
        require(np.array_equal(base[field], np.loadtxt(optical_dir / path)[:, slot]),
                "retained baseline " + field)
    h0, d0 = base["HYDRO7"][TARGET_ROW], base["HYDRO_DEFF7"][TARGET_ROW]
    qi, ni, rho = (float(data["QICE"][TARGET_K]), float(data["QNICE"][TARGET_K]),
                   float(output.rho_d[0, TARGET_K]))
    require(qi == pins["records"]["baseline"]["qi_f32"] and
            ni == pins["records"]["baseline"]["ni_f32"], "retained native moment")
    close(h0, 1000.0 * rho * qi, "independent content", atol=1e-17)
    require(float(data["QSNOW"][TARGET_K]) == 0.0 and qi > 1e-15 and ni > 0,
            "active no-snow branch")
    require(h0 > 1e-6 and 10.01 < d0 / 2 < 125.0 and 10.0 < d0 < 120.0,
            "content/radius/diameter branch margins")
    require(float(baseline.cfrac[0, TARGET_ROW]) == 0.999999, "cloud gate")
    vjp = check_vjp(block, output, config, h0, d0, qi, ni, rho)
    # The parent verifier authenticated these same-run K arrays and BT secants.
    with np.load(PARENT / "packet/results/baseline/values.npz", allow_pickle=False) as saved_k:
        k_h = saved_k["hydro7"][0, :, TARGET_ROW].copy()
        k_d = saved_k["deff7"][0, :, TARGET_ROW].copy()
    parent_audit = json.loads((PARENT / "packet/results/independent_audit.json").read_bytes())
    require(parent_audit["channels"] == list(range(10, 17)) and
            k_h.shape == k_d.shape == (7,) and
            np.isfinite(k_h).all() and np.isfinite(k_d).all(), "same-run K coordinate")
    directions = {
        "qi_only": (qi, 0.0, 0.0),
        "raw_ni_only": (0.0, ni, 0.0),
        "coupled": (qi, -ni, 0.0),
        "rho_only": (0.0, 0.0, rho),
        "qi_rho_null": (qi, 0.0, -rho),
    }
    results = {}
    for name, (dq, dn, dr) in directions.items():
        j = profile_jvp(block, output, tangent_output(output, dq, dn, dr), config, np.array([0]))
        only_target(j, name)
        predicted = analytic(h0, d0, qi, ni, rho, dq, dn, dr)
        jh, jd = float(j["HYDRO7"][0, TARGET_ROW]), float(j["HYDRO_DEFF7"][0, TARGET_ROW])
        close(jh, predicted[0], name + " content JVP", atol=1e-15)
        close(jd, predicted[1], name + " diameter JVP")
        dot = vjp[0] * dq + vjp[1] * dn + vjp[2] * dr
        close(jh / h0 + jd / d0, dot, name + " JVP/VJP dot", atol=1e-12)
        fd_errors = []
        for h in HS:
            endpoints = []
            for sign in (1, -1):
                trial = change(output, qi=qi + sign * h * dq, ni=ni + sign * h * dn,
                               rho=rho + sign * h * dr)
                values = profile(block, trial, config)
                trial_arrays = components(values)
                for field, original in base.items():
                    mask = np.ones(original.shape, dtype=bool)
                    if field in ("HYDRO7", "HYDRO_DEFF7"):
                        mask[TARGET_ROW] = False
                    require(np.array_equal(trial_arrays[field][mask], original[mask]),
                            name + " finite-difference off-target " + field)
                require(float(values.cfrac[0, TARGET_ROW]) == 0.999999, "finite-difference cloud gate")
                target_h = float(values.ciw[0, TARGET_ROW])
                target_d = float(values.deff_ice[0, TARGET_ROW])
                require(target_h > 1e-6 and 10.01 < target_d / 2 < 125.0 and
                        10.0 < target_d < 120.0, "finite-difference branch margins")
                model = scalar_endpoint(d0, qi, ni, rho, dq, dn, dr, sign * h)
                close(target_h, model[0], name + " scalar content endpoint", atol=1e-15)
                close(target_d, model[1], name + " scalar diameter endpoint")
                endpoints.append((target_h, target_d))
            fd = [(endpoints[0][i] - endpoints[1][i]) / (2 * h) for i in (0, 1)]
            model_plus = scalar_endpoint(d0, qi, ni, rho, dq, dn, dr, h)
            model_minus = scalar_endpoint(d0, qi, ni, rho, dq, dn, dr, -h)
            model_fd = [(model_plus[i] - model_minus[i]) / (2 * h) for i in (0, 1)]
            for i, field in enumerate(("content", "diameter")):
                close(fd[i], model_fd[i], name + " scalar " + field + " secant", atol=2e-9)
            fd_errors.append([fd[0] - jh, fd[1] - jd])
        results[name] = {"jvp": [jh, jd], "f64_fd_minus_jvp": fd_errors}
    # The previous REAL4 endpoint packet tests a different, realized direction.
    realized = []
    for i, h in enumerate(HS):
        endpoints = []
        for sign, suffix in ((1, "plus"), (-1, "minus")):
            name = f"h{i}_{suffix}"
            record = pins["records"][name]
            changed = change(output, qi=record["qi_f32"], ni=record["ni_f32"])
            values = profile(block, changed, config)
            case_dir = PARENT / "packet/results" / name / "in/profiles/001/atm"
            for field, path, slot in (("HYDRO7", "hydro.txt", 6),
                                      ("HYDRO_DEFF7", "hydro_deff.txt", 6)):
                require(np.array_equal(components(values)[field], np.loadtxt(case_dir / path)[:, slot]),
                        "retained REAL4 " + name + " " + field)
            actual_q, actual_n = record["qi_f32"], record["ni_f32"]
            target_h = float(values.ciw[0, TARGET_ROW])
            target_d = float(values.deff_ice[0, TARGET_ROW])
            require(float(values.cfrac[0, TARGET_ROW]) == record["fraction"] == 0.999999,
                    "REAL4 cloud gate " + name)
            require(target_h > 1e-6 and 10.01 < target_d / 2 < 125.0 and
                    10.0 < target_d < 120.0, "REAL4 branch margins " + name)
            close(target_h, 1000.0 * rho * actual_q,
                  "REAL4 scalar content " + name, atol=1e-17)
            expected_d = d0 * math.exp(SOURCE_EXPONENT * math.log((actual_q / qi) / (actual_n / ni)))
            close(target_d, expected_d,
                  "REAL4 scalar diameter " + name)
            endpoints.append((record["qi_f32"], record["ni_f32"],
                              target_h, target_d))
        dq = (endpoints[0][0] - endpoints[1][0]) / (2 * h)
        dn = (endpoints[0][1] - endpoints[1][1]) / (2 * h)
        j = profile_jvp(block, output, tangent_output(output, dq, dn, 0.0), config, np.array([0]))
        only_target(j, "realized REAL4")
        wanted = analytic(h0, d0, qi, ni, rho, dq, dn, 0.0)
        close(float(j["HYDRO7"][0, TARGET_ROW]), wanted[0], "REAL4 direction content JVP", atol=1e-15)
        close(float(j["HYDRO_DEFF7"][0, TARGET_ROW]), wanted[1], "REAL4 direction diameter JVP")
        secant = [(endpoints[0][k] - endpoints[1][k]) / (2 * h) for k in (2, 3)]
        j_h = float(j["HYDRO7"][0, TARGET_ROW])
        j_d = float(j["HYDRO_DEFF7"][0, TARGET_ROW])
        fd = np.asarray(parent_audit["steps"][str(h)]["central_fd"], dtype=np.float64)
        k_optical_h, k_optical_d = k_h * secant[0], k_d * secant[1]
        k_optical = k_optical_h + k_optical_d
        require(np.array_equal(k_optical, np.asarray(parent_audit["steps"][str(h)]["k_total"])),
                "parent optical K join")
        k_jvp_h, k_jvp_d = k_h * j_h, k_d * j_d
        k_jvp = k_jvp_h + k_jvp_d
        optical_residual = fd - k_optical
        content_curvature = k_h * (secant[0] - j_h)
        diameter_curvature = k_d * (secant[1] - j_d)
        full_residual = fd - k_jvp
        reconstruction = np.array([
            math.fsum((float(optical_residual[c]), float(content_curvature[c]),
                       float(diameter_curvature[c]))) for c in range(7)
        ])
        decomposition_roundoff = full_residual - reconstruction
        scale = (np.abs(fd) + np.abs(k_optical_h) + np.abs(k_optical_d) +
                 np.abs(k_jvp_h) + np.abs(k_jvp_d) +
                 np.abs(content_curvature) + np.abs(diameter_curvature))
        bound = 32 * np.finfo(np.float64).eps * scale + 16 * np.finfo(np.float64).tiny
        require(np.isfinite(full_residual).all() and
                np.all(np.abs(decomposition_roundoff) <= bound),
                "signed FD-KJG decomposition")
        realized.append({"h": h, "relative_qi": dq / qi, "relative_raw_ni": dn / ni,
                         "optical_secant_minus_jvp": [secant[0] - wanted[0], secant[1] - wanted[1]],
                         "channel_ids": parent_audit["channels"],
                         "bt_fd": fd.tolist(), "k_optical_secant": k_optical.tolist(),
                         "k_profile_jvp": k_jvp.tolist(),
                         "bt_fd_minus_optical_k": optical_residual.tolist(),
                         "content_curvature_k": content_curvature.tolist(),
                         "diameter_curvature_k": diameter_curvature.tolist(),
                         "bt_fd_minus_profile_jvp_k": full_residual.tolist(),
                         "decomposition_roundoff": decomposition_roundoff.tolist(),
                         "max_abs_bt_fd_minus_profile_jvp_k": float(np.max(np.abs(full_residual)))})
    print(json.dumps({"status": "PROFILE_JVP_REPLAY_PASSED", "scientific_status": "INCONCLUSIVE",
                      "native_ijk": [164, 242, 21], "rttov_row": TARGET_ROW,
                      "baseline": {"hydro7_g_m3": h0, "deff7_um": d0, "rho_d": rho},
                      "directions": results, "real4_secants": realized}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
