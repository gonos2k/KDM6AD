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
import struct
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "harness" / "g33_fixture_v1.json"
CPP_OUT = ROOT / "harness" / "g33_overlay" / "g33_fixture_v1.h"
FORTRAN_OUT = ROOT / "harness" / "g33_fortran" / "g33_fixture_v1.f90"


@dataclass(frozen=True)
class FixtureSpec:
    """One fixture's authority, its generated bindings, and how each build selects
    it. The two builds took differently-spelled flags; keeping the mapping here means
    a caller names the fixture once and cannot pair one backend's fixture with the
    other's by mistake."""
    fixture_id: str
    manifest: Path
    cpp_header: Path
    fortran_module: Path
    cpp_define: str = ""            # selfcheck_build.sh --fixture=... selector
    #: The strongest verdict this fixture may support (see _DECISION_CEILINGS).
    #: Defaults to STRUCTURAL_ONLY so a new fixture cannot support a mechanism verdict
    #: by omission — stating the stronger claim has to be deliberate.
    decision_ceiling: str = "STRUCTURAL_ONLY"

    @property
    def mechanism_admissible(self) -> bool:
        return self.decision_ceiling == "MECHANISM"

    @property
    def fortran_build_name(self) -> str:
        """fortran_build.sh --fixture=<name> (the generated module's stem)."""
        return self.fortran_module.stem


#: Every fixture a four-case run may use. Explicit: a caller names the fixture it
#: wants, so no entry point can be silently bound to whichever authority happens to
#: be the module default. `spec()` re-reads the manifest's own `fixture_id`, so a
#: mislabelled row here cannot pass a fixture off as another.
FIXTURES = {
    "arithmetic_synthetic_v1": FixtureSpec(
        "arithmetic_synthetic_v1", MANIFEST, CPP_OUT, FORTRAN_OUT,
        decision_ceiling="MECHANISM"),
    "arithmetic_multisubcycle_v1": FixtureSpec(
        "arithmetic_multisubcycle_v1",
        ROOT / "harness" / "g33_fixture_multisubcycle_v1.json",
        ROOT / "harness" / "g33_overlay" / "g33_fixture_multisubcycle_v1.h",
        ROOT / "harness" / "g33_fortran" / "g33_fixture_multisubcycle_v1.f90",
        cpp_define="multisubcycle", decision_ceiling="MECHANISM"),
    # MAPPING ONLY. Every degeneracy the two arithmetic fixtures share is broken
    # here: pii is non-unity and varies per cell (so `t = th` cannot pass for
    # `t = th*pii`), xland is mixed so `xland >= 1.5` is actually exercised,
    # ncmin_land != ncmin_sea so selecting the wrong one is visible, p/rho/delz are
    # distinct per cell so a K-flip or column transposition changes the bits, nccn
    # is distinct per column so the wrapper's profile overwrite is unmistakable, and
    # qc/qi/ni carry out-of-band cells so kdm62D's entry padding is live — measured
    # on arithmetic_multisubcycle_v1, that clamp changes 0 of 180 cells, so the
    # existing fixtures cannot tell a working clamp from a missing one.
    #
    # It is NOT a microphysics case: dt is below DTCLDCR, so it takes one outer loop.
    "boundary_mapping_v1": FixtureSpec(
        "boundary_mapping_v1",
        ROOT / "harness" / "g33_fixture_boundary_mapping_v1.json",
        ROOT / "harness" / "g33_overlay" / "g33_fixture_boundary_mapping_v1.h",
        ROOT / "harness" / "g33_fortran" / "g33_fixture_boundary_mapping_v1.f90",
        # STRUCTURAL_ONLY: it carries deliberately out-of-band prognostics to exercise
        # code paths, so a mechanism verdict from it would be a claim about physics
        # drawn from values chosen to be unphysical (owner P0-8).
        cpp_define="boundary_mapping", decision_ceiling="STRUCTURAL_ONLY"),
    # THE MOISTURE GRADIENT. Every fixture above carries `qv` CONSTANT in the
    # column -- measured, in-column spread exactly 0.0 across every published
    # stream that has it. Under a uniform profile the dry and moist number
    # ledgers differ by a constant per column, and that constant cancels out of
    # every ratio, so no fixture could distinguish the two measures
    # (FINDING_number_basis_gap_v1). This one differs from boundary_mapping in
    # `qv` ALONE, so it is that fixture's matched control for the basis
    # question and nothing else moves.
    "moisture_gradient_v1": FixtureSpec(
        "moisture_gradient_v1",
        ROOT / "harness" / "g33_fixture_moisture_gradient_v1.json",
        ROOT / "harness" / "g33_overlay" / "g33_fixture_moisture_gradient_v1.h",
        ROOT / "harness" / "g33_fortran" / "g33_fixture_moisture_gradient_v1.f90",
        cpp_define="moisture_gradient", decision_ceiling="STRUCTURAL_ONLY"),
}
DEFAULT_FIXTURE_ID = "arithmetic_synthetic_v1"


class UnknownFixture(KeyError):
    """A fixture id that is not in the registry."""


def canonical_id(name: str) -> str:
    """The registry key for a fixture, from either spelling.

    The registry is keyed by `fixture_id` (`boundary_mapping_v1`) while callers
    pass the MODULE name (`g33_fixture_boundary_mapping_v1`), and the driver
    emits the id. Two spellings of one fact, and the first thing that compared
    them refused every stream (43 tests). One function resolves both, so
    nothing has to remember which end it is holding.

    The two are NOT related by a prefix: `arithmetic_multisubcycle_v1` lives in
    `g33_fixture_multisubcycle_v1`. The mapping is the registry's own, which is
    why this reads it rather than editing strings.
    """
    if name in FIXTURES:
        return name
    # FROM THE REGISTRY, not by string surgery. The first draft stripped a
    # `g33_fixture_` prefix, which is right for `boundary_mapping_v1` and wrong
    # for `arithmetic_multisubcycle_v1`, whose module is
    # `g33_fixture_multisubcycle_v1` -- the two names are not related by a
    # prefix at all. The registry already holds both: the id is the key and the
    # module is its Fortran output's stem.
    for fid, entry in FIXTURES.items():
        if name in (entry.fortran_module.stem, entry.fortran_build_name,
                    entry.cpp_header.stem):
            return fid
    raise UnknownFixture(
        f"unknown fixture {name!r} (known ids: {sorted(FIXTURES)}, "
        f"known modules: {sorted(e.fortran_module.stem for e in FIXTURES.values())})")


def spec(fixture_id: str) -> FixtureSpec:
    """The registry entry for `fixture_id`, verified against its own manifest."""
    return load_fixture(fixture_id)[0]


def load_fixture(fixture_id: str) -> tuple[FixtureSpec, dict]:
    """The registry entry AND its validated authority, in ONE strict load. Reading
    the manifest twice — once raw to check the label, once strict for the data —
    leaves a window where the two disagree."""
    try:
        entry = FIXTURES[fixture_id]
    except KeyError:
        raise UnknownFixture(
            f"unknown fixture id {fixture_id!r} (known: {sorted(FIXTURES)})") from None
    data = load_manifest(entry.manifest)
    if data["fixture_id"] != fixture_id:
        raise ValueError(f"registry says {fixture_id!r} but "
                         f"{entry.manifest.name} declares {data['fixture_id']!r}")
    return entry, data

#: Fields that can serve as the COLUMN anchor: a real physical input that is
#: unique across columns and constant down each one.
_COLUMN_ANCHORS = ("qv", "nccn")

STATE_FIELDS = ("th", "qv", "qc", "qr", "qi", "qs", "qg",
                "nccn", "nc", "ni", "nr", "bg")
FORCING_FIELDS = ("rho", "pii", "p", "delz")
GRID_FIELDS = STATE_FIELDS + FORCING_FIELDS
COMMON_PARAMETERS = ("dt", "ncmin_land", "ncmin_sea", "qmin")
FORTRAN_ONLY_PARAMETERS = ("ccn0", "scale_h")
_HEX32 = re.compile(r"^[0-9a-f]{8}$")
#: The strongest verdict a fixture may support. STRUCTURAL_ONLY covers pack,
#: orientation and mapping; MECHANISM additionally covers the arithmetic question.
#:
#: It lives on the REGISTRY entry, not in the manifest JSON. The manifest's hash is a
#: decision anchor recorded in every bundle, so adding a field to it invalidates every
#: bundle ever produced — the enforcement would cost a full four-leg rebuild each time
#: a ceiling is stated. The registry is code: it is attested through the harness source
#: SHAs, read by the decision path, and cannot be set by a caller.
_DECISION_CEILINGS = frozenset(("STRUCTURAL_ONLY", "MECHANISM"))
#: Prognostic inputs that are physically non-negative. `th` is excluded (a potential
#: temperature is positive but is not a padded prognostic) and so are the forcings,
#: which are checked as strictly positive elsewhere.
_NONNEG_INPUTS = ("qv", "qc", "qr", "qi", "qs", "qg", "nccn", "nc", "ni", "nr", "bg")


def _f32_word(word: str) -> float:
    return struct.unpack(">f", bytes.fromhex(word))[0]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_manifest(path: Path = MANIFEST) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    _require(data.get("schema_version") == 1, "fixture schema_version must be 1")
    _require(data.get("fixture_id") in FIXTURES,
             "unexpected fixture_id")
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
    _require(isinstance(anchors, dict) and set(anchors) == {"vertical", "column"},
             "anchor_fields must declare exactly a vertical and a column anchor")
    _require(anchors["vertical"] == "p", "the vertical anchor must be `p`")
    # THE COLUMN ANCHOR IS DECLARED, not fixed at `qv`.
    #
    # It exists to catch a column transposition, and the property it needs is
    # "unique across B, constant along K" -- which `qv` has in every fixture so
    # far and is not the only field that does. Fixing it at `qv` made a vertical
    # MOISTURE GRADIENT unrepresentable, and that is exactly what the dry-air
    # number-measure question needs: under a column-uniform `qv` the dry and
    # moist ledgers differ by a constant per column and it cancels out of every
    # ratio (FINDING_number_basis_gap_v1). The schema forbade the experiment.
    #
    # WIDENING, not loosening: whichever field is named must still pass BOTH
    # checks, so a fixture cannot escape the transposition guard by declaring a
    # field that does not carry it. Every existing fixture declares `qv` and
    # validates exactly as before.
    _require(anchors["column"] in _COLUMN_ANCHORS,
             f"column anchor must be one of {list(_COLUMN_ANCHORS)}, "
             f"got {anchors['column']!r}")
    p0 = fields[anchors["vertical"]][:K]
    _require(len(set(p0)) == K, "vertical anchor field p is not unique along K")
    for b in range(B):
        _require(fields["p"][b*K:(b+1)*K] == p0,
                 "vertical anchor p must use the same K profile in every column")
    ca = anchors["column"]
    ca_cols = [fields[ca][b*K] for b in range(B)]
    _require(len(set(ca_cols)) == B,
             f"column anchor field {ca} is not unique across B")
    for b in range(B):
        _require(len(set(fields[ca][b*K:(b+1)*K])) == 1,
                 f"column anchor {ca} must be constant along K in each column")

    # DYNAMICS-NEGATIVE INPUT, declared rather than discovered.
    #
    # kdm62D pads negative prognostics at entry (F:822-839, "padding 0 for negative
    # values generated by dynamics"), so negative input is legitimate — but the stream
    # parser rejected it outright, which is why that clamp is dead in every arithmetic
    # fixture (measured: it changes 0 of 180 cells on arithmetic_multisubcycle_v1).
    #
    # A fixture that wants to exercise the clamp says so, and the declaration must
    # MATCH the data in both directions: a fixture cannot quietly acquire a negative,
    # and one cannot claim to test the clamp while carrying nothing to pad.
    allows_negative = data.get("allows_negative_input", False)
    _require(isinstance(allows_negative, bool),
             "allows_negative_input must be a boolean")
    negatives = [(name, i) for name in _NONNEG_INPUTS
                 for i, w in enumerate(fields[name]) if _f32_word(w) < 0.0]
    _require(bool(negatives) == allows_negative,
             f"allows_negative_input={allows_negative} but the fields carry "
             f"{len(negatives)} negative prognostic cell(s): {negatives[:3]}")

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
    # A second fixture (arithmetic_multisubcycle_v1) renders through the SAME
    # generator so both are built from one authority format. The generated Fortran
    # module keeps the name g33_fixture_v1 so the driver needs no change; the build
    # script selects which .f90 to compile.
    parser.add_argument("--fixture-id", default=None, choices=sorted(FIXTURES),
                        help="render/check one registry entry (paths come from it)")
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--cpp-out", type=Path, default=CPP_OUT)
    parser.add_argument("--fortran-out", type=Path, default=FORTRAN_OUT)
    args = parser.parse_args()
    if args.fixture_id:
        entry, data = load_fixture(args.fixture_id)
        args.manifest, args.cpp_out, args.fortran_out = (
            entry.manifest, entry.cpp_header, entry.fortran_module)
    else:
        data = load_manifest(args.manifest)
    for path, content in {args.cpp_out: render_cpp(data),
                          args.fortran_out: render_fortran(data)}.items():
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
