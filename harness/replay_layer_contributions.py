#!/usr/bin/env python3
"""Build and replay the compact offline PR224 layer/K evidence.

The replay path is deliberately standard-library only.  It reads the public
JSON, contracts the retained raw K tokens with the fixed profile tangents, and
checks the recorded per-channel values and the decimal-token bound
``sum(abs(v) * q / 2)``.  ``--build`` is an evidence-maintainer convenience
that reads the retained local PR221/PR223 artifacts and writes the JSON.
Neither path invokes RTTOV or performs a new finite difference.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "harness/evidence/layer_contributions_2026-09-19.json"
NCH = 16
CHANNELS = list(range(9, 16))
FIELDS = ("T", "Q", "HYDRO6", "HYDRO7", "HYDRO_DEFF6", "HYDRO_DEFF7")
PROCESSES = ("deposition", "riming")
RAW_FIELDS = {
    "T": ("T", None),
    "Q": ("Q", None),
    "HYDRO6": ("HYDRO", 5),
    "HYDRO7": ("HYDRO", 6),
    "HYDRO_DEFF6": ("HYDRO_DEFF", 5),
    "HYDRO_DEFF7": ("HYDRO_DEFF", 6),
}
HEADER = re.compile(r"^PROFILES_K\(\s*(\d+)\s*\)%\s*([A-Za-z0-9_]+)\s*=\s*\($")
NUMERIC = re.compile(r"^[+-]?(?:(?:\d+(?:\.\d*)?)|(?:\.\d+))(?:[EeDd][+-]?\d+)?$")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rel(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT.resolve()))


def parse_numbers(path: Path) -> list[float]:
    return [float(x.replace("D", "E").replace("d", "e")) for x in path.read_text().split()]


def raw_blocks(path: Path) -> dict[str, dict[int, list[str]]]:
    blocks: dict[str, dict[int, list[str]]] = {}
    current: tuple[int, str] | None = None
    values: list[str] = []
    for line in path.read_text().splitlines():
        if current is None:
            match = HEADER.match(line)
            if match:
                current = (int(match.group(1)), match.group(2))
                values = []
            continue
        if line.strip() == ")":
            row, field = current
            if row in blocks.setdefault(field, {}):
                raise AssertionError(f"duplicate raw K block {field} row {row}")
            blocks[field][row] = values
            current = None
            values = []
            continue
        for token in line.split():
            if not NUMERIC.fullmatch(token):
                raise AssertionError(f"invalid raw K token {token!r}")
            values.append(token)
    if current is not None:
        raise AssertionError(f"unterminated raw K block {current}")
    return blocks


def token_quantum_decimal(token: str) -> Decimal:
    value = Decimal(token.replace("D", "E").replace("d", "e"))
    return Decimal(1).scaleb(value.as_tuple().exponent)


def selected_tokens(k_path: Path, nlay: int) -> dict[str, dict[str, list[str]]]:
    blocks = raw_blocks(k_path)
    result: dict[str, dict[str, list[str]]] = {}
    for field in FIELDS:
        raw_field, slot = RAW_FIELDS[field]
        rows = blocks.get(raw_field)
        if rows is None or sorted(rows) != list(range(1, NCH + 1)):
            raise AssertionError(f"incomplete raw {raw_field} rows in {k_path}")
        length = len(rows[1])
        if slot is None:
            if length != nlay:
                raise AssertionError(f"bad {field} length {length}, expected {nlay}")
        elif length % nlay or length // nlay <= slot:
            raise AssertionError(f"bad {field} type-major length {length}")
        result[field] = {}
        for channel in CHANNELS:
            row = rows[channel + 1]
            if slot is None:
                selected = row
            else:
                selected = row[slot * nlay : (slot + 1) * nlay]
            if len(selected) != nlay:
                raise AssertionError(f"bad {field} selected length")
            # Keep the exact token spelling: it is the evidence input.
            result[field][str(channel)] = selected
    return result


def pressure(case: Path, nlay: int) -> tuple[list[float], list[float], dict[str, str]]:
    p = case / "in/profiles/001/atm/p.txt"
    ph = case / "in/profiles/001/atm/p_half.txt"
    p_hpa, p_half_hpa = parse_numbers(p), parse_numbers(ph)
    if len(p_hpa) != nlay or len(p_half_hpa) != nlay + 1:
        raise AssertionError("pressure shape mismatch")
    if not all(a < b < c for a, b, c in zip(p_half_hpa, p_hpa, p_half_hpa[1:])):
        raise AssertionError("pressure profile is not strictly interleaved")
    return p_hpa, p_half_hpa, {"p": sha256(p), "p_half": sha256(ph)}


def summarize(tokens: dict[str, list[str]], v: list[float]) -> dict[str, object]:
    nlay = len(v)
    if nlay != 39:
        raise AssertionError("this evidence is fixed to native 39 layers")
    if not all(math.isfinite(value) for value in v):
        raise AssertionError("non-finite tangent")
    channel_signed = []
    channel_bound = []
    channel_bound_decimal = []
    for channel in CHANNELS:
        row = tokens[str(channel)]
        if len(row) != nlay:
            raise AssertionError("K/tangent layer mismatch")
        if not all(math.isfinite(float(token.replace("D", "E").replace("d", "e"))) for token in row):
            raise AssertionError("non-finite raw K token")
        channel_signed.append(math.fsum(float(token.replace("D", "E").replace("d", "e")) * v[i] for i, token in enumerate(row)))
        # Use Decimal for the tiny bound accumulation.  v is the fixed
        # tangent as serialized in this artifact; Decimal(str(v)) preserves
        # that published decimal value while q comes from the exact token.
        bound = sum(
            abs(Decimal(str(v[i]))) * token_quantum_decimal(token) / Decimal(2)
            for i, token in enumerate(row)
        )
        channel_bound_decimal.append(format(bound, ".30e"))
        channel_bound.append(float(bound))
    nonzero = [i for i, value in enumerate(v) if value != 0.0]
    zeros = [i for i, value in enumerate(v) if value == 0.0]
    return {
        "channel_signed": channel_signed,
        "channel_k_text_bound": channel_bound,
        "channel_k_text_bound_decimal": channel_bound_decimal,
        "signed_total": math.fsum(channel_signed),
        "absolute_total": math.fsum(abs(x) for x in channel_signed),
        "nonzero_layer_indices": nonzero,
        "zero_layer_indices": zeros,
    }


def build() -> dict[str, object]:
    native = ROOT / "graphify-out/pr221-view/native_view_aux.json"
    psfc_meta = ROOT / "graphify-out/pr223-bottom/psfc_bottom.json"
    source = json.loads(native.read_text())
    center = ROOT / "graphify-out/pr221-view/actual-live-control-cases-i0dsh5gj/deposition-alpha0"
    bottom = ROOT / "graphify-out/pr223-bottom/psfc-bottom-deposition-alpha0"
    cases = {"center": center, "psfc_bottom": bottom}
    nlay = 39
    tangents: dict[str, dict[str, list[float]]] = {}
    for process in PROCESSES:
        tangents[process] = {}
        profile = source["processes"][process]["forward_ad_fixed_baseline_K"]["profile_tangents"]
        for field in FIELDS:
            values = [float(x) for x in profile[field]]
            if len(values) != nlay or not all(math.isfinite(x) for x in values):
                raise AssertionError(f"bad tangent {process}/{field}")
            tangents[process][field] = values

    p_hpa, p_half_hpa, pressure_hashes = pressure(center, nlay)
    case_data: dict[str, object] = {}
    for label, case in cases.items():
        k_path = case / "out/k/profiles_k.txt"
        case_p, case_ph, hashes = pressure(case, nlay)
        # The native layer-center pressure is retained identically.  The
        # bottom interface can move with PSFC; retain that case-specific
        # interface explicitly instead of silently treating it as a layer.
        if case_p != p_hpa:
            raise AssertionError("center and PSFC layer-center grids differ")
        case_data[label] = {
            "case_path": rel(case),
            "k_path": rel(k_path),
            "k_sha256": sha256(k_path),
            "pressure_paths_sha256": hashes,
            "p_hpa_by_layer": case_p,
            "p_half_hpa_by_interface": case_ph,
            "raw_k_tokens": selected_tokens(k_path, nlay),
        }

    # Add the sparse/full tangent contract and K-v summaries.  The raw token
    # rows remain complete for all 39 layers; no zero layer is implicit.
    tangent_data: dict[str, object] = {}
    summaries: dict[str, object] = {}
    for process in PROCESSES:
        tangent_data[process] = {}
        summaries[process] = {"fields": {}, "per_channel_total_psfc_minus_center": {}}
        for field in FIELDS:
            v = tangents[process][field]
            nz = [
                {"layer_index": i, "pressure_hpa": p_hpa[i], "v": v[i]}
                for i in range(nlay)
                if v[i] != 0.0
            ]
            tangent_data[process][field] = {
                "v_by_layer": v,
                "nonzero_layers": nz,
                "zero_layer_indices": [i for i, x in enumerate(v) if x == 0.0],
            }
            field_summary: dict[str, object] = {}
            for label in cases:
                tokens = case_data[label]["raw_k_tokens"][field]  # type: ignore[index]
                field_summary[label] = summarize(tokens, v)
            a = field_summary["center"]["channel_signed"]  # type: ignore[index]
            b = field_summary["psfc_bottom"]["channel_signed"]  # type: ignore[index]
            ba = field_summary["center"]["channel_k_text_bound"]  # type: ignore[index]
            bb = field_summary["psfc_bottom"]["channel_k_text_bound"]  # type: ignore[index]
            field_summary["psfc_minus_center"] = {
                "channel_delta": [y - x for x, y in zip(a, b)],
                "channel_abs_delta": [abs(y - x) for x, y in zip(a, b)],
                "channel_bound": [x + y for x, y in zip(ba, bb)],
            }
            summaries[process]["fields"][field] = field_summary  # type: ignore[index]

        for channel_offset, channel in enumerate(CHANNELS):
            deltas = [summaries[process]["fields"][f]["psfc_minus_center"]["channel_delta"][channel_offset] for f in FIELDS]  # type: ignore[index]
            bounds = [summaries[process]["fields"][f]["psfc_minus_center"]["channel_bound"][channel_offset] for f in FIELDS]  # type: ignore[index]
            total_delta = math.fsum(deltas)
            summaries[process]["per_channel_total_psfc_minus_center"][str(channel)] = {  # type: ignore[index]
                "delta": total_delta,
                "abs_delta": abs(total_delta),
                "bound": math.fsum(bounds),
            }

    result: dict[str, object] = {
        "evidence_id": "pr224-offline-layer-contributions-20260919",
        "status": "complete_offline_replay",
        "scope": "retained PR221 center and PR223 PSFC-bottom raw K; fixed PR221 profile tangents",
        "no_live_rttov": True,
        "no_new_finite_difference": True,
        "no_external_data": True,
        "dimensions": {
            "nlay": nlay,
            "usable_channels": CHANNELS,
            "channel_indexing": "0-based RTTOV channel slots; raw PROFILES_K rows are channel+1",
            "fields": list(FIELDS),
            "processes": list(PROCESSES),
            "layer_order": "index 0 is model top; index 38 is bottom; p and p_half increase downward",
            "p_hpa_by_layer": p_hpa,
            "p_half_hpa_by_interface": p_half_hpa,
            "interface_pressure_note": "layer-center p is common; retain each case's p_half, whose bottom interface may differ under PSFC substitution",
        },
        "source_artifacts": {
            "native_view_aux": {"path": rel(native), "sha256": sha256(native)},
            "psfc_bottom": {"path": rel(psfc_meta), "sha256": sha256(psfc_meta)},
            "pr224_replay_source": {"path": rel(ROOT / "graphify-out/pr224-contribution/replay_psfc_contribution.py"), "sha256": sha256(ROOT / "graphify-out/pr224-contribution/replay_psfc_contribution.py")},
            "pressure_grid_sha256": pressure_hashes,
        },
        "raw_layout": {field: {"raw_field": raw, "type_slot_zero_based": slot} for field, (raw, slot) in RAW_FIELDS.items()},
        "cases": case_data,
        "fixed_profile_tangents": tangent_data,
        "kv_summaries": summaries,
        "bound_contract": {
            "a": "sum_over_layers(float(raw_token) * v[layer])",
            "q": "10**decimal_exponent(raw_token), from the exact printed token",
            "per_channel_k_text_bound": "sum_over_layers(abs(v[layer]) * q[layer] / 2)",
            "total_psfc_bound": "sum of the six field bounds for that process/channel",
            "conditional_interpretation": "nearest-rounding fixed-v K-text bound only; it excludes upstream tangent error, RTTOV arithmetic, dK/dx, and upper extrapolation resolution",
        },
        "limitations": [
            "This artifact reuses retained offline PR221/PR223 outputs and does not make a live RTTOV call.",
            "The bound is conditional on fixed profile tangents and nearest decimal rounding of each raw K token.",
            "A layer span describes nonzero fixed-tangent support; all omitted layers are listed explicitly in zero_layer_indices.",
            "Existing liquid tangents HYDRO6 and HYDRO_DEFF6 are exactly zero in both retained process tangents.",
        ],
    }
    return result


def replay(data: dict[str, object]) -> None:
    dims = data["dimensions"]
    assert dims["nlay"] == 39
    assert dims["usable_channels"] == CHANNELS
    for process in PROCESSES:
        for field in FIELDS:
            tangent = data["fixed_profile_tangents"][process][field]  # type: ignore[index]
            v = tangent["v_by_layer"]  # type: ignore[index]
            assert len(v) == 39
            nonzero_indices = {entry["layer_index"] for entry in tangent["nonzero_layers"]}  # type: ignore[index]
            zero_indices = set(tangent["zero_layer_indices"])  # type: ignore[index]
            assert all(0 <= i < 39 for i in nonzero_indices | zero_indices)
            assert len(tangent["nonzero_layers"]) == len(nonzero_indices)  # type: ignore[index]
            assert len(tangent["zero_layer_indices"]) == len(zero_indices)  # type: ignore[index]
            assert nonzero_indices.isdisjoint(zero_indices)
            assert nonzero_indices | zero_indices == set(range(39))
            assert len(nonzero_indices) + len(zero_indices) == 39
            for entry in tangent["nonzero_layers"]:  # type: ignore[index]
                assert entry["v"] == v[entry["layer_index"]]
                assert entry["v"] != 0.0
            for index in zero_indices:
                assert v[index] == 0.0
            recomputed: dict[str, object] = {}
            for label in ("center", "psfc_bottom"):
                tokens = data["cases"][label]["raw_k_tokens"][field]  # type: ignore[index]
                assert set(tokens) == {str(channel) for channel in CHANNELS}
                assert all(len(tokens[str(channel)]) == 39 for channel in CHANNELS)
                got = summarize(tokens, v)
                recorded = data["kv_summaries"][process]["fields"][field][label]  # type: ignore[index]
                for key in ("channel_signed", "channel_k_text_bound"):
                    assert len(got[key]) == 7 and len(recorded[key]) == 7
                    for actual, expected in zip(got[key], recorded[key]):
                        assert math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-25), (process, field, label, key, actual, expected)
                assert got["channel_k_text_bound_decimal"] == recorded["channel_k_text_bound_decimal"]
                recomputed[label] = got
            field_record = data["kv_summaries"][process]["fields"][field]  # type: ignore[index]
            field_delta = field_record["psfc_minus_center"]  # type: ignore[index]
            assert len(field_delta["channel_delta"]) == 7
            assert len(field_delta["channel_bound"]) == 7
            expected_delta = [
                psfc - center
                for center, psfc in zip(recomputed["center"]["channel_signed"], recomputed["psfc_bottom"]["channel_signed"])  # type: ignore[index]
            ]
            expected_bound = [
                center + psfc
                for center, psfc in zip(recomputed["center"]["channel_k_text_bound"], recomputed["psfc_bottom"]["channel_k_text_bound"])  # type: ignore[index]
            ]
            for actual, expected in zip(field_delta["channel_delta"], expected_delta):
                assert math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-25)
            for actual, expected in zip(field_delta["channel_bound"], expected_bound):
                assert math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-25)
    for process in PROCESSES:
        for offset, channel in enumerate(CHANNELS):
            fields = data["kv_summaries"][process]["fields"]  # type: ignore[index]
            d = math.fsum(fields[field]["psfc_minus_center"]["channel_delta"][offset] for field in FIELDS)
            b = math.fsum(fields[field]["psfc_minus_center"]["channel_bound"][offset] for field in FIELDS)
            recorded = data["kv_summaries"][process]["per_channel_total_psfc_minus_center"][str(channel)]  # type: ignore[index]
            assert math.isclose(d, recorded["delta"], rel_tol=0.0, abs_tol=1e-25)
            assert math.isclose(b, recorded["bound"], rel_tol=0.0, abs_tol=1e-25)
    print("layer contribution replay: PASS")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true", help="build the evidence JSON from retained local artifacts")
    parser.add_argument("--json", type=Path, default=OUT)
    args = parser.parse_args()
    if args.build:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(build(), indent=2) + "\n")
    replay(json.loads(args.json.read_text()))


if __name__ == "__main__":
    main()
