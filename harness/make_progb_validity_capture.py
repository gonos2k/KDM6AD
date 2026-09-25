"""Build strip-exact validity-only Fortran overlays from private canonical KDM6 sources.

The source is read-only.  Every injected statement is guarded by
KDM6_PROGB_VALIDITY_CAPTURE and is removable to recover the exact source bytes.
The capture emits branch/consumer bits only; it never reads or serializes an
INTENT(OUT) value whose assignment bit is false.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

MACRO = "KDM6_PROGB_VALIDITY_CAPTURE"
SOURCE_SHA = {
    "mp37": "fc0a72d33a5e61803fea56eb9118018039c6da8b5775813032b4861a2bd66eb5",
    "mp237": "4f0103c8a8321b8e854d3500f4ae567755e41eb78746fac54519eca2686a6648",
}
TARGETS = {"lat": 73, "active_i": 113, "inactive_i": 115}
# Stable S10RHO logical IDs. The integer values match legacy mp37 line anchors;
# mp237 source-line locations differ and are recorded in each run manifest.
RHO_CONSUMER_IDS = {
    1418: "pgmlt/rhox",
    2824: "pgdep/rhox",
    2915: "pgevp/rhox",
    2916: "pgeml/rhox",
    3027: "preProgB max/rhox",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _guard(label: str, code: str, base: str | None = None) -> str:
    begin = f"! S10_CAPTURE_BEGIN:{label}\n"
    end = f"! S10_CAPTURE_END:{label}\n"
    block = f"{begin}#ifdef {MACRO}\n{code}"
    if not code.endswith("\n"):
        block += "\n"
    if base is not None:
        block += "#else\n" + base
        if not base.endswith("\n"):
            block += "\n"
    block += f"#endif\n{end}"
    return block


def strip_capture(text: str) -> str:
    """Remove only complete marked overlays, preserving their #else base arm."""
    while "! S10_CAPTURE_BEGIN:" in text:
        start = text.index("! S10_CAPTURE_BEGIN:")
        line_end = text.index("\n", start) + 1
        label = text[start + len("! S10_CAPTURE_BEGIN:"):line_end].strip()
        end_marker = f"! S10_CAPTURE_END:{label}\n"
        end = text.find(end_marker, line_end)
        if end < 0:
            raise ValueError(f"missing capture end marker for {label}")
        block = text[line_end:end]
        prefix = f"#ifdef {MACRO}\n"
        if not block.startswith(prefix) or not block.endswith("#endif\n"):
            raise ValueError(f"malformed capture block {label}")
        body = block[len(prefix):-len("#endif\n")]
        if "#else\n" in body:
            if body.count("#else\n") != 1:
                raise ValueError(f"nested/duplicate #else in capture block {label}")
            _, base = body.split("#else\n", 1)
        else:
            base = ""
        text = text[:start] + base + text[end + len(end_marker):]
    if f"#ifdef {MACRO}" in text or f"#endif /* {MACRO} */" in text:
        raise ValueError("unmarked probe preprocessor block remains")
    return text


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected one anchor, found {count}: {old[:100]!r}")
    return text.replace(old, new, 1)


def _insert_before(text: str, anchor: str, code: str, label: str) -> str:
    return _replace_once(text, anchor, _guard(label, code) + anchor, label)


def _insert_after(text: str, anchor: str, code: str, label: str) -> str:
    return _replace_once(text, anchor, anchor + _guard(label, code), label)


def _replace_seven_calls(text: str) -> str:
    lines = text.splitlines(keepends=True)
    indices = [i for i, line in enumerate(lines) if "call ProgB_param(" in line]
    if len(indices) != 7:
        raise ValueError(f"expected 7 ProgB calls in kdm62D, found {len(indices)}")
    loop_n = (("0", "0"), ("loop", "n"), ("loop", "n"),
              ("loop", "0"), ("loop", "0"), ("loop", "0"), ("loop", "0"))
    for site, call_i in reversed(list(enumerate(indices, 1))):
        end_i = next((i for i in range(call_i, min(call_i + 12, len(lines)))
                      if lines[i].rstrip().endswith("dgbgmug1)")), None)
        if end_i is None:
            raise ValueError(f"ProgB call site {site} has no anchored final argument")
        original = lines[end_i]
        stripped = original.rstrip("\n")
        indent = stripped[:len(stripped) - len(stripped.lstrip())]
        base_line = original
        code = (f"{stripped[:-1]} &\n"
                f"{indent}, capture_enabled,capture_step,lat,{site},{loop_n[site-1][0]}, "
                f"{loop_n[site-1][1]}, capture_rhox_assigned, capture_cmg_assigned, &\n"
                f"{indent}capture_pidn0g_assigned, capture_params_assigned)\n")
        # The guarded active arm adds arguments; the else arm is the original line.
        lines[end_i] = _guard(f"progb_call_{site}", code, base_line)
        # Explicitly publish the current site for later rhox consumer records.
        lines.insert(call_i, _guard(
            f"progb_site_{site}",
            f"   capture_last_site = {site}\n"
            f"   capture_last_loop = {loop_n[site-1][0]}\n"
            f"   capture_last_substep = {loop_n[site-1][1]}\n"))
    return "".join(lines)


def _add_slope_events(text: str) -> str:
    lines = text.splitlines(keepends=True)
    indices = [i for i, line in enumerate(lines) if "call slope_kdm6(" in line]
    if len(indices) != 7:
        raise ValueError(f"expected 7 immediate slope_kdm6 calls, found {len(indices)}")
    for site, call_i in reversed(list(enumerate(indices, 1))):
        end_i = next((i for i in range(call_i, min(call_i + 8, len(lines)))
                      if lines[i].rstrip().endswith("rslopegbmax)")), None)
        if end_i is None:
            raise ValueError(f"slope call site {site} has no anchored final argument")
        code = (
            "   if (capture_enabled .and. capture_step.eq.1 .and. lat.eq.73) then\n"
            "   do k = kts, kte\n"
            "     do i = its, ite\n"
            "       if (capture_enabled .and. capture_step.eq.1 .and. lat.eq.73 .and. "
            "(i.eq.113 .or. i.eq.115)) then\n"
            "         write(*,'(A,18(1X,I0))') 'S10SLP', capture_step, lat, "
            "capture_last_site,capture_last_loop,capture_last_substep,i,k, &\n"
            "           merge(1,0,capture_rhox_assigned(i,k)), "
            "merge(1,0,capture_cmg_assigned(i,k)), &\n"
            "           merge(1,0,capture_pidn0g_assigned(i,k)), "
            "merge(1,0,capture_params_assigned(i,k)), &\n"
            "           merge(1,0,qrs_tmp(i,k,3).gt.qcrmin), "
            "merge(1,0,qrs_tmp(i,k,3).le.0.), &\n"
            "           1, merge(1,0,qrs_tmp(i,k,3).gt.qcrmin), &\n"
            "           merge(1,0,qrs_tmp(i,k,3).gt.qcrmin), &\n"
            "           merge(1,0,qrs_tmp(i,k,3).le.qcrmin), 1\n"
            "       endif\n"
            "     enddo\n"
            "   enddo\n"
            "   endif\n"
            "   if (capture_enabled .and. capture_step.eq.1) then\n"
            "   capture_trace_seen = .false.\n"
            "   do k = kts, kte\n"
            "     do i = its, ite\n"
            "       if (capture_enabled .and. capture_step.eq.1 .and. &\n"
            "           .not.capture_trace_seen .and. qrs_tmp(i,k,3).gt.0. .and. &\n"
            "           qrs_tmp(i,k,3).le.qcrmin .and. brs(i,k).le.1.e-15) then\n"
            "         capture_trace_seen = .true.\n"
            "         write(*,'(A,16(1X,I0))') 'S10TRS',capture_step,lat, &\n"
            "           capture_last_site,capture_last_loop,capture_last_substep,i,k, &\n"
            "           1,0,merge(1,0,capture_rhox_assigned(i,k)), &\n"
            "           merge(1,0,capture_cmg_assigned(i,k)), &\n"
            "           merge(1,0,capture_pidn0g_assigned(i,k)), &\n"
            "           merge(1,0,capture_params_assigned(i,k)),1,1,1\n"
            "       endif\n"
            "     enddo\n"
            "   enddo\n"
            "   endif\n"
        )
        lines.insert(end_i + 1, _guard(f"slope_consumer_{site}", code))
    return "".join(lines)


def _add_rhox_read_events(text: str) -> str:
    sites = (
        ("rhox_pgmlt", "              brs(i,k) = brs(i,k) + (pgmlt(i,k)/rhox(i,k))", 1418),
        ("rhox_pgdep", "            brs(i,k) = max(brs(i,k)+(pgdep(i,k)/rhox(i,k)+biacr(i,k)           &", 2824),
        ("rhox_pgevp", "            bgevp(i,k)=pgevp(i,k)/rhox(i,k)", 2915),
        ("rhox_pgeml", "            bgeml(i,k)=pgeml(i,k)/rhox(i,k)", 2916),
        ("rhox_preprogB", "         rhox(i,k) = max(rhox(i,k) ,0.)", 3027),
    )
    if {consumer_id for _, _, consumer_id in sites} != set(RHO_CONSUMER_IDS):
        raise ValueError("S10RHO semantic consumer-ID contract does not match its anchors")
    for label, anchor, consumer_id in sites:
        event = (
            "#ifdef " + MACRO + "\n"
            "         if (capture_enabled .and. capture_step.eq.1 .and. lat.eq.73 .and. "
            "(i.eq.113 .or. i.eq.115)) then\n"
            "           write(*,'(A,10(1X,I0))') 'S10RHO', capture_step, lat, &\n"
            "             capture_last_site,capture_last_loop,capture_last_substep,i,k, " + str(consumer_id) + ", &\n"
            "             merge(1,0,capture_rhox_assigned(i,k)), 1\n"
            "         endif\n"
            "#endif\n"
        )
        text = _insert_before(text, anchor, event, label)
    return text


def _add_final_diag_event(text: str) -> str:
    anchor = "         if (qrs(i,k,3) <= qcrmin) then\n"
    code = (
        "       if (capture_enabled .and. itimestep.eq.1 .and. j.eq.73 .and. "
        "(i.eq.113 .or. i.eq.115)) then\n"
        "         write(*,'(A,7(1X,I0))') 'S10DIAG', itimestep, j, i, k, &\n"
        "           merge(1,0,qrs(i,k,3).gt.qcrmin), &\n"
        "           merge(1,0,capture_rhox_assigned_2d(i,k)), &\n"
        "           merge(1,0,qrs(i,k,3).gt.qcrmin)\n"
        "       endif\n"
    )
    return _insert_before(text, anchor, code, "diag_consumer")


def build(source: Path, output: Path, manifest: Path, variant: str) -> dict:
    raw = source.read_bytes()
    digest = sha256(raw)
    if digest != SOURCE_SHA[variant]:
        raise ValueError(f"{variant} source SHA mismatch: {digest}")
    text = raw.decode("utf-8")
    # Add the final-validity scratch array and thread the run step through kdm62D.
    text = _insert_after(
        text,
        "   real, dimension(its:ite,kts:kte) :: rhox\n",
        "#ifdef " + MACRO + "\n"
        "   logical :: capture_enabled\n"
        "   logical, dimension(ims:ime,kms:kme) :: capture_rhox_assigned_2d\n"
        "#endif\n",
        "kdm6_capture_local",
    )
    call_old = "                ,graupel(ims,j),graupelncv(ims,j)          &\n                )\n"
    call_new = (
        "                ,graupel(ims,j),graupelncv(ims,j)          &\n"
        "                ,itimestep,capture_rhox_assigned_2d,capture_enabled)\n"
    )
    text = _replace_once(text, call_old, _guard("kdm62d_call", call_new, call_old), "kdm62d_call")
    # Add guarded formal metadata to kdm62D and its declaration.
    sig_old = "                   ,graupel,graupelncv                            &\n                    )\n"
    sig_new = (
        "                   ,graupel,graupelncv                            &\n"
        "                   ,capture_step,capture_rhox_assigned_2d,capture_enabled &\n"
        "                    )\n"
    )
    text = _replace_once(text, sig_old, _guard("kdm62d_signature", sig_new, sig_old), "kdm62d_signature")
    intent_anchor = "   real, dimension(its:ite,kts:kte)       , intent(out) :: rhox\n"
    text = _insert_after(
        text,
        intent_anchor,
        "#ifdef " + MACRO + "\n"
        "   integer, intent(in) :: capture_step\n"
        "   logical, intent(in) :: capture_enabled\n"
        "   logical, dimension(ims:ime,kms:kme), intent(out) :: capture_rhox_assigned_2d\n"
        "#endif\n",
        "kdm62d_capture_intents",
    )
    block_decl_anchor = "     integer :: kdm6_dstep, kdm6_dstep_ios\n"
    text = _insert_after(
        text,
        block_decl_anchor,
        "#ifdef " + MACRO + "\n"
        "     character(len=16) :: kdm6_progb_capture_env\n"
        "#endif\n",
        "kdm6_capture_env_declaration",
    )
    capture_env_call = "     call get_environment_variable('KDM6_SUBSTEP_DUMP', kdm6_dump_dir)\n"
    text = _insert_before(
        text,
        capture_env_call,
        "#ifdef " + MACRO + "\n"
        "     kdm6_progb_capture_env = ''\n"
        "     call get_environment_variable('KDM6_PROGB_VALIDITY_CAPTURE_LOG', &\n"
        "          kdm6_progb_capture_env)\n"
        "     capture_enabled = (trim(kdm6_progb_capture_env) == '1')\n"
        "#endif\n",
        "kdm6_capture_runtime_gate",
    )
    # Local validity-only arrays and call-site context; no physics arrays are read here.
    local_anchor = "   integer                            :: i, j, k, mstepmax,mstepmax_i,         &\n                                         iprt, latd, lond, loop, loops, ifsat, &\n                                         n, idim, kdim\n"
    text = _insert_after(
        text,
        local_anchor,
        "#ifdef " + MACRO + "\n"
        "   integer :: capture_last_site,capture_last_loop,capture_last_substep\n"
        "   logical :: capture_trace_seen\n"
        "   logical, dimension(its:ite,kts:kte) :: capture_rhox_assigned, capture_cmg_assigned\n"
        "   logical, dimension(its:ite,kts:kte) :: capture_pidn0g_assigned, capture_params_assigned\n"
        "#endif\n",
        "kdm62d_capture_arrays",
    )
    text = _insert_before(
        text,
        "   do loop = 1,loops\n",
        "   capture_rhox_assigned_2d = .false.\n"
        "   capture_last_site = 0\n"
        "   capture_last_loop = 0\n"
        "   capture_last_substep = 0\n",
        "kdm62d_capture_init",
    )
    text = _replace_seven_calls(text)
    # Add compiler-guarded output-validity dummies and local branch flags to ProgB_param.
    sig = ("                         ,g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1)\n")
    alt = (
        "                         ,g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1 &\n"
        "                         ,capture_enabled &\n"
        "                         ,capture_step,capture_lat,capture_site, &\n"
        "                         capture_loop,capture_substep, &\n"
        "                         capture_rhox_assigned,capture_cmg_assigned, &\n"
        "                         capture_pidn0g_assigned,capture_params_assigned)\n"
    )
    text = _replace_once(text, sig, _guard("progb_signature", alt, sig), "progb_signature")
    decl_anchor = "  REAL, DIMENSION( its:ite , kts:kte),INTENT(OUT)   :: bvtg,bvtg1,bvtg2,bvtg3,bvtg4,rslopegbmax,&\n                                                       g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1\n"
    decl_code = (
        "  INTEGER, INTENT(IN) :: capture_step,capture_lat,capture_site,capture_loop,capture_substep\n"
        "  LOGICAL, INTENT(IN) :: capture_enabled\n"
        "  LOGICAL, DIMENSION(its:ite,kts:kte), INTENT(OUT) :: capture_rhox_assigned, &\n"
        "       capture_cmg_assigned,capture_pidn0g_assigned,capture_params_assigned\n"
        "  LOGICAL :: capture_active,capture_rhox_written,capture_cmg_written, &\n"
        "       capture_pidn0g_written,capture_params_written,capture_trace_seen\n"
    )
    text = _insert_after(text, decl_anchor, decl_code, "progb_valid_declarations")
    # Initialize only the diagnostic flags.  Mark their exact producer assignments.
    cell_anchor = "        do i = its, ite\n\n\n     if (qrs(i,k,3).gt. qcrmin .or. brs(i,k).gt. brs_min) then\n"
    cell_code = (
        "        do i = its, ite\n"
        "#ifdef " + MACRO + "\n"
        "          capture_active = .false.\n"
        "          capture_rhox_written = .false.\n"
        "          capture_cmg_written = .false.\n"
        "          capture_pidn0g_written = .false.\n"
        "          capture_params_written = .false.\n"
        "          if (k.eq.kts .and. i.eq.its) capture_trace_seen = .false.\n"
        "          capture_rhox_assigned(i,k) = .false.\n"
        "          capture_cmg_assigned(i,k) = .false.\n"
        "          capture_pidn0g_assigned(i,k) = .false.\n"
        "          capture_params_assigned(i,k) = .false.\n"
        "#endif\n"
        "\n"
        "     if (qrs(i,k,3).gt. qcrmin .or. brs(i,k).gt. brs_min) then\n"
        "#ifdef " + MACRO + "\n"
        "          capture_active = .true.\n"
        "#endif\n"
    )
    text = _replace_once(text, cell_anchor, _guard("progb_cell_flags", cell_code, cell_anchor), "progb_cell_flags")
    rhox_anchor = "        endif\n\n        if (rhox(i,k).ge. rho_min .and. rhox(i,k).le. rho_max) then\n"
    rhox_code = (
        "#ifdef " + MACRO + "\n"
        "        capture_rhox_written = .true.\n"
        "        capture_rhox_assigned(i,k) = .true.\n"
        "#endif\n"
    )
    rhox_replacement = (
        "        endif\n"
        + _guard("progb_rhox_written", rhox_code)
        + "\n        if (rhox(i,k).ge. rho_min .and. rhox(i,k).le. rho_max) then\n"
    )
    text = _replace_once(text, rhox_anchor, rhox_replacement, "progb_rhox_written")
    pidn_anchor = "        pidn0g(i,k) =  cmg(i,k)*n0g*g1pdgmg/g1pmg\n"
    text = _insert_after(
        text, pidn_anchor,
        "#ifdef " + MACRO + "\n"
        "          capture_cmg_written = .true.\n"
        "          capture_pidn0g_written = .true.\n"
        "          capture_cmg_assigned(i,k) = .true.\n"
        "          capture_pidn0g_assigned(i,k) = .true.\n"
        "#endif\n",
        "progb_cmg_pidn_written",
    )
    cmg_test_anchor = "         if (cmg(i,k).gt. 0) then\n"
    cmg_event = (
        "#ifdef " + MACRO + "\n"
        "         if (capture_enabled .and. capture_step.eq.1 .and. capture_lat.eq.73 .and. &\n"
        "             (i.eq.113 .or. i.eq.115)) then\n"
        "           write(*,'(A,9(1X,I0))') 'S10CMG', capture_step, capture_lat, &\n"
        "             capture_site,capture_loop,capture_substep,i,k, &\n"
        "             merge(1,0,capture_cmg_written),1\n"
        "         endif\n"
        "#endif\n"
    )
    text = _insert_before(text, cmg_test_anchor, cmg_event, "progb_cmg_read")
    # Mark both complete table paths after the last member of their output bundle.
    for anchor, label in (
        ("                   precg2(i,k) = 4.*.31*avtg(i,k)**.5*g5pbgo2(i,k)\n                   exit\n", "progb_params_table"),
        ("                   precg2(i,k) = 4.*.31*avtg(i,k)**.5*g5pbgo2(i,k)\n         endif\n", "progb_params_rhomax"),
    ):
        text = _insert_after(
            text, anchor,
            "#ifdef " + MACRO + "\n"
            "                   capture_params_written = .true.\n"
            "                   capture_params_assigned(i,k) = .true.\n"
            "#endif\n",
            label,
        )
    # Emit the complete assignment bitmap after all branches; no OUT value is read.
    end_cell = "       endif\n      enddo\n    enddo\n\n  END subroutine ProgB_param\n"
    out_event = (
        "       endif\n"
        "#ifdef " + MACRO + "\n"
        "       if (capture_enabled .and. capture_step.eq.1 .and. capture_lat.eq.73 .and. &\n"
        "           (i.eq.113 .or. i.eq.115)) then\n"
        "         write(*,'(A,12(1X,I0))') 'S10PB', capture_step, capture_lat, &\n"
        "           capture_site,capture_loop,capture_substep,i,k, &\n"
        "           merge(1,0,capture_active),merge(1,0,capture_rhox_written), &\n"
        "           merge(1,0,capture_cmg_written),merge(1,0,capture_pidn0g_written), &\n"
        "           merge(1,0,capture_params_written)\n"
        "       endif\n"
        "       if (capture_enabled .and. capture_step.eq.1 .and. &\n"
        "           .not.capture_trace_seen .and. qrs(i,k,3).gt.0. .and. &\n"
        "           qrs(i,k,3).le.qcrmin .and. brs(i,k).le.brs_min) then\n"
        "         capture_trace_seen = .true.\n"
        "         write(*,'(A,14(1X,I0))') 'S10TRACE',capture_step,capture_lat, &\n"
        "           capture_site,capture_loop,capture_substep,i,k,1,0,0, &\n"
        "           merge(1,0,capture_rhox_written),merge(1,0,capture_cmg_written), &\n"
        "           merge(1,0,capture_pidn0g_written),merge(1,0,capture_params_written)\n"
        "       endif\n"
        "#endif\n"
        "      enddo\n    enddo\n"
        "#ifdef " + MACRO + "\n"
        "   if (capture_enabled .and. capture_step.eq.1) then\n"
        "     write(*,'(A,6(1X,I0))') 'S10SCAN',capture_step,capture_lat, &\n"
        "       capture_site,capture_loop,capture_substep,merge(1,0,capture_trace_seen)\n"
        "   endif\n"
        "#endif\n"
        "\n  END subroutine ProgB_param\n"
    )
    text = _replace_once(text, end_cell, _guard("progb_assignment_record", out_event, end_cell), "progb_assignment_record")
    text = _add_slope_events(text)
    text = _add_rhox_read_events(text)
    text = _add_final_diag_event(text)
    # Return the last ProgB rhox validity bits to the top-level diagnostic exporter.
    final_anchor = "   end subroutine kdm62d\n"
    text = _insert_before(
        text, final_anchor,
        "#ifdef " + MACRO + "\n"
        "   capture_rhox_assigned_2d(its:ite,kts:kte) = capture_rhox_assigned(its:ite,kts:kte)\n"
        "#endif\n",
        "kdm62d_final_validity",
    )
    stripped = strip_capture(text)
    if stripped != raw.decode("utf-8"):
        import difflib
        diff = list(difflib.unified_diff(
            raw.decode("utf-8").splitlines(), stripped.splitlines(),
            fromfile="canonical", tofile="stripped", lineterm=""))
        raise ValueError("strip-exact verification failed:\n" + "\n".join(diff[:50]))
    if output.resolve() == source.resolve():
        raise ValueError("refusing to overwrite canonical private source")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    record = {
        "schema": "progb-validity-source-overlay-v1",
        "variant": variant,
        "macro": MACRO,
        "execution_status": "PREPARED_NOT_RUN",
        "logging_environment": "KDM6_PROGB_VALIDITY_CAPTURE_LOG",
        "same_executable_control_capture": True,
        "control_logging_value": "unset",
        "capture_logging_value": "1",
        "canonical_source": str(source.resolve()),
        "canonical_source_sha256": digest,
        "capture_source_sha256": sha256(text.encode("utf-8")),
        "strip_exact": True,
        "instrumentation_output": str(output.resolve()),
        "preselected": {"j": 73, "active_i": 113, "inactive_i": 115,
                        "fortran_levels": [1, 39]},
        "records": ["S10CMG", "S10PB", "S10SLP", "S10RHO", "S10DIAG",
                    "S10SCAN", "S10TRACE", "S10TRS"],
        "measured_impact": "NOT_MEASURED; native execution pending S2 then S6 release",
        "physical_validity_policy": "OPEN",
    }
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=sorted(SOURCE_SHA), required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.output, args.manifest, args.variant), indent=2))


if __name__ == "__main__":
    main()
