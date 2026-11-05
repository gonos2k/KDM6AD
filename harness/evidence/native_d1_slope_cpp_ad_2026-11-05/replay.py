#!/usr/bin/env python3
"""Replay the archived C++ snow/graupel slope → D1 → ProgB stage graph."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

import torch

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from oracle.kdm6.progb import default_progb_params, progb_param_torch  # noqa: E402
from oracle.kdm6.slope import default_slope_params, slope_kdm6_torch  # noqa: E402
from oracle.kdm6.thermo import (  # noqa: E402
    compute_denfac,
    compute_work2_venfac,
    default_thermo_params,
)

PARENT = REPO / "harness/evidence/native_d1_upstream_cpp_ad_2026-11-04"
PARENT_REPLAY_SHA = "5d6eb02407cee56cc90db84f869253a68c0f155fafe88f1ec7e8141dddcaaafa"
BUILD_SHA = "15221c9fa9405136f445b79ce7239f13ff28899024b4352b6d34263f03a80c67"
RESULTS_SHA = "877fe28891466b42c6cae411946f52663f37f65d681d03b1506dab6ef55fd830"
SLOPE_FIELDS = (
    "n0sfac",
    "rslope_s",
    "rslope2_s",
    "rslopeb_s",
    "rslopemu_s",
    "rslope_g",
    "rslope2_g",
    "rslopeb_g",
    "rslopemu_g",
)
INPUTS = ("qv", "t", "qg", "brs", "p", "qs")
DIRECTIONS = {
    **{
        name: (field, steps)
        for name, (field, steps) in (
            ("relative_qv16", ("qv", (0.1, 0.01, 0.001))),
            ("absolute_t16", ("t", (0.1, 0.01, 0.001))),
            ("relative_qg16", ("qg", (1e-5, 1e-6, 1e-7))),
            ("relative_brs_pre16", ("brs", (1e-5, 1e-6, 1e-7))),
            ("relative_p16", ("p", (0.01, 0.001, 0.0001))),
        )
    },
    "relative_qs16": ("qs", (0.01, 0.001, 0.0001)),
}


def need(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError(why)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def parent_module():
    need(
        sha((PARENT / "replay.py").read_bytes()) == PARENT_REPLAY_SHA,
        "pinned upstream parent replay",
    )
    spec = importlib.util.spec_from_file_location(
        "native_slope_parent", PARENT / "replay.py"
    )
    need(spec is not None and spec.loader is not None, "parent upstream replay import")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_and_runs(upstream) -> dict:
    raw = (HERE / "raw/cpp_build_receipt.json").read_bytes()
    need(sha(raw) == BUILD_SHA, "pinned slope C++ build receipt")
    receipt = upstream.parse_json(raw)
    parent_native = upstream.parse_json(
        upstream.pinned("raw/native_build_receipt.json")
    )
    need(
        receipt["schema"] == "kdm6.native_d1_slope_cpp_ad_build.v1"
        and receipt["run_exit_code"] == 0
        and receipt["build_type"] == "Debug"
        and "-ffp-contract=off" in receipt["cxx_flags"]
        and "NDEBUG" not in receipt["cxx_flags"]
        and receipt["torch_version"] == "2.13.0",
        "slope C++ build contract",
    )
    need(
        receipt["native_archive_sha256"] == parent_native["archive_sha256"]
        and receipt["native_slope_object_sha256"]
        == parent_native["object_sha256"]["slope.cpp.o"]
        and receipt["parent_native_build_receipt_sha256"]
        == sha(upstream.pinned("raw/native_build_receipt.json"))
        and receipt["input_capture_sha256"] == sha(upstream.pinned(upstream.CAPTURE))
        and receipt["output_sha256"] == OUTPUT_SHA,
        "slope C++ archive/object/input/output lineage",
    )
    expected_paths = {
        "cpp/main.cpp",
        "cpp/CMakeLists.txt",
        "libtorch/src/slope.cpp",
        "oracle/kdm6/slope.py",
        "executed_cpp/slope.cpp",
        "oracle_snapshot/slope.py",
    }
    need(set(receipt["source_sha256"]) == expected_paths, "slope source inventory")
    for name, digest in receipt["source_sha256"].items():
        root = REPO if name.startswith(("libtorch/", "oracle/kdm6/")) else HERE
        need(
            sha((root / name).read_bytes()) == digest,
            "pinned slope producer source: " + name,
        )
    need(
        receipt["native_slope_source_sha256"]
        == receipt["source_sha256"]["libtorch/src/slope.cpp"]
        == receipt["source_sha256"]["executed_cpp/slope.cpp"]
        and receipt["source_sha256"]["oracle/kdm6/slope.py"]
        == receipt["source_sha256"]["oracle_snapshot/slope.py"],
        "native slope source identity",
    )
    metadata = receipt["build_metadata_sha256"]
    need(
        {Path(name).name for name in metadata}
        == {"CMakeCache.txt", "flags.make", "link.txt"}
        and len(metadata) == 3,
        "slope C++ metadata inventory",
    )
    for name, digest in metadata.items():
        need(
            sha((HERE / "build_metadata" / Path(name).name).read_bytes()) == digest,
            "slope C++ build metadata: " + name,
        )
    need(
        set(receipt["torch_libraries_sha256"])
        == {"libc10.dylib", "libtorch.dylib", "libtorch_cpu.dylib"}
        and all(len(x) == 64 for x in receipt["torch_libraries_sha256"].values())
        and len(receipt["runtime_linked_libraries"]) >= 3,
        "slope C++ library inventory",
    )
    return {
        "native_archive_sha256": receipt["native_archive_sha256"],
        "native_slope_object_sha256": receipt["native_slope_object_sha256"],
        "cpp_executable_sha256": receipt["executable_sha256"],
        "cpp_output_sha256": OUTPUT_SHA,
    }


def vector(raw: object, size: int, why: str) -> list[float]:
    need(type(raw) is list and len(raw) == size, why + " shape")
    need(
        all(type(x) in (int, float) and math.isfinite(x) for x in raw), why + " finite"
    )
    return [float(x) for x in raw]


def inputs_at(fields: dict, parent, k: int) -> dict[str, float]:
    v = parent.value
    return {
        "qv": v(fields, parent.ENTRY, "qv", k),
        "t": v(fields, parent.ENTRY, "t", k),
        "qg": v(fields, parent.ENTRY, "qg", k),
        "brs": v(fields, parent.ENTRY, "brs", k),
        "p": v(fields, parent.ENTRY, "p", k),
        "qs": v(fields, "d1_melt_producer", "qs", k),
    }


def slope39(fields: dict, parent) -> dict:
    v = parent.value

    def tensor(stage: str, name: str) -> torch.Tensor:
        return torch.tensor(
            [[v(fields, stage, name, k) for k in range(39)]], dtype=torch.float64
        )

    qg = tensor(parent.ENTRY, "qg")
    t = tensor(parent.ENTRY, "t")
    den = tensor(parent.ENTRY, "den")
    pg = progb_param_torch(
        qg, tensor(parent.ENTRY, "brs"), params=default_progb_params()
    )
    slope = slope_kdm6_torch(
        qr=tensor("d1_state_entry", "qr"),
        qs=tensor("d1_melt_producer", "qs"),
        qg=qg,
        qi=tensor("d1_melt_producer", "qi"),
        nr=tensor("d1_state_entry", "nr"),
        ni=tensor("d1_melt_producer", "ni"),
        den=tensor(parent.ENTRY, "dend"),
        denfac=compute_denfac(den, params=default_thermo_params()),
        t=t,
        pidn0g=pg.pidn0g,
        pvtg=pg.pvtg,
        bvtg=pg.bvtg,
        rslopegbmax=pg.rslopegbmax,
        params=default_slope_params(),
    )
    maxima = {name: 0.0 for name in SLOPE_FIELDS}
    for name in SLOPE_FIELDS:
        out = getattr(slope, name)
        for k in range(39):
            ulps = parent.check_reference_word(
                fields[("d1_melt_producer", name, k)]["raw_hex"],
                out[0, k].item(),
                "independent 39-level slope: " + name,
                max_ulps=64,
            )
            maxima[name] = max(maxima[name], ulps)
    return {"levels": 39, "max_oracle_ulp_by_field": maxima}


def dynamic(fields: dict, upstream, progb_parent, state_parent, producer):
    base = progb_parent.make_d1_base(fields, state_parent)
    v = upstream.value
    k = upstream.TARGET
    tp, pp, sp = default_thermo_params(), default_progb_params(), default_slope_params()
    fixed = {
        "qr": v(fields, "d1_state_entry", "qr", k),
        "nr": v(fields, "d1_state_entry", "nr", k),
        "qi": v(fields, "d1_melt_producer", "qi", k),
        "ni": v(fields, "d1_melt_producer", "ni", k),
        "den": v(fields, upstream.ENTRY, "den", k),
        "dend": v(fields, upstream.ENTRY, "dend", k),
    }

    def shaped(x: torch.Tensor) -> torch.Tensor:
        return x.reshape((1, 1))

    def scalar(x: float) -> torch.Tensor:
        return torch.tensor([[x]], dtype=torch.float64)

    def fn(qv, t, qg, brs, p, qs):
        entry = progb_param_torch(shaped(qg), shaped(brs), params=pp)
        den = scalar(fixed["den"])
        slope = slope_kdm6_torch(
            qr=scalar(fixed["qr"]),
            qs=shaped(qs),
            qg=shaped(qg),
            qi=scalar(fixed["qi"]),
            nr=scalar(fixed["nr"]),
            ni=scalar(fixed["ni"]),
            den=scalar(fixed["dend"]),
            denfac=compute_denfac(den, params=tp),
            t=shaped(t),
            pidn0g=entry.pidn0g,
            pvtg=entry.pvtg,
            bvtg=entry.bvtg,
            rslopegbmax=entry.rslopegbmax,
            params=sp,
        )
        work2 = compute_work2_venfac(shaped(p), shaped(t), den, params=tp).reshape(())
        dynamic_base = {
            **base,
            "work2": work2,
            "precg2": entry.precg2.reshape(()),
            "rhox": entry.rhox.reshape(()),
            "brs_before": entry.bg.reshape(()),
            "p": p,
            **{name: getattr(slope, name).reshape(()) for name in SLOPE_FIELDS},
        }
        d1, _ = state_parent.torch_state(
            dynamic_base, producer, qv, t, qs, qg, entry.rhox.reshape(())
        )
        post, _ = progb_parent.torch_progb(d1[7], d1[14])
        return torch.stack(
            (
                work2,
                entry.precg2.reshape(()),
                entry.rhox.reshape(()),
                entry.bg.reshape(()),
                entry.avtg.reshape(()),
                entry.bvtg.reshape(()),
                d1[0],
                d1[1],
                d1[7],
                d1[14],
                d1[13],
                post[3],
                post[4],
                post[5],
                post[6],
                d1[15],
                *(getattr(slope, name).reshape(()) for name in SLOPE_FIELDS),
            )
        )

    return fn


def verify_output(
    raw: bytes, fields: dict, upstream, progb_parent, state_parent, producer
) -> dict:
    saved = upstream.parse_json(raw)
    order = list(upstream.OUTPUT_ORDER) + list(SLOPE_FIELDS)
    need(saved["schema"] == "kdm6.native_d1_slope_cpp_ad.v1", "slope C++ schema")
    need(
        saved["output_order"] == order and set(saved["directions"]) == set(DIRECTIONS),
        "slope C++ inventory",
    )
    base = vector(saved["baseline"]["values"], len(order), "slope C++ baseline")
    words = saved["baseline"]["raw_hex"]
    need(type(words) is list and len(words) == len(base), "slope baseline words")
    old = upstream.parse_json(upstream.pinned("raw/cpp_result.json"))
    for i, got in enumerate(base):
        expected = (
            old["baseline"]["raw_hex"][i]
            if i < 16
            else fields[("d1_melt_producer", SLOPE_FIELDS[i - 16], upstream.TARGET)][
                "raw_hex"
            ]
        )
        need(
            words[i] == upstream.word(got) == expected,
            "actual C++ slope graph/native raw bits: " + order[i],
        )
    fn = dynamic(fields, upstream, progb_parent, state_parent, producer)
    x0 = inputs_at(fields, upstream, upstream.TARGET)
    x = tuple(torch.tensor(x0[name], dtype=torch.float64) for name in INPUTS)
    py0 = vector(fn(*x).tolist(), len(order), "Python slope baseline")
    baseline_ulps = 0.0
    for i, expected in enumerate(py0):
        baseline_ulps = max(
            baseline_ulps,
            upstream.check_reference_word(
                words[i],
                expected,
                "Python/C++ slope baseline: " + order[i],
                max_ulps=64,
            ),
        )
    maxima = {
        "baseline_ulp": baseline_ulps,
        "jvp_abs": 0.0,
        "endpoint_ulp": 0.0,
        "fd_normalized": 0.0,
    }
    for name, (field, steps) in DIRECTIONS.items():
        section = saved["directions"][name]
        seed = 1.0 if field == "t" else x0[field]
        need(
            upstream.word(section["seed"]) == upstream.word(seed),
            "slope direction seed",
        )
        jvp = vector(section["jvp"], len(order), "slope C++ JVP")
        tangent = tuple(
            xi
            if key == field and field != "t"
            else torch.ones_like(xi)
            if key == field
            else torch.zeros_like(xi)
            for key, xi in zip(INPUTS, x)
        )
        _, py_jvp = torch.func.jvp(fn, x, tangent)
        for i, expected in enumerate(py_jvp.tolist()):
            err = abs(jvp[i] - expected)
            tol = 1e-10 * abs(expected) + max(2e-18, 0.25 * math.ulp(base[i]))
            need(err <= tol, "C++/Python slope JVP: " + name + "/" + order[i])
            maxima["jvp_abs"] = max(maxima["jvp_abs"], err)
        weights = (
            2.0,
            -3.0,
            5.0,
            7.0,
            -11.0,
            13.0,
            -17.0,
            19.0,
            -23.0,
            29.0,
            -31.0,
            37.0,
            -41.0,
            43.0,
            -47.0,
            53.0,
            -59.0,
            61.0,
            -67.0,
            71.0,
            -73.0,
            79.0,
            -83.0,
            89.0,
            -97.0,
        )
        products = [w * y for w, y in zip(weights, jvp)]
        dot = math.fsum(products)
        u = 2.0**-53
        gamma = len(products) * u / (1 - len(products) * u)
        tol = gamma * math.fsum(map(abs, products)) + 2 * math.ulp(dot)
        need(
            abs(section["jvp_dot"] - dot) <= tol
            and abs(section["vjp_dot"] - dot) <= tol,
            "slope C++ saved JVP/VJP dot versus verified tangent: " + name,
        )
        need(
            set(map(float, section["finite_differences"])) == set(steps),
            "slope FD steps",
        )
        for h_text, trial in section["finite_differences"].items():
            h = float(h_text)
            hi = vector(trial["high"], len(order), "slope FD high")
            lo = vector(trial["low"], len(order), "slope FD low")
            fd = vector(trial["fd"], len(order), "slope FD secant")
            upper, lower = x0[field] + seed * h, x0[field] - seed * h
            gap = (upper - lower) / seed
            need(
                upstream.word(trial["gap"]) == upstream.word(gap),
                "slope realized FD gap",
            )
            for got, endpoint in ((hi, upper), (lo, lower)):
                xx = {**x0, field: endpoint}
                py = vector(
                    fn(
                        *(torch.tensor(xx[n], dtype=torch.float64) for n in INPUTS)
                    ).tolist(),
                    len(order),
                    "independent slope endpoint",
                )
                need(
                    xx["qs"] > 1e-9 and xx["qg"] > 1e-9 and xx["t"] > 273.15,
                    "same snow/graupel/warm gate",
                )
                need(
                    800 < py[2] < 900 and 800 < py[11] < 900,
                    "same entry/postmelt ProgB segment",
                )
                need(
                    -xx["qs"] < py[6] < 0 and -xx["qg"] < py[7] < 0,
                    "same open snow/graupel melt cap",
                )
                need(py[16] == 1.0, "same snow-intercept floor branch")
                for i, expected in enumerate(py):
                    ulps = upstream.check_reference_word(
                        upstream.word(got[i]),
                        expected,
                        "independent slope C++ FD endpoint: " + name + "/" + order[i],
                        max_ulps=64,
                    )
                    maxima["endpoint_ulp"] = max(maxima["endpoint_ulp"], ulps)
            for i, out in enumerate(order):
                need(
                    abs(fd[i] - (hi[i] - lo[i]) / gap) <= 2 * math.ulp(fd[i]),
                    "saved slope FD arithmetic: " + name + "/" + out,
                )
                error = abs(fd[i] - jvp[i])
                bound = (
                    10 * h * h * abs(jvp[i])
                    + 128 * math.ulp(base[i]) / abs(gap)
                    + 1e-18
                )
                need(error <= bound, "slope FD/JVP: " + name + "/" + out)
                maxima["fd_normalized"] = max(
                    maxima["fd_normalized"], error / max(1, abs(jvp[i]))
                )
    crossing = saved["qg_cross_cap"]
    crossing_values = {}
    for side, qg in (("high", x0["qg"] * 1.0001), ("low", x0["qg"] * 0.9999)):
        got = vector(crossing[side], len(order), "slope QG cap crossing " + side)
        xx = {**x0, "qg": qg}
        py = vector(
            fn(*(torch.tensor(xx[n], dtype=torch.float64) for n in INPUTS)).tolist(),
            len(order),
            "independent slope cap crossing " + side,
        )
        for i, expected in enumerate(py):
            maxima["endpoint_ulp"] = max(
                maxima["endpoint_ulp"],
                upstream.check_reference_word(
                    upstream.word(got[i]),
                    expected,
                    "slope C++ cap crossing: " + side + "/" + order[i],
                    max_ulps=64,
                ),
            )
        crossing_values[side] = {"entry_rhox": got[2], "post_rhox": got[11]}
    need(
        crossing_values["high"] == {"entry_rhox": 900.0, "post_rhox": 900.0}
        and 800 < crossing_values["low"]["entry_rhox"] < 900
        and 800 < crossing_values["low"]["post_rhox"] < 900,
        "separate QG upper-cap crossing",
    )
    return {
        "baseline_raw_equal": len(order),
        "directions": list(DIRECTIONS),
        "qg_crossing": crossing_values,
        **maxima,
    }


def replay(
    *, output_override: bytes | None = None, output_sha: str | None = None
) -> dict:
    upstream = parent_module()
    parent_result = upstream.replay()
    need(parent_result["scientific_status"] == "INCONCLUSIVE", "upstream parent replay")
    progb_parent = upstream.parent_module()
    state_parent = progb_parent.parent_module()
    producer = state_parent.parent_module()
    source = source_and_runs(upstream)
    fields = upstream.load_capture(upstream.pinned(upstream.CAPTURE), progb_parent)
    slopes = slope39(fields, upstream)
    if output_override is None:
        raw = (HERE / "raw/cpp_result.json").read_bytes()
        need(sha(raw) == OUTPUT_SHA, "pinned actual slope C++ output")
    else:
        need(
            output_sha is not None and sha(output_override) == output_sha,
            "test slope C++ output SHA",
        )
        raw = output_override
    verified = verify_output(
        raw, fields, upstream, progb_parent, state_parent, producer
    )
    result = {
        "schema": "kdm6.native_d1_slope_cpp_ad_replay.v1",
        "scientific_status": "INCONCLUSIVE",
        "physical_unit_status": "INCONCLUSIVE",
        "parent_cpp_baseline_raw_equal": parent_result["verified_cpp"][
            "cpp_baseline_raw_bit_equal_outputs"
        ],
        "source_and_runs": source,
        "slope39": slopes,
        "verified_cpp": verified,
    }
    if output_override is None:
        saved_raw = (HERE / "results.json").read_bytes()
        need(sha(saved_raw) == RESULTS_SHA, "pinned slope replay result")
        saved = upstream.parse_json(saved_raw)
        need(
            all(
                saved[key] == result[key]
                for key in (
                    "schema",
                    "scientific_status",
                    "physical_unit_status",
                    "parent_cpp_baseline_raw_equal",
                    "source_and_runs",
                )
            )
            and saved["slope39"]["levels"] == result["slope39"]["levels"]
            and all(
                saved["verified_cpp"][key] == result["verified_cpp"][key]
                for key in ("baseline_raw_equal", "directions", "qg_crossing")
            ),
            "saved slope replay stable results",
        )
    return result


OUTPUT_SHA = "6131cbef647e97373f7a78055a9bbf2dabb4ee81cf377a1ee8c7430f97aeb39d"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output is None:
        result = replay()
    else:
        raw = args.output.read_bytes()
        result = replay(output_override=raw, output_sha=sha(raw))
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
