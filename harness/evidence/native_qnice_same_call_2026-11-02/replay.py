"""Authenticate two native NI handoffs and compare conditional density maps.

The recorded run used the legacy raw-number boundary. The two dry-number
expressions below are counterfactual coordinate calculations, not host runs.
"""

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import struct


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
PARENT = REPO / "harness/evidence/native_c5_limiter_call_2026-11-01"
PARENT_VERIFIER = importlib.import_module(
    "harness.evidence.native_c5_limiter_call_2026-11-01.verify_packet"
)
PACKET_SHA256 = PARENT_VERIFIER.PACKET_SHA256
NUMBER_FIELDS = ("NN", "NC", "NI", "NR")


def need(condition, message):
    if not condition:
        raise ValueError(message)


def decoded(raw_hex, dtype):
    size, fmt = {"f32": (4, "<f"), "f64": (8, "<d")}[dtype]
    word = int(raw_hex, 16)
    need(0 <= word < 1 << (8 * size), "numeric bit width")
    return struct.unpack(fmt, word.to_bytes(size, "little"))[0]


def f64_word(value):
    return int.from_bytes(struct.pack("<d", value), "little")


def f32_word(value):
    return int.from_bytes(struct.pack("<f", value), "little")


def replay(raw, pin=PACKET_SHA256):
    """Verify exactly the bytes that supply all selected host and C++ rows."""
    PARENT_VERIFIER.verify(raw, pin)
    packet = json.loads(raw)
    need(packet["schema"] == "kdm6.native_c5_limiter_selected.v1",
         "parent packet schema")
    traces = {
        (entry["stage"], entry["native_ijk_1based"][-1]):
        dict(zip(entry["fields"], entry["raw_hex"]))
        for entry in packet["host_selected_trace"]["on_v1"]
    }
    cells = {}
    for native_level, k_zero in ((21, "20"), (23, "22")):
        rows = {(r["stage"], r["field"]): r for r in packet["selected_rows"]
                if r["k_zero"] == k_zero}
        host_in = traces["MP_INPUT", native_level]
        host_out = traces["MP_OUTPUT", native_level]

        def row_word(stage, field, dtype):
            entry = rows[stage, field]
            need(entry["dtype"] == dtype, "row dtype " + stage + "/" + field)
            return int(entry["raw_hex"], 16)

        for host_field, abi_field in (("NI", "ni"), ("DEN", "den"),
                                      ("QI", "qi")):
            need(int(host_in[host_field], 16) ==
                 row_word("abi_ingress", abi_field, "f32"),
                 "host/ABI raw bit " + host_field)
        for host_field, converted in (
            ("NI", "scalar_ingress_state->ni"),
            ("DEN", "scalar_ingress_forcing->den"),
            ("Q", "scalar_ingress_state->qv"),
        ):
            value = decoded(host_in[host_field], "f32")
            need(f64_word(value) == row_word("converted_ingress", converted, "f64"),
                 "host/C++ widened bit " + host_field)

        ni = decoded(host_in["NI"], "f32")
        den = decoded(host_in["DEN"], "f32")
        qv = decoded(host_in["Q"], "f32")
        need(den > 0 and qv > -1 and ni >= 0, "coordinate domain")
        final_ni = decoded(rows["dsd_out", "new_state.ni"]["raw_hex"], "f64")
        need(f32_word(final_ni) == int(host_out["NI"], 16),
             "C++/host final NI raw bit")

        # These two alternative dry-number multipliers are evaluated from
        # the same *recorded* numeric operands. Neither was executed here.
        generic_rho = den / (1.0 + qv)
        cells[str(native_level)] = {
            "native_ijk_1based": [164, 242, native_level],
            "host_input_raw_hex": {name: host_in[name] for name in
                                   ("Q", "DEN", "QI", *NUMBER_FIELDS)},
            "host_output_ni_raw_hex": host_out["NI"],
            "legacy_ingress_ni": ni,
            "legacy_ingress_den": den,
            "converted_ingress_qv": qv,
            "dsd_output_ni": final_ni,
            "conditional_dry_number": {
                "source_inferred_native_dry_den": den,
                "generic_v2_density_from_den_and_qv": generic_rho,
                "host_ni_times_native_den": ni * den,
                "host_ni_times_generic_v2_density": ni * generic_rho,
                "generic_to_native_density_ratio": generic_rho / den,
            },
        }
    return {
        "schema": "kdm6.native_qnice_same_call_coordinate.v1",
        "parent_packet_sha256": hashlib.sha256(raw).hexdigest(),
        "parent_selected_rows": len(packet["selected_rows"]),
        "cells": cells,
        "executed_coordinate": "legacy raw NI at ingress; dry_number opt-in not executed",
        "physical_unit_status": "INCONCLUSIVE",
        "limits": [
            "The host trace has Q, DEN and NI but no same-call AL/ALB or ABI Q word.",
            "Current private host source is a source-level density inference, not a historical build attestation.",
            "Neither conditional dry-number multiplier certifies the original QNICE payload basis.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path, nargs="?",
                        default=PARENT / "selected_packet.json")
    parser.add_argument("--sha256", default=PACKET_SHA256)
    args = parser.parse_args()
    try:
        raw = args.packet.read_bytes()
        print(json.dumps(replay(raw, args.sha256), indent=2, allow_nan=False))
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as exc:
        parser.exit(1, "INVALID: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
