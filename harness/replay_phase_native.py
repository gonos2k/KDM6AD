"""Strict arithmetic replay of the selected native D2/D3 phase capture.

The public JSON contains original hex tokens and run identity summaries. This
replayer cannot rehash private inputs or rerun mp37; it validates recorded
structure, f32 stores, f64 limited amounts and stage separation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import struct
import subprocess
import sys
from pathlib import Path

import numpy as np

STAGES = ("D2_PRE", "D2_POST", "D3_PRE", "D3_POST",
          "POST_STATE_UPDATE", "FINAL")
SOURCE_SHA256 = "fc0a72d33a5e61803fea56eb9118018039c6da8b5775813032b4861a2bd66eb5"
INSTRUMENTED_SHA256 = "44fac3a847beb9aa9f53325ff66037a7e708b9a98e4b0e0768f66788a2b93b94"
HISTORY_SHA256 = "49bbda101a367d5eeb9c460e21c2304767311d274dddecb17a4ec39fe14f1d04"
PRIOR_FRAME_SHA256 = "30ee8656cedf57cc827ad041e4ed8084d8bbf5afdbe0a21b28b33564544bca9f"
BASELINE_EXE_SHA256 = "fe2fe66a510ffa5dc16e781eda204285dd04086e5cd1b697bfa2669e437a3c8f"
CAPTURE_EXE_SHA256 = "c58ff9c41d196cfcde17a1c70a340901dc793dae18810446a137acca509b2700"
INPUT_MANIFEST_SHA256 = "12e132ecefa9e0f7e0a0bd67d57353ec3a7ec113ab1b43121474340293125fdf"
RSL_OUT_SHA256 = "66883044f9dc9019a7d43a57cc6279759f0e2ab1529dbebdf1df84da01941891"
RAW_RECORDS_SHA256 = "8df47b69ae78be1369599ab60d657e7895fe03caf9e5ed615e66987b2221498a"
ASSEMBLY_SHA256 = "78d359323c948c5c3515117ab9249f57c2a75626621db414ba94043b96347f7d"
OBJECT_SHA256 = "5290a373e968ae7e61cef94be688a297d68d2678d05c7bcf241b2e57ea01b9aa"
COMMAND_SHA256 = {
    "compile_command": "c8097c1ae47efe84919824810a33aefb0d08370e0765cb7618e81e4e580235b3",
    "assemble_command": "569b97bf2e61b8f3f928864d5c652299c61ad42e7fc9b35d559c062011181b66",
    "link_command": "b8342066ae66c92ba9605554c9ecdc4d029d33e959f6dfe6c9b4597503f6e194",
}
PROFILE_FIELDS = ("THM", "P", "PB", "PH", "PHB", "QVAPOR", "QCLOUD", "QRAIN",
                  "QICE", "QSNOW", "QGRAUP", "QNCCN", "QNCLOUD", "QNICE",
                  "QNRAIN", "QIB", "XLAND")
STATE_FIELDS = ("qc", "qi", "nc", "ni", "t")
HEX = re.compile(r"^[0-9A-F]+$")


def _unpack(bits: str, width: int) -> float:
    if len(bits) != width or not HEX.fullmatch(bits):
        raise ValueError("malformed hex token")
    return struct.unpack(">f" if width == 8 else ">d", bytes.fromhex(bits))[0]


def _bits32(value: float) -> str:
    return struct.pack(">f", float(value)).hex().upper()


def _output_arg(argv: list[str]) -> str:
    if argv.count("-o") != 1:
        raise ValueError("build command must declare exactly one -o target")
    at = argv.index("-o") + 1
    if at >= len(argv) or not argv[at]:
        raise ValueError("build command has no -o target")
    return argv[at]


def _command_sha(argv: list[str]) -> str:
    return hashlib.sha256(json.dumps(argv, separators=(",", ":")).encode()).hexdigest()


def parse_line(line: str) -> dict:
    tokens = line.split()
    if len(tokens) < 11 or tokens[:1] != ["X2PHASE"] or tokens[1] not in STAGES:
        raise ValueError("unknown native phase record")
    stage = tokens[1]
    if tuple(map(int, tokens[2:6])) != (1, 97, 173, 22):
        raise ValueError("wrong loop or native cell identity")
    pre = stage.endswith("_PRE")
    post = stage in ("D2_POST", "D3_POST")
    with_flag = pre or post
    f32_count = 7 if pre else 5
    f64_count = 2 if with_flag else 0
    if len(tokens) != 6 + int(with_flag) + f32_count + f64_count:
        raise ValueError("incomplete native phase token set")
    offset = 6
    flag = None
    if with_flag:
        if tokens[offset] not in ("0", "1"):
            raise ValueError("invalid number-branch validity flag")
        flag = int(tokens[offset])
        offset += 1
    f32_bits = tokens[offset:offset + f32_count]
    f64_bits = tokens[offset + f32_count:]
    f32_values = [_unpack(s, 8) for s in f32_bits]
    f64_values = [_unpack(s, 16) for s in f64_bits]
    if not all(math.isfinite(x) for x in (*f32_values, *f64_values)):
        raise ValueError("nonfinite native phase token")
    result = {"stage": stage, "number_valid": flag,
              "state": dict(zip(STATE_FIELDS, f32_values[:5])),
              "state_bits": dict(zip(STATE_FIELDS, f32_bits[:5]))}
    if pre:
        result["xlf"], result["cpm"] = f32_values[5:]
        result["request_mass"], result["request_number"] = f64_values
    elif post:
        result["applied_mass"], result["applied_number"] = f64_values
    return result


def _source_store(before: dict, pre: dict, post: dict) -> dict:
    if pre["number_valid"] != post["number_valid"]:
        raise ValueError("number-branch validity changed within one process")
    amount = post["applied_mass"]
    raw = pre["request_mass"]
    if raw < 0 or amount < 0 or amount != min(raw, before["qc"]):
        raise ValueError("mass application does not match the native storage cap")
    n_amount = post["applied_number"]
    n_raw = pre["request_number"]
    if pre["number_valid"]:
        if n_raw < 0 or n_amount < 0 or n_amount != min(n_raw, before["nc"]):
            raise ValueError("number application does not match its valid cap")
    elif n_raw != 0 or n_amount != 0:
        raise ValueError("inactive number output was read as a physical amount")
    expected = {
        "qc": np.float32(float(before["qc"]) - amount),
        "qi": np.float32(float(before["qi"]) + amount),
        "nc": np.float32(float(before["nc"]) - n_amount),
        "ni": np.float32(float(before["ni"]) + n_amount),
    }
    # xlf/cpm are f32 operands. Their quotient is rounded to f32 before the
    # f64 mass amount promotes the product; the final t store rounds to f32.
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        coefficient = np.float32(np.float32(pre["xlf"]) / np.float32(pre["cpm"]))
        expected["t"] = np.float32(float(before["t"]) + float(coefficient) * amount)
    for field, value in expected.items():
        if post["state_bits"][field] != _bits32(value):
            raise ValueError(f"{pre['stage']}: source-ordered {field} store differs")
    return {
        "requested_mass": raw, "applied_mass": amount,
        "number_valid": bool(pre["number_valid"]),
        "requested_number": n_raw, "applied_number": n_amount,
        "coefficient_k_per_mixing_ratio": float(coefficient),
        "thermal_step_before_f32_store_k": float(coefficient) * amount,
        "stored_temperature_change_k": post["state"]["t"] - before["t"],
    }


def replay(data: dict) -> dict:
    runs = data.get("experiment_valid")
    if (not isinstance(runs, list) or len(runs) != 2
            or any(not isinstance(run, dict)
                   or run.get("experiment_valid") is not True
                   or run.get("model_completed") is not True
                   or run.get("exit_code") != 0
                   or run.get("actual_proc_grid") != "1x1"
                   or run.get("invalid_reasons") != [] for run in runs)):
        raise ValueError("native run completion evidence changed")
    build = data.get("build", {})
    cc, asm, ld = (build.get(name) for name in
                   ("compile_command", "assemble_command", "link_command"))
    if (not all(isinstance(x, list) for x in (cc, asm, ld))
            or not all(isinstance(arg, str) for argv in (cc, asm, ld) for arg in argv)
            or not all(flag in cc for flag in ("-O2", "-ffp-contract=off",
                                                 "-DKDM6_PHASE_CAPTURE"))
            or "-S" not in cc
            or len(asm) != 5 or asm[:2] != ["/usr/bin/clang", "-c"]
            or asm[3] != "-o" or asm[2] != _output_arg(cc)
            or asm[4] != _output_arg(asm) or asm[4] not in ld
            or not any(arg.endswith("module_mp_kdm6_phase_v3.F") for arg in cc)
            or not _output_arg(ld).endswith("wrf_phase_capture_v3.exe")):
        raise ValueError("source-to-object-to-executable build chain changed")
    if (build.get("command_sha256") != COMMAND_SHA256
            or any(_command_sha(build[name]) != digest
                   for name, digest in COMMAND_SHA256.items())):
        raise ValueError("native build command identity changed")
    if (data.get("schema") != "cross-phenomena-native-phase-v1"
            or data.get("scope") != "selected_mp37_native_phase_boundary"
            or data.get("source_sha256") != SOURCE_SHA256
            or data.get("instrumented_sha256") != INSTRUMENTED_SHA256
            or data.get("history_sha256") != [HISTORY_SHA256, HISTORY_SHA256]
            or data.get("prior_frame_20s", {}).get("sha256") != PRIOR_FRAME_SHA256
            or data.get("prior_frame_20s", {}).get("same_fields") != list(PROFILE_FIELDS)
            or data.get("executable_sha256") != [BASELINE_EXE_SHA256, CAPTURE_EXE_SHA256]
            or data.get("input_manifest_sha256") != INPUT_MANIFEST_SHA256
            or data.get("rsl_out_sha256") != RSL_OUT_SHA256
            or data.get("raw_records_sha256") != RAW_RECORDS_SHA256
            or data.get("build", {}).get("assembly_sha256") != ASSEMBLY_SHA256
            or data.get("build", {}).get("object_sha256") != OBJECT_SHA256
            or data.get("build", {}).get("compile_flags") != ["-O2", "-ffp-contract=off", "-DKDM6_PHASE_CAPTURE"]
            or data.get("native_host_executed") is not True
            or data.get("accepted_full_energy") is not False
            or data.get("physical_number_basis_resolved") is not False
            or data.get("operational_p1_closed") is not False
            or data.get("run_conditions") != {"mp": 37, "dt_s": 20,
                                              "elapsed_s": 40, "mpi_ranks": 1,
                                              "threads": 1, "history_times_s": [0, 20, 40]}):
        raise ValueError("native evidence identity or scope changed")
    lines = data.get("raw_records")
    if not isinstance(lines, list) or len(lines) != 12:
        raise ValueError("expected six phase records for each of two native calls")
    if not all(isinstance(line, str) for line in lines):
        raise ValueError("native phase records must be text tokens")
    if hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest() != RAW_RECORDS_SHA256:
        raise ValueError("native phase token set changed")
    records = [parse_line(line) for line in lines]
    events = []
    for call in range(2):
        rows = records[call * 6:(call + 1) * 6]
        if tuple(row["stage"] for row in rows) != STAGES:
            raise ValueError("missing or reordered native phase boundary")
        d2pre, d2post, d3pre, d3post, later, final = rows
        if d2post["state_bits"] != d3pre["state_bits"]:
            raise ValueError("D3 did not receive D2's actual post-state")
        if call == 0 and (d2pre["number_valid"] != 0 or d3pre["number_valid"] != 0):
            raise ValueError("inactive first call changed")
        if call == 1 and (d2pre["number_valid"] != 1 or d3pre["number_valid"] != 1):
            raise ValueError("active second call changed")
        p2 = _source_store(d2pre["state"], d2pre, d2post)
        p3 = _source_store(d3pre["state"], d3pre, d3post)
        # These are separate model stages; later states are never folded back
        # into D2/D3's local mass or latent-temperature equation.
        events.append({"call_ordinal": call + 1, "D2": p2, "D3": p3,
                       "phase_end": d3post["state"],
                       "post_state_update": later["state"],
                       "final": final["state"]})
    if not (events[1]["D2"]["applied_mass"] > 0
            and events[1]["D3"]["applied_mass"] > 0
            and events[1]["post_state_update"] != events[1]["phase_end"]
            and events[1]["final"] != events[1]["post_state_update"]):
        raise ValueError("active phase and separate later boundaries not demonstrated")
    return {"scope": "arithmetic_replay_of_native_recorded_tokens",
            "events": events, "native_runs_reported": 2,
            "full_energy_or_unit_approval": False}


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def capture(control: Path, diagnostic: Path, instrument_manifest: Path,
            prior_frame: Path, compile_command: Path, link_command: Path,
            instrumented_source: Path, assembly: Path, object_file: Path) -> dict:
    identity = json.loads(instrument_manifest.read_text())
    if (identity.get("source_sha256") != SOURCE_SHA256
            or identity.get("instrumented_sha256") != INSTRUMENTED_SHA256
            or _sha(instrumented_source) != INSTRUMENTED_SHA256
            or _sha(assembly) != ASSEMBLY_SHA256
            or _sha(object_file) != OBJECT_SHA256):
        raise ValueError("instrumented source identity changed")
    validity = [json.loads((path / "experiment_valid.json").read_text())
                for path in (control, diagnostic)]
    if any(not x.get("experiment_valid") or x.get("exit_code") != 0
           or x.get("actual_proc_grid") != "1x1" for x in validity):
        raise ValueError("native control or capture did not complete as declared")
    inputs = [json.loads((path / "input_sha256.json").read_text())
              for path in (control, diagnostic)]
    if inputs[0] != inputs[1] or inputs[0].get("complete") is not True:
        raise ValueError("native input identities differ")
    names = [next(path.glob("klfs_lc05_fcst.*")) for path in (control, diagnostic)]
    histories = [_sha(name) for name in names]
    if histories != [HISTORY_SHA256, HISTORY_SHA256]:
        raise ValueError("instrumented native history differs from control")
    if _sha(prior_frame) != PRIOR_FRAME_SHA256:
        raise ValueError("input-selected prior 20 s frame changed")
    import netCDF4
    with netCDF4.Dataset(prior_frame) as prior, netCDF4.Dataset(names[0]) as present:
        if not all(np.asarray(prior[field][1, ...]).tobytes()
                   == np.asarray(present[field][1, ...]).tobytes()
                   for field in PROFILE_FIELDS):
            raise ValueError("20 s source fields differ from the input-selected frame")
    log = diagnostic / "rsl.out.0000"
    lines = [line.strip() for line in log.read_text().splitlines()
             if line.startswith("X2PHASE ")]
    compile_args = json.loads(compile_command.read_text())
    link_args = json.loads(link_command.read_text())
    if (not all(flag in compile_args for flag in ("-O2", "-ffp-contract=off",
                                                 "-DKDM6_PHASE_CAPTURE"))
            or str(instrumented_source.resolve()) not in compile_args
            or _output_arg(compile_args) != str(assembly.resolve())
            or str(object_file.resolve()) not in link_args
            or not _output_arg(link_args).endswith("wrf_phase_capture_v3.exe")
            or _sha(Path(_output_arg(link_args))) != CAPTURE_EXE_SHA256):
        raise ValueError("capture build command does not match the measured source")
    assemble_args = ["/usr/bin/clang", "-c", str(assembly.resolve()),
                     "-o", str(object_file.resolve())]
    commands = {"compile_command": compile_args, "assemble_command": assemble_args,
                "link_command": link_args}
    if any(_command_sha(commands[name]) != digest
           for name, digest in COMMAND_SHA256.items()):
        raise ValueError("native build command differs from the executed case")
    result = {
        "schema": "cross-phenomena-native-phase-v1",
        "scope": "selected_mp37_native_phase_boundary",
        "native_host_executed": True,
        "source_sha256": SOURCE_SHA256,
        "instrumented_sha256": INSTRUMENTED_SHA256,
        "history_sha256": histories,
        "rsl_out_sha256": _sha(log),
        "input_manifest_sha256": inputs[0]["canonical_sha256"],
        "build": {"compile_flags": ["-O2", "-ffp-contract=off", "-DKDM6_PHASE_CAPTURE"],
                  "command_sha256": COMMAND_SHA256,
                  "compile_command": compile_args,
                  "assembly_sha256": ASSEMBLY_SHA256,
                  "assemble_command": assemble_args,
                  "object_sha256": OBJECT_SHA256,
                  "link_command": link_args,
                  "dependency_scope": "reused host objects and libraries; only mp37 module and executable rebuilt"},
        "prior_frame_20s": {"sha256": PRIOR_FRAME_SHA256,
                            "same_fields": list(PROFILE_FIELDS),
                            "comparison": "full-domain raw bytes at frame index 1"},
        "executable_sha256": [
            (path / "wrf_exe_sha256").read_text().splitlines()[0].strip()
            for path in (control, diagnostic)
        ],
        "run_conditions": {"mp": 37, "dt_s": 20, "elapsed_s": 40,
                           "mpi_ranks": 1, "threads": 1,
                           "history_times_s": [0, 20, 40]},
        "raw_records": lines,
        "raw_records_sha256": hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest(),
        "experiment_valid": validity,
        "accepted_full_energy": False,
        "physical_number_basis_resolved": False,
        "operational_p1_closed": False,
    }
    replay(result)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--control-run", type=Path)
    ap.add_argument("--diagnostic-run", type=Path)
    ap.add_argument("--instrument-manifest", type=Path)
    ap.add_argument("--prior-frame", type=Path)
    ap.add_argument("--compile-command", type=Path)
    ap.add_argument("--link-command", type=Path)
    ap.add_argument("--instrumented-source", type=Path)
    ap.add_argument("--assembly", type=Path)
    ap.add_argument("--object", type=Path, dest="object_file")
    ap.add_argument("--output", type=Path)
    ap.add_argument("--replay", type=Path)
    a = ap.parse_args()
    if a.replay:
        print(json.dumps(replay(json.loads(a.replay.read_text())), indent=2))
    else:
        if any(x is None for x in (a.control_run, a.diagnostic_run,
                                  a.instrument_manifest, a.prior_frame,
                                  a.compile_command, a.link_command,
                                  a.instrumented_source, a.assembly,
                                  a.object_file, a.output)):
            ap.error("capture requires both runs, source, object, manifest, prior frame, build commands and output")
        a.output.write_text(json.dumps(capture(a.control_run, a.diagnostic_run,
                                              a.instrument_manifest, a.prior_frame,
                                              a.compile_command, a.link_command,
                                              a.instrumented_source, a.assembly,
                                              a.object_file), indent=2) + "\n")


if __name__ == "__main__":
    main()
