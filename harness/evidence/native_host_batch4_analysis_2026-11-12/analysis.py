#!/usr/bin/env python3
"""Analyze archived B=1 f64 directional FD; executes no model calls."""

import csv
import gzip
import hashlib
import io
import json
import math
import struct
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE.parent
PARENT = EVIDENCE / "native_host_batch3_shared_2026-11-12"
ANALYSIS = EVIDENCE / "native_host_analysis_batch_2026-11-12"
FIELDS = (
    "th",
    "qv",
    "qc",
    "qr",
    "qi",
    "qs",
    "qg",
    "nccn",
    "nc",
    "ni",
    "nr",
    "bg",
    "rho",
    "pii",
    "p",
    "delz",
)
SCALES = (1.0, 1e-3, 1e-3, 1e-3, 1e-3, 1e-3, 1e-3, 1e8, 1e8, 1e6, 1e6, 1e-6)
PINS = {
    PARENT
    / "raw/screening_raw.zip": "f682b42606d133b72b77e6a31ef0eef47a971a3e975f52a8b230229a7bf48088",
    PARENT
    / "screening_results.json": "2840221470d0a2690bf7d1efa896397f115bb6f166db8f9f8781c95348725853",
    PARENT
    / "stage_compare.json.gz": "df5c46ae1b9c22e78893f3a9ea01c330f10a0e5319cac9003536f9b77f907567",
    ANALYSIS
    / "f32_f64_diff.json.gz": "53449cd1e45e3632b3220b2db870be14595375f5906ff2715dc90e87ec0d6b5c",
    ANALYSIS
    / "reviewed_source/verify_state_forcing_ad.py.gz": "6a10f941f8eb3b96cc46c1df68c918eefcbe913a478c3921cfa450bae1384728",
}


def need(ok, msg):
    if not ok:
        raise ValueError(msg)


def f(x):
    return struct.unpack(">d", bytes.fromhex(x))[0]


def w(x):
    return struct.pack(">d", x).hex()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def bits(word):
    x = int(word, 16)
    return (~x & ((1 << 64) - 1)) if x >> 63 else x | (1 << 63)


def json_gz(p):
    return json.loads(gzip.decompress(p.read_bytes()))


def check_scales():
    raw = gzip.decompress(
        (ANALYSIS / "reviewed_source/verify_state_forcing_ad.py.gz").read_bytes()
    )
    need(
        digest(raw)
        == "08f762aa5802aced370eccfa972308170b1d0a90dd0d5cb9dbc1623bd70a3f26",
        "scale source original SHA",
    )
    need(
        b"OUTPUT_SCALES = np.array([1.,1e-3,1e-3,1e-3,1e-3,1e-3,1e-3,1e8,1e8,1e6,1e6,1e-6])[:,None]"
        in raw,
        "scale declaration",
    )


def row_metrics(center, direction, h, idx, lo, hi, jword, delta, stable, stencil):
    yl, yu, j = map(f, (lo, hi, jword))
    fd = (yu - yl) / delta
    diff = fd - j
    scale = SCALES[idx // 39]
    signal_ulps = abs(bits(hi) - bits(lo))
    resolved = yl != yu
    ulp = max(math.ulp(yl), math.ulp(yu))
    output_residual = (yu - yl) - j * delta
    need(
        all(math.isfinite(x) for x in (yl, yu, j, fd, diff, output_residual)),
        "nonfinite diagnostic",
    )
    return {
        "center": center,
        "direction": direction,
        "h": h,
        "stencil": stencil,
        "field": FIELDS[idx // 39],
        "level_bottom_first": idx % 39 + 1,
        "index": idx,
        "lower_word": lo,
        "upper_word": hi,
        "jvp_word": jword,
        "denominator": delta,
        "fd": fd,
        "jvp": j,
        "absolute_error": abs(diff),
        "field_scale": scale,
        "field_scaled_absolute_error": abs(diff) / scale,
        "relative_error_to_jvp": abs(diff) / abs(j) if j else None,
        "output_ulp_residual": abs(output_residual) / ulp,
        "signal_ulp_distance": signal_ulps,
        "endpoint_words_equal": lo == hi,
        "resolution": "distinct_output_words" if resolved else "unresolved_equal_words",
        "captured_masks_stable": stable,
        "classification": "captured_branch_crossing"
        if not stable
        else "exploratory_distinct_words"
        if resolved
        else "unresolved_equal_words",
    }


def upper_pii_review(z, diagnostics):
    def stages(path):
        raw = gzip.decompress(z.read(path)).decode("ascii")
        rows = list(
            csv.DictReader(
                line for line in io.StringIO(raw) if not line.startswith("#")
            )
        )
        need(
            len(rows) == 19656 and raw.rstrip().endswith("status=complete"),
            "upper PII capture",
        )
        masks = {}
        selected = {}
        schedule = {}
        for r in rows:
            key = "|".join(
                r[k]
                for k in (
                    "one_step_call",
                    "runtime_call",
                    "substep",
                    "b_zero",
                    "k_zero",
                    "stage",
                    "field",
                )
            )
            if r["dtype"] == "bool":
                masks[key] = r["raw_hex"]
            if (
                r["stage"] == "runtime_full_schedule"
                and r["field"]
                in ("mstep_ice_col", "mstep_main_col", "mstepmax_ice", "mstepmax_main")
            ) or (r["stage"] == "runtime_full_meta" and r["field"] == "loops"):
                schedule[key] = (r["dtype"], r["raw_hex"])
            if (
                r["stage"] == "fd_satadj_inner"
                and r["k_zero"] == "23"
                and r["substep"] == "0"
            ):
                selected[r["field"]] = {"dtype": r["dtype"], "raw_hex": r["raw_hex"]}
        need(
            len(masks) == 1170 and len(schedule) == 195 and len(selected) == 33,
            "upper PII trace inventory",
        )
        return masks, schedule, selected

    baseline = stages("screen/calls/center_upper_capture/capture.csv.gz")
    cases = []
    for h, label in ((1e-4, "screen"), (1e-5, "adaptive")):
        for sign in (-1, 1):
            key = (
                "upper_pii"
                + ("" if label == "screen" else "_" + str(h))
                + f"_{sign:+d}"
            )
            mask, schedule, trace = stages(
                f"{label}/calls/{key}_capture/capture.csv.gz"
            )
            delta = [
                k
                for k in sorted(set(mask) | set(baseline[0]))
                if mask.get(k) != baseline[0].get(k)
            ]
            sd = [
                k
                for k in sorted(set(schedule) | set(baseline[1]))
                if schedule.get(k) != baseline[1].get(k)
            ]
            output = json.loads(z.read(f"{label}/calls/{key}_capture/output.json"))[
                "output_words"
            ]
            cases.append(
                {
                    "h": h,
                    "sign": sign,
                    "key": key,
                    "captured_mask_changes": delta,
                    "captured_schedule_changes": sd,
                    "nc16_output_word": output[8 * 39 + 15],
                    "native16_activation_trace": {
                        k: trace[k]
                        for k in (
                            "sw_percent",
                            "activation_fraction_pow",
                            "activation_fraction_min_output",
                            "ncact_raw",
                            "ncact_nccn_rate_cap",
                            "ncact",
                            "nc_final",
                        )
                    },
                }
            )
    return {
        "center_native16_activation_trace": {
            k: baseline[2][k]
            for k in (
                "sw_percent",
                "activation_fraction_pow",
                "activation_fraction_min_output",
                "ncact_raw",
                "ncact_nccn_rate_cap",
                "ncact",
                "nc_final",
            )
        },
        "endpoints": cases,
        "scope": "recorded masks and native16 activation trace only; no claim for uninstrumented branches or causality",
    }


def check_effective_direction(xlo, xhi, den, seed):
    need(
        len(xlo) == len(xhi) == len(seed) == 624
        and den > 0
        and all(w((f(b) - f(a)) / den) == v for a, b, v in zip(xlo, xhi, seed)),
        "represented componentwise direction",
    )


def recorded_endpoint_stable(receipt, key):
    """Require the complete +2 endpoint receipt before using an NC stencil."""
    field = "endpoints" if receipt["schema"] == "kdm6.batch3.screen.v1" else "checks"
    matches = [item for item in receipt[field] if item["key"] == key]
    need(len(matches) == 1, "NC +2 endpoint receipt inventory")
    item = matches[0]
    parity = (
        "installed_capture_exact_468"
        if field == "endpoints"
        else "installed_capture_468_equal"
    )
    need(
        item[parity] is True and item["capture_rows"] == 19656,
        "NC +2 endpoint parity and capture",
    )
    need(
        type(item["bool_changed_keys"]) is list
        and type(item["schedule_changed_keys"]) is list,
        "NC +2 endpoint mask receipt",
    )
    return not item["bool_changed_keys"] and not item["schedule_changed_keys"]


def checked_second_forward_stable(first_stable, receipt, key):
    plus2_stable = recorded_endpoint_stable(receipt, key)
    return first_stable and plus2_stable


def analyze():
    for p, h in PINS.items():
        need(digest(p.read_bytes()) == h, "input SHA " + p.name)
    check_scales()
    diagnostics = json.loads((PARENT / "screening_results.json").read_bytes())[
        "diagnostics"
    ]
    need(len(diagnostics) == 61, "diagnostic inventory")
    with zipfile.ZipFile(PARENT / "raw/screening_raw.zip") as z:

        def get(name):
            return json.loads(z.read(name))

        allrows = []
        nc2 = []
        summaries = []
        for d in diagnostics:
            center, name, h = d["center"], d["direction"], d["h"]
            label = "screen" if h == 1e-4 else "adaptive"
            prefix = f"{center}_{name}" + ("" if label == "screen" else "_" + str(h))
            minus = "center_" + center if name == "nc" else prefix + "_-1"
            plus = prefix + "_+1"
            lo = get(
                f"{'screen' if name == 'nc' else label}/calls/{minus}_capture/output.json"
            )["output_words"]
            hi = get(f"{label}/calls/{plus}_capture/output.json")["output_words"]
            ilo = get(
                f"{'screen' if name == 'nc' else label}/calls/{minus}_capture/input.json"
            )
            ihi = get(f"{label}/calls/{plus}_capture/input.json")
            graph = (
                get(f"screen/effective_calls/{center}/output.json")
                if label == "screen"
                else get(f"adaptive/calls/adaptive_center_{center}_graph/output.json")
            )
            j = graph["jvps"][name if label == "screen" else f"{name}_{h}"]
            den = h if name == "nc" else 2 * h
            xlo = ilo["state_words"] + ilo["forcing_words"]
            xhi = ihi["state_words"] + ihi["forcing_words"]
            seed = j["state_direction_words"] + j["forcing_direction_words"]
            need(
                len(lo) == len(hi) == len(j["output_words"]) == 468
                and len(xlo) == len(xhi) == len(seed) == 624,
                "array lengths",
            )
            check_effective_direction(xlo, xhi, den, seed)
            stable = d["status"] == "captured_masks_stable"
            need(
                d["status"] in ("captured_masks_stable", "captured_mask_crossing"),
                "captured status",
            )
            rows = [
                row_metrics(
                    center,
                    name,
                    h,
                    i,
                    lo[i],
                    hi[i],
                    j["output_words"][i],
                    den,
                    stable,
                    "first_forward" if name == "nc" else "central",
                )
                for i in range(468)
            ]
            allrows.extend(rows)
            summaries.append(
                {
                    "center": center,
                    "direction": name,
                    "h": h,
                    "distinct_output_words": sum(
                        r["resolution"] == "distinct_output_words" for r in rows
                    ),
                    "unresolved_outputs": sum(
                        r["resolution"] == "unresolved_equal_words" for r in rows
                    ),
                    "branch_crossing_outputs": sum(
                        r["classification"] == "captured_branch_crossing" for r in rows
                    ),
                }
            )
            if name == "nc":
                second_stable = checked_second_forward_stable(
                    stable, get(f"{label}/result.json"), prefix + "_+2"
                )
                twice = get(f"{label}/calls/{prefix}_+2_capture/output.json")[
                    "output_words"
                ]
                itwice = get(f"{label}/calls/{prefix}_+2_capture/input.json")
                x2 = itwice["state_words"] + itwice["forcing_words"]
                idx_nc = 8 * 39 + 15
                need(
                    len(twice) == 468
                    and len(x2) == 624
                    and all(
                        xlo[i] == xhi[i] == x2[i] for i in range(624) if i != idx_nc
                    ),
                    "NC forward coordinate confinement",
                )
                a = xlo[idx_nc]
                b = xhi[idx_nc]
                c = x2[idx_nc]
                first_effective = (f(b) - f(a)) / h
                second_effective = (4 * (f(b) - f(a)) - (f(c) - f(a))) / (2 * h)
                need(
                    first_effective != 0 and math.isfinite(second_effective),
                    "NC represented seed",
                )
                rows2 = []
                for i in range(468):
                    y0, y1, y2 = f(lo[i]), f(hi[i]), f(twice[i])
                    fd2 = (4 * (y1 - y0) - (y2 - y0)) / (2 * h)
                    j2 = f(j["output_words"][i]) * (second_effective / first_effective)
                    scale = SCALES[i // 39]
                    err = fd2 - j2
                    ulp = max(math.ulp(y0), math.ulp(y1), math.ulp(y2))
                    signal = max(
                        abs(bits(lo[i]) - bits(hi[i])),
                        abs(bits(lo[i]) - bits(twice[i])),
                    )
                    resolved = y0 != y1 or y0 != y2
                    need(
                        all(math.isfinite(v) for v in (fd2, j2, err)),
                        "second forward finite",
                    )
                    rows2.append(
                        {
                            "center": center,
                            "direction": "nc",
                            "h": h,
                            "field": FIELDS[i // 39],
                            "level_bottom_first": i % 39 + 1,
                            "index": i,
                            "stencil": "second_forward",
                            "center_word": lo[i],
                            "plus_word": hi[i],
                            "plus2_word": twice[i],
                            "fd": fd2,
                            "effective_jvp": j2,
                            "absolute_error": abs(err),
                            "field_scale": scale,
                            "relative_error_to_jvp": abs(err) / abs(j2) if j2 else None,
                            "output_ulp_residual": abs(
                                (4 * (y1 - y0) - (y2 - y0)) - j2 * (2 * h)
                            )
                            / ulp,
                            "signal_ulp_distance": signal,
                            "resolution": "distinct_output_words"
                            if resolved
                            else "unresolved_equal_words",
                            "captured_masks_stable": second_stable,
                            "classification": "captured_branch_crossing"
                            if not second_stable
                            else "exploratory_distinct_words"
                            if resolved
                            else "unresolved_equal_words",
                        }
                    )
                nc2.extend(rows2)
        upper_pii = upper_pii_review(z, diagnostics)
    need(len(allrows) == 61 * 468 and len(nc2) == 9 * 468, "output inventory")
    stage = json_gz(PARENT / "stage_compare.json.gz")
    compare = json_gz(ANALYSIS / "f32_f64_diff.json.gz")
    need(compare["summary"]["rounded_mismatch_count"] == 101, "f32/f64 mismatch count")
    stage_link = {
        "f32_f64_baseline_rounded_mismatches": 101,
        "all_101_mismatches": compare["mismatches"],
        "nc12": {
            "baseline_output_mismatch": next(
                x
                for x in compare["mismatches"]
                if x["field"] == "nc" and x["native_level_1based"] == 12
            ),
            "recorded_number_fields": stage["comparison"]["levels"]["12"][
                "number_field_records"
            ],
        },
        "nr16": {
            "baseline_output_mismatch": next(
                x
                for x in compare["mismatches"]
                if x["field"] == "nr" and x["native_level_1based"] == 16
            ),
            "recorded_number_fields": stage["comparison"]["levels"]["16"][
                "number_field_records"
            ],
        },
        "nc16": {
            "baseline_rounded_f32_mismatch": any(
                x["field"] == "nc" and x["native_level_1based"] == 16
                for x in compare["mismatches"]
            ),
            "lower_plateau": stage["lower_center_plateau"],
        },
        "scope": "recorded same-input stage observations are not a complete causal attribution of the 101 final differences",
    }
    for label, fields in (
        ("nc12", ("nc", "nc_before", "nc_after", "nc_input", "nc_final", "ncact_raw")),
        ("nr16", ("nr", "nr_before", "nr_after")),
    ):
        candidates = stage_link[label]["recorded_number_fields"]
        stage_link[label]["first_recorded_selected_field_rounded_difference"] = next(
            (
                r
                for r in candidates
                if r["field"] in fields and not r["f64_rounded_f32_equal"]
            ),
            None,
        )
    stage_link["mismatches_by_field"] = compare["summary"]["mismatches_by_field"]
    return {
        "schema": "kdm6.native_host_batch4_analysis.v1",
        "scope": "single selected B=1 f64 column; fixed captured masks only; no new model calls or complete Jacobian",
        "gate_policy": {
            "signal": "equal numerical endpoint values, including signed zero, are unresolved; distinct values report ULP separation without asserting adequate resolution",
            "residual": "absolute, field-scaled and relative-to-JVP residuals are reported without a pass threshold; existing evidence does not define a general output-wise acceptance contract",
            "branch": "captured masks/schedules may identify crossings; unrecorded branches remain unknown",
            "certification": "exploratory comparisons only, no numerical pass or physical/full derivative certification",
            "field_scale": "declared numerical scales, not physical uncertainty or unit approval",
            "second_forward_jvp": "rescaled saved first-forward JVP by ratio of represented NC directions, using linearity; not independently executed second-forward JVP",
            "output_ulp": "prediction residual divided by the larger local f64 ULP; separate from f64-rounded-to-f32 output word distance",
        },
        "field_scales": dict(zip(FIELDS[:12], SCALES)),
        "diagnostics": summaries,
        "output_rows": allrows,
        "nc_second_forward_rows": nc2,
        "f32_f64_stage_link": stage_link,
        "upper_pii_recorded_gap": upper_pii,
        "scientific_status": "INCONCLUSIVE",
        "physical_unit_status": "INCONCLUSIVE",
    }


def encode(d):
    raw = (
        json.dumps(d, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", filename="", mtime=0) as gz:
        gz.write(raw)
    return buf.getvalue()


if __name__ == "__main__":
    (HERE / "results.json.gz").write_bytes(encode(analyze()))
