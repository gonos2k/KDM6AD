#!/usr/bin/env python3
"""Replay archived bounded B=1 f64 screening; no model execution."""

import csv
import gzip
import hashlib
import io
import json
import math
import re
import struct
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE.parent
ARCHIVE = HERE / "raw/screening_raw.zip"
MANIFEST = HERE / "raw/screening_raw_manifest.json"
MANIFEST_SHA = "1368feb9eea1a2ae37d1a432d8e652f6861c7a6564d7aeb2b4fa09ddc39d3cef"
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
CENTERS = ("baseline", "lower", "upper")
DIRECTIONS = (
    "th",
    "qv",
    "nc",
    "nccn",
    "state_mixed",
    "rho",
    "pii",
    "p",
    "delz",
    "forcing_mixed",
)
SELECTED = "e3117d277a073042bbae648b87e7dd6661d14b600fc8245f6aeabc19fe715eae"
INSTALLED = "7adcb6921f6205af66c62720ce9447928a1608f5c261546183b928bebbd9dba7"
CAPTURE = "eabb607b08760a5b757031f864f6644e5f75aa83aebdc4c32f8fdfc8c2245c95"


def need(ok, why):
    if not ok:
        raise ValueError(why)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def f(word):
    return struct.unpack(">d", bytes.fromhex(word))[0]


def w(x):
    return struct.pack(">d", x).hex()


def vector(words, n, label):
    need(isinstance(words, list) and len(words) == n, label + " count")
    need(
        all(
            isinstance(x, str)
            and re.fullmatch("[0-9a-f]{16}", x)
            and math.isfinite(f(x))
            for x in words
        ),
        label + " finite words",
    )
    return words


def load_archive():
    raw = MANIFEST.read_bytes()
    need(sha(raw) == MANIFEST_SHA, "archive manifest SHA")
    manifest = json.loads(raw)
    need(
        manifest["schema"] == "kdm6.batch3.screening_raw_archive.v1"
        and sha(ARCHIVE.read_bytes()) == manifest["archive_sha256"],
        "archive SHA/schema",
    )
    z = zipfile.ZipFile(ARCHIVE)
    names = z.namelist()
    need(
        len(names) == len(set(names)) == 647 and set(names) == set(manifest["files"]),
        "archive inventory",
    )
    for name in names:
        data = z.read(name)
        need(sha(data) == manifest["files"][name], "archive member SHA " + name)
        if not name.endswith(".csv.gz"):
            need(
                not any(x in data for x in (b"/Users/", b"/private/", b"/opt/")),
                "unredacted local path",
            )
    return z, manifest


def parse_csv(raw, original_sha):
    data = gzip.decompress(raw)
    need(
        sha(data) == original_sha and data.rstrip().endswith(b"status=complete"),
        "capture original SHA/complete",
    )
    rows = list(
        csv.DictReader(
            line
            for line in io.StringIO(data.decode("ascii"))
            if not line.startswith("#")
        )
    )
    need(
        len(rows) == 19656
        and len({r["stage"] for r in rows}) == 51
        and {r["k_zero"] for r in rows} == {str(i) for i in range(39)}
        and {r["substep"] for r in rows} == {"0", "1"},
        "capture dimensions",
    )
    masks = {}
    schedule = {}
    states = {}
    for r in rows:
        need(
            r["B"] == "1"
            and r["K"] == "39"
            and r["b_zero"] == "0"
            and r["runtime_call"] == "1"
            and r["one_step_call"] in ("0", "1"),
            "capture identity",
        )
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
            need(key not in masks and r["raw_hex"] in ("0", "1"), "capture boolean")
            masks[key] = r["raw_hex"]
        if (
            r["stage"] == "runtime_full_schedule"
            and r["field"]
            in ("mstep_ice_col", "mstep_main_col", "mstepmax_ice", "mstepmax_main")
        ) or (r["stage"] == "runtime_full_meta" and r["field"] == "loops"):
            need(key not in schedule, "capture schedule duplicate")
            schedule[key] = (r["dtype"], r["raw_hex"])
        if r["stage"] in (
            "runtime_full_entry",
            "runtime_full_forcing",
            "runtime_full_exit",
        ):
            idx = (r["stage"], r["field"], int(r["k_zero"]))
            need(idx not in states, "capture state duplicate")
            states[idx] = r
    need(len(masks) == 1170 and len(schedule) == 195, "capture mask/schedule count")
    return masks, schedule, states


def check_input(x, center, direction_specs, nominal_h):
    state = vector(x["state_words"], 468, "state input")
    forcing = vector(x["forcing_words"], 156, "forcing input")
    before = center["state_words"] + center["forcing_words"]
    after = state + forcing
    direction = x["direction"]
    need(direction in direction_specs, "declared direction")
    spec = direction_specs[direction]
    mult = x["h_multiple"]
    need(mult in ((1, 2) if direction == "nc" else (-1, 1)), "direction stencil")
    expected = before.copy()
    for component, scale in spec["seed"].items():
        idx = FIELDS.index(component[:-2]) * 39 + 15
        expected[idx] = w(f(before[idx]) + mult * nominal_h * scale)
    need(after == expected, "preflight expected endpoint words")
    changed = {
        FIELDS[i // 39] + "16"
        for i, (a, b) in enumerate(zip(before, after))
        if a != b and i % 39 == 15
    }
    need(
        all(a == b for i, (a, b) in enumerate(zip(before, after)) if i % 39 != 15)
        and changed == set(x["represented_deltas"]),
        "represented components",
    )
    for name, d in x["represented_deltas"].items():
        idx = FIELDS.index(name[:-2]) * 39 + 15
        actual = f(after[idx]) - f(before[idx])
        key = "input_word" if "input_word" in d else "word"
        need(
            d["base_word"] == before[idx]
            and d[key] == after[idx]
            and d["delta_word"] == w(actual)
            and d["delta"] == actual,
            "component delta",
        )
    for name in ("th", "qv", "nccn", "rho", "pii", "p", "delz"):
        need(f(after[FIELDS.index(name) * 39 + 15]) > 0, "positive target")
    need(f(after[8 * 39 + 15]) >= 0, "nonnegative NC")


def check_graph_center(inp, key, label, centers):
    center = inp["center"]
    need(
        center in CENTERS
        and key == ("center_" if label == "screen" else "adaptive_center_") + center,
        "graph key/center identity",
    )
    need(
        inp["state_words"] == centers[center]["state_words"]
        and inp["forcing_words"] == centers[center]["forcing_words"],
        "graph input center",
    )


def check_reuse_identity(proof, center, capinput):
    need(
        proof["center"] == center
        and proof["side"] == ("lower" if capinput["h_multiple"] == -1 else "upper")
        and capinput["direction"] == "th"
        and capinput["nominal_h"] == 1e-5
        and proof["th_word"] == capinput["state_words"][15],
        "reuse input/side identity",
    )


def check_call(inp, out, mode):
    need(
        out["schema"] == "kdm6.batch3.screen.call.v1"
        and out["input_key"] == inp["key"]
        and out["mode"] == mode
        and out["rc"] == 0
        and out["errors"] == []
        and out["handle_null_after"] is True,
        "call status",
    )
    vector(out["output_words"], 468, "call output")
    need(out["output_finite_count"] == 468, "call finite receipt")
    need(
        out["handle_nonnull"] == (mode == "graph")
        and out["close_rc"] == (0 if mode == "graph" else None),
        "handle lifecycle",
    )
    if mode == "graph":
        v = out["vjp"]
        need(v["rc"] == 0 and v["seed"] == "nc16_unit", "VJP receipt")
        vector(v["state_words"], 468, "VJP state")
        vector(v["forcing_words"], 156, "VJP forcing")
        need(
            v["state_finite_count"] == 468 and v["forcing_finite_count"] == 156,
            "VJP counts",
        )
        for j in out["jvps"].values():
            need(j["rc"] == 0 and j["finite_count"] == 468, "JVP status")
            vector(j["state_direction_words"], 468, "JVP state seed")
            vector(j["forcing_direction_words"], 156, "JVP forcing seed")
            vector(j["output_words"], 468, "JVP output")


def check_capture_state(states, inp, out):
    for stage, names, words in (
        ("runtime_full_entry", FIELDS[:12], inp["state_words"]),
        ("runtime_full_forcing", FIELDS[12:], inp["forcing_words"]),
        ("runtime_full_exit", FIELDS[:12], out["output_words"]),
    ):
        for fieldidx, name in enumerate(names):
            for k in range(39):
                r = states[(stage, name, 38 - k)]
                need(
                    r["dtype"] == "f64"
                    and r["raw_hex"].zfill(16) == words[fieldidx * 39 + k],
                    "capture input/output words",
                )


def check_diagnostic_inventory(label, records):
    inventory = (
        {(c, d, 1e-4) for c in CENTERS for d in DIRECTIONS}
        if label == "screen"
        else {(c, d, 1e-5) for c in CENTERS for d in DIRECTIONS if d != "nccn"}
        | {(c, "nc", 1e-6) for c in CENTERS}
        | {("lower", "pii", 1e-6)}
    )
    need(
        len(records) == len(inventory)
        and {(r["center"], r["direction"], r["nominal_h"]) for r in records}
        == inventory,
        "analysis record inventory",
    )


def source_checks(z, manifest, screen, adaptive):
    sources = manifest["source_redactions"]
    for name, original in [
        ("screen/source_redacted/screen.py", screen["source_sha256"]),
        ("adaptive/source_redacted/adaptive.py", adaptive["source_sha256"]),
        (
            "screen/source_redacted/effective_jvp.py",
            json.loads(z.read("screen/effective_result.json"))["source_sha256"],
        ),
        (
            "screen/source_redacted/analyze_screen.py",
            json.loads(z.read("screen/offline_summary.json"))["source_sha256"],
        ),
        (
            "adaptive/source_redacted/analyze_adaptive.py",
            json.loads(z.read("adaptive/analysis.json"))["source_sha256"],
        ),
    ]:
        need(
            sources[name]["original_sha256"] == original
            and sources[name]["redacted_sha256"] == sha(z.read(name)),
            "producer source attribution",
        )
    code = z.read("screen/source_redacted/screen.py").decode()
    need(
        "lib.kdm6_step_ad_c if mode=='installed' else lib.kdm6_step_ad_state_forcing_c"
        in code
        and "kdm6_handle_state_forcing_jvp_c" in code
        and "kdm6_handle_state_forcing_vjp_c" in code,
        "ABI source attribution",
    )


def replay():
    z, manifest = load_archive()
    def get(name):
        return json.loads(z.read(name))
    screen = get("screen/result.json")
    adaptive = get("adaptive/result.json")
    sinput = get("screen/inputs.json")
    ainput = get("adaptive/inputs.json")
    effective = get("screen/effective_result.json")
    need(
        screen["schema"] == "kdm6.batch3.screen.v1"
        and screen["status"] == "complete"
        and screen["calls"] == 126
        and adaptive["schema"] == "kdm6.batch3.adaptive.screen.v1"
        and adaptive["status"] == "complete"
        and adaptive["calls"] == 123,
        "run receipt status",
    )
    for d in (screen, adaptive):
        need(
            d["installed_dso_sha256"] == INSTALLED
            and d["capture_dso_sha256"] == CAPTURE,
            "DSO hashes",
        )
    need(
        screen["inputs_sha256"] == sha(z.read("screen/inputs.json"))
        and adaptive["inputs_sha256"] == sha(z.read("adaptive/inputs.json"))
        and ainput["prior_screen_sha256"] == sha(z.read("screen/result.json"))
        and sinput["selected_sha256"] == ainput["selected_sha256"] == SELECTED
        and effective["parent_screen_sha256"] == sha(z.read("screen/result.json")),
        "receipt lineage",
    )
    source_checks(z, manifest, screen, adaptive)
    sitems = {x["key"]: x for x in sinput["inputs"]}
    need(len(sitems) == 63, "screen inputs")
    centers = {c: sitems["center_" + c] for c in CENTERS}
    planraw = (HERE / "raw/screening_preflight_plan.json").read_bytes()
    need(
        sha(planraw)
        == "4a1870660005751aaa208155d92f79c4feac77cc5d83114e1358b96d3df19e0c"
        and sinput["plan_sha256"] == sha(planraw),
        "pinned preflight plan",
    )
    plan = json.loads(planraw)
    specs = {x["id"]: x for x in plan["directions"]}
    need(
        len(specs) == 10 and set(specs) == set(DIRECTIONS) and plan["h"] == 1e-4,
        "preflight directions",
    )
    adaptive_items = ainput["fixed_inputs"] + ainput["optional_inputs"]
    need(
        len(adaptive_items) == 64 and len({x["key"] for x in adaptive_items}) == 64,
        "adaptive declared inputs",
    )
    for x in sinput["inputs"]:
        if x["direction"] is not None:
            need(
                x["key"] == f"{x['center']}_{x['direction']}_{x['h_multiple']:+d}",
                "screen endpoint key",
            )
            check_input(x, centers[x["center"]], specs, plan["h"])
    for x in adaptive_items:
        need(
            x["nominal_h"] in (1e-5, 1e-6)
            and x["key"]
            == f"{x['center']}_{x['direction']}_{x['nominal_h']:.0e}_{x['h_multiple']:+d}",
            "adaptive step/key",
        )
        check_input(x, centers[x["center"]], specs, x["nominal_h"])
    declared = {"screen": sitems, "adaptive": {x["key"]: x for x in adaptive_items}}
    selected_raw = (
        EVIDENCE / "native_host_column_f32_2026-11-11/raw/selected_full.json"
    ).read_bytes()
    need(sha(selected_raw) == SELECTED, "selected input SHA")
    selected = json.loads(selected_raw)
    widened = [
        w(struct.unpack(">f", bytes.fromhex(word))[0])
        for name in FIELDS
        for word in selected["input_words_hex"][name]
    ]
    for c in CENTERS:
        x = centers[c]
        words = x["state_words"] + x["forcing_words"]
        need(
            len(words) == 624
            and words[:15] + words[16:] == widened[:15] + widened[16:]
            and words[15]
            == {
                "baseline": "4073ff66c0000000",
                "lower": "4074002793cded6a",
                "upper": "407400797f530c23",
            }[c],
            "center native input",
        )
    captured = {}
    outputs = {}
    graphs = {}
    for label, receipt in [("screen", screen), ("adaptive", adaptive)]:
        seen = set()
        for r in receipt["records"]:
            key, mode = r["key"], r["mode"]
            need((key, mode) not in seen, "duplicate call")
            seen.add((key, mode))
            if mode == "installed_reuse":
                continue
            folder = f"{label}/calls/{key}_{mode}/"
            inpraw = z.read(folder + "input.json")
            outraw = z.read(folder + "output.json")
            need(
                sha(inpraw) == r["input_sha256"]
                and sha(outraw) == r["output_sha256"]
                and r["process_returncode"] == 0
                and r["rc"] == 0,
                "call receipt hashes",
            )
            inp = json.loads(inpraw)
            out = json.loads(outraw)
            check_call(inp, out, mode)
            if mode == "graph":
                check_graph_center(inp, key, label, centers)
                reference = centers[inp["center"]]
            else:
                reference = declared[label][key]
            need(
                inp["state_words"] == reference["state_words"]
                and inp["forcing_words"] == reference["forcing_words"],
                "call declared input words",
            )
            if mode == "capture":
                raw = z.read(folder + "capture.csv.gz")
                need(sha(raw) == r["capture_gzip_sha256"], "capture gzip SHA")
                mask, sched, states = parse_csv(raw, r["capture_csv_sha256"])
                check_capture_state(states, inp, out)
                captured[(label, key)] = (mask, sched)
                outputs[(label, key)] = out["output_words"]
            elif mode == "graph":
                graphs[(label, key)] = (inp, out)
        need(len(seen) == (126 if label == "screen" else 127), "call inventory")
    need(len(captured) == 125 and len(graphs) == 6, "capture/graph counts")
    for c in CENTERS:
        graph = graphs[("screen", "center_" + c)][1]
        need(
            graph["output_words"] == outputs[("screen", "center_" + c)],
            "center graph/capture",
        )
        need(
            graphs[("adaptive", "adaptive_center_" + c)][1]["output_words"]
            == graph["output_words"],
            "adaptive graph baseline",
        )
    expected = []
    for label, receipt in [("screen", screen), ("adaptive", adaptive)]:
        checks = receipt["endpoints"] if label == "screen" else receipt["checks"]
        expected_keys = (
            {x["key"] for x in sinput["inputs"] if x["direction"] is not None}
            if label == "screen"
            else {x["key"] for x in ainput["fixed_inputs"]}
            | {x["key"] for x in ainput["optional_inputs"] if x["center"] == "lower"}
        )
        need(
            len(checks) == (60 if label == "screen" else 62)
            and {x["key"] for x in checks} == expected_keys,
            "endpoint check inventory",
        )
        for item in checks:
            key = item["key"]
            center = key.split("_")[0]
            ref = captured[("screen", "center_" + center)]
            cap = captured[(label, key)]
            diff = [
                k
                for k in sorted(set(ref[0]) | set(cap[0]))
                if ref[0].get(k) != cap[0].get(k)
            ]
            sched = [
                k
                for k in sorted(set(ref[1]) | set(cap[1]))
                if ref[1].get(k) != cap[1].get(k)
            ]
            need(
                diff == item["bool_changed_keys"]
                and sched == item["schedule_changed_keys"],
                "captured mask/schedule diff",
            )
            records = [
                r
                for r in receipt["records"]
                if r["key"] == key and r["mode"] in ("installed", "installed_reuse")
            ]
            need(len(records) == 1, "installed endpoint record")
            rec = records[0]
            capinput = get(f"{label}/calls/{key}_capture/input.json")
            if rec["mode"] == "installed":
                inp = get(f"{label}/calls/{key}_installed/input.json")
                out = get(f"{label}/calls/{key}_installed/output.json")
                check_input(
                    inp,
                    centers[center],
                    specs,
                    plan["h"] if label == "screen" else inp["nominal_h"],
                )
                need(
                    inp["state_words"] == declared[label][key]["state_words"]
                    and inp["forcing_words"] == declared[label][key]["forcing_words"],
                    "installed/capture input parity",
                )
                need(
                    out["output_words"] == outputs[(label, key)],
                    "installed/capture parity",
                )
            else:
                proof = rec["proof"]
                check_reuse_identity(proof, center, capinput)
                interior = json.loads(
                    gzip.decompress(
                        (
                            EVIDENCE
                            / "native_host_column_f64_da_2026-11-12/raw/interior_ad_fd.json.gz"
                        ).read_bytes()
                    )
                )
                need(
                    sha(
                        gzip.decompress(
                            (
                                EVIDENCE
                                / "native_host_column_f64_da_2026-11-12/raw/interior_ad_fd.json.gz"
                            ).read_bytes()
                        )
                    )
                    == proof["archive_sha256"],
                    "reuse parent SHA",
                )
                c = next(x for x in interior["centers"] if x["name"] == proof["center"])
                d = next(x for x in c["differences"] if x["h_requested"] == 1e-5)
                need(
                    d[proof["side"]]["output_words"]
                    == proof["output_words"]
                    == outputs[(label, key)]
                    and d[proof["side"] + "_word"] == proof["th_word"],
                    "reused endpoint parity",
                )
            check_input(
                capinput,
                centers[center],
                specs,
                plan["h"] if label == "screen" else capinput["nominal_h"],
            )
            need(
                capinput["state_words"] == declared[label][key]["state_words"]
                and capinput["forcing_words"] == declared[label][key]["forcing_words"],
                "capture declared inputs",
            )
            expected.append((label, key, diff, sched))
    need(
        len(expected) == 122 and sum(bool(x[2] or x[3]) for x in expected) == 2,
        "mask crossing count",
    )
    # Compute every FD/JVP using represented-component directions, not nominal mixed seeds.
    diagnostics = []
    for label, analysis_name in [
        ("screen", "screen/offline_summary.json"),
        ("adaptive", "adaptive/analysis.json"),
    ]:
        summary = get(analysis_name)
        records = summary["comparisons"] if label == "screen" else summary["records"]
        check_diagnostic_inventory(label, records)
        for rec in records:
            center, name, h = rec["center"], rec["direction"], rec["nominal_h"]
            prefix = f"{center}_{name}" + ("" if label == "screen" else "_" + str(h))
            plus = prefix + "_+1"
            minus = "center_" + center if name == "nc" else prefix + "_-1"
            lo = outputs[("screen", minus)] if name == "nc" else outputs[(label, minus)]
            hi = outputs[(label, plus)]
            den = h if name == "nc" else 2 * h
            if label == "screen":
                gi_raw = z.read(f"screen/effective_calls/{center}/input.json")
                go_raw = z.read(f"screen/effective_calls/{center}/output.json")
                er = next(x for x in effective["centers"] if x["center"] == center)
                need(
                    sha(gi_raw) == er["input_sha256"]
                    and sha(go_raw) == er["output_sha256"],
                    "effective graph receipt",
                )
                gi, go = json.loads(gi_raw), json.loads(go_raw)
                direction = name
            else:
                gi, go = graphs[("adaptive", "adaptive_center_" + center)]
                direction = f"{name}_{h}"
            check_call(gi, go, "graph")
            need(
                gi["center"] == center
                and gi["state_words"] == centers[center]["state_words"]
                and gi["forcing_words"] == centers[center]["forcing_words"],
                "effective graph input center",
            )
            need(
                go["output_words"] == outputs[("screen", "center_" + center)],
                "effective graph center",
            )
            j = go["jvps"][direction]
            seed = j["state_direction_words"] + j["forcing_direction_words"]
            need(len(seed) == 624, "effective seed")
            first = (
                sitems["center_" + center]
                if name == "nc"
                else get(f"{label}/calls/{minus}_capture/input.json")
            )
            last = get(f"{label}/calls/{plus}_capture/input.json")
            actual = [
                (f(b) - f(a)) / den
                for a, b in zip(
                    first["state_words"] + first["forcing_words"],
                    last["state_words"] + last["forcing_words"],
                )
            ]
            need(
                all(w(x) == y for x, y in zip(actual, seed)),
                "componentwise represented effective seed",
            )
            js = vector(j["output_words"], 468, "effective JVP")
            fd = [(f(b) - f(a)) / den for a, b in zip(lo, hi)]
            need(all(math.isfinite(x) for x in fd), "finite FD")
            v = go["vjp"]
            adj = [f(x) for x in v["state_words"] + v["forcing_words"]]
            dot = sum(x * y for x, y in zip(adj, actual))
            j16 = f(js[8 * 39 + 15])
            need(math.isclose(j16, dot, rel_tol=1e-10, abs_tol=1e-10), "JVP/VJP dot")
            check_keys = {plus, minus}
            if name == "nc":
                check_keys.add(prefix + "_+2")
            signs = [x for x in expected if x[0] == label and x[1] in check_keys]
            crossing = any(x[2] or x[3] for x in signs)
            resolved = sum(a != b for a, b in zip(lo, hi))
            diagnostics.append(
                {
                    "center": center,
                    "direction": name,
                    "h": h,
                    "status": "captured_mask_crossing"
                    if crossing
                    else "captured_masks_stable",
                    "resolved_output_words": resolved,
                    "unresolved_equal_output_words": 468 - resolved,
                    "nc16_signal": "resolved"
                    if lo[8 * 39 + 15] != hi[8 * 39 + 15]
                    else "unresolved_equal_words",
                    "nc16_fd": fd[8 * 39 + 15],
                    "nc16_jvp": j16,
                    "nc16_vjp_dot": dot,
                }
            )
    need(len(diagnostics) == 61, "diagnostic count")
    for c in CENTERS:
        need(
            any(
                x["center"] == c and x["direction"] == "nc" and x["h"] == 1e-6
                for x in diagnostics
            ),
            "NC 1e-6 coverage",
        )
    counts = {
        "captured_mask_crossing": sum(
            x["status"] == "captured_mask_crossing" for x in diagnostics
        ),
        "captured_masks_stable": sum(
            x["status"] == "captured_masks_stable" for x in diagnostics
        ),
        "nc16_unresolved": sum(
            x["nc16_signal"] == "unresolved_equal_words" for x in diagnostics
        ),
    }
    return {
        "schema": "kdm6.batch3.screening_replay.v1",
        "classification_counts": counts,
        "second_step_exclusions": "NCCN direction not run at h=1e-5; upper PII h=1e-6 not run",
        "screen_calls": 129,
        "adaptive_new_calls": 123,
        "adaptive_reused_installed_calls": 4,
        "capture_csvs": 125,
        "endpoint_parity_checks": 122,
        "diagnostics": diagnostics,
        "scope": "bounded same selected B=1 f64 value calls; captured masks/schedules only; no hidden-branch or physical-unit claim",
        "abi_attribution": "capture DSO uses joint state+forcing AD; installed DSO values use state-only ABI; no installed joint-AD claim",
        "interpretation": "resolved means distinct output words, not derivative acceptance; equal output words unresolved; captured crossings rejected for smooth FD interpretation",
        "scientific_status": "INCONCLUSIVE",
        "physical_unit_status": "INCONCLUSIVE",
    }


def main():
    print(json.dumps(replay(), indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
