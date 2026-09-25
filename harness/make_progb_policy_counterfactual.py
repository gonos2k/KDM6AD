"""Create isolated OUT-retention and explicit-fallback ProgB shadow sources.

The two variants are research counterfactuals, not approved operational policy.
Source paths are read-only; all overlays and build products belong in an ignored
scratch directory. Native execution is intentionally handled by the S14 queue.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from make_progb_validity_capture import MACRO, SOURCE_SHA, build, strip_capture

RHO_MID = 400.0
POLICY_MACRO = "KDM6_PROGB_POLICY_MIDPOINT"
OUTPUT_INIT_LINES = (
    "          rhox(i,k) = 0.\n"
    "          cmg(i,k) = 0.\n"
    "          pidn0g(i,k) = 0.\n"
    "          avtg(i,k) = 0.\n"
    "          pvtg(i,k) = 0.\n"
    "          precg2(i,k) = 0.\n"
    "          bvtg(i,k) = 0.\n"
    "          bvtg1(i,k) = 0.\n"
    "          bvtg2(i,k) = 0.\n"
    "          bvtg3(i,k) = 0.\n"
    "          bvtg4(i,k) = 0.\n"
    "          rslopegbmax(i,k) = 0.\n"
    "          g1pbg(i,k) = 0.\n"
    "          g3pbg(i,k) = 0.\n"
    "          g4pbg(i,k) = 0.\n"
    "          g5pbgo2(i,k) = 0.\n"
    "          g1pdgbgmg(i,k) = 0.\n"
    "          dgbgmug1(i,k) = 0.\n"
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def _retention_policy(text: str) -> tuple[str, dict[str, Any]]:
    start = text.index("SUBROUTINE ProgB_param(")
    end = text.index("END subroutine ProgB_param", start)
    head, proc, tail = text[:start], text[start:end], text[end:]
    declarations = (
        "REAL, DIMENSION( its:ite , kts:kte),INTENT(OUT)   :: rhox",
        "REAL, DIMENSION( its:ite , kts:kte),INTENT(OUT)   :: cmg,pidn0g",
        "REAL, DIMENSION( its:ite , kts:kte),INTENT(OUT)   :: avtg,pvtg,precg2",
        "REAL, DIMENSION( its:ite , kts:kte),INTENT(OUT)   :: bvtg,bvtg1,bvtg2,bvtg3,bvtg4,rslopegbmax,&",
    )
    for declaration in declarations:
        if proc.count(declaration) != 1:
            raise ValueError(f"retention policy declaration anchor missing: {declaration}")
        proc = proc.replace(declaration, declaration.replace("INTENT(OUT)", "INTENT(INOUT)"), 1)
    if any("INTENT(OUT)" in line and any(name in line for name in
                                           (":: rhox", ":: cmg,pidn0g", ":: avtg,pvtg",
                                            ":: bvtg,bvtg1"))
           for line in proc.splitlines()):
        raise ValueError("retention policy left a physical OUT group in ProgB_param")
    capture_decl = "  LOGICAL :: capture_active,capture_rhox_written,capture_cmg_written, &\n"
    proc = _replace_once(
        proc, capture_decl,
        "  REAL :: retention_brs_before,retention_delta_brs\n" + capture_decl,
        "retention volume-ledger declaration",
    )
    capture_seed_anchor = "          capture_active = .false.\n"
    proc = _replace_once(
        proc, capture_seed_anchor,
        "          retention_brs_before = brs(i,k)\n"
        "          retention_delta_brs = 0.\n" + capture_seed_anchor,
        "retention volume-ledger seed",
    )
    active_brs_anchor = "        brs(i,k)  = qrs(i,k,3)/rhox(i,k)\n"
    active_log = (
        "#ifdef " + MACRO + "\n"
        "        retention_delta_brs = brs(i,k)-retention_brs_before\n"
        "        if (capture_enabled .and. capture_step.eq.1 .and. &\n"
        "            ((capture_lat.eq.73 .and. (i.eq.113 .or. i.eq.115)) .or. &\n"
        "             (capture_lat.eq.2 .and. i.eq.142 .and. k.eq.17))) then\n"
        "          write(*,'(A,8(1X,I0),5(1X,ES24.16E3))') 'S10VOL', &\n"
        "            capture_step,capture_lat,capture_site,capture_loop,capture_substep, &\n"
        "            i,k,0,qrs(i,k,3),retention_brs_before,brs(i,k), &\n"
        "            retention_delta_brs,rhox(i,k)\n"
        "        endif\n"
        "#endif\n"
    )
    proc = _replace_once(proc, active_brs_anchor,
                         active_brs_anchor + active_log,
                         "retention active-volume log")
    cmg_event = "! S10_CAPTURE_BEGIN:progb_cmg_read\n"
    inactive_log = (
        "#ifdef " + MACRO + "\n"
        "       if (capture_enabled .and. capture_step.eq.1 .and. .not.capture_active .and. &\n"
        "           ((capture_lat.eq.73 .and. (i.eq.113 .or. i.eq.115)) .or. &\n"
        "            (capture_lat.eq.2 .and. i.eq.142 .and. k.eq.17))) then\n"
        "         retention_delta_brs = brs(i,k)-retention_brs_before\n"
        "         write(*,'(A,8(1X,I0),5(1X,ES24.16E3))') 'S10VOL', &\n"
        "           capture_step,capture_lat,capture_site,capture_loop,capture_substep, &\n"
        "           i,k,3,qrs(i,k,3),retention_brs_before,brs(i,k), &\n"
        "           retention_delta_brs,rhox(i,k)\n"
        "       endif\n"
        "#endif\n"
    )
    proc = _replace_once(proc, cmg_event, inactive_log + cmg_event,
                         "retention inactive-volume log")
    return head + proc + tail, {
        "policy": "initialized_value_retention",
        "fortran_change": "ProgB_param output dummies OUT -> INOUT",
        "seed": "kdm62d sets every output group to zero at each outer loop before ProgB calls",
        "inactive_rule": "retain the latest current-loop value; initial state is the explicit loop zero",
        "volume_record": "S10VOL action 0 logs active density projection; action 3 logs retained inactive state with zero direct ProgB volume change",
        "changes_qg_or_brs_inside_ProgB": False,
        "caveat": "defined retention can be zero or stale; it is not asserted physically valid",
    }


def _midpoint_policy(text: str) -> tuple[str, dict[str, Any]]:
    proc_start = text.index("SUBROUTINE ProgB_param(")
    proc_end = text.index("END subroutine ProgB_param", proc_start)
    proc = text[proc_start:proc_end]
    decl_old = "  LOGICAL :: capture_active,capture_rhox_written,capture_cmg_written, &\n"
    decl_new = (
        "#ifdef " + POLICY_MACRO + "\n"
        "  REAL :: policy_brs_before,policy_delta_brs\n"
        "  LOGICAL :: policy_gate_active\n"
        "#endif\n"
        + decl_old
    )
    proc = _replace_once(proc, decl_old, decl_new, "fallback volume correction declaration")

    cell_old = "        do i = its, ite\n#ifdef " + MACRO + "\n          capture_active = .false.\n"
    cell_new = (
        "        do i = its, ite\n"
        "#ifdef " + POLICY_MACRO + "\n"
        "          policy_brs_before = brs(i,k)\n"
        "          policy_delta_brs = 0.\n"
        "          policy_gate_active = qrs(i,k,3).gt.qcrmin .or. brs(i,k).gt.brs_min\n"
        "#endif\n"
        "#ifdef " + POLICY_MACRO + "\n"
        + OUTPUT_INIT_LINES
        + "#endif\n"
        "#ifdef " + MACRO + "\n          capture_active = .false.\n"
    )
    proc = _replace_once(proc, cell_old, cell_new, "per-call output zero seed")

    cell_flag_begin = proc.index("! S10_CAPTURE_BEGIN:progb_cell_flags")
    cell_flag_end = proc.index("! S10_CAPTURE_END:progb_cell_flags", cell_flag_begin)
    cell_flag_block = proc[cell_flag_begin:cell_flag_end]
    gate_expr = "if (qrs(i,k,3).gt. qcrmin .or. brs(i,k).gt. brs_min) then"
    if cell_flag_block.count(gate_expr) != 2:
        raise ValueError("expected active and base-arm ProgB gate anchors")
    cell_flag_block = cell_flag_block.replace(gate_expr, "if (policy_gate_active) then", 1)
    proc = proc[:cell_flag_begin] + cell_flag_block + proc[cell_flag_end:]

    flags_old = (
        "          capture_rhox_written = .false.\n"
        "          capture_cmg_written = .false.\n"
        "          capture_pidn0g_written = .false.\n"
        "          capture_params_written = .false.\n"
        "          if (k.eq.kts .and. i.eq.its) capture_trace_seen = .false.\n"
        "          capture_rhox_assigned(i,k) = .false.\n"
        "          capture_cmg_assigned(i,k) = .false.\n"
        "          capture_pidn0g_assigned(i,k) = .false.\n"
        "          capture_params_assigned(i,k) = .false.\n"
    )
    flags_new = (
        "#ifdef " + POLICY_MACRO + "\n"
        "          capture_rhox_written = .true.\n"
        "          capture_cmg_written = .true.\n"
        "          capture_pidn0g_written = .true.\n"
        "          capture_params_written = .true.\n"
        "          capture_rhox_assigned(i,k) = .true.\n"
        "          capture_cmg_assigned(i,k) = .true.\n"
        "          capture_pidn0g_assigned(i,k) = .true.\n"
        "          capture_params_assigned(i,k) = .true.\n"
        "#else\n"
        "          capture_rhox_written = .false.\n"
        "          capture_cmg_written = .false.\n"
        "          capture_pidn0g_written = .false.\n"
        "          capture_params_written = .false.\n"
        "          capture_rhox_assigned(i,k) = .false.\n"
        "          capture_cmg_assigned(i,k) = .false.\n"
        "          capture_pidn0g_assigned(i,k) = .false.\n"
        "          capture_params_assigned(i,k) = .false.\n"
        "#endif\n"
        "          if (k.eq.kts .and. i.eq.its) capture_trace_seen = .false.\n"
    )
    proc = _replace_once(proc, flags_old, flags_new, "fallback validity bits")

    active_volume_log = (
        "#ifdef " + MACRO + "\n"
        "        policy_delta_brs = brs(i,k)-policy_brs_before\n"
        "        if (capture_enabled .and. capture_step.eq.1 .and. &\n"
        "            ((capture_lat.eq.73 .and. (i.eq.113 .or. i.eq.115)) .or. &\n"
        "             (capture_lat.eq.2 .and. i.eq.142 .and. k.eq.17))) then\n"
        "          write(*,'(A,8(1X,I0),5(1X,ES24.16E3))') 'S10VOL', &\n"
        "            capture_step,capture_lat,capture_site,capture_loop,capture_substep, &\n"
        "            i,k,0,qrs(i,k,3),policy_brs_before,brs(i,k), &\n"
        "            policy_delta_brs,rhox(i,k)\n"
        "        endif\n"
        "#endif\n"
    )
    active_volume_anchor = "        brs(i,k)  = qrs(i,k,3)/rhox(i,k)\n"
    proc = _replace_once(proc, active_volume_anchor,
                         active_volume_anchor + active_volume_log,
                         "active density volume correction log")

    fallback = (
        "#ifdef " + POLICY_MACRO + "\n"
        "        if (.not.policy_gate_active) then\n"
        "          if (qrs(i,k,3).gt.0.) then\n"
        "            rhox(i,k) = rho_mid\n"
        "            brs(i,k) = qrs(i,k,3)/rho_mid\n"
        "            cmg(i,k) = pi*rho_mid/6\n"
        "            pidn0g(i,k) = cmg(i,k)*n0g*g1pdgmg/g1pmg\n"
        "            policy_delta_brs = brs(i,k)-policy_brs_before\n"
        "          else\n"
        "            rhox(i,k) = 0.\n"
        "            cmg(i,k) = 0.\n"
        "            pidn0g(i,k) = 0.\n"
        "            brs(i,k) = 0.\n"
        "            policy_delta_brs = brs(i,k)-policy_brs_before\n"
        "          endif\n"
        "#ifdef " + MACRO + "\n"
        "          if (capture_enabled .and. capture_step.eq.1 .and. &\n"
        "              ((capture_lat.eq.73 .and. (i.eq.113 .or. i.eq.115)) .or. &\n"
        "               (capture_lat.eq.2 .and. i.eq.142 .and. k.eq.17))) then\n"
        "            write(*,'(A,8(1X,I0),5(1X,ES24.16E3))') 'S10VOL', &\n"
        "              capture_step,capture_lat,capture_site,capture_loop,capture_substep, &\n"
        "              i,k,merge(1,2,qrs(i,k,3).gt.0.),qrs(i,k,3), &\n"
        "              policy_brs_before,brs(i,k),policy_delta_brs,rhox(i,k)\n"
        "          endif\n"
        "#endif\n"
        "        endif\n"
        "#endif\n"
    )
    fallback_anchor = "! S10_CAPTURE_BEGIN:progb_cmg_read\n"
    proc = _replace_once(proc, fallback_anchor, fallback + fallback_anchor,
                         "midpoint fallback branch")
    return text[:proc_start] + proc + text[proc_end:], {
        "policy": "per_call_rho_mid_with_brs_projection",
        "rho_mid_kg_m3": RHO_MID,
        "inactive_gate": "qg<=qcrmin and brs<=brs_min, evaluated from the pre-call state",
        "inactive_positive_trace": "rhox=rho_mid; brs=qg/rho_mid; build the rho_mid table bundle",
        "inactive_zero_qg": "zero local output bundle and set brs=0",
        "volume_record": "S10VOL action 0 logs active density projection; 1 logs positive-trace rho_mid projection; 2 logs zero-qg volume cleanup",
        "state_change": "delta_brs is an explicit volume-state correction; qg mass is unchanged in ProgB_param",
        "active_branch_changed": False,
        "not_approved": True,
    }


def build_policy_overlay(source: Path, output: Path, manifest_path: Path,
                         variant: str, policy: str) -> dict[str, Any]:
    if variant not in SOURCE_SHA:
        raise ValueError(f"unsupported source variant: {variant}")
    if policy not in {"retention", "midpoint"}:
        raise ValueError(f"unsupported policy: {policy}")
    raw = source.read_bytes()
    source_sha = _sha(raw)
    if source_sha != SOURCE_SHA[variant]:
        raise ValueError(f"{variant} canonical source SHA mismatch: {source_sha}")
    base_path = output.with_name(output.stem + "_s10_base.F")
    base_manifest = manifest_path.with_name(manifest_path.stem + "_s10_base.json")
    build(source, base_path, base_manifest, variant)
    base = base_path.read_text(encoding="utf-8")
    if policy == "retention":
        rendered, contract = _retention_policy(base)
    else:
        rendered, contract = _midpoint_policy(base)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    record = {
        "schema": "s10-progb-counterfactual-source-v1",
        "variant": variant,
        "policy": policy,
        "approved_operational_policy": False,
        "native_execution_status": "WAITING_FOR_S14_NATIVE_SLOT",
        "canonical_source_path": str(source.resolve()),
        "canonical_source_sha256": source_sha,
        "overlay_path": str(output.resolve()),
        "overlay_sha256": _sha(rendered.encode()),
        "base_s10_capture_overlay_sha256": _sha(base.encode()),
        "s10_capture_macro": MACRO,
        "physical_policy_macro": POLICY_MACRO if policy == "midpoint" else None,
        "policy_contract": contract,
        "s10_capture_strip_exact": strip_capture(base) == raw.decode("utf-8"),
        "policy_delta_from_canonical": "intent/physics policy change; not strip-exact",
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=("mp37", "mp237"), required=True)
    parser.add_argument("--policy", choices=("retention", "midpoint"), required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_policy_overlay(args.source, args.output, args.manifest,
                                          args.variant, args.policy), indent=2))


if __name__ == "__main__":
    main()
