#!/usr/bin/env python3
"""Offline numerical verification for the pinned serialized optical experiment.

Input bundle layout and provenance requirements are documented in README.md.
This program does not call RTTOV and does not claim an independent VJP.
"""

import argparse
import gzip
import sys
import tempfile
import hashlib
import json
from fractions import Fraction
from pathlib import Path

import numpy as np

HS = (1e-3, 1e-4, 1e-5, 1e-6)
CORNERS = ("GG", "PP")
MODES = ("hydro", "deff", "mixed")
RUNNER_SHA = "20bcd57f001d2a63fbb4d70a9b64029622de50576d2dd7174baac5f4972099ca"
LAUNCH_SHA = "f21949d6a8a845ee54c07b3c9bb881101c30e5c41e79a8eae4d946e7cb04b7a5"
HYDROTABLE_SHA = "fdbe99ea68fd750e146fb78a798ab72b8568e4a3d545a2d847263cb374746890"
PINS_SHA = "3287e676da020da12b5de78fd5b7cb8c4348b275d6ca25677587c313943b6585"
UNIT_ROUNDOFF = Fraction(1, 2**53)
HALF_MIN_SUBNORMAL = Fraction(1, 2**1075)
MIN_NORMAL = Fraction.from_float(sys.float_info.min)
MAX_FINITE = Fraction.from_float(sys.float_info.max)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text())


def check(cond, message):
    if not cond:
        raise ValueError(message)


def verify_sources(source_root=None):
    root = (
        Path(source_root)
        if source_root is not None
        else Path(__file__).resolve().parent
    )
    manifest = load(root / "source_manifest.json")
    check(
        manifest.get("schema") == "east-optical-derivative-sources-v1", "source schema"
    )
    files = manifest.get("files")
    expected = {"verify.py", "export.py", "test_verify.py", "README.md"}
    check(isinstance(files, dict) and set(files) == expected, "source inventory")
    for name in sorted(expected):
        check(sha(root / name) == files[name], f"source hash: {name}")


def arr(path, keys):
    with np.load(path, allow_pickle=False) as data:
        check(set(data.files) == set(keys), f"{path}: fields")
        out = {key: np.asarray(data[key]) for key in keys}
    for value in out.values():
        check(
            value.dtype == np.float64 and np.isfinite(value).all(),
            f"{path}: non-finite or non-f64",
        )
    return out


def same(a, b):
    return a.shape == b.shape and np.array_equal(a.view(np.uint64), b.view(np.uint64))


def gamma(operations):
    """Conservative nearest-binary64 relative bound for a serial path."""
    n_u = operations * UNIT_ROUNDOFF
    return n_u / (1 - n_u)


def contract_jvp(kh, kd, vh, vd):
    """Replay the runner's reduction, kept replaceable for order-portability tests."""
    return np.einsum("pcl,pl->pc", kh, vh) + np.einsum("pcl,pl->pc", kd, vd)


def exact_contraction_reference(kh, kd, vh, vd, cot):
    """Exact contractions of the *stored* binary64 K, direction and cotangent.

    Each field has at most six nonzero direction layers per profile. A product
    plus at most five field additions and one cross-field addition is bounded
    by gamma(8). Dot bounds cover the 70-output lhs and 660-layer rhs serial
    reduction paths. Small absolute allowances cover gradual subnormal results.
    No bound here covers errors in the RTTOV K or in constructing the inputs.
    """
    references = [[Fraction(0) for _ in range(7)] for _ in range(10)]
    scales = [[Fraction(0) for _ in range(7)] for _ in range(10)]
    exact_dot = Fraction(0)
    dot_scale = Fraction(0)
    for p in range(10):
        active_h = np.flatnonzero(vh[p])
        active_d = np.flatnonzero(vd[p])
        check(len(active_h) <= 6 and len(active_d) <= 6, "roundoff term inventory")
        for matrix, direction, active in (
            (kh, vh, active_h),
            (kd, vd, active_d),
        ):
            for layer in active:
                weighted = [
                    Fraction.from_float(float(cot[p, channel]))
                    * Fraction.from_float(float(matrix[p, channel, layer]))
                    for channel in range(7)
                ]
                for term in weighted:
                    check(
                        term == 0 or MIN_NORMAL <= abs(term) <= MAX_FINITE,
                        "rhs cotangent-K intermediate is subnormal or overflowing",
                    )
                channel_sum = sum(weighted, Fraction(0))
                check(
                    channel_sum == 0 or MIN_NORMAL <= abs(channel_sum) <= MAX_FINITE,
                    "rhs channel contraction is subnormal or overflowing",
                )
                propagated = channel_sum * Fraction.from_float(
                    float(direction[p, layer])
                )
                check(
                    propagated == 0 or MIN_NORMAL <= abs(propagated) <= MAX_FINITE,
                    "rhs direction product is subnormal or overflowing",
                )
        for channel in range(7):
            weight = Fraction.from_float(float(cot[p, channel]))
            terms = [
                Fraction.from_float(float(kh[p, channel, layer]))
                * Fraction.from_float(float(vh[p, layer]))
                for layer in active_h
            ]
            terms.extend(
                Fraction.from_float(float(kd[p, channel, layer]))
                * Fraction.from_float(float(vd[p, layer]))
                for layer in active_d
            )
            for term in terms:
                check(
                    term == 0 or MIN_NORMAL <= abs(term) <= MAX_FINITE,
                    "roundoff reference has a subnormal or overflowing product",
                )
                weighted = weight * term
                check(
                    weighted == 0 or MIN_NORMAL <= abs(weighted) <= MAX_FINITE,
                    "dot reference has a subnormal or overflowing product",
                )
            reference = sum(terms, Fraction(0))
            scale = sum((abs(term) for term in terms), Fraction(0))
            check(
                abs(reference) <= MAX_FINITE and scale <= MAX_FINITE,
                "roundoff reference exceeds binary64 range",
            )
            references[p][channel] = reference
            scales[p][channel] = scale
            exact_dot += weight * reference
            dot_scale += abs(weight) * scale
    check(
        abs(exact_dot) <= MAX_FINITE and dot_scale <= MAX_FINITE,
        "dot reference exceeds binary64 range",
    )
    return references, scales, exact_dot, dot_scale


def within_exact_bound(value, reference, bound, message):
    check(np.isfinite(value), message + ": nonfinite value")
    difference = abs(Fraction.from_float(float(value)) - reference)
    check(difference <= bound, message)
    return float(difference)


def verify(root):
    verify_sources()
    manifest = load(root / "packet.json")
    check(manifest["schema"] == "east-optical-derivative-packet-v1", "schema")
    files = manifest["files"]
    for name, digest in files.items():
        path = Path(name)
        check(
            not path.is_absolute()
            and ".." not in path.parts
            and (root / path).is_file(),
            "unsafe/missing packet path",
        )
        check(sha(root / path) == digest, f"packet hash: {name}")
    expected = {
        "runner.py",
        "locked_launch.py",
        "pins.json",
        "preflight.json",
        "summary.json",
        "attempt.json",
    }
    expected.update(f"{c}_baseline.npz" for c in CORNERS)
    keys = [f"{c}_K" for c in CORNERS]
    keys += [
        f"{c}_{m}_{i}_{s}"
        for c in CORNERS
        for m in MODES
        for i in range(4)
        for s in ("plus", "minus")
    ]
    expected.update(
        f"{key}/{f}"
        for key in keys
        for f in ("receipt.json", "values.npz", "direct_radiance.txt")
    )
    expected.update(
        f"{c}_K/{f}" for c in CORNERS for f in ("k_radiance.txt", "profiles_k.txt.gz")
    )
    check(set(files) == expected, "packet inventory")
    check(
        files["runner.py"] == RUNNER_SHA
        and files["pins.json"] == PINS_SHA
        and files["locked_launch.py"] == LAUNCH_SHA,
        "locked sources",
    )
    pins = load(root / "pins.json")
    sources = pins["sources"]
    table = [
        digest
        for path, digest in sources.items()
        if path.endswith("/hydrotable_visir/rttov_hydrotable_gkompsat2_1_ami.dat")
    ]
    check(table == [HYDROTABLE_SHA], "hydrotable pin")
    for suffix, packet_name in (
        ("/preflight.json", "preflight.json"),
        ("/GG/result.npz", "GG_baseline.npz"),
        ("/PP/result.npz", "PP_baseline.npz"),
    ):
        matches = [digest for path, digest in sources.items() if path.endswith(suffix)]
        check(
            len(matches) == 1 and matches[0] == files[packet_name],
            f"source pin: {packet_name}",
        )
    project = Path(__file__).resolve().parents[3]
    for relative in (
        "oracle/kdm6/obs/rttov_runner.py",
        "oracle/kdm6/obs/_rttov_reference/rttov_ascii.py",
    ):
        matches = [
            digest for path, digest in sources.items() if path.endswith("/" + relative)
        ]
        check(
            len(matches) == 1 and sha(project / relative) == matches[0],
            f"parser source pin: {relative}",
        )
    sys.path.insert(0, str(project))
    from oracle.kdm6.obs.rttov_runner import (
        parse_rttov_radiance,
        parse_rttov_profiles_k,
    )
    from oracle.kdm6.obs._rttov_reference.rttov_ascii import parse_rttov_ascii_blocks

    attempt = load(root / "attempt.json")
    check(
        attempt["runner_sha256"] == RUNNER_SHA
        and attempt["manifest_sha256"] == PINS_SHA,
        "attempt pin",
    )
    check(
        attempt["planned_calls"]
        == pins["calls"]
        == {
            "subprocesses": 50,
            "direct_mode_paths": 50,
            "K_mode_paths": 2,
            "direct_only_fd_subprocesses": 48,
            "combined_baseline_K_subprocesses": 2,
        },
        "planned calls",
    )
    check(set(pins["cases"]) == set(keys), "prepared case inventory")
    report = load(root / "preflight.json")
    summary = load(root / "summary.json")
    check(
        summary["subprocesses"] == 50
        and summary["direct_mode_paths"] == 50
        and summary["K_mode_paths"] == 2
        and summary["direct_only_fd_subprocesses"] == 48
        and summary["combined_baseline_K_subprocesses"] == 2,
        "summary calls",
    )
    data = {}
    for key in keys:
        receipt = load(root / key / "receipt.json")
        k = key.endswith("_K")
        check(
            receipt["input_hashes"] == pins["cases"][key]
            and receipt["value_sha256"] == files[f"{key}/values.npz"],
            f"{key}: receipt",
        )
        check(
            receipt["mode"] == ("K" if k else "direct") and receipt["do_k"] is k,
            f"{key}: mode",
        )
        raw = parse_rttov_radiance(root / key / "direct_radiance.txt", nchannels=7)
        check(
            raw["nprofiles"] == 10 and not np.any(raw["rad_quality"]),
            f"{key}: raw direct quality/count",
        )
        data[key] = arr(
            root / key / "values.npz",
            ("bt", "hydro7", "deff7", "ratio", "total", "direct_bt") if k else ("bt",),
        )
        check(data[key]["bt"].shape == (10, 7), f"{key}: BT shape")
    findings = {}
    for c in CORNERS:
        base = data[f"{c}_K"]
        with np.load(root / f"{c}_baseline.npz", allow_pickle=False) as f:
            preserved = np.asarray(f["bt"])
            check(
                np.asarray(f["quality"]).shape == (10, 7) and not np.any(f["quality"]),
                "baseline quality",
            )
        check(
            preserved.dtype == np.float64
            and same(preserved, base["direct_bt"])
            and same(base["bt"], base["direct_bt"]),
            f"{c}: baseline K incompatibility",
        )
        kh, kd = base["hydro7"], base["deff7"]
        check(
            kh.ndim == 3 and kh.shape[:2] == (10, 7) and kd.shape == kh.shape,
            "K slot 7 shape",
        )
        check(
            base["ratio"].shape == (10, 7) and base["total"].shape == (10, 7),
            "K coordinate fields",
        )
        raw_rad = root / f"{c}_K/k_radiance.txt"
        raw_k_rad = parse_rttov_radiance(raw_rad, nchannels=7)
        check(
            raw_k_rad["nprofiles"] == 10 and not np.any(raw_k_rad["rad_quality"]),
            "raw K quality/count",
        )
        total = np.asarray(parse_rttov_ascii_blocks(raw_rad)["RADIANCE%TOTAL"]).reshape(
            10, 7
        )
        check(same(total, base["total"]), "raw K total mismatch")
        with tempfile.TemporaryDirectory() as temp:
            raw_profile = Path(temp) / "profiles_k.txt"
            raw_profile.write_bytes(
                gzip.decompress((root / f"{c}_K/profiles_k.txt.gz").read_bytes())
            )
            raw_k, nprofiles = parse_rttov_profiles_k(raw_profile, nchannels=7)
        check(nprofiles == 10, "raw K profile count")
        nlay = kh.shape[-1]
        for field, ntype, stored in (("HYDRO", 8, kh), ("HYDRO_DEFF", 7, kd)):
            native = np.asarray(raw_k[field])
            check(
                native.shape == (10, 7, ntype * nlay),
                f"{field}: native type-major shape",
            )
            ice = native.reshape(10, 7, ntype, nlay)[:, :, 6, :]
            check(
                np.array_equal(ice * base["ratio"][:, :, None], stored),
                f"{field}: raw slot-7 K mismatch",
            )
        rows = report["cases"][c]["checks"]
        check(report["cases"][c]["active_rows"] == 42, "active row count")
        modes = {}
        for mode in MODES:
            steps = []
            for i, h in enumerate(HS):
                selected = [r for r in rows if r["field"] == mode and r["h"] == h]
                check(
                    len(selected) == 42
                    and len({(r["profile"], r["layer_zero_based"]) for r in selected})
                    == 42
                    and all(r["fraction"] > 0 for r in selected),
                    "active rows",
                )
                knot_crossings = sum(
                    min(r["deff_plus"], r["deff_minus"])
                    < 20.0
                    < max(r["deff_plus"], r["deff_minus"])
                    for r in selected
                )
                vh, vd = np.zeros((10, kh.shape[-1])), np.zeros((10, kh.shape[-1]))
                for r in selected:
                    p, layer = r["profile"] - 1, r["layer_zero_based"]
                    check(0 <= p < 10 and 0 <= layer < kh.shape[-1], "row index")
                    vh[p, layer] = (r["content_plus"] - r["content_minus"]) / (2 * h)
                    vd[p, layer] = (r["deff_plus"] - r["deff_minus"]) / (2 * h)
                plus = data[f"{c}_{mode}_{i}_plus"]["bt"]
                minus = data[f"{c}_{mode}_{i}_minus"]["bt"]
                fd = (plus - minus) / (2 * h)
                jvp = contract_jvp(kh, kd, vh, vd)
                cot = np.where(np.arange(70).reshape(10, 7) % 2 == 0, 1.0, -1.0) / 70
                lhs = float(np.sum(cot * jvp))
                rhs = float(
                    np.sum(vh * np.einsum("pc,pcl->pl", cot, kh))
                    + np.sum(vd * np.einsum("pc,pcl->pl", cot, kd))
                )
                saved = summary["comparisons"][c]["steps"][f"{mode}_{h:g}"]
                saved_fd = np.asarray(saved["fd"], dtype=np.float64)
                saved_jvp = np.asarray(saved["jvp"], dtype=np.float64)
                check(
                    same(fd, saved_fd) and saved_jvp.shape == jvp.shape,
                    "FD or JVP shape/computation mismatch",
                )
                references, scales, exact_dot, dot_scale = exact_contraction_reference(
                    kh, kd, vh, vd, cot
                )
                saved_jvp_roundoff = []
                replay_jvp_roundoff = []
                jvp_roundoff_bounds = []
                for profile in range(10):
                    for channel in range(7):
                        bound = (
                            gamma(8) * scales[profile][channel]
                            + 20 * HALF_MIN_SUBNORMAL
                        )
                        saved_jvp_roundoff.append(
                            within_exact_bound(
                                saved_jvp[profile, channel],
                                references[profile][channel],
                                bound,
                                "saved JVP exceeds binary64 reduction bound",
                            )
                        )
                        replay_jvp_roundoff.append(
                            within_exact_bound(
                                jvp[profile, channel],
                                references[profile][channel],
                                bound,
                                "recomputed JVP exceeds binary64 reduction bound",
                            )
                        )
                        jvp_roundoff_bounds.append(float(bound))
                lhs_bound = gamma(80) * dot_scale + 200 * HALF_MIN_SUBNORMAL
                max_direction = max(
                    1.0, float(np.max(np.abs(vh))), float(np.max(np.abs(vd)))
                )
                rhs_bound = gamma(670) * dot_scale + (
                    2000 * HALF_MIN_SUBNORMAL * Fraction.from_float(max_direction)
                )
                saved_lhs = saved["dot_lhs"]
                saved_rhs = saved["dot_rhs"]
                saved_lhs_roundoff = within_exact_bound(
                    saved_lhs,
                    exact_dot,
                    lhs_bound,
                    "saved lhs dot exceeds binary64 reduction bound",
                )
                saved_rhs_roundoff = within_exact_bound(
                    saved_rhs,
                    exact_dot,
                    rhs_bound,
                    "saved rhs dot exceeds binary64 reduction bound",
                )
                replay_lhs_roundoff = within_exact_bound(
                    lhs,
                    exact_dot,
                    lhs_bound,
                    "recomputed lhs dot exceeds binary64 reduction bound",
                )
                replay_rhs_roundoff = within_exact_bound(
                    rhs,
                    exact_dot,
                    rhs_bound,
                    "recomputed rhs dot exceeds binary64 reduction bound",
                )
                steps.append(
                    {
                        "observed_20_micron_knot_crossing_rows": knot_crossings,
                        "algebraic_transpose_dot_abs_error": abs(saved_lhs - saved_rhs),
                        "arithmetic_replay": {
                            "saved_jvp_vs_exact_max_abs": max(saved_jvp_roundoff),
                            "recomputed_jvp_vs_exact_max_abs": max(replay_jvp_roundoff),
                            "saved_vs_recomputed_jvp_max_abs": float(
                                np.max(np.abs(saved_jvp - jvp))
                            ),
                            "jvp_roundoff_bound_max_abs": max(jvp_roundoff_bounds),
                            "saved_lhs_vs_exact_abs": saved_lhs_roundoff,
                            "saved_rhs_vs_exact_abs": saved_rhs_roundoff,
                            "recomputed_lhs_vs_exact_abs": replay_lhs_roundoff,
                            "recomputed_rhs_vs_exact_abs": replay_rhs_roundoff,
                            "lhs_roundoff_bound_abs": float(lhs_bound),
                            "rhs_roundoff_bound_abs": float(rhs_bound),
                            "saved_vs_recomputed_lhs_abs": abs(saved_lhs - lhs),
                            "saved_vs_recomputed_rhs_abs": abs(saved_rhs - rhs),
                            "method": "exact rational contraction of stored f64 operands; gamma(8) JVP, gamma(80/670) dot bounds under IEEE nearest with gradual underflow",
                        },
                        "h": h,
                        "max_abs_fd": float(np.max(np.abs(fd))),
                        "max_abs_error": float(np.max(np.abs(fd - saved_jvp))),
                        "max_abs_bt_difference": float(np.max(np.abs(plus - minus))),
                        "nonzero_bt_elements": int(np.count_nonzero(plus - minus)),
                        "fd": fd.tolist(),
                        "jvp": saved_jvp.tolist(),
                    }
                )
            modes[mode] = {
                "steps": steps,
                "adjacent_max_abs_fd_difference": [
                    float(
                        np.max(
                            np.abs(
                                np.asarray(steps[i]["fd"])
                                - np.asarray(steps[i + 1]["fd"])
                            )
                        )
                    )
                    for i in range(3)
                ],
            }
        findings[c] = modes
    return {
        "hydrotable_sha256": HYDROTABLE_SHA,
        "knot_diagnostic": "Crossings of 20 microns only; not a full lookup-branch audit or proof of causation.",
        "status": "INCONCLUSIVE",
        "reason": "Numerical values require signal and plateau review; zero differences never establish agreement.",
        "comparisons": findings,
        "limitations": [
            "Algebraic transpose is not an independent VJP.",
            "External linked library identity and execution-time captures require separate evidence.",
            "Fixed cloud fraction and serialized optical inputs only; no host-boundary or QNICE derivative, units or branch certification.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("packet", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.packet), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
