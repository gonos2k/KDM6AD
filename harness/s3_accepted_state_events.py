#!/usr/bin/env python3
"""Source-pinned G2 candidate reader and raw-operand S3 event replay."""

from __future__ import annotations

import math
import hashlib
import json
import struct
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from replay_native_number import f32
from replay_negative_number_trace import fma32, rk_value


SCHEMA = "s3-first-negative-face-event-v2"
FACE_ORDER = ("xL", "xR", "yS", "yN", "zB", "zT")
G2_EVIDENCE_SHA256 = "fcb0cb61b3dcdeded0705d4de8f5161aeae0f071041f9ffd5c4a0f310c2a6596"
OWNED_GRID = {"i0": 1, "i1": 234, "j0": 1, "j1": 282, "k0": 1, "k1": 39}
TILE_EXTENTS = {
    1: {"i0": 1, "i1": 234, "j0": 1, "j1": 142, "k0": 1, "k1": 39, "owned": 1_295_892},
    2: {"i0": 1, "i1": 234, "j0": 143, "j1": 282, "k0": 1, "k1": 39, "owned": 1_277_640},
}
SOURCE_HASHES = {
    "module_advect_em.F": "58253bdbeb188dd47ed0579fcd2891086be1889b75c0c7d3696c9ad1d213559d",
    "module_em.F": "7695bfb05a7f99763334a6e69523bbcc1de0f2c659177a18c10a6e1cf530a0c7",
    "solve_em.F": "d66e9db1bba8f37e3f46d30c2fd74bdf8def411adf233376a69e0b401c6d3d1f",
}
HOST_MODULE_EM_OBJECT_SHA256 = "7be51c5276e3e28cefe6482377b9fb9d7e8cb3d1db972efbf2ad2b24137348c2"
FIRST_SCAN = (2, 1, "RK_AFTER")
QN_FIELDS = ("QNCLOUD", "QNRAIN", "QNICE")
_RK12 = ("RK_TEND_BEFORE", "RK_TEND_AFTER", "RK_BEFORE", "RK_AFTER",
         "FLOW_BC_BEFORE", "FLOW_BC_AFTER", "RK_PHYS_BC_BEFORE",
         "RK_PHYS_BC_AFTER")
_RK3 = ("PD_OLD_PHYS_BC_BEFORE", "PD_OLD_PHYS_BC_AFTER", "RK_PD_BEFORE",
        "RK_PD_AFTER", "RK_TEND_BEFORE", "RK_TEND_AFTER", "RK_BEFORE",
        "RK_AFTER", "FLOW_BC_BEFORE", "FLOW_BC_AFTER")
PRIOR_SCAN_STAGES = tuple(
    [(1, 0, "BEGIN")]
    + [(1, rk, stage) for rk in (1, 2) for stage in _RK12]
    + [(1, 3, stage) for stage in _RK3]
    + [(1, 4, stage) for stage in ("FINAL_PHYS_BC_BEFORE", "FINAL_PHYS_BC_AFTER")]
    + [(1, 0, stage) for stage in ("MICRO_BEFORE", "MICRO_AFTER", "END")]
    + [(2, 0, "BEGIN")]
    + [(2, 1, stage) for stage in ("RK_TEND_BEFORE", "RK_TEND_AFTER", "RK_BEFORE")]
)


@dataclass(frozen=True)
class Attribution:
    """Budget attribution from one newly negative QN donor store."""

    state_class: str
    budget_before_store: Fraction | None
    accepted_value: float
    status: str
    cause: str
    crossing_group: str | None


@dataclass(frozen=True)
class FirstCandidate:
    """Lexicographically first QN transition at the measured whole-grid scan."""

    variant: str
    field: str
    step: int
    rk: int
    i: int
    k: int
    j: int
    before: float
    after: float
    source_tile: int
    state_class: str = "solver_internal"


def _first_qn_candidate(data: dict[str, Any], variant: str) -> FirstCandidate:
    """Find the first step-2/RK1 whole-owned-grid QN transition in G2 data.

    This selects a source-pinned follow-up target. The existing two-tile scan
    orders each tile's first transition; taking the minimum global
    ``(k,j,i)`` yields the lexicographic grid candidate. It is not an in-call
    event-order claim.
    """
    if data.get("schema") != "number-face-flux-v1":
        raise ValueError("unexpected whole-grid evidence schema")
    prov = data.get("provenance", {})
    if prov.get("advect_source", {}).get("source_sha256") != SOURCE_HASHES["module_advect_em.F"]:
        raise ValueError("advector source hash does not match the pinned evidence")
    if prov.get("solver_source", {}).get("source_sha256") != SOURCE_HASHES["solve_em.F"]:
        raise ValueError("solver source hash does not match the pinned evidence")
    if variant not in data.get("variants", {}):
        raise ValueError("missing requested trajectory")
    rows = data["variants"][variant].get("summaries", [])
    for step, rk, stage in PRIOR_SCAN_STAGES:
        checkpoint = [
            row for row in rows
            if (row.get("step"), row.get("rk"), row.get("stage")) == (step, rk, stage)
            and row.get("field") in QN_FIELDS
        ]
        expected_tiles = {0} if rk == 0 else {1, 2}
        if stage in {"RK_PD_BEFORE", "RK_PD_AFTER"}:
            expected_buffers = {0, 1}
        elif stage.startswith("PD_OLD_"):
            expected_buffers = {1}
        else:
            expected_buffers = {0}
        if {row.get("buffer") for row in checkpoint} != expected_buffers:
            raise ValueError(f"unexpected buffer set at {step}/{rk}/{stage}")
        for buffer in expected_buffers:
            buffer_rows = [row for row in checkpoint if row.get("buffer") == buffer]
            if (len(buffer_rows) != 3 * len(expected_tiles)
                    or {r.get("tile") for r in buffer_rows} != expected_tiles):
                raise ValueError(f"incomplete prior QN scan at {step}/{rk}/{stage}/buffer={buffer}")
            for row in buffer_rows:
                if row.get("rank") != 0:
                    raise ValueError(f"unexpected rank owner at {step}/{rk}/{stage}")
                if rk == 0:
                    if (row.get("tile") != 0 or row.get("owned") != 2_573_532
                            or any(row.get(key) != value for key, value in OWNED_GRID.items())):
                        raise ValueError(f"whole-grid census mismatch at {step}/{rk}/{stage}/{row['field']}")
                else:
                    tile = row.get("tile")
                    if tile not in TILE_EXTENTS:
                        raise ValueError(f"unexpected owner tile at {step}/{rk}/{stage}/{row['field']}")
                    expected = TILE_EXTENTS[tile]
                    if (row.get("selected") != {"QNCLOUD": 3, "QNICE": 4, "QNRAIN": 6}[row["field"]]
                            or any(row.get(key) != expected[key] for key in expected)):
                        raise ValueError(f"tile geometry/census mismatch at {step}/{rk}/{stage}/{row['field']}/tile={tile}")
            for field in QN_FIELDS:
                field_rows = [row for row in buffer_rows if row["field"] == field]
                if sum(row.get("owned", 0) for row in field_rows) != 2_573_532:
                    raise ValueError(f"owned-grid coverage mismatch at {step}/{rk}/{stage}/{field}")
        if any(row.get("negative") != 0 for row in checkpoint):
            raise ValueError(f"a QN negative predates the pinned candidate at {step}/{rk}/{stage}")
    candidate_rows = [
        row for row in rows
        if (row.get("step"), row.get("rk"), row.get("stage")) == FIRST_SCAN
        and row.get("field") in QN_FIELDS
    ]
    if len(candidate_rows) != 6:
        raise ValueError("first-scan candidate universe is incomplete")
    transitions = [row for row in candidate_rows
                   if row.get("first_new_valid") is True and row.get("new_negative", 0) > 0]
    if not transitions:
        raise ValueError("no QN transition at the pinned first scan")
    owners = {(r.get("rank"), r.get("tile")) for r in transitions}
    if any(rank != 0 or tile not in (1, 2) for rank, tile in owners):
        raise ValueError("unexpected ownership topology in pinned two-tile scan")
    for field in QN_FIELDS:
        field_rows = [r for r in transitions if r["field"] == field]
        if {r["tile"] for r in field_rows} != {1, 2}:
            raise ValueError(f"incomplete two-tile scan for {field}")
        for r in field_rows:
            tile = r["tile"]
            expected = TILE_EXTENTS[tile]
            if (r.get("rank") != 0
                    or any(r.get(key) != expected[key] for key in expected)
                    or r.get("selected") != {"QNCLOUD": 3, "QNICE": 4, "QNRAIN": 6}[field]):
                raise ValueError(f"candidate owner/field identity mismatch for {field}/tile={tile}")
            xyz = (r.get("first_new_i"), r.get("first_new_j"), r.get("first_new_k"))
            if any(isinstance(v, bool) or not isinstance(v, int) for v in xyz):
                raise ValueError("candidate coordinates must be integer Fortran indices")
            if not (expected["i0"] <= xyz[0] <= expected["i1"]
                    and expected["j0"] <= xyz[1] <= expected["j1"]
                    and expected["k0"] <= xyz[2] <= expected["k1"]):
                raise ValueError(f"candidate cell is outside its declared owner tile: {field}/tile={tile}")
            if r.get("owned") != expected["owned"]:
                raise ValueError(f"per-tile owned-cell census mismatch for {field}/tile={tile}")
    row = min(transitions, key=lambda r: (r["first_new_k"], r["first_new_j"], r["first_new_i"]))
    if row["first_new_previous"] < 0 or row["first_new_value"] >= 0:
        raise ValueError("summary does not describe a nonnegative-to-negative transition")
    if row["field"] != "QNCLOUD" or (row["first_new_i"], row["first_new_k"], row["first_new_j"]) != (46, 1, 2):
        raise ValueError("first candidate does not match the pinned QNCLOUD cell identity")
    return FirstCandidate(
        variant, row["field"], row["step"], row["rk"], row["first_new_i"],
        row["first_new_k"], row["first_new_j"], row["first_new_previous"],
        row["first_new_value"], row["tile"],
    )


def first_qn_candidate(path: str, variant: str) -> FirstCandidate:
    """Read the immutable G2 artifact, then validate all owned scan records."""
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != G2_EVIDENCE_SHA256:
        raise ValueError("G2 evidence bytes do not match the accepted source-pinned artifact")
    return _first_qn_candidate(json.loads(raw), variant)


def _raw_f32(word: Any, name: str) -> float:
    if not isinstance(word, str) or len(word) != 10 or not word.startswith("0x"):
        raise ValueError(f"{name} must be an eight-hex-digit binary32 word")
    try:
        value = struct.unpack("!f", bytes.fromhex(word[2:]))[0]
    except (ValueError, struct.error) as exc:
        raise ValueError(f"{name} is not a binary32 word") from exc
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def _word(value: float) -> str:
    return "0x" + struct.pack("!f", f32(value)).hex()


def _identity(event: dict[str, Any]) -> tuple[str, int, int]:
    """Check the source-pinned candidate identity shared by trace states."""
    identity = event.get("identity")
    if not isinstance(identity, dict):
        raise ValueError("event must contain a Fortran owner identity")
    expected = {
        "field": "QNCLOUD", "species": 3, "step": 2, "rank": 0,
        "tile": 1, "i": 46, "k": 1, "j": 2,
    }
    if any(identity.get(key) != value for key, value in expected.items()):
        raise ValueError("event owner/field/coordinate differs from pinned RK1 candidate")
    if any(isinstance(identity.get(key), bool) or not isinstance(identity.get(key), int)
           for key in ("species", "step", "rank", "tile", "i", "k", "j")):
        raise ValueError("event identity fields must be integer Fortran indices")
    return identity["field"], identity["step"], identity.get("rk")


def attribute_event(event: dict[str, Any]) -> Attribution:
    """Replay the pinned RK1 raw operands, or classify accepted state only.

    A model-step accepted state follows RK3, intervening microphysics, and
    boundary processing. Without those intervening source deltas, it cannot be
    attributed to the earlier RK1 face operands.
    """
    if event.get("schema") != SCHEMA:
        raise ValueError("unexpected S3 event schema")
    if event.get("source_hashes") != SOURCE_HASHES:
        raise ValueError("source hashes do not match the pinned native path")
    if event.get("layout") != {"mpi_ranks": 1, "threads": 1, "tiles": 1}:
        raise ValueError("event is not from the declared 1x1 layout")
    state_class = event.get("state_class")
    if state_class not in {"solver_internal", "model_step_accepted"}:
        raise ValueError("state_class must distinguish internal stage from accepted step")
    expected_checkpoint = {
        "solver_internal": ("RK_AFTER", "rk_update_scalar"),
        "model_step_accepted": ("STEP_ACCEPTED", "step_acceptance_scan"),
    }[state_class]
    if (event.get("checkpoint"), event.get("producer")) != expected_checkpoint:
        raise ValueError("checkpoint/producer does not match the declared state class")
    if event.get("copy_only") is not False:
        raise ValueError("event must be a producing store or accepted-state scan, not a boundary copy")
    for name in ("native_build_sha256", "control_history_sha256", "capture_history_sha256"):
        digest = event.get(name)
        if (not isinstance(digest, str) or len(digest) != 64
                or any(c not in "0123456789abcdef" for c in digest)):
            raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    if event["control_history_sha256"] != event["capture_history_sha256"]:
        raise ValueError("native capture failed the required history noninterference check")
    if event.get("module_em_object_sha256") != HOST_MODULE_EM_OBJECT_SHA256:
        raise ValueError("RK store replay requires the source-pinned retained module_em object")
    _, step, identity_rk = _identity(event)
    rk = event.get("rk")
    if rk != identity_rk or step != event.get("identity", {}).get("step"):
        raise ValueError("event stage differs from its owner identity")
    if state_class == "model_step_accepted":
        accepted_keys = {
            "schema", "source_hashes", "layout", "state_class", "checkpoint", "producer",
            "copy_only", "identity", "rk", "value_after_bits", "native_build_sha256",
            "control_history_sha256", "capture_history_sha256", "module_em_object_sha256",
        }
        if set(event) != accepted_keys:
            raise ValueError("accepted-state events are classification-only; RK operands cannot be attached")
        if rk != 3:
            raise ValueError("a model-step accepted event must follow the final RK stage")
        after = _raw_f32(event.get("value_after_bits"), "value_after_bits")
        if after >= 0.0:
            raise ValueError("accepted-state classification requires a negative QN value")
        return Attribution(state_class, None, after, "UNVERIFIED_ARITHMETIC",
                           "accepted_state_classification_only", None)

    internal_keys = {
        "schema", "source_hashes", "layout", "state_class", "checkpoint", "producer",
        "copy_only", "identity", "rk", "value_before_bits", "value_after_bits", "limiter",
        "face_flux_bits", "metric_bits", "rk_bits", "native_build_sha256",
        "control_history_sha256", "capture_history_sha256", "module_em_object_sha256",
    }
    if set(event) != internal_keys:
        raise ValueError("internal events must use the raw-operand schema without derived face amounts")
    if (step, rk) != (2, 1):
        raise ValueError("source arithmetic is pinned only for step 2 RK1")
    value = _raw_f32(event.get("value_before_bits"), "value_before_bits")
    after = _raw_f32(event.get("value_after_bits"), "value_after_bits")
    if value < 0.0 or after >= 0.0:
        raise ValueError("event is not the pinned nonnegative-to-negative transition")
    if event.get("limiter") != "none_at_this_stage":
        raise ValueError("RK1 uses ordinary advection; PD limiter attribution is invalid")

    faces = event.get("face_flux_bits")
    metrics = event.get("metric_bits")
    rk_words = event.get("rk_bits")
    if not isinstance(faces, dict) or set(faces) != set(FACE_ORDER):
        raise ValueError("raw event must contain exactly six oriented face flux words")
    if not isinstance(metrics, dict) or set(metrics) != {"msftx", "msfty", "rdx", "rdy", "rdzw", "dt"}:
        raise ValueError("raw event is missing a pinned face metric or timestep")
    expected_rk_words = {"c1", "c2", "mu_old", "mu_new", "mu_base",
                         "scalar_tend", "observed_advect_tend"}
    if not isinstance(rk_words, dict) or set(rk_words) != expected_rk_words:
        raise ValueError("raw event is missing RK numerator or tendency operands")
    flux = {name: _raw_f32(faces[name], f"face_flux_bits.{name}") for name in FACE_ORDER}
    m = {name: _raw_f32(metrics[name], f"metric_bits.{name}") for name in metrics}
    q = {name: _raw_f32(rk_words[name], f"rk_bits.{name}") for name in rk_words}

    # module_advect_em.F: ordinary advect_scalar updates x, then y, then z.
    # Each difference, metric product, and tendency store is rounded to REAL4.
    tendency = 0.0
    mrdx = f32(m["msftx"] * m["rdx"])
    x_difference = f32(flux["xR"] - flux["xL"])
    tendency = f32(tendency - f32(mrdx * x_difference))
    mrdy = f32(m["msftx"] * m["rdy"])
    y_difference = f32(flux["yN"] - flux["yS"])
    tendency = f32(tendency - f32(mrdy * y_difference))
    z_difference = f32(flux["zT"] - flux["zB"])
    tendency = f32(tendency - f32(_raw_f32(metrics["rdzw"], "rdzw") * z_difference))
    if _word(tendency) != rk_words["observed_advect_tend"]:
        raise ValueError("source-order REAL4 face replay does not match observed advective tendency")

    rk_input = dict(
        old=value, rk=1, value=value,
        mu_old=q["mu_old"], mu_new=q["mu_new"], mu_base=q["mu_base"],
        c1=q["c1"], c2=q["c2"], advect_tend=tendency,
        msfty=m["msfty"], sc_tend=q["scalar_tend"], dt=m["dt"], i=46, j=2,
    )
    replayed = rk_value(rk_input)
    if _word(replayed) != event.get("value_after_bits"):
        raise ValueError("fused REAL4 RK numerator/store does not match observed output")

    # Only report a face crossing when independently computed face terms close
    # to the executed mapped tendency in source order. Otherwise preserve the
    # negative store with an unverified status.
    weighted_dt = f32(m["dt"] * m["msfty"])
    face_metrics = {"xL": mrdx, "xR": mrdx, "yS": mrdy,
                    "yN": mrdy, "zB": m["rdzw"], "zT": m["rdzw"]}
    signs = {"xL": 1, "xR": -1, "yS": 1, "yN": -1, "zB": 1, "zT": -1}
    deltas = {
        name: f32(signs[name] * f32(f32(weighted_dt * face_metrics[name]) * flux[name]))
        for name in FACE_ORDER
    }
    face_total = 0.0
    for name in FACE_ORDER:
        face_total = f32(face_total + deltas[name])
    expected_advective_amount = f32(m["dt"] * f32(tendency * m["msfty"]))
    if _word(face_total) != _word(expected_advective_amount):
        return Attribution(state_class, None, after, "UNVERIFIED_ARITHMETIC",
                           "per_face_amounts_do_not_close", None)

    # The source evaluates opposing faces as a pair. Report the first axis
    # group that crosses zero, never a fabricated single-face execution order.
    base_weight = fma32(q["c1"], f32(q["mu_old"] + q["mu_base"]), q["c2"])
    if base_weight <= 0.0:
        raise ValueError("source mass coefficient must be positive")
    available = Fraction(base_weight) * Fraction(value) + Fraction(m["dt"]) * Fraction(q["scalar_tend"])
    remaining = available
    crossing_group = None
    for group, pair in (("x_pair", ("xL", "xR")), ("y_pair", ("yS", "yN")),
                        ("z_pair", ("zB", "zT"))):
        remaining += Fraction(deltas[pair[0]]) + Fraction(deltas[pair[1]])
        if crossing_group is None and remaining < 0:
            crossing_group = group
    status = "ARITHMETIC_REPLAY_MATCHED" if crossing_group is not None else "UNVERIFIED_ARITHMETIC"
    cause = "RK1_FACE_PAIR_BUDGET_CROSSING" if crossing_group is not None else "no_face_pair_crossing"
    return Attribution(state_class, remaining, after, status, cause, crossing_group)
