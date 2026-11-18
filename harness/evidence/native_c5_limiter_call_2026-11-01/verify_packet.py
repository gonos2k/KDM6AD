"""Verify selected C5/limiter packet and replay local value and derivative maps.

Private full captures and execution artifacts are attestations, not distributed
bytes. This verifier does not establish host AD or the physical QNICE basis.
"""

import argparse
import hashlib
import json
import math
import re
import struct
from pathlib import Path
from .capture_schema import STAGES
from .replay import replay, derivative_diagnostics

REPO = Path(__file__).resolve().parents[3]
BASELINE = (
    REPO / "harness/evidence/native_c3_c4_dsd_call_2026-11-01/selected_packet.json"
)
PUBLIC_SOURCES = Path(__file__).resolve().parent / "public_sources"
# Filled only after private exporter succeeds and packet bytes are frozen.
PACKET_SHA256 = "cb73fc3c6c2b30c080bde622b88db097e933e7ea88e56d2b9583a46f394d33ba"
SOURCE_MANIFEST_SHA256 = (
    "24c8a505a624cabdf3c3b3262ceaefa37c4842276185c423b1607ed6aa07bd36"
)
SELECTED_CAPTURE_SHA256 = (
    "ff7130c4b4b42a58eca275ef2e2cf86a3f698ae8e64c3ecb5a7d0e939cd34a4e"
)
BUILD_RECEIPT_SHA256 = (
    "5a0a6e8d81bc73afe0656c5b87afab0e9a1e9e3b6a43f78e3d48b8ed0e1afb49"
)
DSO_SHA256 = "c857a240d4517800d10bb38b0651cb73f1ab16c4d211c9931ed2ef46a6adf7c7"
BASELINE_SHA = "ef185f41ef0aca0226c980ee0449c7e8ec4809770c98e46a09acfc113c38a224"
FIELDS = {
    "one_step_call",
    "runtime_call",
    "substep",
    "b_zero",
    "k_zero",
    "B",
    "K",
    "stage",
    "field",
    "dtype",
    "raw_hex",
}
BRANCH = {"icenuc.ifsat", "depsub.ifsat", "depsub.ice_complete_sublim"}


def need(condition, message):
    if not condition:
        raise ValueError(message)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def verify(raw, pin):
    need(
        isinstance(PACKET_SHA256, str)
        and re.fullmatch("[0-9a-f]{64}", PACKET_SHA256)
        and re.fullmatch("[0-9a-f]{64}", pin)
        and sha(raw) == pin == PACKET_SHA256,
        "fixed independent packet digest",
    )
    manifest_raw = (
        Path(__file__).resolve().parent / "source_manifest.json"
    ).read_bytes()
    need(sha(manifest_raw) == SOURCE_MANIFEST_SHA256, "source manifest pin")
    manifest = json.loads(manifest_raw)
    for relative, expected in manifest.items():
        need(
            sha((REPO / relative).read_bytes()) == expected, "replay source " + relative
        )
    packet = json.loads(raw)
    selection = {
        k: packet[k] for k in ("selected_rows", "capture_files", "capture_metadata")
    }
    need(
        sha(json.dumps(selection, sort_keys=True, separators=(",", ":")).encode())
        == SELECTED_CAPTURE_SHA256,
        "fixed selected capture digest",
    )
    need(
        packet["schema"] == "kdm6.native_c5_limiter_selected.v1"
        and packet["scientific_status"] == "INCONCLUSIVE",
        "packet schema",
    )
    baseline_bytes = BASELINE.read_bytes()
    need(
        sha(baseline_bytes) == BASELINE_SHA == packet["baseline_packet_sha256"]
        and packet["baseline_selected_rows_raw_bit_equal"] is True,
        "baseline pin",
    )
    baseline = json.loads(baseline_bytes)
    off, on = packet["run_off"], packet["run_on"]
    for key in (
        "historical_plan_sha256",
        "origin_sha256",
        "startup_sha256",
        "endpoint_sha256",
        "historical_endpoint_sha256",
        "executable_sha256",
        "dso_sha256",
        "isolated_build_receipt_sha256",
    ):
        need(
            re.fullmatch("[0-9a-f]{64}", off[key]) and off[key] == on[key],
            "paired hash " + key,
        )
    need(
        off["endpoint_sha256"] == off["historical_endpoint_sha256"]
        and off["historical_endpoint_match"] is True
        and on["historical_endpoint_match"] is True,
        "endpoint",
    )
    for key in ("origin_sha256", "startup_sha256", "endpoint_sha256"):
        need(baseline["run_on"][key] == on[key], "baseline endpoint " + key)
    for key in ("source_sha256", "compiled_source_sha256"):
        need(
            off[key] == on[key]
            and isinstance(off[key], dict)
            and off[key]
            and all(re.fullmatch("[0-9a-f]{64}", v) for v in off[key].values()),
            "source hash " + key,
        )
    build = packet["isolated_build_receipt"]
    build_raw = (json.dumps(build, indent=2, sort_keys=True) + "\n").encode()
    need(
        sha(build_raw) == on["isolated_build_receipt_sha256"]
        and sha(build_raw) == BUILD_RECEIPT_SHA256
        and build["dso_sha256"] == DSO_SHA256
        and build["schema"] == "kdm6.isolated_c5_limiter_capture_build.v1"
        and build["dso_sha256"] == on["dso_sha256"]
        and build["coordinator_source_sha256"]
        == on["compiled_source_sha256"]["src/coordinator.cpp"]
        and "-ffp-contract=off" in build["compile_flags"],
        "build receipt",
    )
    need(
        build["previous_receipt_sha256"]
        == "d91ab3f48a78db2d970433862d9069e3368de15483b8b2a87549fc77e0858f2c",
        "previous build receipt pin",
    )
    members = build["archive_members"]
    expected_members = {
        name + ".cpp.o"
        for name in (
            "cloud_dsd",
            "cold",
            "coordinator",
            "melt_freeze",
            "ops",
            "progb",
            "runtime",
            "satadj",
            "sedimentation",
            "sedimentation_conservative",
            "slope",
            "state",
            "thermo",
            "warm",
        )
    }
    need(set(members) == expected_members, "archive inventory")
    for name, hashes in members.items():
        need(
            set(hashes) == {"current", "previous"}
            and all(re.fullmatch("[0-9a-f]{64}", x) for x in hashes.values()),
            "archive member hash",
        )
        if name == "coordinator.cpp.o":
            need(
                hashes["current"] == build["coordinator_object_sha256"],
                "coordinator object",
            )
        else:
            need(hashes["current"] == hashes["previous"], "unchanged archive member")
    snapshot = Path(__file__).resolve().parent / "executed_sources"
    need(
        sha((snapshot / "coordinator.cpp.txt").read_bytes())
        == build["coordinator_source_sha256"],
        "compiled coordinator snapshot",
    )
    need(
        sha((snapshot / "run_host.py.txt").read_bytes())
        == off["private_runner_sha256"]
        == on["private_runner_sha256"],
        "runner snapshot",
    )
    need(
        sha((snapshot / "export_private.py.txt").read_bytes())
        == packet["exporter_sha256"],
        "exporter snapshot",
    )
    expected_sources = {
        "libtorch/CMakeLists.txt",
        "libtorch/src/coordinator.cpp",
        "libtorch/src/runtime.cpp",
        "libtorch/bridge/kdm6_c_api.cpp",
        "harness/native_live_stepper.py",
        "harness/run_ss_case.py",
    }
    need(set(off["source_sha256"]) == expected_sources, "executed source inventory")
    for relative, expected in off["source_sha256"].items():
        need(
            sha((PUBLIC_SOURCES / relative).read_bytes()) == expected,
            "executed source " + relative,
        )
    c = packet["coordinate"]
    need(
        c["native_ijk_1based"] == [[164, 242, 21], [164, 242, 23]]
        and c["batch_b_zero"] == 22617
        and c["k_zero"] == [20, 22]
        and c["tile2_B"] == 32248,
        "coordinate",
    )
    traces = packet["host_selected_trace"]
    need(traces["off_v1"] == traces["on_v1"], "host trace equality")
    host = {}
    for rec in traces["on_v1"]:
        key = (rec["stage"], tuple(rec["native_ijk_1based"]))
        need(
            key not in host
            and rec["step"] == 3
            and len(rec["fields"]) == len(rec["raw_hex"])
            and len(set(rec["fields"])) == len(rec["fields"])
            and all(re.fullmatch("[0-9a-f]{8}", x) for x in rec["raw_hex"]),
            "host record",
        )
        host[key] = dict(zip(rec["fields"], rec["raw_hex"]))
    need(
        set(host)
        == {(s, (164, 242, k)) for s in ("MP_INPUT", "MP_OUTPUT") for k in (21, 23)},
        "host inventory",
    )
    groups = {}
    for row in packet["selected_rows"]:
        need(set(row) == FIELDS, "row schema")
        for key in (
            "one_step_call",
            "runtime_call",
            "substep",
            "b_zero",
            "k_zero",
            "B",
            "K",
        ):
            need(isinstance(row[key], str) and row[key].isdigit(), "row index")
        need(
            (
                row["one_step_call"],
                row["runtime_call"],
                row["substep"],
                row["b_zero"],
                row["B"],
                row["K"],
            )
            == ("2", "2", "1", "22617", "32248", "39")
            and row["k_zero"] in ("20", "22"),
            "row identity",
        )
        stage, field = row["stage"], row["field"]
        need(stage in STAGES and field in STAGES[stage], "row inventory")
        dtype = (
            "f32"
            if stage == "abi_ingress" or field == "fconst.pi_f32"
            else "bool"
            if field in BRANCH
            else "f64"
        )
        need(
            row["dtype"] == dtype and re.fullmatch("[0-9a-f]+", row["raw_hex"]),
            "row dtype",
        )
        bits = int(row["raw_hex"], 16)
        size = {"bool": 1, "f32": 4, "f64": 8}[dtype]
        need(bits < 1 << (8 * size) and (dtype != "bool" or bits in (0, 1)), "row bits")
        val = struct.unpack(
            {"bool": "<?", "f32": "<f", "f64": "<d"}[dtype],
            bits.to_bytes(size, "little"),
        )[0]
        need(math.isfinite(val), "finite row")
        group = groups.setdefault(row["k_zero"], {})
        need((stage, field) not in group, "duplicate row")
        group[(stage, field)] = row
    inventory = {(stage, field) for stage, fields in STAGES.items() for field in fields}
    need(
        set(groups) == {"20", "22"}
        and all(set(g) == inventory for g in groups.values()),
        "complete per-level inventory",
    )
    for rows in groups.values():
        for field in ("pre.supcol", "forcing.dend"):
            c3 = rows[("c3_in", field)]
            c5 = rows[("c5_in", field)]
            need(
                c3["dtype"] == c5["dtype"]
                and c3["raw_hex"] == c5["raw_hex"],
                "C3/C5 shared input " + field,
            )

    def key(r):
        return tuple(r[x] for x in sorted(FIELDS))

    old = [
        r
        for r in packet["selected_rows"]
        if r["stage"] not in {"c5_in", "c5_out", "limiter_in"}
    ]
    need(
        sorted(map(key, old)) == sorted(map(key, baseline["selected_rows"])),
        "baseline row equality",
    )
    for k, rows in groups.items():
        native = host[("MP_INPUT", (164, 242, int(k) + 1))]
        for field, conv in (
            ("qi", "scalar_ingress_state->qi"),
            ("ni", "scalar_ingress_state->ni"),
            ("p", "scalar_ingress_forcing->p"),
            ("den", "scalar_ingress_forcing->den"),
        ):
            abi = rows[("abi_ingress", field)]
            converted = rows[("converted_ingress", conv)]
            bits = int(abi["raw_hex"], 16)
            need(bits == int(native[field.upper()], 16), "host ABI " + field)
            widened = struct.unpack("<f", bits.to_bytes(4, "little"))[0]
            need(
                int(converted["raw_hex"], 16)
                == int.from_bytes(struct.pack("<d", widened), "little"),
                "ABI converted " + field,
            )
        native_out = host[("MP_OUTPUT", (164, 242, int(k) + 1))]
        for field in ("qi", "ni"):
            row = rows[("dsd_out", "new_state." + field)]
            value = struct.unpack("<d", int(row["raw_hex"], 16).to_bytes(8, "little"))[
                0
            ]
            need(
                int.from_bytes(struct.pack("<f", value), "little")
                == int(native_out[field.upper()], 16),
                "DSD host output " + field,
            )
    files = packet["capture_files"]
    names = {f["name"] for f in files}
    need(
        len(files) == 2 and len(names) == 2 and names == set(on["capture_files"]),
        "capture file inventory",
    )
    for f in files:
        expected_scalar = 12 * int(f["identity"][3]) + 2 * (
            sum(map(len, STAGES.values())) - len(STAGES["converted_ingress"])
        )
        need(
            f["sha256"] == on["capture_files"][f["name"]]
            and re.fullmatch("[0-9a-f]{64}", f["sha256"])
            and f["scalar_rows"] == expected_scalar
            and f["total_rows"] == f["scalar_rows"] + 1
            and f["metadata_rows"] == 1,
            "capture receipt",
        )
    need(
        {tuple(f["identity"]) for f in files}
        == {("1", "1", "1", "32712", "39"), ("2", "2", "1", "32248", "39")},
        "capture identity inventory",
    )
    descriptors = {f["name"]: f for f in files}
    metadata = packet["capture_metadata"]
    need(
        len(metadata) == 2 and {m["name"] for m in metadata} == names,
        "metadata inventory",
    )
    for m in metadata:
        need(len(m["rows"]) == 1, "metadata count")
        row = m["rows"][0]
        need(
            set(row) == FIELDS
            and row["stage"] == "meta"
            and row["field"] == "dtcld"
            and row["dtype"] == "f64"
            and tuple(
                row[x] for x in ("one_step_call", "runtime_call", "substep", "B", "K")
            )
            == tuple(descriptors[m["name"]]["identity"]),
            "metadata identity",
        )
        need(
            re.fullmatch("[0-9a-f]+", row["raw_hex"])
            and int(row["raw_hex"], 16) < 2**64,
            "metadata encoding",
        )
        dt = struct.unpack("<d", int(row["raw_hex"], 16).to_bytes(8, "little"))[0]
        need(math.isfinite(dt) and dt > 0, "metadata timestep")
        if row["B"] == "32248":
            for group in groups.values():
                need(
                    int(group[("c5_in", "dtcld")]["raw_hex"], 16)
                    == int(row["raw_hex"], 16),
                    "timestep handoff",
                )
    need(
        len(packet["unique_batch_checks"]) == 1
        and all(
            x["batch_b_zero"] == 22617
            and x["six_host_fields_exact"] is True
            and x["unique_candidate_count"] == 1
            for x in packet["unique_batch_checks"]
        ),
        "unique batch receipt",
    )
    results = {}
    for k, rows in groups.items():
        replay(rows)
        results[k] = derivative_diagnostics(rows)
    return {
        "packet_sha256": sha(raw),
        "levels": results,
        "status": "INCONCLUSIVE",
        "limitations": [
            "Private full captures, source snapshots and host endpoint bytes are hash attestations.",
            "Other upstream producer rates are frozen; host AD and raw QNICE units are not certified.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("packet", type=Path)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    try:
        print(
            json.dumps(
                verify(args.packet.read_bytes(), args.sha256), indent=2, allow_nan=False
            )
        )
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as exc:
        parser.exit(1, "INVALID: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
