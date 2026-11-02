"""Versioned synthetic ice-NI applied-amount packet and independent replay.

The producer is the public Python ice substep with IceNumberAppliedLedger.
This schema does not attest a native C++ or host capture or physical NI units.
"""

from fractions import Fraction
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import struct


SCHEMA = "kdm6.ice_number_applied.synthetic.v1"
FIELDS = ("before", "after", "workn", "fall_rate", "candidate_out",
          "applied_out", "candidate_in", "applied_in", "projection",
          "fall_before", "fall_after", "delz", "dend")
HEX = re.compile(r"[0-9a-f]+\Z")


def need(ok, message):
    if not ok:
        raise ValueError(message)


def validate_identity(case_id, call_identity):
    """Apply the same exact-type contract to producer and verifier inputs."""
    need(type(case_id) is str and bool(case_id.strip()), "case id")
    need(type(call_identity) is dict and
         set(call_identity) == {"call", "column", "vertical_order"} and
         type(call_identity["call"]) is str and
         bool(call_identity["call"].strip()) and
         type(call_identity["column"]) is int and
         call_identity["column"] >= 0 and
         type(call_identity["vertical_order"]) is str and
         call_identity["vertical_order"] == "sedimentation_top_first",
         "call identity")


def fmt(dtype):
    return "<f" if dtype == "f32" else "<d"


def word(value, dtype):
    return format(int.from_bytes(struct.pack(fmt(dtype), float(value)), "little"),
                  "08x" if dtype == "f32" else "016x")


def value(raw, dtype):
    size = 4 if dtype == "f32" else 8
    need(isinstance(raw, str) and HEX.fullmatch(raw) is not None and
         len(raw) == 2*size, "numeric raw word")
    x = struct.unpack(fmt(dtype), int(raw, 16).to_bytes(size, "little"))[0]
    need(math.isfinite(x), "nonfinite numeric word")
    return x


def rounded(x, dtype):
    return value(word(x, dtype), dtype)


def serialize(records, *, case_id, call_identity, workn_by_step):
    """Serialize detached records plus the synthetic velocity operands."""
    validate_identity(case_id, call_identity)
    need(records and len(records) <= 100 and
         len(workn_by_step) == len(records),
         "substep/velocity inventory")
    first = records[0]
    need(first.before.shape[0] == 1 and 1 <= first.before.shape[1] <= 39,
         "one nonempty column required")
    K = first.before.shape[1]
    dtype = {"torch.float32": "f32", "torch.float64": "f64"}.get(str(first.before.dtype))
    need(dtype is not None, "record dtype")
    steps = []
    for position, record in enumerate(records, 1):
        need(type(record.n_current) is int and record.n_current == position and
             record.before.shape == (1, K) and
             record.before.dtype == first.before.dtype, "substep order/shape")
        data = {}
        workn = workn_by_step[position-1].detach().clone()  # value-only capture
        need(workn.shape == (1, K) and workn.dtype == first.before.dtype,
             "velocity shape/dtype")
        fall_rate = (record.before * workn / record.mstep_divisor[:, None]
                     * record.gate[:, None])
        for field in FIELDS:
            tensor = (workn if field == "workn" else fall_rate if field == "fall_rate"
                      else getattr(record, field))
            need(tensor.shape == (1, K) and tensor.dtype == first.before.dtype,
                 "record field shape/dtype " + field)
            data[field] = [word(x, dtype) for x in tensor[0].tolist()]
        steps.append({"n_current": position,
                      "dtcld": word(record.dtcld, "f64"),
                      "mstep": word(record.mstep_divisor[0].item(), dtype),
                      "gate": word(record.gate[0].item(), dtype),
                      "fields": data})
    return {"schema": SCHEMA, "scientific_status": "SYNTHETIC_ONLY",
            "case_id": case_id, "call_identity": call_identity.copy(),
            "dtype": dtype, "K": K, "substeps": steps}


def replay(packet, *, expected_case_id, expected_identity,
           expected_levels, expected_substeps):
    """Check exact schema and reconstruct state stores before budget metrics."""
    need(isinstance(packet, dict) and set(packet) ==
         {"schema", "scientific_status", "case_id", "call_identity",
          "dtype", "K", "substeps"}, "packet inventory")
    validate_identity(packet["case_id"], packet["call_identity"])
    validate_identity(expected_case_id, expected_identity)
    need(packet["schema"] == SCHEMA and
         packet["scientific_status"] == "SYNTHETIC_ONLY" and
         packet["case_id"] == expected_case_id and
         packet["call_identity"] == expected_identity,
         "trusted synthetic identity")
    dtype = packet["dtype"]
    need(dtype in ("f32", "f64") and type(expected_levels) is int and
         1 <= expected_levels <= 39 and type(packet["K"]) is int and
         packet["K"] == expected_levels and type(expected_substeps) is int and
         1 <= expected_substeps <= 100 and
         isinstance(packet["substeps"], list) and
         len(packet["substeps"]) == expected_substeps,
         "dtype/level/substep inventory")
    K = packet["K"]
    previous_after = None
    previous_fall_after = None
    fixed_call_words = None
    summaries = []
    for n_current, step in enumerate(packet["substeps"], 1):
        need(isinstance(step, dict) and set(step) ==
             {"n_current", "dtcld", "mstep", "gate", "fields"} and
             type(step["n_current"]) is int and
             step["n_current"] == n_current and
             isinstance(step["fields"], dict) and
             set(step["fields"]) == set(FIELDS), "substep field/order inventory")
        dt = value(step["dtcld"], "f64")
        dt_operand = rounded(dt, dtype)  # scalar → tensor dtype before multiply
        mstep = value(step["mstep"], dtype)
        gate = value(step["gate"], dtype)
        need(dt > 0 and 1 <= mstep <= 100 and mstep.is_integer() and
             gate == float(n_current <= mstep), "substep gate/divisor")
        fields = {}
        for field in FIELDS:
            words = step["fields"][field]
            need(isinstance(words, list) and len(words) == K,
                 "level inventory " + field)
            fields[field] = [value(x, dtype) for x in words]
        before, after = fields["before"], fields["after"]
        if previous_after is not None:
            need(step["fields"]["before"] == previous_after,
                 "substep state continuity")
            need(step["fields"]["fall_before"] == previous_fall_after,
                 "substep fall continuity")
        previous_after = step["fields"]["after"]
        previous_fall_after = step["fields"]["fall_after"]
        call_words = (step["dtcld"], step["mstep"],
                      tuple(step["fields"]["delz"]),
                      tuple(step["fields"]["dend"]))
        if fixed_call_words is None:
            fixed_call_words = call_words
        else:
            need(call_words == fixed_call_words, "call-wide timestep/geometry")
        need(all(z > 0 for z in fields["delz"]) and
             all(z > 1e-9 for z in fields["delz"]) and
             all(z > 0 for z in fields["dend"]), "geometry/density domain")
        expected = []
        for k in range(K):
            out = fields["applied_out"][k]
            incoming = fields["applied_in"][k]
            candidate_out = fields["candidate_out"][k]
            candidate_in = fields["candidate_in"][k]
            fall_rate = fields["fall_rate"][k]
            workn = fields["workn"][k]
            need(workn >= 0 and fall_rate >= 0, "fall velocity/rate domain")
            source_rate = rounded(before[k] * workn, dtype)
            source_rate = rounded(source_rate / mstep, dtype)
            source_rate = rounded(source_rate * gate, dtype)
            need(word(source_rate, dtype) == step["fields"]["fall_rate"][k],
                 "fall rate source-order raw bits")
            need(word(rounded(fall_rate * dt_operand, dtype), dtype) ==
                 step["fields"]["candidate_out"][k],
                 "fall candidate source-order raw bits")
            need(word(rounded(fields["fall_before"][k] + fall_rate, dtype), dtype)
                 == step["fields"]["fall_after"][k],
                 "fall accumulator raw bits")
            need(candidate_out >= 0 and candidate_in >= 0 and
                 0 <= out <= candidate_out and 0 <= incoming <= candidate_in,
                 "applied/candidate bounds")
            if k == 0:
                need(step["fields"]["applied_out"][k] ==
                     step["fields"]["candidate_out"][k] and
                     step["fields"]["applied_in"][k] == word(0.0, dtype) and
                     step["fields"]["candidate_in"][k] == word(0.0, dtype),
                     "top applied amounts")
            else:
                source_in = rounded(fields["fall_rate"][k-1] *
                                    fields["delz"][k-1], dtype)
                source_in = rounded(source_in / fields["delz"][k], dtype)
                source_in = rounded(source_in * dt_operand, dtype)
                need(word(source_in, dtype) ==
                     step["fields"]["candidate_in"][k],
                     "incoming candidate source-order raw bits")
                need(step["fields"]["applied_out"][k] ==
                     word(min(candidate_out, before[k]), dtype) and
                     step["fields"]["applied_in"][k] ==
                     word(min(candidate_in, expected[k-1]), dtype),
                     "interior applied cap")
            pre_floor = rounded(before[k] - out, dtype)
            if k:
                pre_floor = rounded(pre_floor + incoming, dtype)
            reconstructed = max(pre_floor, 0.0)
            correction = max(-pre_floor, 0.0)
            need(word(reconstructed, dtype) == step["fields"]["after"][k],
                 "state replay raw bits")
            need(word(correction, dtype) == step["fields"]["projection"][k],
                 "projection raw bits")
            expected.append(reconstructed)

        # Fraction.from_float isolates aggregate roundoff from the already
        # recorded f32/f64 stores. It does not undo those stores' rounding.
        f = Fraction.from_float
        weights = [f(x) for x in fields["delz"]]
        change = sum((weights[k] * (f(after[k]) - f(before[k]))
                      for k in range(K)), Fraction())
        bottom = weights[-1] * f(fields["applied_out"][-1])
        interfaces = [weights[k]*f(fields["applied_out"][k]) -
                      weights[k+1]*f(fields["applied_in"][k+1])
                      for k in range(K-1)]
        projection = sum((weights[k]*f(fields["projection"][k])
                          for k in range(K)), Fraction())
        attributed = bottom + sum(interfaces, Fraction()) - projection
        loss = -change
        summaries.append({
            "n_current": n_current,
            "state_replay_raw_bits_equal": True,
            "state_replay_max_abs_residual": 0.0,
            "column_change_dz": float(change),
            "column_loss_dz": float(loss),
            "bottom_applied_out_dz": float(bottom),
            "interface_difference_dz": [float(x) for x in interfaces],
            "projection_dz": float(projection),
            "attributed_loss_dz": float(attributed),
            "closure_residual_dz": float(loss-attributed),
            "top_candidate_out": fields["candidate_out"][0],
            "top_scheduled_debit_before_floor": fields["applied_out"][0],
            "top_projection": fields["projection"][0],
            "top_realized_loss": before[0]-after[0],
            "fall_accumulator_delta_bottom":
                fields["fall_after"][-1]-fields["fall_before"][-1],
            "fall_rate_bottom": fields["fall_rate"][-1],
            "fall_amount_candidate_bottom": fields["candidate_out"][-1],
            "weight_coordinate": "dz in recorded numerical NI basis",
        })
    return {"schema": SCHEMA, "scientific_status": "SYNTHETIC_ONLY",
            "case_id": expected_case_id, "call_identity": expected_identity,
            "dtype": dtype, "K": K, "substeps": summaries,
            "physical_conservation_certified": False}


def canonical_bytes(packet):
    return (json.dumps(packet, indent=2, sort_keys=True) + "\n").encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--call", required=True)
    parser.add_argument("--column", type=int, required=True)
    parser.add_argument("--levels", type=int, required=True)
    parser.add_argument("--substeps", type=int, required=True)
    args = parser.parse_args()
    try:
        raw = args.packet.read_bytes()
        need(hashlib.sha256(raw).hexdigest() == args.sha256,
             "independent packet SHA-256")
        packet = json.loads(raw)
        identity = {"call": args.call, "column": args.column,
                    "vertical_order": "sedimentation_top_first"}
        print(json.dumps(replay(packet, expected_case_id=args.case_id,
                                expected_identity=identity,
                                expected_levels=args.levels,
                                expected_substeps=args.substeps),
                         indent=2, allow_nan=False))
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as exc:
        parser.exit(1, "INVALID: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
