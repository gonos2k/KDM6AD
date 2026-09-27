"""Generate a hash-pinned, macro-gated S15 Fortran instrumentation shadow.

The generator never edits the private host tree. Its source snippets are added
to a disposable copy and disappear when KDM6AD_S15_FACE_CAPTURE is undefined.
"""

from __future__ import annotations

import hashlib
import json
import re
import difflib
from pathlib import Path
from typing import Any

import s15_face_cause_probe as replay
from s15_face_cause_probe import SCHEDULE, _projection


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
    lines: list[str], proc_name: str, names: tuple[str, ...]
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
        "   INTEGER, OPTIONAL, INTENT(IN) :: " + ", ".join(names),
        "#endif",
    ]
    return [*lines[: implicit + 1], *decl, *lines[implicit + 1 :]]


def _owner_call_args() -> list[str]:
    return [
        "s15_step=grid%itimestep",
        "s15_rk=rk_step",
        "s15_owner=MERGE(5,0,is==P_QIB)",
        "s15_tile=ij",
    ]


def _patch_solve(text: str) -> str:
    lines = text.splitlines()
    anchors = find_dual_owner_calls(text)
    # Locate each loop again, then re-find its call after each prior insertion.
    for loop_label, call_name in (PRODUCER_ANCHOR, CONSUMER_ANCHOR):
        loop_start_pat = re.compile(rf"^\s*{loop_label}\s*:\s*DO\b", re.I)
        loop_end_pat = re.compile(rf"^\s*ENDDO\s+{loop_label}\b", re.I)
        start = next(i for i, line in enumerate(lines) if loop_start_pat.search(line))
        end = next(i for i, line in enumerate(lines) if loop_end_pat.search(line))
        call_start, call_end = _call_span(lines, start, end, call_name)
        lines = _append_actuals(lines, call_start, call_end, _owner_call_args())
    if not anchors["producer"] or not anchors["consumer"]:
        raise OverlayError("dual owner-call regression anchors are empty")
    return "\n".join(lines) + "\n"


def _patch_module_em(text: str) -> str:
    lines = text.splitlines()
    # Producer context: rk_scalar_tend dispatches to ordinary or PD advection.
    for proc_name in ("rk_scalar_tend", "rk_update_scalar"):
        lines = _extend_signature(lines, proc_name, list(CONTEXT_NAMES))
        lines = _add_optional_declarations(lines, proc_name, CONTEXT_NAMES)

    start, end = _find_proc(lines, "rk_scalar_tend")
    for call_name, branch in (("advect_scalar_pd", 2), ("advect_scalar", 1)):
        cstart, cend = _call_span(lines, start, end, call_name)
        actuals = [f"{name}={name}" for name in CONTEXT_NAMES] + [
            f"s15_branch={branch}"
        ]
        lines = _append_actuals(lines, cstart, cend, actuals)
        start, end = _find_proc(lines, "rk_scalar_tend")
    lines = _patch_rk_store_taps(lines)
    lines = _append_module_em_helpers(lines)
    return "\n".join(lines) + "\n"


def _patch_advect(text: str) -> str:
    lines = text.splitlines()
    for proc_name in ("advect_scalar", "advect_scalar_pd"):
        lines = _extend_signature(lines, proc_name, [*CONTEXT_NAMES, "s15_branch"])
        lines = _add_optional_declarations(
            lines, proc_name, (*CONTEXT_NAMES, "s15_branch")
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
        lines = _tap_advection_procedure(lines, proc_name)
    lines = _append_advect_helpers(lines)
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
    source_root: Path, shadow_root: Path, public_root: Path
) -> dict[str, Any]:
    sources = _source_bytes(source_root)
    projection = _projection(public_root)
    dual_calls = find_dual_owner_calls(sources["dyn_em/solve_em.F"].decode())
    if shadow_root.exists():
        raise OverlayError("overlay shadow directory must be new")
    patched = {}
    for relative, patcher in (
        ("dyn_em/solve_em.F", _patch_solve),
        ("dyn_em/module_em.F", _patch_module_em),
        ("dyn_em/module_advect_em.F", _patch_advect),
    ):
        original = sources[relative].decode()
        patched[relative] = _restore_cpp_line_numbers(
            original, patcher(original), relative
        )
    shadow_root.mkdir(parents=True)
    for relative, output in patched.items():
        path = shadow_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output, encoding="utf-8", newline="")
    manifest = {
        "schema": "KDM6AD-S15-FACE-FORTRAN-OVERLAY-v1",
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
        "schedule": [list(key) for key in SCHEDULE],
        "coordinates": [list(x) for x in projection],
        "status": "macro-gated producer/consumer and directional/limiter taps; compile-only pending",
    }
    (shadow_root / "s15_face_overlay_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


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


def _append_module_em_helpers(lines: list[str]) -> list[str]:
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
            "end select",
            "END SUBROUTINE s15_rk_match",
            "SUBROUTINE s15_emit_rk(step,rk,owner,tile,its,ite,jts,jte,i,j,k,advect,msfty,sc_tend,tendency,reference,dt,c1,c2,muold,munew,after)",
            "INTEGER, INTENT(IN) :: step,rk,owner,tile,its,ite,jts,jte,i,j,k",
            "REAL, INTENT(IN) :: advect,msfty,sc_tend,tendency,reference,dt,c1,c2,muold,munew,after",
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


def _tap_advection_procedure(lines: list[str], proc_name: str) -> list[str]:
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
        lines = _tap_pd_limiter(lines)
    return lines


def _tap_pd_limiter(lines: list[str]) -> list[str]:
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
    lines[endif + 1 : endif + 1] = post
    return lines


def _append_advect_helpers(lines: list[str]) -> list[str]:
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
            "end select",
            "END SUBROUTINE s15_face_match",
            "SUBROUTINE s15_emit_axis(step,rk,owner,tile,its,ite,jts,jte,i,j,k,branch,axis,fm,fp,lm,lp,metric,spacing,before,after)",
            "INTEGER, INTENT(IN) :: step,rk,owner,tile,its,ite,jts,jte,i,j,k,branch,axis",
            "REAL, INTENT(IN) :: fm,fp,lm,lp,metric,spacing,before,after",
            "WRITE(6,'(A,1X,11(I0,1X),2(I0,1X),8(Z8.8,1X))') 'S15AX', &",
            " step,rk,owner,tile,its,ite,jts,jte,i,j,k,axis,branch, &",
            " transfer(fm,0),transfer(fp,0),transfer(lm,0),transfer(lp,0), &",
            " transfer(metric,0),transfer(spacing,0),transfer(before,0),transfer(after,0)",
            "END SUBROUTINE s15_emit_axis",
            "SUBROUTINE s15_emit_pd(step,rk,owner,tile,its,ite,jts,jte,i,j,k,active,fluxout,available,eps,scale,low,pre,post)",
            "INTEGER, INTENT(IN) :: step,rk,owner,tile,its,ite,jts,jte,i,j,k,active",
            "REAL, INTENT(IN) :: fluxout,available,eps,scale,low(6),pre(6),post(6)",
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
    text: str, public_root: Path, config: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse the bounded raw-word Fortran stream and validate all six joins."""
    coordinates = _projection(public_root)
    schedule_to_slot = {
        key: (index % 2 + 1, coordinates[index]) for index, key in enumerate(SCHEDULE)
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
        schedule_key = (step, rk, owner, ti0, ti1, tj0, tj1)
        if schedule_key not in schedule_to_slot:
            raise OverlayError(
                f"{label} key is outside the independent six-slot schedule"
            )
        expected_tile, coordinate = schedule_to_slot[schedule_key]
        if tile != expected_tile or (i, j, k) != coordinate:
            raise OverlayError(
                f"{label} tile slot or coordinate differs from the pinned projection"
            )
        row = dict(
            zip(replay.KEY_FIELDS, (step, rk, owner, ti0, ti1, tj0, tj1, i, j, k))
        )
        return event_key, row

    for line_no, raw in enumerate(text.splitlines(), 1):
        tokens = raw.split()
        if not tokens or not tokens[0].startswith("S15"):
            continue
        tag = tokens[0]
        if tag not in {"S15AX", "S15PD", "S15RK"}:
            raise OverlayError(f"line {line_no}: unknown S15 record tag {tag}")
        if tag == "S15AX":
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
        elif tag == "S15PD":
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

    if len(axes) != 6 or len(consumers) != 6:
        raise OverlayError(
            "Fortran stream must contain exactly six producer keys and six consumers"
        )
    if set(axes) != set(consumers):
        raise OverlayError("producer and consumer full tile/cell keys differ")
    expected_pd_keys = {key for key in axes if key[1] == 3}
    if set(pds) != expected_pd_keys:
        raise OverlayError(
            "exactly the two RK3 selected PD limiter records are required"
        )

    producers: list[dict[str, Any]] = []
    for event_key in sorted(axes):
        by_axis = axes[event_key]
        if set(by_axis) != set(replay.AXES):
            raise OverlayError(
                "each selected producer must contain exactly Y/X/Z records"
            )
        schedule_key = event_key[:3] + event_key[4:8]
        expected_slot = schedule_to_slot[schedule_key][0]
        identity_row = {
            name: value
            for name, value in by_axis[replay.ORDINARY_ORDER[0]].items()
            if name in replay.KEY_FIELDS
        }
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
                        a: axis_rows[a]["face_fluxes"] for a in replay.AXES
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

    replay.validate_capture(producers, list(consumers.values()), public_root, config)
    return producers, list(consumers.values())
