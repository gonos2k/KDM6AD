"""Generate an isolated midpoint-plus-zero-qg-denominator-guard C arm.

The retained midpoint fallback is unchanged and remains unapproved. Only a
zero qg plus exact-zero same-process rate bypasses its density quotient; every
other case takes the original division. The canonical private source is read
only. No host defaults or operational files are written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from make_progb_policy_counterfactual import _midpoint_policy
from make_progb_validity_capture import MACRO, SOURCE_SHA, build, strip_capture

ZERO_QG_MACRO = "KDM6_PROGB_ZERO_QG_DIV_GUARD"
POLICY_MACRO = "KDM6_PROGB_POLICY_MIDPOINT"


GUARD_SITES = (
    {
        "label": "rhox_pgmlt",
        "consumer_id": 1418,
        "rate": "pgmlt(i,k)",
        "anchor": "              brs(i,k) = brs(i,k) + (pgmlt(i,k)/rhox(i,k))\n",
        # Keep the source store in the exact-zero arm. The stage-1 producer
        # guard makes this arm unreachable (qg starts positive and pgmlt=0
        # cannot reduce it to zero), but retaining the store avoids changing
        # control flow semantics if that producer contract ever changes.
        "zero_statement": "              brs(i,k) = brs(i,k) + (0.)\n",
    },
    {
        "label": "rhox_pgdep",
        "consumer_id": 2824,
        "rate": "pgdep(i,k)",
        "anchor": (
            "            brs(i,k) = max(brs(i,k)+(pgdep(i,k)/rhox(i,k)+biacr(i,k)           &\n"
            "                           +braci(i,k)+bsacr(i,k)+bracs(i,k)+bgaci(i,k)        &\n"
            "                           +baacw(i,k)+bgacr(i,k))*dtcld,0.)\n"
        ),
        "zero_statement": (
            "            brs(i,k) = max(brs(i,k)+(0.+biacr(i,k)         &\n"
            "                           +braci(i,k)+bsacr(i,k)+bracs(i,k)+bgaci(i,k)        &\n"
            "                           +baacw(i,k)+bgacr(i,k))*dtcld,0.)\n"
        ),
    },
    {
        "label": "rhox_pgevp",
        "consumer_id": 2915,
        "rate": "pgevp(i,k)",
        "anchor": "            bgevp(i,k)=pgevp(i,k)/rhox(i,k)\n",
        "zero_statement": "            bgevp(i,k)=0.\n",
    },
    {
        "label": "rhox_pgeml",
        "consumer_id": 2916,
        "rate": "pgeml(i,k)",
        "anchor": "            bgeml(i,k)=pgeml(i,k)/rhox(i,k)\n",
        "zero_statement": "            bgeml(i,k)=0.\n",
    },
)


STAGE_ANCHORS = {
    "stage1_before_mass": "              qrs(i,k,3) = qrs(i,k,3) + pgmlt(i,k)\n",
    "stage1_end": "            endif\n!---------------------------------------------------------------\n! pimlt:",
    "stage2_before_mass": "            qrs(i,k,3) = max(qrs(i,k,3)+(pgdep(i,k)+pgaut(i,k)                 &\n",
    "stage2_volume": "! S10_CZERO_END:rhox_pgdep\n",
    "stage2_heat": "            t(i,k) = t(i,k)-xlwork2/cpm(i,k)*dtcld\n",
    "stage3_before_volume": "            work2(i,k)=-(prevp(i,k)+psevp(i,k)+pgevp(i,k))\n",
    "stage3_before_mass": "            qrs(i,k,3) = max(qrs(i,k,3)+(pgacs(i,k)+pgevp(i,k)                 &\n",
    "stage3_volume": "            brs(i,k) = max(brs(i,k)+(bgevp(i,k)+bgeml(i,k))*dtcld,0.)\n",
    "stage3_heat": "            t(i,k) = t(i,k)-xlwork2/cpm(i,k)*dtcld\n",
    "melt_gate": "          if(t(i,k).gt.t0c) then\n",
    "phase_gate": "          if(supcol.lt.0.) then\n",
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected one source anchor, found {count}: {old[:90]!r}")
    return text.replace(old, new, 1)


def _capture_block(text: str, label: str, before: int) -> tuple[str, int, int]:
    begin = f"! S10_CAPTURE_BEGIN:{label}\n"
    end = f"! S10_CAPTURE_END:{label}\n"
    start = text.rfind(begin, 0, before)
    if start < 0:
        raise ValueError(f"missing S10RHO marker for {label}")
    stop = text.find(end, start)
    if stop < 0 or stop > before:
        raise ValueError(f"malformed S10RHO marker for {label}")
    stop += len(end)
    if text[stop:before].strip():
        raise ValueError(f"S10RHO marker for {label} is not adjacent to its consumer")
    return text[start:stop], start, stop


def _event(label: str, tag: str, id_values: Iterable[str], real_values: Iterable[str],
           id_width: int, real_width: int) -> str:
    ints = list(id_values)
    reals = list(real_values)
    if len(ints) != id_width or len(reals) > real_width:
        raise ValueError(f"{tag}/{label}: schema width mismatch")
    lines = ["         if (capture_enabled .and. capture_step.eq.1 .and. lat.eq.73 .and. &\n",
             "             (i.eq.113 .or. i.eq.115)) then\n",
             f"           write(*,'(A,{id_width}(1X,I0),{real_width}(1X,ES24.16E3))') '{tag}', &\n"]
    prefix = ["capture_step", "lat", "capture_last_site", "capture_last_loop",
              "capture_last_substep", "i", "k"]
    if ints[:7] != prefix:
        raise ValueError(f"{tag}/{label}: event key must begin with the fixed call key")
    items = ints + reals
    # Format the Fortran argument list with bounded source-line lengths.
    for index in range(0, len(items), 3):
        group = items[index:index + 3]
        comma = ", &\n" if index + 3 < len(items) else "\n"
        lines.append("             " + ", ".join(group) + comma)
    lines.extend(["         endif\n"])
    return f"! S10_CAPTURE_BEGIN:czero_{label}\n#ifdef {MACRO}\n" + "".join(lines) + \
        f"#endif\n! S10_CAPTURE_END:czero_{label}\n"


def _key_ints(extra: Iterable[str]) -> list[str]:
    return ["capture_step", "lat", "capture_last_site", "capture_last_loop",
            "capture_last_substep", "i", "k", *extra]


def _capture_if(label: str, real_vars: Iterable[tuple[str, str]]) -> str:
    # Assign only under the logger switch so control/capture share a binary but
    # control makes no extra state reads or stores.
    variables = list(real_vars)
    assign = "\n".join(f"           {name} = {source}" for name, source in variables)
    return (
        f"! S10_CAPTURE_BEGIN:czero_snapshot_{label}\n#ifdef {MACRO}\n"
        "       if (capture_enabled .and. capture_step.eq.1 .and. lat.eq.73 .and. &\n"
        "           (i.eq.113 .or. i.eq.115)) then\n"
        + assign + "\n"
        "       endif\n"
        f"#endif\n! S10_CAPTURE_END:czero_snapshot_{label}\n"
    )


def _guard_site(text: str, site: dict[str, str | int]) -> str:
    anchor = str(site["anchor"])
    anchor_at = text.index(anchor)
    event, start, stop = _capture_block(text, str(site["label"]), anchor_at)
    rate = str(site["rate"])
    consumer_id = int(site["consumer_id"])
    log = _event(
        f"zg_{consumer_id}", "S10ZG",
        _key_ints([str(consumer_id), "s10_guard_action"]),
        ["qrs(i,k,3)", rate, "rhox(i,k)"], 9, 3,
    )
    selected_call = (
        "         if (capture_enabled .and. capture_step.eq.1 .and. lat.eq.73 .and. &\n"
        "             (i.eq.113 .or. i.eq.115)) then\n"
        f"#ifndef {ZERO_QG_MACRO}\n"
        "           s10_guard_action = 1\n"
        "#endif\n"
        "           if (s10_guard_action.eq.1) then\n"
        f"             s10_guard_term = {rate}/rhox(i,k)\n"
        "           else\n"
        "             s10_guard_term = 0.\n"
        "           endif\n"
        "         endif\n"
    )
    action_capture = (
        f"! S10_CAPTURE_BEGIN:czero_action_{consumer_id}\n#ifdef {MACRO}\n"
        + selected_call + log
        + f"#endif\n! S10_CAPTURE_END:czero_action_{consumer_id}\n"
    )
    zero_statement = str(site["zero_statement"])
    zero_action_capture = (
        f"#ifdef {MACRO}\n"
        "          if (capture_enabled .and. capture_step.eq.1 .and. lat.eq.73 .and. &\n"
        "              (i.eq.113 .or. i.eq.115)) then\n"
        "            s10_guard_action = 0\n"
        "            s10_guard_term = 0.\n"
        "          endif\n"
        "#endif\n"
    )
    guarded = (
        f"#ifdef {ZERO_QG_MACRO}\n"
        f"        if (qrs(i,k,3).eq.0. .and. {rate}.eq.0.) then\n"
        + zero_action_capture
        + zero_statement
        + "        else\n"
        + event
        + zero_action_capture.replace("s10_guard_action = 0", "s10_guard_action = 1")
        + anchor
        + "        endif\n"
        + "#else\n"
        + event
        + anchor
        + "#endif\n"
        + action_capture
        + f"! S10_CZERO_END:{site['label']}\n"
    )
    return text[:start] + guarded + text[anchor_at + len(anchor):]


def _insert_before(text: str, anchor: str, payload: str, label: str) -> str:
    return _replace_once(text, anchor, payload + anchor, label)


def _insert_after(text: str, anchor: str, payload: str, label: str) -> str:
    return _replace_once(text, anchor, anchor + payload, label)


def _insert_after_nth(text: str, anchor: str, payload: str,
                      label: str, occurrence: int) -> str:
    positions = []
    position = 0
    while True:
        position = text.find(anchor, position)
        if position < 0:
            break
        positions.append(position)
        position += len(anchor)
    if occurrence >= len(positions):
        raise ValueError(f"{label}: expected occurrence {occurrence + 1}, found {len(positions)}")
    position = positions[occurrence] + len(anchor)
    return text[:position] + payload + text[position:]


def _ledger_declarations(text: str) -> str:
    anchor = "! S10_CAPTURE_BEGIN:kdm62d_capture_arrays\n"
    declarations = (
        f"! S10_CAPTURE_BEGIN:czero_ledger_declarations\n#ifdef {MACRO}\n"
        "   real :: s10_guard_term, s10_qg_before, s10_qrain_before\n"
        "   real :: s10_brs_before, s10_t_before\n"
        "   integer :: s10_guard_action\n"
        f"#endif\n! S10_CAPTURE_END:czero_ledger_declarations\n"
    )
    return _replace_once(text, anchor, declarations + anchor, "C-arm guard/ledger declarations")


def _stage_snapshot(text: str, anchor: str, label: str,
                    qg_before: str = "qrs(i,k,3)") -> str:
    return _insert_before(text, anchor, _capture_if(label, [
        ("s10_qg_before", qg_before),
        ("s10_brs_before", "brs(i,k)"),
        ("s10_t_before", "t(i,k)"),
        ("s10_qrain_before", "qrs(i,k,1)"),
    ]), label)


def _budget_record(tag: str, label: str, stage: int,
                   values: Iterable[str], width: int) -> str:
    return _event(label, tag, _key_ints([str(stage)]), list(values), 8, width)


def add_zero_qg_guard(text: str) -> tuple[str, dict[str, Any]]:
    """Add only the exact-zero qg/rate guard plus macro-only selected ledgers."""
    rendered = _ledger_declarations(text)
    for site in GUARD_SITES:
        rendered = _guard_site(rendered, site)

    rendered = _stage_snapshot(rendered, STAGE_ANCHORS["stage1_before_mass"],
                               "stage1_snapshot")
    stage1_mass = _budget_record("S10MASS", "stage1_mass", 1,
        ("s10_qg_before", "pgmlt(i,k)", "qrs(i,k,3)",
         "s10_qrain_before", "qrs(i,k,1)"), 5)
    stage1_vol = _budget_record("S10VOLUME", "stage1_volume", 1,
        ("qrs(i,k,3)", "pgmlt(i,k)", "rhox(i,k)", "s10_guard_term",
         "s10_brs_before", "brs(i,k)"), 6)
    stage1_heat = _budget_record("S10HEAT", "stage1_heat", 1,
        ("s10_qg_before", "pgmlt(i,k)", "qrs(i,k,3)", "xlf", "cpm(i,k)",
         "s10_t_before", "t(i,k)"), 7)
    end1 = "            endif\n!---------------------------------------------------------------\n! pimlt:"
    rendered = _replace_once(rendered, end1,
        stage1_mass + stage1_vol + stage1_heat + end1,
        "stage1 qg/volume/heat ledger")

    rendered = _stage_snapshot(rendered, STAGE_ANCHORS["stage2_before_mass"],
                               "stage2_snapshot")
    stage2_mass_anchor = (
        "                           +pgacr(i,k)+pgacs(i,k))*dtcld,0.)\n")
    stage2_mass = _budget_record("S10MASS", "stage2_mass", 2,
        ("s10_qg_before", "pgdep(i,k)", "pgaut(i,k)", "piacr(i,k)", "delta3",
         "praci(i,k)", "psacr(i,k)", "delta2", "pracs(i,k)", "pgaci(i,k)",
         "paacw(i,k)", "pgacr(i,k)", "pgacs(i,k)", "dtcld", "qrs(i,k,3)"), 15)
    rendered = _insert_after(rendered, stage2_mass_anchor, stage2_mass,
                             "stage2 source-ordered qg mass ledger")

    stage2_volume = _budget_record("S10VOLUME", "stage2_volume", 2,
        ("qrs(i,k,3)", "s10_brs_before", "pgdep(i,k)", "rhox(i,k)",
         "s10_guard_term", "biacr(i,k)", "braci(i,k)", "bsacr(i,k)",
         "bracs(i,k)", "bgaci(i,k)", "baacw(i,k)", "bgacr(i,k)",
         "dtcld", "brs(i,k)"), 14)
    rendered = _insert_after(rendered, STAGE_ANCHORS["stage2_volume"], stage2_volume,
                             "stage2 volume ledger")

    rendered = _stage_snapshot(rendered, STAGE_ANCHORS["stage3_before_volume"],
                               "stage3_snapshot")
    stage3_mass_anchor = "+pgeml(i,k))*dtcld,0.)\n"
    stage3_mass = _budget_record("S10MASS", "stage3_mass", 3,
        ("s10_qg_before", "pgacs(i,k)", "pgevp(i,k)", "pgeml(i,k)",
         "dtcld", "qrs(i,k,3)"), 6)
    rendered = _insert_after(rendered, stage3_mass_anchor, stage3_mass,
                             "stage3 source-ordered qg mass ledger")
    stage3_vol = _budget_record("S10VOLUME", "stage3_volume", 3,
        ("s10_qg_before", "qrs(i,k,3)", "pgevp(i,k)", "rhox(i,k)", "bgevp(i,k)",
         "pgeml(i,k)", "rhox(i,k)", "bgeml(i,k)", "dtcld",
         "s10_brs_before", "brs(i,k)"), 11)
    rendered = _insert_after(rendered, STAGE_ANCHORS["stage3_volume"], stage3_vol,
                             "stage3 volume ledger")

    # Stage 1 heat is logged with the end-of-process record already inserted.
    # Stage 2/3 heat operands are recorded immediately after their actual T stores.
    stage2_heat = _budget_record("S10HEAT", "stage2_heat", 2,
        ("psdep(i,k)", "pgdep(i,k)", "pidep(i,k)", "pinud(i,k)", "prevp(i,k)",
         "piacr(i,k)", "paacw(i,k)", "pmulcs(i,k)", "pmulcg(i,k)",
         "pmulrs(i,k)", "pmulrg(i,k)", "piacw(i,k)", "pgacr(i,k)",
         "psacr(i,k)", "xls", "xl(i,k)", "xlf", "xlwork2", "dtcld",
         "cpm(i,k)", "s10_t_before", "t(i,k)"), 22)
    rendered = _insert_after_nth(rendered, STAGE_ANCHORS["stage2_heat"], stage2_heat,
                                 "stage2 latent/heat operands", 0)
    stage3_heat = _budget_record("S10HEAT", "stage3_heat", 3,
        ("prevp(i,k)", "psevp(i,k)", "pgevp(i,k)", "pseml(i,k)", "pgeml(i,k)",
         "xl(i,k)", "xlf", "xlwork2", "dtcld", "cpm(i,k)",
         "s10_t_before", "t(i,k)"), 12)
    rendered = _insert_after_nth(rendered, STAGE_ANCHORS["stage3_heat"], stage3_heat,
                                 "stage3 latent/heat operands", 1)

    melt_gate = _event("melt_gate", "S10MELTGATE",
        _key_ints(["merge(1,0,t(i,k).gt.t0c)"]),
        ["qrs(i,k,3)", "t(i,k)", "t0c"], 8, 3)
    rendered = _insert_before(rendered, STAGE_ANCHORS["melt_gate"], melt_gate,
                              "independent melt-gate census")
    phase_gate = _event("phase_gate", "S10PHASE",
        _key_ints(["merge(1,0,supcol.lt.0.)"]),
        ["supcol", "qrs(i,k,3)", "dtcld"], 8, 3)
    rendered = _insert_before(rendered, STAGE_ANCHORS["phase_gate"], phase_gate,
                              "independent cold/warm phase census")

    return rendered, {
        "schema": "s10-czeroqg-guard-v1",
        "zero_guard_macro": ZERO_QG_MACRO,
        "positive_trace_policy": "unchanged B midpoint rho_mid=400 kg m-3; unapproved",
        "guard_predicate": "qrs(i,k,3)==0 AND same process rate==0, in binary32",
        "guard_action_zero": "set only the zero quotient to 0; keep other volume additions",
        "guard_action_one": "execute the exact original inline process_rate/rhox statement, including nonzero rate at qg==0",
        "diagnostic_quotient": "capture-only S10 value; never feeds the physical state update",
        "altered_physical_terms": ["exact-zero qg / exact-zero numerator density quotients only"],
        "captured_ledgers": ["S10ZG", "S10MASS", "S10VOLUME", "S10HEAT"],
        "not_approved": True,
    }


def strip_macro_else(text: str, macro: str) -> str:
    """Remove each #ifdef MACRO block while retaining its #else branch."""
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    start_token = f"#ifdef {macro}"
    while i < len(lines):
        if lines[i].strip() != start_token:
            out.append(lines[i])
            i += 1
            continue
        depth = 1
        branch = 0
        has_else = False
        true_lines: list[str] = []
        false_lines: list[str] = []
        i += 1
        while i < len(lines) and depth:
            stripped = lines[i].strip()
            if stripped.startswith(("#ifdef ", "#ifndef ", "#if ")):
                depth += 1
                (true_lines if branch == 0 else false_lines).append(lines[i])
            elif stripped.startswith("#endif"):
                depth -= 1
                if depth:
                    (true_lines if branch == 0 else false_lines).append(lines[i])
            elif stripped == "#else" and depth == 1:
                branch = 1
                has_else = True
            else:
                (true_lines if branch == 0 else false_lines).append(lines[i])
            i += 1
        if depth:
            raise ValueError(f"unterminated {macro} block")
        if has_else:
            out.extend(false_lines)
    result = "".join(out)
    if f"#ifdef {macro}" in result:
        raise ValueError(f"unstripped {macro} directive remains")
    return result


def strip_czero_capture(text: str) -> str:
    """Remove only C-arm ledger markers, leaving the shared S10 B capture intact."""
    while "! S10_CAPTURE_BEGIN:czero_" in text:
        start = text.index("! S10_CAPTURE_BEGIN:czero_")
        line_end = text.index("\n", start) + 1
        label = text[start + len("! S10_CAPTURE_BEGIN:"):line_end].strip()
        end_marker = f"! S10_CAPTURE_END:{label}\n"
        end = text.find(end_marker, line_end)
        if end < 0:
            raise ValueError(f"missing C-arm capture end marker: {label}")
        block = text[line_end:end]
        if not block.startswith(f"#ifdef {MACRO}\n") or block.count("#else\n"):
            raise ValueError(f"malformed C-arm capture marker: {label}")
        text = text[:start] + text[end + len(end_marker):]
    return "".join(line for line in text.splitlines(keepends=True)
                   if not line.startswith("! S10_CZERO_END:"))


def build_c_overlay(source: Path, output: Path, manifest_path: Path,
                    variant: str) -> dict[str, Any]:
    if variant not in SOURCE_SHA:
        raise ValueError(f"unsupported KDM6 source variant: {variant}")
    raw = source.read_bytes()
    canonical_sha = _sha(raw)
    if canonical_sha != SOURCE_SHA[variant]:
        raise ValueError(f"{variant} canonical source SHA mismatch: {canonical_sha}")
    base_path = output.with_name(output.stem + "_s10_base.F")
    base_manifest = manifest_path.with_name(manifest_path.stem + "_s10_base.json")
    build(source, base_path, base_manifest, variant)
    capture_base = base_path.read_text(encoding="utf-8")
    b_source, policy = _midpoint_policy(capture_base)
    c_source, guard = add_zero_qg_guard(b_source)
    if strip_capture(capture_base) != raw.decode("utf-8"):
        raise ValueError("S10 instrumentation base does not strip to canonical source")
    macro_off = strip_czero_capture(strip_macro_else(c_source, ZERO_QG_MACRO))
    if macro_off != b_source:
        raise ValueError("C guard macro-off source differs from B midpoint source")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(c_source, encoding="utf-8")
    record = {
        "schema": "s10-czeroqg-source-v1",
        "variant": variant,
        "policy": "midpoint_plus_exact_zero_qg_rate_guard",
        "approved_operational_policy": False,
        "canonical_source_path": str(source.resolve()),
        "canonical_source_sha256": canonical_sha,
        "capture_base_sha256": _sha(capture_base.encode()),
        "b_midpoint_source_sha256": _sha(b_source.encode()),
        "c_guard_source_path": str(output.resolve()),
        "c_guard_source_sha256": _sha(c_source.encode()),
        "zero_guard_macro": ZERO_QG_MACRO,
        "midpoint_policy_macro": POLICY_MACRO,
        "macro_off_matches_b_midpoint": True,
        "s10_capture_strips_to_canonical": strip_capture(capture_base) == raw.decode("utf-8"),
        "guard": guard,
        "positive_trace_policy": policy["policy"],
        "positive_trace_policy_approved": False,
        "native_status": "WAITING_FOR_S15_NATIVE_SLOT",
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=("mp37", "mp237"), required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_c_overlay(args.source, args.output, args.manifest, args.variant),
                     indent=2))


if __name__ == "__main__":
    main()
