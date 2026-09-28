"""Generate a hash-pinned, macro-gated S15 Fortran instrumentation shadow.

The generator never edits the private host tree. Its source snippets are added
to a disposable copy and disappear when KDM6AD_S15_FACE_CAPTURE is undefined.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import difflib
import stat
from pathlib import Path
from typing import Any

import s15_face_cause_probe as replay
from s15_face_cause_probe import (
    NEIGHBOR_RECEIVERS,
    SCHEDULE,
    _capture_roster,
    _projection,
)


class OverlayError(ValueError):
    pass


MACRO = "KDM6AD_S15_FACE_CAPTURE"
SOURCE_PINS = {
    "dyn_em/solve_em.F": "d66e9db1bba8f37e3f46d30c2fd74bdf8def411adf233376a69e0b401c6d3d1f",
    "dyn_em/module_em.F": "7695bfb05a7f99763334a6e69523bbcc1de0f2c659177a18c10a6e1cf530a0c7",
    "dyn_em/module_advect_em.F": "58253bdbeb188dd47ed0579fcd2891086be1889b75c0c7d3696c9ad1d213559d",
}
PRODUCER_ANCHOR = ("scalar_tile_loop_1", "rk_scalar_tend")
CONSUMER_ANCHOR = ("scalar_tile_loop_2", "rk_update_scalar")
CONTEXT_NAMES = ("s15_step", "s15_rk", "s15_owner", "s15_tile")
PD_EPS_F32 = "1E3CE508"
FACE_TAGS = frozenset({b"S15AX", b"S15PD", b"S15RK"})
LEGACY_TAGS = frozenset({b"S15Q", b"S15QC", b"S15M"})
MAX_FULL_STDOUT_BYTES = 1024 * 1024
MAX_CAPTURE_LINE_BYTES = 64 * 1024
MAX_FACE_STREAM_BYTES = 64 * 1024
MAX_LEGACY_STREAM_BYTES = 1024 * 1024
MAX_LEGACY_RECORDS = 100_000
EXPECTED_FACE_TAG_COUNTS = {"S15AX": 18, "S15PD": 2, "S15RK": 6}
EXPECTED_NEIGHBOR_FACE_TAG_COUNTS = {"S15AX": 42, "S15PD": 10, "S15RK": 14}
QN_FACE_TAGS = frozenset({b"S3QNAX", b"S3QNPD", b"S3QNRK"})
EXPECTED_QN_FACE_TAG_COUNTS = {"S3QNAX": 15, "S3QNPD": 5, "S3QNRK": 5}
QN_XR_SHADOW_FACTOR_WORD = replay.QN_XR_SHADOW_FACTOR_WORD
QN_XR_SHADOW_INPUT_WORD = replay.QN_XR_SHADOW_INPUT_WORD
QN_XR_SHADOW_FACTOR_LITERAL = "0.9999784827232361"
WRF_CPP_BASE = ("-P", "-nostdinc", "-xassembler-with-cpp")
WRF_TRADITIONAL_CPP = ("-traditional-cpp",)


def wrf_suffix_final_cpp_argv(cpp: str | Path, input_file: str | Path) -> list[str]:
    """Build the configured .F.o final pass: CPP base plus TRADFLAG only."""
    return [str(cpp), *WRF_CPP_BASE, *WRF_TRADITIONAL_CPP, str(input_file)]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _source_bytes(source_root: Path) -> dict[str, bytes]:
    result = {}
    for relative, expected in SOURCE_PINS.items():
        path = source_root / relative
        if not path.is_file():
            raise OverlayError(f"pinned source file is absent: {relative}")
        payload = path.read_bytes()
        if sha256(payload) != expected:
            raise OverlayError(f"pinned source hash mismatch: {relative}")
        result[relative] = payload
    return result


def _find_proc(lines: list[str], name: str) -> tuple[int, int]:
    start_pat = re.compile(rf"^\s*SUBROUTINE\s+{re.escape(name)}\s*\(", re.I)
    end_pat = re.compile(rf"^\s*END\s+SUBROUTINE\s+{re.escape(name)}\b", re.I)
    starts = [i for i, line in enumerate(lines) if start_pat.search(line)]
    ends = [i for i, line in enumerate(lines) if end_pat.search(line)]
    if len(starts) != 1 or len(ends) != 1 or ends[0] <= starts[0]:
        raise OverlayError(f"expected one complete procedure {name}")
    return starts[0], ends[0]


def _call_span(lines: list[str], first: int, last: int, name: str) -> tuple[int, int]:
    pattern = re.compile(rf"\bCALL\s+{re.escape(name)}\s*\(", re.I)
    starts = [i for i in range(first, last) if pattern.search(lines[i])]
    if len(starts) != 1:
        raise OverlayError(f"expected one {name} call in pinned scope")
    start = starts[0]
    depth = 0
    started = False
    for index in range(start, last):
        line = lines[index].split("!", 1)[0]
        for char in line:
            if char == "(":
                depth += 1
                started = True
            elif char == ")" and started:
                depth -= 1
                if depth == 0:
                    return start, index
    raise OverlayError(f"unterminated {name} call")


def find_dual_owner_calls(solve_text: str) -> dict[str, tuple[int, int]]:
    """Return 1-based producer/consumer call extents; both anchors are required."""
    lines = solve_text.splitlines()
    found: dict[str, tuple[int, int]] = {}
    for role, (loop_label, call_name) in (
        ("producer", PRODUCER_ANCHOR),
        ("consumer", CONSUMER_ANCHOR),
    ):
        loop_start_pat = re.compile(rf"^\s*{loop_label}\s*:\s*DO\b", re.I)
        loop_end_pat = re.compile(rf"^\s*ENDDO\s+{loop_label}\b", re.I)
        starts = [i for i, line in enumerate(lines) if loop_start_pat.search(line)]
        ends = [i for i, line in enumerate(lines) if loop_end_pat.search(line)]
        if len(starts) != 1 or len(ends) != 1 or ends[0] <= starts[0]:
            raise OverlayError(f"missing or duplicate owner-5 {role} loop anchor")
        span = _call_span(lines, starts[0], ends[0], call_name)
        found[role] = (span[0] + 1, span[1] + 1)
    if found["producer"] == found["consumer"]:
        raise OverlayError("producer and consumer anchors must be distinct callsites")
    return found


def _wrap_closing_line(line: str, args: list[str]) -> list[str]:
    stripped = line.rstrip()
    if not stripped.endswith(")"):
        raise OverlayError("source anchor must end on a closing-parenthesis line")
    indent = line[: len(line) - len(line.lstrip())]
    prefix = stripped[:-1].rstrip()
    macro_line = prefix + ", &"
    arg_lines = [
        indent + "   " + arg + (", &" if n < len(args) - 1 else " )")
        for n, arg in enumerate(args)
    ]
    return [
        f"#ifdef {MACRO}",
        macro_line,
        *arg_lines,
        "#else",
        line,
        "#endif",
    ]


def _append_actuals(
    lines: list[str], start: int, end: int, args: list[str]
) -> list[str]:
    return [*lines[:end], *_wrap_closing_line(lines[end], args), *lines[end + 1 :]]


def _extend_signature(lines: list[str], name: str, args: list[str]) -> list[str]:
    start, end = _find_proc(lines, name)
    depth = 0
    close = None
    for i in range(start, end):
        code = lines[i].split("!", 1)[0]
        depth += code.count("(") - code.count(")")
        if depth == 0 and i > start:
            close = i
            break
    if close is None:
        raise OverlayError(f"cannot locate signature end for {name}")
    return _append_actuals(lines, start, close, args)


def _add_optional_declarations(
    lines: list[str],
    proc_name: str,
    names: tuple[str, ...],
    *,
    declaration_type: str = "INTEGER",
) -> list[str]:
    start, end = _find_proc(lines, proc_name)
    implicit = next(
        (
            i
            for i in range(start, end)
            if re.match(r"\s*IMPLICIT\s+NONE", lines[i], re.I)
        ),
        None,
    )
    if implicit is None:
        raise OverlayError(f"procedure {proc_name} lacks IMPLICIT NONE anchor")
    decl = [
        f"#ifdef {MACRO}",
        f"   {declaration_type}, OPTIONAL, INTENT(IN) :: " + ", ".join(names),
        "#endif",
    ]
    return [*lines[: implicit + 1], *decl, *lines[implicit + 1 :]]


def _owner_call_args() -> list[str]:
    return [
        "s15_step=grid%itimestep",
        "s15_rk=rk_step",
        "s15_owner=MERGE(5,0,is==P_QIB .and. s15_capture_enabled)",
        "s15_tile=ij",
    ]


def _patch_solve(text: str, *, shadow: bool = False) -> str:
    lines = text.splitlines()
    anchors = find_dual_owner_calls(text)
    solve_start, solve_end = _find_proc(lines, "solve_em")
    implicit = next(
        (
            i
            for i in range(solve_start, solve_end)
            if re.match(r"\s*IMPLICIT\s+NONE", lines[i], re.I)
        ),
        None,
    )
    if implicit is None:
        raise OverlayError("solve_em lacks IMPLICIT NONE anchor")
    declaration_body = [
        "LOGICAL :: s15_capture_enabled",
        "INTEGER :: s15_log_status",
        "CHARACTER(LEN=8) :: s15_log_env",
    ]
    if shadow:
        declaration_body.extend(
            [
                "LOGICAL :: s3qn_xr_shadow_latched",
                "INTEGER :: s3qn_xr_shadow_status",
                "CHARACTER(LEN=8) :: s3qn_xr_shadow_env",
            ]
        )
    declarations = _guard(declaration_body)
    lines[implicit + 1 : implicit + 1] = declarations
    solve_start, solve_end = _find_proc(lines, "solve_em")
    scalar_gate = [
        i
        for i in range(solve_start, solve_end)
        if re.search(r"^\s*other_scalar_advance\s*:\s*IF\b", lines[i], re.I)
    ]
    if len(scalar_gate) != 1:
        raise OverlayError(
            "solve_em scalar-advance latch anchor is missing or ambiguous"
        )
    i = scalar_gate[0]
    env_latch_body = [
        "s15_capture_enabled=.false.",
        "s15_log_env=' '",
        "s15_log_status=1",
        "CALL GET_ENVIRONMENT_VARIABLE('KDM6_S15_NATIVE_CAPTURE_LOG', &",
        "     s15_log_env, STATUS=s15_log_status)",
        "if (s15_log_status.eq.0 .and. trim(s15_log_env).eq.'1') &",
        "     s15_capture_enabled=.true.",
    ]
    if shadow:
        env_latch_body.extend(
            [
                "s3qn_xr_shadow_latched=.false.",
                "s3qn_xr_shadow_env=' '",
                "s3qn_xr_shadow_status=1",
                "CALL GET_ENVIRONMENT_VARIABLE('KDM6_S3_QN_XR_SHADOW', &",
                "     s3qn_xr_shadow_env, STATUS=s3qn_xr_shadow_status)",
                "if (s3qn_xr_shadow_status.eq.0 .and. &",
                "    trim(s3qn_xr_shadow_env).eq.'1') s3qn_xr_shadow_latched=.true.",
            ]
        )
    env_latch = _guard(
        env_latch_body,
        lines[i][: len(lines[i]) - len(lines[i].lstrip())],
    )
    lines[i:i] = env_latch
    # Locate each loop again, then re-find its call after each prior insertion.
    for loop_label, call_name in (PRODUCER_ANCHOR, CONSUMER_ANCHOR):
        loop_start_pat = re.compile(rf"^\s*{loop_label}\s*:\s*DO\b", re.I)
        loop_end_pat = re.compile(rf"^\s*ENDDO\s+{loop_label}\b", re.I)
        start = next(i for i, line in enumerate(lines) if loop_start_pat.search(line))
        end = next(i for i, line in enumerate(lines) if loop_end_pat.search(line))
        call_start, call_end = _call_span(lines, start, end, call_name)
        actuals = _owner_call_args()
        if shadow and call_name == PRODUCER_ANCHOR[1]:
            actuals.append(
                "s3qn_xr_shadow_enabled=(is==P_QNC.and.grid%itimestep.eq.2"
                ".and.rk_step.eq.3.and.ij.eq.1.and.s3qn_xr_shadow_latched)"
            )
        lines = _append_actuals(lines, call_start, call_end, actuals)
    if not anchors["producer"] or not anchors["consumer"]:
        raise OverlayError("dual owner-call regression anchors are empty")
    return "\n".join(lines) + "\n"


def _patch_module_em(
    text: str, *, neighbors: bool = False, shadow: bool = False
) -> str:
    lines = text.splitlines()
    # Producer context: rk_scalar_tend dispatches to ordinary or PD advection.
    for proc_name in ("rk_scalar_tend", "rk_update_scalar"):
        signature_names = list(CONTEXT_NAMES)
        if shadow and proc_name == "rk_scalar_tend":
            signature_names.append("s3qn_xr_shadow_enabled")
        lines = _extend_signature(lines, proc_name, signature_names)
        lines = _add_optional_declarations(lines, proc_name, CONTEXT_NAMES)
        if shadow and proc_name == "rk_scalar_tend":
            lines = _add_optional_declarations(
                lines,
                "rk_scalar_tend",
                ("s3qn_xr_shadow_enabled",),
                declaration_type="LOGICAL",
            )

    start, end = _find_proc(lines, "rk_scalar_tend")
    for call_name, branch in (("advect_scalar_pd", 2), ("advect_scalar", 1)):
        cstart, cend = _call_span(lines, start, end, call_name)
        actuals = [f"{name}={name}" for name in CONTEXT_NAMES] + [
            f"s15_branch={branch}"
        ]
        if shadow and call_name == "advect_scalar_pd":
            actuals.append("s3qn_xr_shadow_enabled=s3qn_xr_shadow_enabled")
        lines = _append_actuals(lines, cstart, cend, actuals)
        start, end = _find_proc(lines, "rk_scalar_tend")
    lines = _patch_rk_store_taps(lines)
    lines = _append_module_em_helpers(lines, neighbors=neighbors)
    return "\n".join(lines) + "\n"


def _patch_advect(text: str, *, neighbors: bool = False, shadow: bool = False) -> str:
    lines = text.splitlines()
    for proc_name in ("advect_scalar", "advect_scalar_pd"):
        optional_names = [*CONTEXT_NAMES, "s15_branch"]
        signature_names = list(optional_names)
        if shadow and proc_name == "advect_scalar_pd":
            signature_names.append("s3qn_xr_shadow_enabled")
        lines = _extend_signature(lines, proc_name, signature_names)
        lines = _add_optional_declarations(lines, proc_name, optional_names)
        if shadow and proc_name == "advect_scalar_pd":
            lines = _add_optional_declarations(
                lines,
                proc_name,
                ("s3qn_xr_shadow_enabled",),
                declaration_type="LOGICAL",
            )
        start, _ = _find_proc(lines, proc_name)
        implicit = next(
            i
            for i in range(start, len(lines))
            if re.match(r"\s*IMPLICIT\s+NONE", lines[i], re.I)
        )
        local = ["LOGICAL :: s15_here", "REAL :: s15_prefix_before"]
        if proc_name == "advect_scalar_pd":
            local.extend(
                [
                    "INTEGER :: s15_pd_active",
                    "REAL :: s15_pd_scale,s15_pd_flux_out,s15_pd_available",
                    "REAL, DIMENSION(6) :: s15_pd_low,s15_pd_pre,s15_pd_post",
                ]
            )
        lines[implicit + 1 : implicit + 1] = _guard(local)
        lines = _tap_advection_procedure(lines, proc_name, shadow=shadow)
    lines = _append_advect_helpers(lines, neighbors=neighbors)
    return "\n".join(lines) + "\n"


def _restore_cpp_line_numbers(original: str, patched: str, filename: str) -> str:
    """Reset logical source lines after insertions so macro-off __LINE__ is stable."""
    old_lines = original.splitlines(keepends=True)
    new_lines = patched.splitlines(keepends=True)
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    output: list[str] = []
    edited = False
    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if tag == "equal":
            if edited and old_start < len(old_lines):
                output.append(f'#line {old_start + 1} "{filename}"\n')
            output.extend(new_lines[new_start:new_end])
            edited = False
        else:
            output.extend(new_lines[new_start:new_end])
            edited = True
    return "".join(output)


def _patch_module_em_rk_calls(module_em_text: str) -> str:
    """Compatibility alias retained for focused generator tests."""
    return _patch_module_em(module_em_text)


def prepare_overlay(
    source_root: Path,
    shadow_root: Path,
    public_root: Path,
    *,
    neighbors: bool = False,
    qn: bool = False,
    shadow: bool = False,
) -> dict[str, Any]:
    if neighbors and qn:
        raise OverlayError("S15 neighbor and S3 QNCLOUD modes are exclusive")
    if shadow and not qn:
        raise OverlayError("the fixed xR shadow is available only in S3 QNCLOUD mode")
    sources = _source_bytes(source_root)
    projection = [] if qn else _projection(public_root)
    dual_calls = find_dual_owner_calls(sources["dyn_em/solve_em.F"].decode())
    if shadow_root.exists():
        raise OverlayError("overlay shadow directory must be new")
    patched = {}
    for relative, patcher in (
        (
            "dyn_em/solve_em.F",
            lambda text: _patch_solve(text, shadow=shadow),
        ),
        (
            "dyn_em/module_em.F",
            lambda text: _patch_module_em(
                text, neighbors=(neighbors or qn), shadow=shadow
            ),
        ),
        (
            "dyn_em/module_advect_em.F",
            lambda text: _patch_advect(
                text, neighbors=(neighbors or qn), shadow=shadow
            ),
        ),
    ):
        original = sources[relative].decode()
        patched[relative] = _restore_cpp_line_numbers(
            original, patcher(original), relative
        )
    if qn:
        patched = {name: _convert_qn_overlay(text) for name, text in patched.items()}
        _validate_qn_overlay(patched, shadow=shadow)
    shadow_root.mkdir(parents=True)
    for relative, output in patched.items():
        path = shadow_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output, encoding="utf-8", newline="")
    manifest = {
        "schema": (
            "KDM6AD-S3-QNCLOUD-FACE-FORTRAN-OVERLAY-v1"
            if qn
            else "KDM6AD-S15-FACE-FORTRAN-OVERLAY-v1"
        ),
        "macro": MACRO,
        "source_pins": SOURCE_PINS,
        "producer_call_anchor": {
            "loop": PRODUCER_ANCHOR[0],
            "call": PRODUCER_ANCHOR[1],
        },
        "consumer_call_anchor": {
            "loop": CONSUMER_ANCHOR[0],
            "call": CONSUMER_ANCHOR[1],
        },
        "producer_call_extent_1based": list(dual_calls["producer"]),
        "consumer_call_extent_1based": list(dual_calls["consumer"]),
        "schedule": (
            [list(replay.QN_SCHEDULE)] if qn else [list(key) for key in SCHEDULE]
        ),
        "coordinates": (
            [list(replay.QN_DONOR), *[list(x) for x in replay.QN_RECEIVERS]]
            if qn
            else [list(x) for x in projection]
        ),
        "status": "macro-gated producer/consumer and directional/limiter taps; compile-only pending",
    }
    if neighbors:
        manifest["neighbor_receivers"] = [
            {"tile": tile, "coordinate": list(coordinate)}
            for tile, coordinate in NEIGHBOR_RECEIVERS
        ]
    if qn:
        manifest["capture_mode"] = "S3_QNCLOUD_OWNER3"
        manifest["tile_bounds"] = {"tile": 1, "i": [1, 235], "j": [1, 142]}
        if shadow:
            manifest["shadow_mode"] = "S3_QNCLOUD_XR_HIGH_FACTOR_OPT_IN"
            manifest["physics_enable_env"] = "KDM6_S3_QN_XR_SHADOW=1"
            manifest["physics_factor_f32_word"] = QN_XR_SHADOW_FACTOR_WORD
    manifest_name = (
        "s3_qn_face_overlay_manifest.json" if qn else "s15_face_overlay_manifest.json"
    )
    (shadow_root / manifest_name).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def _convert_qn_overlay(text: str) -> str:
    """Give the fixed QNCLOUD tap its own runtime owner and record namespace."""
    qib_owner = "s15_owner=MERGE(5,0,is==P_QIB .and. s15_capture_enabled)"
    owner_count = text.count(qib_owner)
    if owner_count not in (0, 2):
        raise OverlayError(
            "expected zero or both QIB owner call predicates in one source"
        )
    text = text.replace(
        qib_owner,
        "s15_owner=MERGE(3,0,is==P_QNC .and. s15_capture_enabled)",
    )
    for old, new in (
        ("s15_face_match", "s3qn_face_match"),
        ("s15_rk_match", "s3qn_rk_match"),
        ("s15_emit_axis", "s3qn_emit_axis"),
        ("s15_emit_pd", "s3qn_emit_pd"),
        ("s15_emit_rk", "s3qn_emit_rk"),
        ("S15LIMIT", "S3QN_LIMIT"),
        ("S15AX", "S3QNAX"),
        ("S15PD", "S3QNPD"),
        ("S15RK", "S3QNRK"),
    ):
        text = text.replace(old, new)
    for matcher in ("face", "rk"):
        name = f"s3qn_{matcher}_match"
        pattern = re.compile(
            rf"(?ms)^(\s*SUBROUTINE {name}\([^\n]+\).*?^\s*END SUBROUTINE {name}\s*)$",
            re.I,
        )
        body = [
            f"SUBROUTINE {name}(step,rk,owner,tile,i,j,k,hit)",
            "INTEGER, INTENT(IN) :: step,rk,owner,tile,i,j,k",
            "LOGICAL, INTENT(OUT) :: hit",
            "hit=.false.",
            "if (step.ne.2 .or. rk.ne.3 .or. owner.ne.3 .or. tile.ne.1) return",
            "if (i.lt.1 .or. i.gt.235 .or. j.lt.1 .or. j.gt.142) return",
            "if ((i.eq.233 .and. j.eq.124 .and. k.eq.12) .or. &",
            "    (i.eq.232 .and. j.eq.124 .and. k.eq.12) .or. &",
            "    (i.eq.233 .and. j.eq.123 .and. k.eq.12) .or. &",
            "    (i.eq.233 .and. j.eq.125 .and. k.eq.12) .or. &",
            "    (i.eq.233 .and. j.eq.124 .and. k.eq.13)) hit=.true.",
            f"END SUBROUTINE {name}",
        ]
        text, count = pattern.subn("\n".join(body), text)
        if count > 1:
            raise OverlayError(f"expected one generated {name} helper")
    text = text.replace("if (s15_count.ge.42)", "if (s15_count.ge.15)")
    text = text.replace("if (s15_count.ge.10)", "if (s15_count.ge.5)")
    text = text.replace("if (s15_count.ge.14)", "if (s15_count.ge.5)")
    return text


def _validate_qn_overlay(patched: dict[str, str], *, shadow: bool = False) -> None:
    text = "\n".join(patched.values())
    if text.count("s15_owner=MERGE(3,0,is==P_QNC .and. s15_capture_enabled)") != 2:
        raise OverlayError("QNCLOUD overlay must gate both producer and RK owner calls")
    if re.search(r"s15_owner\s*=\s*MERGE\([^\n]*P_QIB", text) or any(
        tag in text for tag in ("'S15AX'", "'S15PD'", "'S15RK'")
    ):
        raise OverlayError("QNCLOUD overlay retains a QIB tap owner or S15 record tag")
    for name in ("face", "rk"):
        if text.count(f"SUBROUTINE s3qn_{name}_match(") != 1:
            raise OverlayError(f"QNCLOUD overlay must define one s3qn_{name}_match")
        if f"SUBROUTINE s15_{name}_match(" in text:
            raise OverlayError(f"QNCLOUD overlay retains the S15 {name} matcher")
    if (
        "'S3QNAX'" not in text
        or "'S3QNPD'" not in text
        or "'S3QNRK'" not in text
        or text.count("if (s15_count.ge.15) then") != 1
        or text.count("if (s15_count.ge.5) then") != 2
    ):
        raise OverlayError("QNCLOUD overlay tags or 15/5/5 caps are incomplete")
    physics_tokens = (
        "s3qn_xr_shadow_latched",
        "s3qn_xr_shadow_enabled",
        "KDM6_S3_QN_XR_SHADOW",
    )
    if shadow:
        if any(token not in text for token in physics_tokens):
            raise OverlayError("opt-in QNCLOUD xR physics gate is incomplete")
        if text.count("KDM6_S3_QN_XR_SHADOW") != 1:
            raise OverlayError("expected one independent QNCLOUD physics env latch")
        if (
            text.count(
                "s3qn_xr_shadow_enabled=(is==P_QNC.and.grid%itimestep.eq.2.and.rk_step.eq.3.and.ij.eq.1.and.s3qn_xr_shadow_latched)"
            )
            != 1
        ):
            raise OverlayError("physics gate must be QNCLOUD/tile1/step2/RK3 qualified")
        if f"fqx(i+1,k,j)={QN_XR_SHADOW_FACTOR_LITERAL}*fqx(i+1,k,j)" not in text:
            raise OverlayError("fixed xR high-face factor is missing")
        if (
            text.count(
                f"transfer(fqx(i+1,k,j),0).ne.int(z'{QN_XR_SHADOW_INPUT_WORD}',kind=4)"
            )
            != 1
        ):
            raise OverlayError("opt-in physics path must change one xR face operand")
        if (
            "fqx(i+1,k,j).le.0." not in text
            or "S3QN_SHADOW xR f32 input mismatch" not in text
            or "stop 92" not in text
        ):
            raise OverlayError(
                "xR shadow must stop unless its captured input word matches"
            )
        if text.index("s3qn_xr_shadow_enabled .and. i.eq.233") > text.index(
            "s15_pd_post(2)=fqx(i+1,k,j)"
        ):
            raise OverlayError("xR shadow must precede the PD post tap")
    elif any(token in text for token in physics_tokens):
        raise OverlayError(
            "default QNCLOUD overlay unexpectedly contains xR physics shadow"
        )


def strip_capture_macro(text: str) -> str:
    """Test helper that selects only the macro-off branch of our simple guards."""
    lines = text.splitlines(keepends=True)
    output: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].strip() != f"#ifdef {MACRO}":
            output.append(lines[i])
            i += 1
            continue
        i += 1
        true_lines: list[str] = []
        false_lines: list[str] = []
        target = true_lines
        while i < len(lines) and lines[i].strip() != "#endif":
            if lines[i].strip() == "#else":
                target = false_lines
            else:
                target.append(lines[i])
            i += 1
        if i == len(lines):
            raise OverlayError("unterminated S15 macro guard")
        output.extend(false_lines)
        i += 1
    return "".join(output)


def _guard(body: list[str], indent: str = "   ") -> list[str]:
    return [f"#ifdef {MACRO}", *(indent + line for line in body), "#endif"]


def _append_module_em_helpers(
    lines: list[str], *, neighbors: bool = False
) -> list[str]:
    end_module = next(
        (
            i
            for i, line in enumerate(lines)
            if re.match(r"^\s*END\s+MODULE\s+module_em\b", line, re.I)
        ),
        None,
    )
    if end_module is None:
        raise OverlayError("module_em end anchor was not found")
    neighbor_rk_match = []
    if neighbors:
        neighbor_rk_match = [
            f" if(tile.eq.{tile} .and. i.eq.{i} .and. j.eq.{j} .and. k.eq.{k}) hit=.true."
            for tile, (i, j, k) in NEIGHBOR_RECEIVERS
        ]
    rk_cap = 14 if neighbors else 6
    helper = _guard(
        [
            "SUBROUTINE s15_rk_match(step,rk,owner,tile,i,j,k,hit)",
            "INTEGER, INTENT(IN) :: step,rk,owner,tile,i,j,k",
            "LOGICAL, INTENT(OUT) :: hit",
            "hit=.false.",
            "if (step.ne.2 .or. owner.ne.5) return",
            "select case(rk)",
            "case(1)",
            " if(tile.eq.1 .and. i.eq.143 .and. j.eq.2 .and. k.eq.16) hit=.true.",
            " if(tile.eq.2 .and. i.eq.144 .and. j.eq.143 .and. k.eq.14) hit=.true.",
            "case(2)",
            " if(tile.eq.1 .and. i.eq.111 .and. j.eq.2 .and. k.eq.16) hit=.true.",
            " if(tile.eq.2 .and. i.eq.146 .and. j.eq.143 .and. k.eq.13) hit=.true.",
            "case(3)",
            " if(tile.eq.1 .and. i.eq.141 .and. j.eq.2 .and. k.eq.17) hit=.true.",
            " if(tile.eq.2 .and. i.eq.141 .and. j.eq.143 .and. k.eq.16) hit=.true.",
            *neighbor_rk_match,
            "end select",
            "END SUBROUTINE s15_rk_match",
            "SUBROUTINE s15_emit_rk(step,rk,owner,tile,its,ite,jts,jte,i,j,k,advect,msfty,sc_tend,tendency,reference,dt,c1,c2,muold,munew,after)",
            "INTEGER, INTENT(IN) :: step,rk,owner,tile,its,ite,jts,jte,i,j,k",
            "INTEGER, SAVE :: s15_count=0",
            "REAL, INTENT(IN) :: advect,msfty,sc_tend,tendency,reference,dt,c1,c2,muold,munew,after",
            f"if (s15_count.ge.{rk_cap}) then",
            " write(6,'(A)') 'S15LIMIT S15RK event cap exceeded'",
            " stop 91",
            "endif",
            "s15_count=s15_count+1",
            "WRITE(6,'(A,1X,11(I0,1X),11(Z8.8,1X))') 'S15RK', &",
            " step,rk,owner,tile,its,ite,jts,jte,i,j,k, &",
            " transfer(advect,0),transfer(msfty,0),transfer(sc_tend,0), &",
            " transfer(tendency,0),transfer(reference,0),transfer(dt,0), &",
            " transfer(c1,0),transfer(c2,0),transfer(muold,0),transfer(munew,0),transfer(after,0)",
            "END SUBROUTINE s15_emit_rk",
        ]
    )
    return [*lines[:end_module], *helper, *lines[end_module:]]


def _patch_rk_store_taps(lines: list[str]) -> list[str]:
    start, end = _find_proc(lines, "rk_update_scalar")
    stores = []
    pattern = re.compile(
        r"^\s*scalar_2\s*\(\s*i\s*,\s*k\s*,\s*j\s*,\s*im\s*\)\s*=", re.I
    )
    index = start + 1
    while index < end:
        if pattern.search(lines[index]):
            last = index
            while lines[last].rstrip().endswith("&"):
                last += 1
            stores.append((index, last))
            index = last + 1
        else:
            index += 1
    if len(stores) != 2:
        raise OverlayError("expected two scalar_2 RK store statements")
    implicit = next(
        i for i in range(start, end) if re.match(r"\s*IMPLICIT\s+NONE", lines[i], re.I)
    )
    lines[implicit + 1 : implicit + 1] = _guard(["LOGICAL :: s15_here"])
    start, end = _find_proc(lines, "rk_update_scalar")
    stores = []
    index = start + 1
    while index < end:
        if pattern.search(lines[index]):
            last = _statement_end(lines, index, end)
            stores.append((index, last))
            index = last + 1
        else:
            index += 1
    for first, last in reversed(stores):
        indent = lines[first][: len(lines[first]) - len(lines[first].lstrip())]
        body = [
            "s15_here=.false.",
            "if (present(s15_step)) then",
            " if (present(s15_rk)) then",
            "  if (present(s15_owner)) then",
            "   if (present(s15_tile)) then",
            "    call s15_rk_match(s15_step,s15_rk,s15_owner,s15_tile,i,j,k,s15_here)",
            "   endif",
            "  endif",
            " endif",
            "endif",
            "if (s15_here) call s15_emit_rk(s15_step,s15_rk,s15_owner,s15_tile, &",
            "     its,ite,jts,jte,i,j,k,advect_tend(i,k,j),msfty(i,j), &",
            "     sc_tend(i,k,j,im),tendency(i,k,j),scalar_1(i,k,j,im),dt, &",
            "     c1(k),c2(k),muold(i),munew(i),scalar_2(i,k,j,im))",
        ]
        lines[last + 1 : last + 1] = _guard(body, indent)
        start, end = _find_proc(lines, "rk_update_scalar")
    return lines


def _target_gate(i_expr: str, j_expr: str, k_expr: str, indent: str) -> list[str]:
    return _guard(
        [
            "s15_here=.false.",
            "if (present(s15_step)) then",
            " if (present(s15_rk)) then",
            "  if (present(s15_owner)) then",
            "   if (present(s15_tile)) then",
            "    if (present(s15_branch)) then",
            f"     call s15_face_match(s15_step,s15_rk,s15_owner,s15_tile,{i_expr},{j_expr},{k_expr},s15_here)",
            "    endif",
            "   endif",
            "  endif",
            " endif",
            "endif",
        ],
        indent,
    )


def _axis_operands(proc_name: str, axis: str, statement: str) -> tuple[str, ...]:
    if proc_name == "advect_scalar_pd":
        if axis == "y":
            return (
                "fqy(i,k,j)",
                "fqy(i,k,j+1)",
                "fqyl(i,k,j)",
                "fqyl(i,k,j+1)",
                "msftx(i,j)",
                "rdy",
                "j",
            )
        if axis == "x":
            return (
                "fqx(i,k,j)",
                "fqx(i+1,k,j)",
                "fqxl(i,k,j)",
                "fqxl(i+1,k,j)",
                "msftx(i,j)",
                "rdx",
                "j",
            )
        return (
            "fqz(i,k,j)",
            "fqz(i,k+1,j)",
            "fqzl(i,k,j)",
            "fqzl(i,k+1,j)",
            "1.0",
            "rdzw(k)",
            "j",
        )
    if axis == "y":
        if "jp0" in statement and "jp1" not in statement:
            return ("fqy(i,k,jp0)", "0.0", "0.0", "0.0", "msftx(i,j-1)", "rdy", "j-1")
        if "jp1" in statement and "jp0" not in statement:
            return ("0.0", "fqy(i,k,jp1)", "0.0", "0.0", "msftx(i,j-1)", "rdy", "j-1")
        return (
            "fqy(i,k,jp0)",
            "fqy(i,k,jp1)",
            "0.0",
            "0.0",
            "msftx(i,j-1)",
            "rdy",
            "j-1",
        )
    if axis == "x":
        return ("fqx(i,k)", "fqx(i+1,k)", "0.0", "0.0", "msftx(i,j)", "rdx", "j")
    return ("vflux(i,k)", "vflux(i,k+1)", "0.0", "0.0", "1.0", "rdzw(k)", "j")


def _axis_after(indent: str, axis: str, values: tuple[str, ...]) -> list[str]:
    fm, fp, lm, lp, metric, spacing, j_expr = values
    axis_id = {"y": 1, "x": 2, "z": 3}[axis]
    return _guard(
        [
            "if (s15_here) call s15_emit_axis(s15_step,s15_rk,s15_owner,s15_tile, &",
            f"     its,ite,jts,jte,i,{j_expr},k,s15_branch,{axis_id}, &",
            f"     {fm},{fp},{lm},{lp},{metric},{spacing}, &",
            f"     s15_prefix_before,tendency(i,k,{j_expr}))",
        ],
        indent,
    )


def _statement_end(lines: list[str], index: int, limit: int) -> int:
    end = index
    while end < limit - 1 and lines[end].rstrip().endswith("&"):
        end += 1
    return end


def _tap_advection_procedure(
    lines: list[str], proc_name: str, *, shadow: bool = False
) -> list[str]:
    start, end = _find_proc(lines, proc_name)
    assignment = re.compile(
        r"^\s*tendency\s*\(\s*i\s*,\s*k\s*,\s*j(?:\s*-\s*1)?\s*\)\s*=", re.I
    )
    taps = []
    index = start + 1
    while index < end:
        if not assignment.search(lines[index]):
            index += 1
            continue
        last = _statement_end(lines, index, end)
        statement = " ".join(
            line.split("!", 1)[0] for line in lines[index : last + 1]
        ).lower()
        axis = (
            "y"
            if "fqy" in statement
            else "x"
            if "fqx" in statement
            else "z"
            if ("vflux" in statement or "fqz" in statement)
            else ""
        )
        if not axis:
            index = last + 1
            continue
        indent = lines[index][: len(lines[index]) - len(lines[index].lstrip())]
        values = _axis_operands(proc_name, axis, statement)
        j_expr = values[-1]
        before = _target_gate("i", j_expr, "k", indent)
        before.extend(
            _guard([f"if (s15_here) s15_prefix_before=tendency(i,k,{j_expr})"], indent)
        )
        taps.append((index, last, before, _axis_after(indent, axis, values)))
        index = last + 1
    if not taps:
        raise OverlayError(f"no face-divergence statements found in {proc_name}")
    for first, last, before, after in reversed(taps):
        lines[first:first] = before
        last += len(before)
        lines[last + 1 : last + 1] = after
    if proc_name == "advect_scalar_pd":
        lines = _tap_pd_limiter(lines, shadow=shadow)
    return lines


def _tap_pd_limiter(lines: list[str], *, shadow: bool = False) -> list[str]:
    start, end = _find_proc(lines, "advect_scalar_pd")
    predicate = re.compile(r"IF\s*\(\s*flux_out\(i,k,j\).*ph_low\(i,k,j\).*THEN", re.I)
    gate = next((i for i in range(start, end) if predicate.search(lines[i])), None)
    if gate is None:
        raise OverlayError("PD limiter branch anchor was not found")
    indent = lines[gate][: len(lines[gate]) - len(lines[gate].lstrip())]
    capture = _target_gate("i", "j", "k", indent)
    capture.extend(
        _guard(
            [
                "if (s15_here) then",
                " s15_pd_active=0",
                " s15_pd_scale=0.0",
                " s15_pd_flux_out=flux_out(i,k,j)",
                " s15_pd_available=ph_low(i,k,j)",
                " s15_pd_pre(1)=fqx(i,k,j)",
                " s15_pd_pre(2)=fqx(i+1,k,j)",
                " s15_pd_pre(3)=fqy(i,k,j)",
                " s15_pd_pre(4)=fqy(i,k,j+1)",
                " s15_pd_pre(5)=fqz(i,k,j)",
                " s15_pd_pre(6)=fqz(i,k+1,j)",
                " s15_pd_low(1)=fqxl(i,k,j)",
                " s15_pd_low(2)=fqxl(i+1,k,j)",
                " s15_pd_low(3)=fqyl(i,k,j)",
                " s15_pd_low(4)=fqyl(i,k,j+1)",
                " s15_pd_low(5)=fqzl(i,k,j)",
                " s15_pd_low(6)=fqzl(i,k+1,j)",
                " if (flux_out(i,k,j) .gt. ph_low(i,k,j)) s15_pd_active=1",
                "endif",
            ],
            indent,
        )
    )
    lines[gate:gate] = capture
    start, end = _find_proc(lines, "advect_scalar_pd")
    scale = next(
        (
            i
            for i in range(start, end)
            if re.search(r"\bscale\s*=\s*max\s*\(", lines[i], re.I)
        ),
        None,
    )
    if scale is None:
        raise OverlayError("PD scale assignment anchor was not found")
    lines[scale + 1 : scale + 1] = _guard(["if (s15_here) s15_pd_scale=scale"], indent)
    start, end = _find_proc(lines, "advect_scalar_pd")
    gate = next(i for i in range(start, end) if predicate.search(lines[i]))
    scale = next(
        i
        for i in range(gate, end)
        if re.search(r"\bscale\s*=\s*max\s*\(", lines[i], re.I)
    )
    endif = next(
        i for i in range(scale, end) if re.match(r"^\s*END\s*IF\s*$", lines[i], re.I)
    )
    post_indent = lines[endif][: len(lines[endif]) - len(lines[endif].lstrip())]
    shadow_lines = []
    if shadow:
        shadow_lines = _guard(
            [
                "if (present(s3qn_xr_shadow_enabled)) then",
                " if (s3qn_xr_shadow_enabled .and. i.eq.233 .and. &",
                "     j.eq.124 .and. k.eq.12) then",
                "  if (fqx(i+1,k,j).le.0. .or. &",
                f"      transfer(fqx(i+1,k,j),0).ne.int(z'{QN_XR_SHADOW_INPUT_WORD}',kind=4)) then",
                "   write(6,'(A)') 'S3QN_SHADOW xR f32 input mismatch'",
                "   stop 92",
                "  endif",
                f"  fqx(i+1,k,j)={QN_XR_SHADOW_FACTOR_LITERAL}*fqx(i+1,k,j)",
                " endif",
                "endif",
            ],
            post_indent,
        )
    post = _guard(
        [
            "if (s15_here) then",
            " s15_pd_post(1)=fqx(i,k,j)",
            " s15_pd_post(2)=fqx(i+1,k,j)",
            " s15_pd_post(3)=fqy(i,k,j)",
            " s15_pd_post(4)=fqy(i,k,j+1)",
            " s15_pd_post(5)=fqz(i,k,j)",
            " s15_pd_post(6)=fqz(i,k+1,j)",
            " call s15_emit_pd(s15_step,s15_rk,s15_owner,s15_tile, &",
            "      its,ite,jts,jte,i,j,k,s15_pd_active,s15_pd_flux_out, &",
            "      s15_pd_available,eps,s15_pd_scale,s15_pd_low,s15_pd_pre,s15_pd_post)",
            "endif",
        ],
        post_indent,
    )
    lines[endif + 1 : endif + 1] = [*shadow_lines, *post]
    return lines


def _append_advect_helpers(lines: list[str], *, neighbors: bool = False) -> list[str]:
    end_module = next(
        (
            i
            for i, line in enumerate(lines)
            if re.match(r"^\s*END\s+MODULE\s+module_advect_em\b", line, re.I)
        ),
        None,
    )
    if end_module is None:
        raise OverlayError("module_advect_em end anchor was not found")
    neighbor_face_match = []
    if neighbors:
        neighbor_face_match = [
            f" if(tile.eq.{tile} .and. i.eq.{i} .and. j.eq.{j} .and. k.eq.{k}) hit=.true."
            for tile, (i, j, k) in NEIGHBOR_RECEIVERS
        ]
    face_cap = 42 if neighbors else 18
    pd_cap = 10 if neighbors else 2
    helper = _guard(
        [
            "SUBROUTINE s15_face_match(step,rk,owner,tile,i,j,k,hit)",
            "INTEGER, INTENT(IN) :: step,rk,owner,tile,i,j,k",
            "LOGICAL, INTENT(OUT) :: hit",
            "hit=.false.",
            "if (step.ne.2 .or. owner.ne.5) return",
            "select case(rk)",
            "case(1)",
            " if(tile.eq.1 .and. i.eq.143 .and. j.eq.2 .and. k.eq.16) hit=.true.",
            " if(tile.eq.2 .and. i.eq.144 .and. j.eq.143 .and. k.eq.14) hit=.true.",
            "case(2)",
            " if(tile.eq.1 .and. i.eq.111 .and. j.eq.2 .and. k.eq.16) hit=.true.",
            " if(tile.eq.2 .and. i.eq.146 .and. j.eq.143 .and. k.eq.13) hit=.true.",
            "case(3)",
            " if(tile.eq.1 .and. i.eq.141 .and. j.eq.2 .and. k.eq.17) hit=.true.",
            " if(tile.eq.2 .and. i.eq.141 .and. j.eq.143 .and. k.eq.16) hit=.true.",
            *neighbor_face_match,
            "end select",
            "END SUBROUTINE s15_face_match",
            "SUBROUTINE s15_emit_axis(step,rk,owner,tile,its,ite,jts,jte,i,j,k,branch,axis,fm,fp,lm,lp,metric,spacing,before,after)",
            "INTEGER, INTENT(IN) :: step,rk,owner,tile,its,ite,jts,jte,i,j,k,branch,axis",
            "INTEGER, SAVE :: s15_count=0",
            "REAL, INTENT(IN) :: fm,fp,lm,lp,metric,spacing,before,after",
            f"if (s15_count.ge.{face_cap}) then",
            " write(6,'(A)') 'S15LIMIT S15AX event cap exceeded'",
            " stop 91",
            "endif",
            "s15_count=s15_count+1",
            "WRITE(6,'(A,1X,11(I0,1X),2(I0,1X),8(Z8.8,1X))') 'S15AX', &",
            " step,rk,owner,tile,its,ite,jts,jte,i,j,k,axis,branch, &",
            " transfer(fm,0),transfer(fp,0),transfer(lm,0),transfer(lp,0), &",
            " transfer(metric,0),transfer(spacing,0),transfer(before,0),transfer(after,0)",
            "END SUBROUTINE s15_emit_axis",
            "SUBROUTINE s15_emit_pd(step,rk,owner,tile,its,ite,jts,jte,i,j,k,active,fluxout,available,eps,scale,low,pre,post)",
            "INTEGER, INTENT(IN) :: step,rk,owner,tile,its,ite,jts,jte,i,j,k,active",
            "INTEGER, SAVE :: s15_count=0",
            "REAL, INTENT(IN) :: fluxout,available,eps,scale,low(6),pre(6),post(6)",
            f"if (s15_count.ge.{pd_cap}) then",
            " write(6,'(A)') 'S15LIMIT S15PD event cap exceeded'",
            " stop 91",
            "endif",
            "s15_count=s15_count+1",
            "WRITE(6,'(A,1X,11(I0,1X),I0,1X,22(Z8.8,1X))') 'S15PD', &",
            " step,rk,owner,tile,its,ite,jts,jte,i,j,k,active, &",
            " transfer(fluxout,0),transfer(available,0),transfer(eps,0),transfer(scale,0), &",
            " transfer(low(1),0),transfer(low(2),0),transfer(low(3),0),transfer(low(4),0),transfer(low(5),0),transfer(low(6),0), &",
            " transfer(pre(1),0),transfer(pre(2),0),transfer(pre(3),0),transfer(pre(4),0),transfer(pre(5),0),transfer(pre(6),0), &",
            " transfer(post(1),0),transfer(post(2),0),transfer(post(3),0),transfer(post(4),0),transfer(post(5),0),transfer(post(6),0)",
            "END SUBROUTINE s15_emit_pd",
        ]
    )
    return [*lines[:end_module], *helper, *lines[end_module:]]


def parse_fortran_capture(
    text: str,
    public_root: Path,
    config: dict[str, Any],
    *,
    neighbors: bool = False,
    qn: bool = False,
    shadow: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse the bounded stream against six witnesses and optional eight receivers."""
    if neighbors and qn:
        raise OverlayError("S15 neighbor and S3 QNCLOUD capture modes are exclusive")
    if shadow and not qn:
        raise OverlayError("the xR shadow parser mode requires S3 QNCLOUD capture mode")
    roster = _capture_roster(public_root, neighbors=neighbors, qn=qn)
    target_keys = {
        key for key, identity in roster.items() if identity["role"] == "witness"
    }
    axes: dict[tuple[int, ...], dict[str, dict[str, str]]] = {}
    pds: dict[tuple[int, ...], dict[str, Any]] = {}
    consumers: dict[tuple[int, ...], dict[str, Any]] = {}

    def exact_int(token: str, label: str) -> int:
        if not re.fullmatch(r"-?[0-9]+", token):
            raise OverlayError(f"{label} must be an exact integer token")
        return int(token)

    def words(tokens: list[str], count: int, label: str) -> list[str]:
        if len(tokens) != count:
            raise OverlayError(f"{label} has the wrong raw-word count")
        return [replay._word(token, label) for token in tokens]

    def identity(ints: list[int], label: str) -> tuple[tuple[int, ...], dict[str, int]]:
        if len(ints) != 11:
            raise OverlayError(f"{label} must carry the full tile/cell identity")
        step, rk, owner, tile, ti0, ti1, tj0, tj1, i, j, k = ints
        event_key = (step, rk, owner, tile, ti0, ti1, tj0, tj1, i, j, k)
        roster_key = (step, rk, owner, ti0, ti1, tj0, tj1, i, j, k)
        expected = roster.get(roster_key)
        if expected is None or tile != expected["tile"]:
            scope = (
                "five-cell QNCLOUD roster"
                if qn
                else "witness/receiver roster"
                if neighbors
                else "six-slot schedule"
            )
            raise OverlayError(
                f"{label} tile slot or coordinate differs from the pinned {scope}"
            )
        row = dict(
            zip(replay.KEY_FIELDS, (step, rk, owner, ti0, ti1, tj0, tj1, i, j, k))
        )
        return event_key, row

    for line_no, raw in enumerate(text.splitlines(), 1):
        tokens = raw.split()
        if tokens and (
            (qn and tokens[0].startswith(("S15AX", "S15PD", "S15RK")))
            or (not qn and tokens[0].startswith(("S3QNAX", "S3QNPD", "S3QNRK")))
        ):
            raise OverlayError(
                f"line {line_no}: face record belongs to the other capture mode"
            )
        prefix = "S3QN" if qn else "S15"
        if not tokens or not tokens[0].startswith(prefix):
            continue
        tag = tokens[0]
        axis_tag, pd_tag, rk_tag = (
            ("S3QNAX", "S3QNPD", "S3QNRK") if qn else ("S15AX", "S15PD", "S15RK")
        )
        if tag not in {axis_tag, pd_tag, rk_tag}:
            raise OverlayError(f"line {line_no}: unknown {prefix} record tag {tag}")
        if tag == axis_tag:
            if len(tokens) != 22:
                raise OverlayError(f"line {line_no}: S15AX width mismatch")
            ints = [exact_int(x, "S15AX identity") for x in tokens[1:12]]
            event_key, row = identity(ints, tag)
            axis_id, branch_id = (
                exact_int(x, "S15AX axis/branch") for x in tokens[12:14]
            )
            if axis_id not in (1, 2, 3) or branch_id not in (1, 2):
                raise OverlayError(f"line {line_no}: invalid S15AX axis or branch")
            axis = {1: "y", 2: "x", 3: "z"}[axis_id]
            expected_branch = 2 if row["rk"] == 3 else 1
            if branch_id != expected_branch:
                raise OverlayError(
                    f"line {line_no}: source branch does not match RK/config"
                )
            fm, fp, lm, lp, metric, spacing, before, after = words(tokens[14:], 8, tag)
            record = {
                **row,
                "branch": "positive_definite" if branch_id == 2 else "ordinary",
                "face_fluxes": {"minus": fm, "plus": fp},
                "low_face_fluxes": {"minus": lm, "plus": lp},
                "metric_factor": metric,
                "inverse_spacing": spacing,
                "prefix_before": before,
                "prefix_after": after,
            }
            group = axes.setdefault(event_key, {})
            if axis in group:
                raise OverlayError(f"line {line_no}: duplicate {axis} face record")
            group[axis] = record
        elif tag == pd_tag:
            if len(tokens) != 35:
                raise OverlayError(f"line {line_no}: S15PD width mismatch")
            ints = [exact_int(x, "S15PD identity") for x in tokens[1:12]]
            event_key, row = identity(ints, tag)
            active = exact_int(tokens[12], "PD active flag")
            if row["rk"] != 3 or active not in (0, 1):
                raise OverlayError(
                    f"line {line_no}: PD limiter record on wrong stage/flag"
                )
            values = words(tokens[13:], 22, tag)
            floats = values[:4]
            groups = [values[n : n + 6] for n in (4, 10, 16)]
            if floats[2] != PD_EPS_F32:
                raise OverlayError(
                    "PD epsilon differs from the source-pinned binary32 parameter"
                )
            if active == 0 and floats[3] != "00000000":
                raise OverlayError(
                    "inactive PD limiter must retain the initialized zero scale"
                )
            if event_key in pds:
                raise OverlayError(f"line {line_no}: duplicate PD limiter record")
            pds[event_key] = {
                **row,
                "pd_limiter_active": bool(active),
                "pd_flux_out": floats[0],
                "pd_available_state": floats[1],
                "pd_low_order_fluxes": groups[0],
                "pd_unlimited_high_order_fluxes": groups[1],
                "pd_high_order_fluxes": groups[2],
                "pd_scale": floats[3] if active else None,
                "pd_eps": floats[2] if active else None,
            }
        else:
            if len(tokens) != 23:
                raise OverlayError(f"line {line_no}: S15RK width mismatch")
            ints = [exact_int(x, "S15RK identity") for x in tokens[1:12]]
            event_key, row = identity(ints, tag)
            values = words(tokens[12:], 11, tag)
            fields = (
                "advect_tend",
                "msfty",
                "sc_tend",
                "tendency",
                "before",
                "dt",
                "c1",
                "c2",
                "muold",
                "munew",
                "after",
            )
            if event_key in consumers:
                raise OverlayError(f"line {line_no}: duplicate RK consumer record")
            consumers[event_key] = {**row, **dict(zip(fields, values))}

    expected_count = 5 if qn else (14 if neighbors else 6)
    if len(axes) != expected_count or len(consumers) != expected_count:
        raise OverlayError(
            f"Fortran stream must contain exactly {expected_count} producer keys and consumers"
        )
    if set(axes) != set(consumers):
        raise OverlayError("producer and consumer full tile/cell keys differ")
    expected_pd_keys = {key for key in axes if key[1] == 3}
    expected_pd_count = 5 if qn else (10 if neighbors else 2)
    if set(pds) != expected_pd_keys or len(pds) != expected_pd_count:
        raise OverlayError(
            f"exactly the {expected_pd_count} RK3 selected PD limiter records are required"
        )

    producers: list[dict[str, Any]] = []
    for event_key in sorted(axes):
        by_axis = axes[event_key]
        if set(by_axis) != set(replay.AXES):
            raise OverlayError(
                "each selected producer must contain exactly Y/X/Z records"
            )
        identity_row = {
            name: value
            for name, value in by_axis[replay.ORDINARY_ORDER[0]].items()
            if name in replay.KEY_FIELDS
        }
        roster_key = tuple(identity_row[name] for name in replay.KEY_FIELDS)
        expected_slot = roster[roster_key]["tile"]
        order = list(
            replay.PD_ORDER if identity_row["rk"] == 3 else replay.ORDINARY_ORDER
        )
        branch = "positive_definite" if identity_row["rk"] == 3 else "ordinary"
        acc = by_axis[order[0]]["prefix_before"]
        initial = acc
        axis_rows = {}
        prefixes = []
        for axis in order:
            rec = by_axis[axis]
            if rec["branch"] != branch or rec["prefix_before"] != acc:
                raise OverlayError(
                    "axis dispatch or source-order prefix chain is inconsistent"
                )
            high = rec["face_fluxes"]
            low = rec["low_face_fluxes"]
            if branch == "positive_definite":
                dflux = replay._sub(
                    replay._add(replay._sub(high["plus"], high["minus"]), low["plus"]),
                    low["minus"],
                )
                delta = replay._mul(
                    rec["metric_factor"], replay._mul(rec["inverse_spacing"], dflux)
                )
            else:
                dflux = replay._sub(high["plus"], high["minus"])
                delta = replay._mul(
                    replay._mul(rec["metric_factor"], rec["inverse_spacing"]), dflux
                )
            contribution = replay._sub("00000000", delta)
            prefix = rec["prefix_after"]
            acc = prefix
            prefixes.append(prefix)
            axis_rows[axis] = {
                "face_fluxes": high,
                "metric_factor": rec["metric_factor"],
                "inverse_spacing": rec["inverse_spacing"],
                "flux_difference": dflux,
                "directional_contribution": contribution,
                "tendency_prefix": prefix,
            }
        producer = {
            **identity_row,
            "branch": branch,
            "dispatch": {
                "rk_order": 3,
                "adv_opt": "POSITIVEDEF",
                "selected_branch": branch,
            },
            "tendency_order": order,
            "initial_tendency": initial,
            "axes": axis_rows,
            "prefixes": prefixes,
            "advect_tend": acc,
            "tile_slot": expected_slot,
        }
        if branch == "positive_definite":
            pd = pds[event_key]
            producer.update(
                {
                    "pd_limiter_active": pd["pd_limiter_active"],
                    "pd_flux_out": pd["pd_flux_out"],
                    "pd_available_state": pd["pd_available_state"],
                    "pd_low_order_fluxes": {
                        a: {
                            "minus": pd["pd_low_order_fluxes"][n],
                            "plus": pd["pd_low_order_fluxes"][n + 1],
                        }
                        for a, n in (("x", 0), ("y", 2), ("z", 4))
                    },
                    "pd_unlimited_high_order_fluxes": {
                        a: {
                            "minus": pd["pd_unlimited_high_order_fluxes"][n],
                            "plus": pd["pd_unlimited_high_order_fluxes"][n + 1],
                        }
                        for a, n in (("x", 0), ("y", 2), ("z", 4))
                    },
                    "pd_high_order_fluxes": {
                        a: {
                            "minus": pd["pd_high_order_fluxes"][n],
                            "plus": pd["pd_high_order_fluxes"][n + 1],
                        }
                        for a, n in (("x", 0), ("y", 2), ("z", 4))
                    },
                }
            )
            for axis in replay.AXES:
                if (
                    producer["pd_low_order_fluxes"][axis]
                    != by_axis[axis]["low_face_fluxes"]
                ):
                    raise OverlayError(
                        f"PD {axis} low-order faces differ between limiter and divergence taps"
                    )
            if pd["pd_limiter_active"]:
                producer["pd_scale"] = pd["pd_scale"]
                producer["pd_eps"] = pd["pd_eps"]
        producers.append(producer)

    consumer_rows = list(consumers.values())
    pairs = replay.validate_capture(
        producers,
        consumer_rows,
        public_root,
        config,
        neighbors=neighbors,
        qn=qn,
        shadow=shadow,
    )
    for _, consumer in pairs:
        consumer_key = tuple(consumer[name] for name in replay.KEY_FIELDS)
        if (neighbors or qn) and consumer_key not in target_keys:
            continue
        scalar_name = "QNCLOUD" if qn else "QIB"
        before = replay.word_value(consumer["before"], f"{scalar_name} before")
        after = replay.word_value(consumer["after"], f"{scalar_name} after")
        failed_transition = (
            before < 0.0 or after <= 0.0 if shadow else before < 0.0 or after >= 0.0
        )
        if failed_transition:
            transition = (
                "nonnegative-to-positive" if shadow else "nonnegative-to-negative"
            )
            raise OverlayError(
                f"selected {scalar_name} witness did not execute the pinned {transition} RK transition"
            )
    return producers, consumer_rows


def extract_s15_streams(
    full_stdout: Path,
    face_stream: Path,
    legacy_stream: Path,
    *,
    neighbors: bool = False,
    qn: bool = False,
) -> dict[str, Any]:
    """Split bounded S15 or S3QN face records from legacy output.

    The full rank stdout remains byte-for-byte intact. Both selected outputs are
    created exclusively and preserve the source order of their own tag family.
    """
    # Keep output path checks lexical. Path.resolve() follows a dangling output
    # symlink and could redirect exclusive creation outside the requested tree.
    if neighbors and qn:
        raise OverlayError("S15 neighbor and S3 QNCLOUD modes are exclusive")
    active_face_tags = QN_FACE_TAGS if qn else FACE_TAGS
    active_face_counts = (
        EXPECTED_QN_FACE_TAG_COUNTS
        if qn
        else EXPECTED_NEIGHBOR_FACE_TAG_COUNTS
        if neighbors
        else EXPECTED_FACE_TAG_COUNTS
    )
    source = Path(os.path.abspath(full_stdout))
    face = Path(os.path.abspath(face_stream))
    legacy = Path(os.path.abspath(legacy_stream))
    if face == legacy or face == source or legacy == source:
        raise OverlayError(
            "full stdout and selected face/legacy stream paths must be distinct"
        )
    digest = hashlib.sha256()
    total_bytes = 0
    face_bytes = bytearray()
    legacy_bytes = bytearray()
    legacy_records = 0
    counts = {tag.decode("ascii"): 0 for tag in active_face_tags | LEGACY_TAGS}
    source_fd = _open_regular_nofollow(source)
    with os.fdopen(source_fd, "rb") as stream:
        line_no = 0
        while line := stream.readline(MAX_CAPTURE_LINE_BYTES + 1):
            line_no += 1
            total_bytes += len(line)
            if total_bytes > MAX_FULL_STDOUT_BYTES:
                raise OverlayError("full stdout exceeds the configured size cap")
            if len(line) > MAX_CAPTURE_LINE_BYTES:
                raise OverlayError(f"line {line_no}: full stdout line exceeds size cap")
            digest.update(line)
            fields = line.lstrip().split(None, 1)
            if not fields:
                continue
            tag = fields[0]
            if qn and tag.startswith(b"S15") and tag not in LEGACY_TAGS:
                raise OverlayError(
                    f"line {line_no}: unexpected S15 tap in QNCLOUD extraction"
                )
            belongs = (
                tag.startswith(b"S3QN") or tag in LEGACY_TAGS
                if qn
                else tag.startswith(b"S15") or tag.startswith(b"S3QN")
            )
            if not belongs:
                continue
            if not qn and tag.startswith(b"S3QN"):
                raise OverlayError(f"line {line_no}: S3QN record in S15 extraction")
            if tag in active_face_tags:
                face_bytes.extend(line)
                if len(face_bytes) > MAX_FACE_STREAM_BYTES:
                    raise OverlayError("face stream exceeds the configured size cap")
            elif tag in LEGACY_TAGS:
                legacy_bytes.extend(line)
                if len(legacy_bytes) > MAX_LEGACY_STREAM_BYTES:
                    raise OverlayError("legacy stream exceeds the configured size cap")
                if legacy_records >= MAX_LEGACY_RECORDS:
                    raise OverlayError(
                        "legacy stream exceeds the configured record cap"
                    )
                legacy_records += 1
            else:
                raise OverlayError(
                    f"line {line_no}: unknown {'S3QN' if qn else 'S15'} record tag {tag.decode('ascii', 'replace')}"
                )
            counts[tag.decode("ascii")] += 1
    before_hash = digest.hexdigest()
    if _hash_file_bounded(source) != before_hash:
        raise OverlayError("full stdout changed during S15 stream extraction")
    expected_counts = active_face_counts
    if {tag: counts[tag] for tag in expected_counts} != expected_counts:
        expected_message = (
            "15 S3QNAX, 5 S3QNPD, and 5 S3QNRK"
            if qn
            else "42 AX, 10 PD, and 14 RK"
            if neighbors
            else "18 AX, 2 PD, and 6 RK"
        )
        raise OverlayError(
            f"face stream must contain exactly {expected_message} events"
        )
    face_payload = bytes(face_bytes)
    legacy_payload = bytes(legacy_bytes)
    created: list[tuple[int, str]] = []
    try:
        created.append(_exclusive_write_no_symlinks(face, face_payload))
        created.append(_exclusive_write_no_symlinks(legacy, legacy_payload))
        if _hash_file_bounded(source) != before_hash:
            raise OverlayError("full stdout changed during selected-stream writes")
    except BaseException:
        _rollback_created_outputs(created)
        raise
    else:
        for parent_fd, _ in created:
            os.close(parent_fd)
    receipt = {
        "schema": (
            "KDM6AD-S3-QNCLOUD-DUAL-STREAM-EXTRACTION-v1"
            if qn
            else "KDM6AD-S15-DUAL-STREAM-EXTRACTION-v1"
        ),
        "full_stdout_sha256": before_hash,
        "full_stdout_bytes": total_bytes,
        "face_stream_sha256": hashlib.sha256(face_payload).hexdigest(),
        "face_stream_bytes": len(face_payload),
        "legacy_stream_sha256": hashlib.sha256(legacy_payload).hexdigest(),
        "legacy_stream_bytes": len(legacy_payload),
        "tag_counts": counts,
    }
    if qn:
        receipt["capture_mode"] = "S3_QNCLOUD_OWNER3"
    return receipt


def _hash_file_bounded(path: Path) -> str:
    digest = hashlib.sha256()
    total = 0
    fd = _open_regular_nofollow(path)
    with os.fdopen(fd, "rb") as stream:
        while chunk := stream.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_FULL_STDOUT_BYTES:
                raise OverlayError("full stdout exceeds the configured size cap")
            digest.update(chunk)
    return digest.hexdigest()


def _exclusive_write_no_symlinks(path: Path, data: bytes) -> tuple[int, str]:
    """Create a new output without following a target symlink.

    Reject symlinks in every existing parent component before creation, then
    request O_NOFOLLOW and O_EXCL from the kernel for the leaf. This fails
    closed for dangling leaf symlinks and ordinary existing files alike. Keep
    the parent descriptor open so transaction rollback cannot be redirected by
    a later pathname swap.
    """
    absolute = Path(os.path.abspath(path))
    parent_fd = _open_parent_dirfd(absolute)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(absolute.name, flags, 0o666, dir_fd=parent_fd)
    except FileExistsError as exc:
        os.close(parent_fd)
        raise OverlayError("selected S15 stream destinations must be new") from exc
    except OSError as exc:
        os.close(parent_fd)
        raise OverlayError(f"cannot safely create selected stream: {absolute}") from exc
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(data)
    except BaseException:
        try:
            os.unlink(absolute.name, dir_fd=parent_fd)
        finally:
            os.close(parent_fd)
        raise
    return parent_fd, absolute.name


def _rollback_created_outputs(created: list[tuple[int, str]]) -> None:
    for parent_fd, name in reversed(created):
        try:
            os.unlink(name, dir_fd=parent_fd)
        except FileNotFoundError:
            pass
        except OSError:
            # Preserve the extraction failure; leaving a partial file is safer
            # than resolving the pathname again and risking a wrong deletion.
            pass
        finally:
            os.close(parent_fd)


def _open_parent_dirfd(absolute: Path) -> int:
    """Walk an absolute path's parents with descriptor-relative no-follow opens."""
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    directory_flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        current_fd = os.open(absolute.anchor, directory_flags)
    except OSError as exc:
        raise OverlayError(f"cannot safely open path root: {absolute.anchor}") from exc
    try:
        for component in absolute.parts[1:-1]:
            next_fd = os.open(component, directory_flags, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
        return current_fd
    except OSError as exc:
        os.close(current_fd)
        raise OverlayError(
            f"path has a missing or symlinked parent: {absolute}"
        ) from exc


def _open_regular_nofollow(path: Path) -> int:
    """Open a regular input file using a no-follow parent walk and leaf open."""
    absolute = Path(os.path.abspath(path))
    parent_fd = _open_parent_dirfd(absolute)
    try:
        before = os.stat(absolute.name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        os.close(parent_fd)
        raise OverlayError(f"cannot safely stat regular input: {absolute}") from exc
    if not stat.S_ISREG(before.st_mode):
        os.close(parent_fd)
        raise OverlayError(f"input is not a regular file: {absolute}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(absolute.name, flags, dir_fd=parent_fd)
    except OSError as exc:
        os.close(parent_fd)
        raise OverlayError(f"cannot safely open regular input: {absolute}") from exc
    os.close(parent_fd)
    after = os.fstat(fd)
    identity_before = (before.st_dev, before.st_ino, stat.S_IFMT(before.st_mode))
    identity_after = (after.st_dev, after.st_ino, stat.S_IFMT(after.st_mode))
    if not stat.S_ISREG(after.st_mode) or identity_after != identity_before:
        os.close(fd)
        raise OverlayError(f"input changed while opening or is not regular: {absolute}")
    return fd
