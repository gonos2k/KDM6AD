"""Separate native NI net intervals from saved endpoint density evidence."""

import hashlib
import importlib
import json
from pathlib import Path
import struct


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
PARENT = REPO / "harness/evidence/native_c5_limiter_call_2026-11-01"
PARENT_VERIFY = importlib.import_module(
    "harness.evidence.native_c5_limiter_call_2026-11-01.verify_packet")
ENDPOINT_WORDS_SHA256 = (
    "84c5c44ccac4980697dfccd1e971f10c7799b3194302490d551d509f35e4e631"
)


def need(condition, message):
    if not condition:
        raise ValueError(message)


def f32(raw):
    return struct.unpack("<f", int(raw, 16).to_bytes(4, "little"))[0]


def f64(raw):
    return struct.unpack("<d", int(raw, 16).to_bytes(8, "little"))[0]


def f32_word(value):
    return format(int.from_bytes(struct.pack("<f", value), "little"), "08x")


def report(packet_raw, endpoint_raw):
    PARENT_VERIFY.verify(packet_raw, PARENT_VERIFY.PACKET_SHA256)
    need(hashlib.sha256(endpoint_raw).hexdigest() == ENDPOINT_WORDS_SHA256,
         "selected endpoint words SHA-256")
    packet = json.loads(packet_raw)
    endpoint = json.loads(endpoint_raw)
    need(endpoint["schema"] == "kdm6.native_qnice_endpoint_words.v1" and
         endpoint["endpoint_sha256"] == packet["run_on"]["endpoint_sha256"] and
         endpoint["native_ij_1based"] == [164, 242] and
         endpoint["saved_time"] == "2025-07-19_00:01:00" and
         endpoint["timing"] == "saved 00:01:00 endpoint, not the microphysics call" and
         set(endpoint["cells"]) == {"21", "23"}, "endpoint selection identity")
    traces = {tuple(r["native_ijk_1based"]):
              dict(zip(r["fields"], r["raw_hex"]))
              for r in packet["host_selected_trace"]["on_v1"]
              if r["stage"] == "MP_INPUT"}
    outputs = {tuple(r["native_ijk_1based"]):
               dict(zip(r["fields"], r["raw_hex"]))
               for r in packet["host_selected_trace"]["on_v1"]
               if r["stage"] == "MP_OUTPUT"}
    cells = {}
    for level, index in ((21, "20"), (23, "22")):
        key = (164, 242, level)
        host_in, host_out = traces[key], outputs[key]
        rows = {(r["stage"], r["field"]): r for r in packet["selected_rows"]
                if r["k_zero"] == index}
        words = endpoint["cells"][str(level)]
        need(set(words) == {"AL", "ALB", "RHO", "QVAPOR", "QNICE"} and
             all(isinstance(v, str) and len(v) == 8 for v in words.values()),
             "endpoint field inventory")
        al, alb, rho = (f32(words[name]) for name in ("AL", "ALB", "RHO"))
        source_order_rho = f32(f32_word(1.0 / f32(f32_word(al + alb))))
        need(f32_word(source_order_rho) == words["RHO"],
             "saved endpoint AL/ALB-to-RHO f32 relation")
        need(words["RHO"] == host_in["DEN"],
             "endpoint RHO versus call input DEN bits")
        need(words["QNICE"] == host_out["NI"],
             "endpoint QNICE versus host output NI bits")
        ingress = f32(host_in["NI"])
        step = f64(rows["step_entry", "state.ni"]["raw_hex"])
        c3 = f64(rows["c3_in", "state.ni"]["raw_hex"])
        final = f64(rows["dsd_out", "new_state.ni"]["raw_hex"])
        need(f32_word(final) == host_out["NI"], "final NI host rounding")
        cells[str(level)] = {
            "ingress_ni": ingress, "post_sed_step_entry_ni": step,
            "c3_input_ni": c3, "final_dsd_ni": final,
            "net_ingress_to_step": step - ingress,
            "net_step_to_c3": c3 - step,
            "net_c3_to_final": final - c3,
            "endpoint_words": words,
            "endpoint_source_order_rho": source_order_rho,
            "endpoint_rho_equals_ingress_den_bits": True,
            "endpoint_qv_equals_ingress_qv_bits": words["QVAPOR"] == host_in["Q"],
        }
    return {
        "schema": "kdm6.native_qnice_prec3_endpoints.v1",
        "parent_packet_sha256": hashlib.sha256(packet_raw).hexdigest(),
        "endpoint_words_sha256": hashlib.sha256(endpoint_raw).hexdigest(),
        "cells": cells,
        "physical_unit_status": "INCONCLUSIVE",
        "interpretation": "Selected numeric net intervals and later saved endpoint only; no applied process budget or same-call AL/ALB capture.",
    }


def main():
    packet = (PARENT / "selected_packet.json").read_bytes()
    words = (ROOT / "endpoint_density_words.json").read_bytes()
    print(json.dumps(report(packet, words), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
