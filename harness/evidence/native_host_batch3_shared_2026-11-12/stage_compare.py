#!/usr/bin/env python3
"""Compare archived same-input f32/f64 stage captures; executes no model calls."""

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
F32 = EVIDENCE / "native_host_column_f32_2026-11-11/raw/activation_capture.csv.gz"
BOUNDARY = EVIDENCE / "native_host_column_f64_da_2026-11-12/raw/boundary.json.gz"
ZIP = EVIDENCE / "native_host_column_f64_da_2026-11-12/raw/parity_calls.zip"
F32_SHA = "257b136e97b976bce08db0d2f682855f201024d785c8048c5645fee5e622e642"
BOUNDARY_SHA = "79c88cab57c813cb7c42bc2d6d4666a0ff0166fe98eb8f26d953062bcc40a9d7"
ZIP_SHA = "05f6039f355d961b47a62c9e1e6a0d12c91cb1dee292ebd8c6d99c3abb2a8bcf"
KEY = ("runtime_call", "one_step_call", "substep", "b_zero", "k_zero", "stage", "field")


def need(ok, why):
    if not ok:
        raise ValueError(why)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def value(row):
    dtype = row["dtype"]
    w = row["raw_hex"]
    if dtype == "bool":
        need(w in ("0", "1"), "boolean word")
        return int(w)
    need(dtype in ("f32", "f64"), "unknown dtype")
    n = 8 if dtype == "f32" else 16
    need(1 <= len(w) <= n and all(c in "0123456789abcdef" for c in w), "raw word")
    v = struct.unpack(">f" if dtype == "f32" else ">d", bytes.fromhex(w.zfill(n)))[0]
    need(math.isfinite(v), "nonfinite capture word")
    return v


def capture(raw):
    text = gzip.decompress(raw).decode("ascii")
    need(text.rstrip().endswith("status=complete"), "capture complete")
    rows = list(
        csv.DictReader(line for line in io.StringIO(text) if not line.startswith("#"))
    )
    need(
        len(rows) == 19656
        and len({r["stage"] for r in rows}) == 51
        and {r["substep"] for r in rows} == {"0", "1"}
        and {r["k_zero"] for r in rows} == {str(k) for k in range(39)},
        "capture inventory",
    )
    seen = set()
    for r in rows:
        key = tuple(r[k] for k in KEY)
        need(key not in seen, "duplicate record")
        seen.add(key)
        need(
            r["B"] == "1"
            and r["K"] == "39"
            and r["b_zero"] == "0"
            and r["runtime_call"] == "1"
            and r["one_step_call"] in ("0", "1"),
            "capture identity",
        )
        value(r)
    return rows


def compare(a, b):
    need(
        [tuple(x[k] for k in KEY) for x in a] == [tuple(x[k] for k in KEY) for x in b],
        "capture stage/field/order alignment",
    )
    records = []
    for x, y in zip(a, b):
        level = 39 - int(x["k_zero"])
        if level not in (12, 16):
            continue
        va, vb = value(x), value(y)
        if x["dtype"] == "bool" or y["dtype"] == "bool":
            need(x["dtype"] == y["dtype"] == "bool", "boolean dtype alignment")
            rounded_equal = va == vb
        else:
            try:
                rounded_equal = struct.pack(">f", va) == struct.pack(">f", vb)
            except OverflowError:
                rounded_equal = False
        records.append(
            {
                "native_level": level,
                **{k: x[k] for k in KEY},
                "f32_dtype": x["dtype"],
                "f32_raw": x["raw_hex"],
                "f64_dtype": y["dtype"],
                "f64_raw": y["raw_hex"],
                "f32_value": va,
                "f64_value": vb,
                "exact_numeric_equal": va == vb,
                "f64_rounded_f32_equal": rounded_equal,
            }
        )
    return records


def plateau(bound, lower_raw):
    events = {e["th_word"]: e for e in bound["events"]}
    c = next(x for x in bound["centers"] if x["name"] == "lower")
    words = [c["word"]] + [p["word"] for p in c["probes"]]
    need(len(words) == 7 and len(set(words)) == 7, "plateau probe inventory")
    fields = (
        "qv_input",
        "qs1",
        "sw_percent",
        "activation_fraction_pow",
        "activation_fraction_min_output",
        "nc_input",
        "nccn_input",
        "ncact_raw",
        "ncact_nccn_rate_cap",
        "ncact",
        "nc_after_activation",
        "nccn_after_activation",
        "nc_final",
        "nccn_final_raw",
        "nccn_final",
        "nccn_floor_active",
    )
    traces = {k: [events[word]["trace"][k] for word in words] for k in fields}
    for k in (
        "nc_input",
        "nccn_input",
        "ncact_raw",
        "ncact_nccn_rate_cap",
        "ncact",
        "nc_after_activation",
        "nccn_after_activation",
        "nc_final",
        "nccn_final_raw",
        "nccn_final",
        "nccn_floor_active",
    ):
        need(
            len({(t["dtype"], t["raw_hex"]) for t in traces[k]}) == 1,
            "plateau invariant " + k,
        )
    bool_fields = [
        k for k, v in events[c["word"]]["trace"].items() if v["dtype"] == "bool"
    ]
    need(
        len(bool_fields) == 10
        and all(
            all(
                events[word]["trace"][k] == events[c["word"]]["trace"][k]
                for k in bool_fields
            )
            for word in words
        ),
        "plateau selected Boolean masks",
    )
    rows = capture(lower_raw)
    matches = [
        r
        for r in rows
        if r["stage"] == "fd_satadj_inner"
        and r["k_zero"] == "23"
        and r["substep"] == "0"
    ]
    need(
        {r["field"]: {"dtype": r["dtype"], "raw_hex": r["raw_hex"]} for r in matches}
        == events[c["word"]]["trace"],
        "lower center trace link",
    )
    return {
        "center_word": c["word"],
        "probe_words": words,
        "native_level": 16,
        "stage": "fd_satadj_inner",
        "trace_fields": traces,
        "selected_boolean_masks_stable": True,
        "scope": "selected activation-stage trace only; no endpoint full-stage mask or schedule certification",
    }


FIELDS = ("th", "qv", "qc", "qr", "qi", "qs", "qg", "nccn", "nc", "ni", "nr", "bg")
FORCING = ("rho", "pii", "p", "delz")
SELECTED_SHA = "e3117d277a073042bbae648b87e7dd6661d14b600fc8245f6aeabc19fe715eae"
BASE_GZ_SHA = "e84e020e8c4c219d9e93c3165c5e42cae8f53db1ec8b4fbc7826f6b6609c5649"
BASE_CSV_SHA = "49d60ae156212acdf987577ec271f4b5a56a318b5a9ff4829c36419397e29aba"
BASE_OUT_SHA = "c69de944ebd0214abcb9d5fa53c76e8b39728d69d70087f94d159618558e1fa9"
BASE_RECEIPT_SHA = "9be944f01b7be43929877517ec2067b60451ed34f033164cf54a965061a4d2cc"


def scalar_word(row):
    width = {"f32": 8, "f64": 16, "bool": 1}[row["dtype"]]
    return row["raw_hex"].zfill(width)


def validate_io(rows, selected, precision, f64_output):
    lookup = {
        (r["stage"], r["field"], int(r["k_zero"])): r
        for r in rows
        if r["stage"]
        in ("runtime_full_entry", "runtime_full_forcing", "runtime_full_exit")
    }
    for field in FIELDS + FORCING:
        stage = "runtime_full_entry" if field in FIELDS else "runtime_full_forcing"
        for level in range(39):
            row = lookup[(stage, field, 38 - level)]
            w = selected["input_words_hex"][field][level]
            x = struct.unpack(">f", bytes.fromhex(w))[0]
            expected = struct.pack(">f" if precision == "f32" else ">d", x).hex()
            need(
                row["dtype"] == precision and scalar_word(row) == expected,
                "captured input word",
            )
    for index, field in enumerate(FIELDS):
        for level in range(39):
            row = lookup[("runtime_full_exit", field, 38 - level)]
            expected = (
                selected["output_words_hex"][field][level]
                if precision == "f32"
                else f64_output[index * 39 + level]
            )
            need(
                row["dtype"] == precision and scalar_word(row) == expected,
                "captured output word",
            )


def summarize(a, b):
    records = compare(a, b)
    summaries = {}
    watched = {
        "nc",
        "nc_before",
        "nc_after",
        "nc_input",
        "nc_final",
        "ncact_raw",
        "nccn",
        "nccn_before",
        "nccn_after",
        "nr",
        "nr_before",
        "nr_after",
    }
    for level in (12, 16):
        data = [r for r in records if r["native_level"] == level]
        first_exact = next((r for r in data if not r["exact_numeric_equal"]), None)
        first_rounded = next((r for r in data if not r["f64_rounded_f32_equal"]), None)
        selected = [r for r in data if r["field"] in watched]
        summaries[str(level)] = {
            "record_count": len(data),
            "exact_numeric_mismatches": sum(not r["exact_numeric_equal"] for r in data),
            "rounded_f32_mismatches": sum(not r["f64_rounded_f32_equal"] for r in data),
            "first_recorded_numeric_difference": first_exact,
            "first_recorded_rounded_difference": first_rounded,
            "number_field_records": selected,
        }
    bool_by_stage = {}
    schedule = {}
    for x, y in zip(a, b):
        if x["dtype"] == "bool" or y["dtype"] == "bool":
            need(x["dtype"] == y["dtype"] == "bool", "boolean dtype alignment")
            if value(x) != value(y):
                key = x["stage"]
                entry = bool_by_stage.setdefault(
                    key,
                    {"count": 0, "fields": [], "counts_by_field": {}, "first": None},
                )
                entry["count"] += 1
                entry["counts_by_field"][x["field"]] = (
                    entry["counts_by_field"].get(x["field"], 0) + 1
                )
                if x["field"] not in entry["fields"]:
                    entry["fields"].append(x["field"])
                if entry["first"] is None:
                    entry["first"] = {k: x[k] for k in KEY} | {
                        "f32_raw": x["raw_hex"],
                        "f64_raw": y["raw_hex"],
                    }
        if x["stage"] == "runtime_full_schedule":
            key = x["field"]
            entry = schedule.setdefault(
                key,
                {
                    "f32_values": [],
                    "f64_values": [],
                    "f32_raw_words": [],
                    "f64_raw_words": [],
                    "equal": True,
                    "records": 0,
                },
            )
            vx, vy = value(x), value(y)
            for label, v in [("f32_values", vx), ("f64_values", vy)]:
                if v not in entry[label]:
                    entry[label].append(v)
            for label, row in [("f32_raw_words", x), ("f64_raw_words", y)]:
                pair = {"dtype": row["dtype"], "raw_hex": row["raw_hex"]}
                if pair not in entry[label]:
                    entry[label].append(pair)
            entry["equal"] &= vx == vy
            entry["records"] += 1
    return {
        "levels": summaries,
        "boolean_mask_mismatches_by_stage": bool_by_stage,
        "runtime_full_schedule": schedule,
    }


SCREEN_SHA = "e90f9e53f61d2fc74f3aa3dec5764fbe2e3e0f3bd1b8ad2a96a5c89030d9d6eb"
PROGB_SHA = "00c2527db1e6801d691ca267bb49495e20c1b6710515933a938262f8a6d4ec97"


def progb_review(a, b):
    path = EVIDENCE / "native_d1_progb_ad_2026-11-04/executed_cpp/progb.cpp"
    raw = path.read_bytes()
    need(digest(raw) == PROGB_SHA, "archived ProgB source SHA")
    source = raw.decode()
    for needle in (
        "const bool op_f32 = (odt == torch::kFloat32);",
        "auto bg_den = op_f32 ? bg.to(odt) : torch::clamp(bg.to(odt), /*min=*/BRS_MIN);",
        "auto zero_den = bg_den == 0;",
        "torch::logical_and(active, zero_den)",
    ):
        need(needle in source, "archived ProgB expression")
    values = {}
    for name, rows in [("f32", a), ("f64", b)]:
        fields = {
            r["field"]: {"dtype": r["dtype"], "raw_hex": r["raw_hex"]}
            for r in rows
            if r["stage"] == "d1_postmelt_progb"
            and r["k_zero"] == "23"
            and r["substep"] == "0"
        }
        values[name] = {
            k: fields[k] for k in ("op_f32", "bg", "bg_den", "zero_den", "active")
        }
    need(
        values["f32"]["op_f32"]["raw_hex"] == "1"
        and values["f64"]["op_f32"]["raw_hex"] == "0"
        and values["f32"]["zero_den"]["raw_hex"] == "1"
        and values["f64"]["zero_den"]["raw_hex"] == "0",
        "ProgB observed mode",
    )
    return {
        "archived_source_sha256": PROGB_SHA,
        "native_level": 16,
        "stage": "d1_postmelt_progb",
        "observed": values,
        "source_rule": "f32 uses bg directly; f64 clamps bg to BRS_MIN before zero_den comparison; f32 zero endpoint replacement also requires active",
        "scope": "observed source branch path and captured values, not proof this difference causes NC or NR output differences; archived executed source is not proof of installed DSO build identity",
    }


def lower_endpoints(bound, center_raw, screen_raw):
    receipt = json.loads(screen_raw)
    need(
        receipt["schema"] == "kdm6.batch3.screen.v1"
        and receipt["status"] == "complete",
        "screening receipt",
    )
    need(
        receipt["source_sha256"]
        == "69130c49cc79330cb3ee54559acd32b59c16cf707167c392342a3948e184e17e"
        and receipt["inputs_sha256"]
        == "bfd0c6907cee515b2520dd84a9298aefed63a2d45c32d44d222d135a7e831448",
        "screen producer/input receipt",
    )
    need(
        receipt["installed_dso_sha256"]
        == "7adcb6921f6205af66c62720ce9447928a1608f5c261546183b928bebbd9dba7"
        and receipt["capture_dso_sha256"]
        == "eabb607b08760a5b757031f864f6644e5f75aa83aebdc4c32f8fdfc8c2245c95",
        "screening DSO provenance",
    )
    center = capture(center_raw)
    events = {e["th_word"]: e for e in bound["events"]}
    boundary_center = next(c for c in bound["centers"] if c["name"] == "lower")
    center_word = boundary_center["word"]
    details = []
    for label, sign in (("minus", -1), ("plus", 1)):
        key = f"lower_th_{sign:+d}"
        entry = next(
            x for x in receipt["records"] if x["key"] == key and x["mode"] == "capture"
        )
        need(
            entry["rc"] == 0
            and entry["process_returncode"] == 0
            and entry["installed_capture_exact_468"] is True,
            "screen capture receipt status",
        )
        rawfiles = {}
        for suffix, hash_key in (
            ("input.json", "input_sha256"),
            ("output.json", "output_sha256"),
            ("capture.csv.gz", "capture_gzip_sha256"),
        ):
            rawfiles[suffix] = (
                HERE / "raw" / f"stage_lower_{label}_{suffix}"
            ).read_bytes()
            need(
                digest(rawfiles[suffix]) == entry[hash_key],
                "screen capture asset " + key + " " + suffix,
            )
        need(
            digest(gzip.decompress(rawfiles["capture.csv.gz"]))
            == entry["capture_csv_sha256"],
            "screen original CSV SHA",
        )
        inp = json.loads(rawfiles["input.json"])
        out = json.loads(rawfiles["output.json"])
        expected = next(
            p for p in boundary_center["probes"] if p["h"] == 1e-4 and p["sign"] == sign
        )["word"]
        need(
            inp["key"] == out["input_key"] == key
            and inp["center"] == "lower"
            and inp["direction"] == "th"
            and inp["h_multiple"] == sign
            and inp["state_words"][15] == expected
            and inp["represented_deltas"]["th16"]["base_word"] == center_word
            and inp["represented_deltas"]["th16"]["input_word"] == expected,
            "screen represented input",
        )
        need(
            out["schema"] == "kdm6.batch3.screen.call.v1"
            and out["mode"] == "capture"
            and out["rc"] == 0
            and out["handle_nonnull"] is False
            and out["close_rc"] is None
            and out["handle_null_after"] is True
            and out["output_finite_count"] == 468
            and out["output_words"] == events[expected]["output_words"],
            "screen endpoint output",
        )
        rows = capture(rawfiles["capture.csv.gz"])
        need(
            [tuple(x[k] for k in KEY) for x in rows]
            == [tuple(x[k] for k in KEY) for x in center],
            "endpoint identity/order",
        )
        state = inp["state_words"]
        forcing = inp["forcing_words"]
        need(
            len(state) == 468 and len(forcing) == 156 and state[15] == expected,
            "screen input shape",
        )
        base_state = [
            struct.pack(">d", struct.unpack(">f", bytes.fromhex(word))[0]).hex()
            for word in bound["input_words_f32"][:468]
        ]
        base_force = [
            struct.pack(">d", struct.unpack(">f", bytes.fromhex(word))[0]).hex()
            for word in bound["input_words_f32"][468:]
        ]
        base_state[15] = expected
        need(
            state == base_state and forcing == base_force,
            "screen perturbation confined TH16",
        )
        lookup = {
            (r["stage"], r["field"], int(r["k_zero"])): r
            for r in rows
            if r["stage"]
            in ("runtime_full_entry", "runtime_full_forcing", "runtime_full_exit")
        }
        for block, names, words in (
            ("runtime_full_entry", FIELDS, state),
            ("runtime_full_forcing", FORCING, forcing),
            ("runtime_full_exit", FIELDS, out["output_words"]),
        ):
            for field_index, field in enumerate(names):
                for level in range(39):
                    row = lookup[(block, field, 38 - level)]
                    need(
                        row["dtype"] == "f64"
                        and scalar_word(row) == words[field_index * 39 + level],
                        "screen captured input/output",
                    )
        boolean = []
        schedule = []
        number = []
        changed = []
        boolean_count = 0
        schedule_count = 0
        for a, b in zip(center, rows):
            same = (a["dtype"], a["raw_hex"]) == (b["dtype"], b["raw_hex"])
            item = {
                **{k: a[k] for k in KEY},
                "center_dtype": a["dtype"],
                "center_raw": a["raw_hex"],
                "endpoint_dtype": b["dtype"],
                "endpoint_raw": b["raw_hex"],
                "equal": same,
            }
            if a["dtype"] == "bool":
                boolean_count += 1
                if not same:
                    boolean.append(item)
            if (
                a["stage"] == "runtime_full_schedule"
                and a["field"]
                in ("mstep_ice_col", "mstep_main_col", "mstepmax_ice", "mstepmax_main")
            ) or (a["stage"] == "runtime_full_meta" and a["field"] == "loops"):
                schedule_count += 1
                if not same:
                    schedule.append(item)
            if a["k_zero"] == "23" and a["field"].startswith("nc"):
                number.append(item)
            if a["k_zero"] == "23" and a["dtype"] != "bool" and not same:
                changed.append(item)
        need(
            boolean_count == 1170
            and schedule_count == 195
            and not boolean
            and not schedule,
            "endpoint captured mask/schedule changed",
        )
        need(
            number and all(x["equal"] for x in number),
            "NC16/NCCN16 captured field changed",
        )
        first_after_input = next(
            (
                x
                for x in changed
                if x["stage"]
                not in (
                    "runtime_full_entry",
                    "runtime_full_forcing",
                    "runtime_full_meta",
                )
            ),
            None,
        )
        details.append(
            {
                "sign": sign,
                "input_word": expected,
                "capture_original_sha256": entry["capture_csv_sha256"],
                "captured_boolean_count": boolean_count,
                "captured_bool_mismatches": boolean,
                "captured_schedule_count": schedule_count,
                "captured_schedule_mismatches": schedule,
                "number_field_records": number,
                "number_field_records_count": len(number),
                "first_recorded_native16_change": changed[0] if changed else None,
                "first_recorded_native16_change_after_entry": first_after_input,
            }
        )
    return {
        "center_word": center_word,
        "h_requested": 1e-4,
        "native_level": 16,
        "details": details,
        "scope": "recorded stage/field order and captured masks only; no first-causal-operator, uninstrumented-branch or physical-unit claim",
    }


def replay():
    def read_pinned(path, sha):
        raw = path.read_bytes()
        need(digest(raw) == sha, "asset SHA " + str(path))
        return raw

    selected = json.loads(
        read_pinned(
            EVIDENCE / "native_host_column_f32_2026-11-11/raw/selected_full.json",
            SELECTED_SHA,
        )
    )
    base = json.loads(
        gzip.decompress(
            read_pinned(
                EVIDENCE
                / "native_host_column_f64_da_2026-11-12/raw/baseline_probe.json.gz",
                "8141b98a09d116320fdf2829e17fc6ffc90410efb50d5e08ba259b32ac28d8ad",
            )
        )
    )
    bound = json.loads(gzip.decompress(read_pinned(BOUNDARY, BOUNDARY_SHA)))
    raw32 = read_pinned(F32, F32_SHA)
    raw64 = read_pinned(HERE / "raw/stage_compare_f64_baseline.csv.gz", BASE_GZ_SHA)
    need(digest(gzip.decompress(raw64)) == BASE_CSV_SHA, "original f64 CSV SHA")
    out = json.loads(
        read_pinned(HERE / "raw/stage_compare_f64_output.json", BASE_OUT_SHA)
    )
    receipt = json.loads(
        read_pinned(HERE / "raw/stage_compare_f64_receipt.json", BASE_RECEIPT_SHA)
    )
    need(
        receipt["schema"] == "kdm6.host_selected_f64_baseline_full_capture.v1"
        and receipt["selected_sha256"] == SELECTED_SHA
        and receipt["assets"]["native_qnice_applied_76647_runtime1.csv"] == BASE_CSV_SHA
        and receipt["assets"]["output.json"] == BASE_OUT_SHA,
        "baseline receipt",
    )
    need(
        receipt["redaction"]["original_receipt_sha256"]
        == "aa6c572aac06069fbeef48a0eae907d09204889772290aee7fb24a4dd1bf5f13",
        "baseline original receipt attribution",
    )
    need(
        receipt["control"]
        == {
            "shape": [1, 39, 1],
            "dt_s": 20,
            "xland": 2,
            "ncmin_land": 10,
            "ncmin_sea": 10,
            "abi": "kdm6_step_ad_c",
            "value_only": 1,
            "runtime_call": 1,
        },
        "baseline controls",
    )
    need(
        out["mode"] == "capture_on"
        and out["th_word"] == "4073ff66c0000000"
        and out["rc"] == 0
        and out["handle_nonnull"] is False
        and out["handle_null_after"] is True
        and out["output_words"] == base["cases"][0]["value_only"]["output_f64_words"],
        "f64 baseline output",
    )
    allinputs = [
        w for name in FIELDS + FORCING for w in selected["input_words_hex"][name]
    ]
    need(
        len(allinputs) == 624
        and allinputs == base["source"]["input_f32_words"] == bound["input_words_f32"]
        and base["source"]["selected_full_sha256"] == SELECTED_SHA,
        "identical input lineage",
    )
    zipraw = read_pinned(ZIP, ZIP_SHA)
    with zipfile.ZipFile(io.BytesIO(zipraw)) as z:
        for mode in (
            "installed_value",
            "installed_graph",
            "capture_value",
            "capture_graph",
        ):
            row = json.loads(z.read(f"parity_calls/4073ff66c0000000_{mode}.json"))
            need(
                row["output_words"] == out["output_words"]
                and row["rc"] == 0
                and row["th_word"] == out["th_word"]
                and row["mode"] == mode
                and row["handle_nonnull"] == mode.endswith("graph")
                and row["close_rc"] == (0 if mode.endswith("graph") else None)
                and row["handle_null_after"] is True,
                "archived f64 off/installed output",
            )
        lower = z.read("parity_calls/4074002793cded6a_capture.csv.gz")
    a, b = capture(raw32), capture(raw64)
    screen = read_pinned(HERE / "raw/stage_screening_receipt.json", SCREEN_SHA)
    validate_io(a, selected, "f32", out["output_words"])
    validate_io(b, selected, "f64", out["output_words"])
    data = summarize(a, b)
    return {
        "schema": "kdm6.native_host.same_input_stage_compare.v1",
        "scope": "separate B=1 value-only f32 and f64 captures of exactly widened same selected input; first recorded stage difference is not causal attribution",
        "capture_identity": {
            "runtime_call": 1,
            "column": 0,
            "levels": 39,
            "vertical_order": "capture top-first; native level=39-k_zero",
            "rows_per_capture": 19656,
            "stages": 51,
        },
        "parent_input_sha256": SELECTED_SHA,
        "f64_capture_original_csv_sha256": BASE_CSV_SHA,
        "f64_capture_original_output_sha256": BASE_OUT_SHA,
        "baseline_outputs": "new capture-on compared word-for-word to archived f64 installed value/graph and capture-off value/graph; no new graph capture",
        "schedule_and_masks_scope": "captured predicates and schedule only; op_f32 is a dtype-mode indicator, not a physical branch; no claim for uncaptured branches",
        "comparison": data,
        "lower_center_plateau": plateau(bound, lower),
        "lower_full_stage_endpoints": lower_endpoints(bound, lower, screen),
        "progb_source_review": progb_review(a, b),
        "scientific_status": "INCONCLUSIVE",
        "physical_unit_status": "INCONCLUSIVE",
    }


def encode(result):
    payload = (
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode()
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", filename="", mtime=0) as stream:
        stream.write(payload)
    return buffer.getvalue()


if __name__ == "__main__":
    (HERE / "stage_compare.json.gz").write_bytes(encode(replay()))
