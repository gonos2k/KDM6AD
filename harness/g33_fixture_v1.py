#!/usr/bin/env python3
"""Single raw-bit authority for the four-backend G3.3 arithmetic fixture.

The JSON contains IEEE-754 f32 words only. This module validates that authority,
computes the fixture/common-parameter identities used by the strict Fortran
parser, generates the C++/Fortran bindings, and validates the C++ fixture-only
probe. Generated bindings are checked in; ``--check`` fails on drift.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "harness" / "g33_fixture_v1.json"
CPP_OUT = ROOT / "harness" / "g33_overlay" / "g33_fixture_v1.h"
FORTRAN_OUT = ROOT / "harness" / "g33_fortran" / "g33_fixture_v1.f90"

STATE_FIELDS = ("th", "qv", "qc", "qr", "qi", "qs", "qg",
                "nccn", "nc", "ni", "nr", "bg")
FORCING_FIELDS = ("rho", "pii", "p", "delz")
GRID_FIELDS = STATE_FIELDS + FORCING_FIELDS
COMMON_PARAMETERS = ("dt", "ncmin_land", "ncmin_sea", "qmin")
FORTRAN_ONLY_PARAMETERS = ("ccn0", "scale_h")
_HEX32 = re.compile(r"^[0-9a-f]{8}$")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_manifest(path: Path = MANIFEST) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    _require(data.get("schema_version") == 1, "fixture schema_version must be 1")
    _require(data.get("fixture_id") == "arithmetic_synthetic_v1", "unexpected fixture_id")
    _require(data.get("science_role") == "arithmetic_synthetic", "science_role must be explicit")
    _require(data.get("vertical_layout") == "top_first", "vertical_layout must be top_first")
    B, K = data.get("B"), data.get("K")
    _require(isinstance(B, int) and B > 0, "B must be a positive integer")
    _require(isinstance(K, int) and K > 1, "K must be an integer > 1")

    fields = data.get("fields")
    _require(isinstance(fields, dict), "fields must be an object")
    _require(set(fields) == set(GRID_FIELDS),
             f"field keys differ: {sorted(set(fields or {}) ^ set(GRID_FIELDS))}")
    for name in GRID_FIELDS:
        words = fields[name]
        _require(isinstance(words, list) and len(words) == B * K,
                 f"{name} must contain B*K={B*K} words")
        _require(all(isinstance(w, str) and _HEX32.fullmatch(w) for w in words),
                 f"{name} contains a malformed f32 word")

    xland = data.get("xland")
    _require(isinstance(xland, list) and len(xland) == B, f"xland must contain {B} words")
    _require(all(isinstance(w, str) and _HEX32.fullmatch(w) for w in xland),
             "xland contains a malformed f32 word")

    anchors = data.get("anchor_fields")
    _require(anchors == {"vertical": "p", "column": "qv"},
             "anchor_fields must use actual physical inputs p/qv")
    p0 = fields[anchors["vertical"]][:K]
    _require(len(set(p0)) == K, "vertical anchor field p is not unique along K")
    for b in range(B):
        _require(fields["p"][b*K:(b+1)*K] == p0,
                 "vertical anchor p must use the same K profile in every column")
    qv_cols = [fields["qv"][b*K] for b in range(B)]
    _require(len(set(qv_cols)) == B, "column anchor field qv is not unique across B")
    for b in range(B):
        _require(len(set(fields["qv"][b*K:(b+1)*K])) == 1,
                 "column anchor qv must be constant along K in each column")

    common = data.get("common_parameters")
    local = data.get("fortran_only_parameters")
    _require(isinstance(common, dict) and set(common) == set(COMMON_PARAMETERS),
             "common parameter keys differ")
    _require(isinstance(local, dict) and set(local) == set(FORTRAN_ONLY_PARAMETERS),
             "Fortran-only parameter keys differ")
    _require(all(isinstance(v, str) and _HEX32.fullmatch(v)
                 for v in (*common.values(), *local.values())),
             "parameter contains a malformed f32 word")
    return data


def canonical_manifest_bytes(data: dict) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("ascii")


def input_records(data: dict) -> dict[tuple[str, int, int], int]:
    B, K = data["B"], data["K"]
    out: dict[tuple[str, int, int], int] = {}
    for field in GRID_FIELDS:
        words = data["fields"][field]
        for b in range(B):
            for k in range(K):
                out[(field, b + 1, k)] = int(words[b * K + k], 16)
    for b, word in enumerate(data["xland"], 1):
        out[("xland", b, -1)] = int(word, 16)
    return out


def ordered_input_records(data: dict):
    B, K = data["B"], data["K"]
    for field in GRID_FIELDS:
        words = data["fields"][field]
        for b in range(B):
            for k in range(K):
                yield (field, b + 1, k), int(words[b * K + k], 16)
    for b, word in enumerate(data["xland"], 1):
        yield ("xland", b, -1), int(word, 16)


def fixture_sha256(data: dict) -> str:
    body = "".join(f"{f}:{c}:{k}:{bits:08x}"
                   for (f, c, k), bits in sorted(input_records(data).items()))
    return hashlib.sha256(body.encode("ascii")).hexdigest()


def parameter_sha256(data: dict) -> str:
    body = "".join(f"{name}:{int(word, 16):08x}"
                   for name, word in sorted(data["common_parameters"].items()))
    return hashlib.sha256(body.encode("ascii")).hexdigest()


def fortran_parameter_sha256(data: dict) -> str:
    body = "".join(f"{name}:{int(word, 16):08x}"
                   for name, word in sorted(data["fortran_only_parameters"].items()))
    return hashlib.sha256(body.encode("ascii")).hexdigest()


def manifest_sha256(data: dict) -> str:
    return hashlib.sha256(canonical_manifest_bytes(data)).hexdigest()


def render_fixture_protocol(data: dict) -> str:
    lines = [f"KDM6FIX BEGIN v1 {data['fixture_id']} {data['B']} {data['K']}"]
    for (field, col, k), bits in ordered_input_records(data):
        lines.append(f"KDM6FIX FIXIN {field} {col} {k} f32 {bits:08x}")
    for name, word in sorted(data["common_parameters"].items()):
        lines.append(f"KDM6FIX PARAM {name} f32 {word}")
    lines.append(f"KDM6FIX END v1 {data['fixture_id']}")
    return "\n".join(lines) + "\n"


def parse_fixture_protocol(raw: bytes | str, data: dict | None = None) -> tuple[str, str]:
    """Require the actual C++ fixture-only stream to equal the raw-bit authority."""
    data = load_manifest() if data is None else data
    if isinstance(raw, bytes):
        try:
            text = raw.decode("ascii")
        except UnicodeDecodeError as exc:
            raise ValueError(f"fixture stream is not ASCII: {exc}") from None
    else:
        text = raw
    lines = text.splitlines()
    begin = f"KDM6FIX BEGIN v1 {data['fixture_id']} {data['B']} {data['K']}"
    end = f"KDM6FIX END v1 {data['fixture_id']}"
    if not lines or lines[0] != begin or lines[-1:] != [end]:
        raise ValueError("fixture stream has a missing/wrong BEGIN or END")

    got_inputs: dict[tuple[str, int, int], int] = {}
    got_order: list[tuple[str, int, int]] = []
    got_params: dict[str, int] = {}
    for line in lines[1:-1]:
        tok = line.split()
        if len(tok) == 7 and tok[:2] == ["KDM6FIX", "FIXIN"] and tok[5] == "f32":
            try:
                key = (tok[2], int(tok[3]), int(tok[4]))
            except ValueError:
                raise ValueError(f"FIXIN has non-integer index: {line!r}") from None
            if not _HEX32.fullmatch(tok[6]):
                raise ValueError(f"FIXIN has malformed f32 word: {line!r}")
            if key in got_inputs:
                raise ValueError(f"duplicate FIXIN key: {key}")
            got_inputs[key] = int(tok[6], 16)
            got_order.append(key)
        elif len(tok) == 5 and tok[:2] == ["KDM6FIX", "PARAM"] and tok[3] == "f32":
            if not _HEX32.fullmatch(tok[4]):
                raise ValueError(f"PARAM has malformed f32 word: {line!r}")
            if tok[2] in got_params:
                raise ValueError(f"duplicate PARAM key: {tok[2]}")
            got_params[tok[2]] = int(tok[4], 16)
        else:
            raise ValueError(f"malformed/unknown fixture line: {line!r}")

    want_inputs = input_records(data)
    want_order = [key for key, _ in ordered_input_records(data)]
    if got_order != want_order:
        raise ValueError("FIXIN records are missing, extra, or reordered")
    if got_inputs != want_inputs:
        missing = sorted(set(want_inputs) - set(got_inputs))
        extra = sorted(set(got_inputs) - set(want_inputs))
        wrong = sorted(k for k in set(got_inputs) & set(want_inputs)
                       if got_inputs[k] != want_inputs[k])
        raise ValueError(f"fixture inputs differ: missing={missing[:3]} extra={extra[:3]} "
                         f"wrong_bits={wrong[:3]}")
    want_params = {n: int(w, 16) for n, w in data["common_parameters"].items()}
    if got_params != want_params:
        raise ValueError("common parameters differ from the raw-bit authority")
    return fixture_sha256(data), parameter_sha256(data)


def _cpp_array(name: str, words: list[str], length: str) -> str:
    body = ", ".join(f"0x{w}u" for w in words)
    return f"inline constexpr std::array<std::uint32_t, {length}> {name} = {{{{{body}}}}};"


def render_cpp(data: dict) -> str:
    B, K = data["B"], data["K"]
    lines = [
        "#pragma once",
        "// GENERATED by harness/g33_fixture_v1.py from g33_fixture_v1.json.",
        "// Do not edit: run the generator and commit both outputs.",
        "#include <array>", "#include <cstdint>", "",
        "namespace g33_fixture_v1 {",
        f"inline constexpr std::int64_t B = {B};",
        f"inline constexpr std::int64_t K = {K};",
        f'inline constexpr char FIXTURE_ID[] = "{data["fixture_id"]}";',
        f'inline constexpr char MANIFEST_SHA256[] = "{manifest_sha256(data)}";',
        f'inline constexpr char FIXTURE_SHA256[] = "{fixture_sha256(data)}";',
        f'inline constexpr char PARAMETER_SHA256[] = "{parameter_sha256(data)}";',
        f'inline constexpr char FORTRAN_PARAMETER_SHA256[] = "{fortran_parameter_sha256(data)}";', "",
    ]
    for field in GRID_FIELDS:
        lines.append(_cpp_array(f"{field}_bits", data["fields"][field], "B * K"))
    lines.append(_cpp_array("xland_bits", data["xland"], "B"))
    lines.append("")
    for name in COMMON_PARAMETERS:
        lines.append(f"inline constexpr std::uint32_t {name}_bits = "
                     f"0x{data['common_parameters'][name]}u;")
    for name in FORTRAN_ONLY_PARAMETERS:
        lines.append(f"inline constexpr std::uint32_t fortran_{name}_bits = "
                     f"0x{data['fortran_only_parameters'][name]}u;")
    lines += ["", "}  // namespace g33_fixture_v1", ""]
    return "\n".join(lines)


def _f_int(word: str) -> str:
    return f"int(z'{word.upper()}', int32)"


def _fortran_grid_array(name: str, words: list[str], B: int, K: int) -> list[str]:
    ordered = [words[b * K + k] for k in range(K) for b in range(B)]
    chunks = [ordered[i:i + 4] for i in range(0, len(ordered), 4)]
    out = [f"  integer(int32), parameter :: {name.upper()}_BITS(B,K) = reshape([ &"]
    for i, chunk in enumerate(chunks):
        suffix = ", &" if i != len(chunks) - 1 else " &"
        out.append("       " + ", ".join(_f_int(w) for w in chunk) + suffix)
    out.append("       ], [B,K])")
    return out


def _fortran_vector(name: str, words: list[str], length: str) -> list[str]:
    chunks = [words[i:i + 4] for i in range(0, len(words), 4)]
    out = [f"  integer(int32), parameter :: {name.upper()}_BITS({length}) = [ &"]
    for i, chunk in enumerate(chunks):
        suffix = ", &" if i != len(chunks) - 1 else " &"
        out.append("       " + ", ".join(_f_int(w) for w in chunk) + suffix)
    out.append("       ]")
    return out


def render_fortran(data: dict) -> str:
    B, K = data["B"], data["K"]
    lines = [
        "! GENERATED by harness/g33_fixture_v1.py from g33_fixture_v1.json.",
        "! Do not edit: run the generator and commit both outputs.",
        "module g33_fixture_v1", "  use, intrinsic :: iso_fortran_env, only: int32",
        "  implicit none", f"  integer, parameter :: B = {B}, K = {K}",
        f"  character(len=*), parameter :: FIXTURE_ID = '{data['fixture_id']}'",
        f"  character(len=*), parameter :: MANIFEST_SHA256 = '{manifest_sha256(data)}'",
        f"  character(len=*), parameter :: FIXTURE_SHA256 = '{fixture_sha256(data)}'",
        f"  character(len=*), parameter :: PARAMETER_SHA256 = '{parameter_sha256(data)}'",
        f"  character(len=*), parameter :: FORTRAN_PARAMETER_SHA256 = '{fortran_parameter_sha256(data)}'", "",
    ]
    for field in GRID_FIELDS:
        lines.extend(_fortran_grid_array(field, data["fields"][field], B, K))
    lines.extend(_fortran_vector("xland", data["xland"], "B"))
    lines.append("")
    for name in COMMON_PARAMETERS:
        lines.append(f"  integer(int32), parameter :: {name.upper()}_BITS = "
                     f"{_f_int(data['common_parameters'][name])}")
    for name in FORTRAN_ONLY_PARAMETERS:
        lines.append(f"  integer(int32), parameter :: {name.upper()}_BITS = "
                     f"{_f_int(data['fortran_only_parameters'][name])}")
    lines += ["end module g33_fixture_v1", ""]
    return "\n".join(lines)


def generated(data: dict) -> dict[Path, str]:
    return {CPP_OUT: render_cpp(data), FORTRAN_OUT: render_fortran(data)}


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args()
    data = load_manifest()
    for path, content in generated(data).items():
        if args.write:
            path.write_text(content, encoding="utf-8")
            print(f"wrote {path.relative_to(ROOT)}")
        else:
            try:
                actual = path.read_text(encoding="utf-8")
            except OSError as exc:
                raise SystemExit(f"generated file missing: {path}: {exc}")
            if actual != content:
                raise SystemExit(f"generated fixture drift: {path.relative_to(ROOT)}")
    print(f"manifest={manifest_sha256(data)} fixture={fixture_sha256(data)} "
          f"params={parameter_sha256(data)} local={fortran_parameter_sha256(data)}")


if __name__ == "__main__":
    main()
