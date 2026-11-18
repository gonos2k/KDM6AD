"""Raw native TH16/QV16 endpoint anchors for the thermal-direction packet."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
from pathlib import Path
import struct

import numpy as np


K = 39
STATE = 12
FORCING = 4
MAGIC = b"KDM6_PRE2_INPUT"
OVERLAPS = (
    ("th16_abs", "native_nc16_fd_expanded_2026-11-06", "th16_abs",
     (("0.01", "1e-02"), ("0.001", "1e-03"), ("0.0001", "1e-04"))),
    ("qv16_rel", "native_nc_nccn_applied_2026-11-07", "qv16_rel",
     (("0.001", "1e-03"), ("0.0001", "1e-04"))),
)


def require(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError("native thermal anchor: " + why)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def word(value: float) -> int:
    return struct.unpack(">Q", struct.pack(">d", float(value)))[0]


def check_native_thermal_anchors(
    result: dict, evidence_root: Path, expected_manifest_shas: dict[str, str],
) -> dict[str, object]:
    """Check every overlapping endpoint's inputs, D1 CSV words, and full output."""
    packet = evidence_root / "native_pre2_input_cpp_ad_2026-11-08"
    binary = (packet / "raw/input.bin").read_bytes()
    require(binary[:len(MAGIC)] == MAGIC, "baseline input magic")
    require(len(binary) == len(MAGIC) + (STATE * K + FORCING * K) * 8 + 4 + 8,
            "baseline input length")
    baseline_state = np.frombuffer(binary, dtype="<f8", count=STATE * K,
                                   offset=len(MAGIC)).copy().reshape(STATE, K)
    baseline_forcing = np.frombuffer(binary, dtype="<f8", count=FORCING * K,
                                     offset=len(MAGIC) + STATE * K * 8).copy().reshape(FORCING, K)
    xland = struct.unpack_from("<f", binary, len(MAGIC) + (STATE * K + FORCING * K) * 8)[0]
    meta = result["thermal_directions"]["input"]
    require(word(baseline_state[0, 15]) == word(meta["th16"]), "baseline TH16 input")
    require(word(baseline_state[1, 15]) == word(meta["qv16"]), "baseline QV16 input")
    require(word(baseline_forcing[1, 15]) == word(meta["pii16"]), "baseline PII16 input")

    types = result["baseline"]["stage_types"]
    d1_words = final_words = input_words = forcing_words = auxiliary_words = 0
    rows: list[dict[str, object]] = []
    for direction, packet_name, stem, steps in OVERLAPS:
        native_dir = evidence_root / packet_name
        manifest_raw = (native_dir / "manifest.json").read_bytes()
        require(sha(manifest_raw) == expected_manifest_shas[packet_name],
                packet_name + " manifest SHA")
        manifest = json.loads(manifest_raw)
        for h, native_h in steps:
            pair = result["thermal_directions"]["directions"][direction]["finite_differences"][h]
            for side, suffix in (("low", "minus"), ("high", "plus")):
                name = f"{stem}_{native_h}_{suffix}"
                prefix = native_dir / "raw/cases" / name
                csv_path = Path(str(prefix) + ".csv.gz")
                npz_path = Path(str(prefix) + (".npz" if direction == "th16_abs"
                                               else ".on.state_output.npz"))
                for path in (csv_path, npz_path):
                    relative = str(path.relative_to(native_dir))
                    require(relative in manifest["files"] and sha(path.read_bytes()) == manifest["files"][relative],
                            name + " source asset SHA: " + relative)

                actual_input = pair[side + "_input"]
                expected_state = baseline_state.copy()
                expected_state[0, 15] = actual_input["th16"]
                expected_state[1, 15] = actual_input["qv16"]
                with np.load(npz_path) as native:
                    require(native["state"].shape == (STATE, K)
                            and native["state"].dtype == np.float64,
                            name + " state shape/dtype")
                    require(native["forcing"].shape == (FORCING, K)
                            and native["forcing"].dtype == np.float64,
                            name + " forcing shape/dtype")
                    require(native["output"].shape == (STATE, K)
                            and native["output"].dtype == np.float64,
                            name + " output shape/dtype")
                    require(np.array_equal(expected_state.view(np.uint64),
                                           native["state"].view(np.uint64)),
                            name + " full input state raw words")
                    require(np.array_equal(baseline_forcing.view(np.uint64),
                                           native["forcing"].view(np.uint64)),
                            name + " full forcing raw words")
                    require(native["xland"].shape == (1,)
                            and native["xland"].dtype == np.float32
                            and native["xland"][0].tobytes() == struct.pack("<f", xland),
                            name + " xland raw word")
                    expected_output = np.array(
                        [int(raw, 16) for raw in pair[side + "_final_raw"]], dtype=np.uint64)
                    require(expected_output.size == STATE * K
                            and np.array_equal(expected_output,
                                               native["output"].reshape(-1).view(np.uint64)),
                            name + " complete output raw words")
                input_words += STATE * K
                forcing_words += FORCING * K
                final_words += STATE * K

                selected: dict[str, dict[str, tuple[str, str]]] = {}
                with gzip.open(csv_path, "rt", newline="") as stream:
                    for row in csv.DictReader(stream):
                        if (row["runtime_call"], row["one_step_call"], row["k_zero"]) != ("1", "1", "23"):
                            continue
                        stage = row["stage"]
                        if stage not in ("d1_melt_producer", "d1_entry_thermo",
                                         "d1_upstream_entry", "d1_upstream_producer",
                                         "fd_satadj_inner"):
                            continue
                        selected.setdefault(stage, {})[row["field"]] = (row["dtype"], row["raw_hex"])

                stages = pair[side + "_stages"]
                native_d1 = selected.get("d1_melt_producer", {})
                require(len(native_d1) == 62, name + " D1 producer field inventory")
                for field, (dtype, raw) in native_d1.items():
                    key = "d1_melt_producer." + field
                    require(key in stages and types[key] == dtype,
                            name + " D1 stage dtype: " + field)
                    if dtype == "f64":
                        require(word(stages[key]) == int(raw, 16),
                                name + " D1 raw word: " + field)
                    else:
                        require(dtype == "bool" and int(bool(stages[key])) == int(raw, 16),
                                name + " D1 bool word: " + field)
                    d1_words += 1

                def native_word(stage: str, field: str) -> int:
                    dtype, raw = selected[stage][field]
                    require(dtype == "f64", name + " auxiliary dtype: " + stage + "." + field)
                    return int(raw, 16)

                links = (
                    ("d1_entry_thermo", "qv", actual_input["qv16"]),
                    ("d1_entry_thermo", "entry_cpm_arg", stages["d1_melt_producer.cpm"]),
                    ("d1_entry_thermo", "fresh_cpm", stages["d1_melt_producer.cpm"]),
                    ("d1_entry_thermo", "applied_cpm", stages["d1_melt_producer.cpm"]),
                    ("d1_upstream_entry", "t", stages["d1_melt_producer.t"]),
                    ("d1_upstream_entry", "qv", actual_input["qv16"]),
                    ("d1_upstream_producer", "work2", stages["d1_melt_producer.work2"]),
                    ("fd_satadj_inner", "activated_fraction",
                     pair[side + "_branch"]["activation"]["activated_fraction"]),
                )
                for stage, field, value in links:
                    require(native_word(stage, field) == word(value),
                            name + " auxiliary raw link: " + stage + "." + field)
                    auxiliary_words += 1
                rows.append({"case": name, "d1_words": len(native_d1),
                             "final_state_words": STATE * K, "auxiliary_words": len(links)})

    require(d1_words == 620 and final_words == 4680 and input_words == 4680
            and forcing_words == 1560 and auxiliary_words == 80,
            "expected overlap inventory")
    return {
        "native_overlap_cases": len(rows),
        "native_overlap_d1_words_raw_equal": d1_words,
        "native_overlap_final_state_words_raw_equal": final_words,
        "native_overlap_input_state_words_raw_equal": input_words,
        "native_overlap_forcing_words_raw_equal": forcing_words,
        "native_overlap_auxiliary_words_raw_equal": auxiliary_words,
        "native_overlap_cases_detail": rows,
    }
