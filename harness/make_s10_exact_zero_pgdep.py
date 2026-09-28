"""Generate a midpoint-free opt-in exact-zero guard for stage-2 pgdep/rhox."""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

try:
    import make_progb_validity_capture as validity
    import make_s10_stage2_pair as pair
except ModuleNotFoundError:
    from harness import make_progb_validity_capture as validity
    from harness import make_s10_stage2_pair as pair

MACRO = "KDM6_S10_EXACT_ZERO_PGDEP"
USE_ANCHOR = "   use module_model_constants, only : RE_QC_BG, RE_QI_BG, RE_QS_BG\n"
SITE_ID = 2824
BRS_MIN_ANCHOR = "  real, parameter   :: brs_min = 1.e-15   !m3 kg-1, min.allowable bulk volume mixing ratio\n"


def _mark(label: str, code: str, base: str | None = None) -> str:
    body = code
    if base is not None:
        body += "#else\n" + base
        if not base.endswith("\n"):
            body += "\n"
    return f"! S10_EXACT_ZERO_BEGIN:{label}\n#ifdef {MACRO}\n{body}#endif\n! S10_EXACT_ZERO_END:{label}\n"


def strip_guard(text: str) -> str:
    """Remove exact-zero blocks, retaining their macro-off source arms."""
    while "! S10_EXACT_ZERO_BEGIN:" in text:
        start = text.index("! S10_EXACT_ZERO_BEGIN:")
        line_end = text.index("\n", start) + 1
        label = text[start + len("! S10_EXACT_ZERO_BEGIN:"):line_end].strip()
        end_marker = f"! S10_EXACT_ZERO_END:{label}\n"
        end = text.find(end_marker, line_end)
        if end < 0:
            raise ValueError(f"missing exact-zero end marker for {label}")
        block = text[line_end:end]
        prefix = f"#ifdef {MACRO}\n"
        if not block.startswith(prefix) or not block.endswith("#endif\n"):
            raise ValueError(f"malformed exact-zero marker {label}")
        body = block[len(prefix):-len("#endif\n")]
        if body.count("#else\n") > 1:
            raise ValueError(f"nested/duplicate #else in exact-zero block {label}")
        base = body.split("#else\n", 1)[1] if "#else\n" in body else ""
        text = text[:start] + base + text[end + len(end_marker):]
    if f"#ifdef {MACRO}" in text:
        raise ValueError("unmarked exact-zero macro block remains")
    return text


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected one source anchor, found {count}")
    return text.replace(old, new, 1)


def _guard_block() -> str:
    zero_store = (
        "            brs(i,k) = max(brs(i,k)+(pgdep(i,k)+biacr(i,k)           &\n"
        "                           +braci(i,k)+bsacr(i,k)+bracs(i,k)+bgaci(i,k)        &\n"
        "                           +baacw(i,k)+bgacr(i,k))*dtcld,0.)\n"
    )
    return (
        "            if (pgdep(i,k).eq.0.) then\n"
        "              s10_pgdep_action = 0\n"
        + zero_store
        + "            else\n"
        "              s10_pgdep_action = 1\n"
        "              if (capture_last_site.ne.5) then\n"
        "                call wrf_error_fatal('S10 pgdep guard expected ProgB site 5')\n"
        "              else if (.not.capture_rhox_assigned(i,k)) then\n"
        "                if (storage_size(0_s10_pgdep_word_kind).ne.32 .or. &\n"
        "                    storage_size(pgdep(i,k)).ne.32 .or. &\n"
        "                    storage_size(qrs(i,k,3)).ne.32) &\n"
        "                  call wrf_error_fatal('S10ZF requires 32-bit raw words')\n"
        "                write(*,'(A,9(1X,I0),5(1X,Z8.8))') 'S10ZF', &\n"
        "                  capture_step,lat,capture_last_site,capture_last_loop, &\n"
        "                  capture_last_substep,i,k,2,0, &\n"
        "                  transfer(pgdep(i,k),0_s10_pgdep_word_kind), &\n"
        "                  transfer(qrs(i,k,3),0_s10_pgdep_word_kind), &\n"
        "                  transfer(brs(i,k),0_s10_pgdep_word_kind), &\n"
        "                  transfer(qcrmin,0_s10_pgdep_word_kind), &\n"
        "                  transfer(1.e-15,0_s10_pgdep_word_kind)\n"
        "                flush(6)\n"
        "                call wrf_error_fatal('S10 nonzero pgdep has unassigned rhox')\n"
        "              else if (.not.ieee_is_finite(rhox(i,k))) then\n"
        "                call wrf_error_fatal('S10 nonzero pgdep has nonfinite rhox')\n"
        "              else if (rhox(i,k).le.0.) then\n"
        "                call wrf_error_fatal('S10 nonzero pgdep has nonpositive rhox')\n"
        "              else\n"
        + pair.COLD_BRS_ANCHOR
        + "              endif\n"
        "            endif\n"
    )


def _zg_log() -> str:
    return (
        "   if (capture_enabled .and. capture_step.eq.1 .and. lat.eq.2 .and. &\n"
        "       i.eq.142 .and. k.eq.17) then\n"
        "     s10_pgdep_density_valid = 0\n"
        "     if (capture_last_site.eq.5) then\n"
        "       if (capture_rhox_assigned(i,k)) then\n"
        "         if (ieee_is_finite(rhox(i,k))) then\n"
        "           if (rhox(i,k).gt.0.) s10_pgdep_density_valid = 1\n"
        "         endif\n"
        "       endif\n"
        "     endif\n"
        "     if (storage_size(0_s10_pgdep_word_kind).ne.32 .or. &\n"
        "         storage_size(pgdep(i,k)).ne.32) &\n"
        "       call wrf_error_fatal('S10 pgdep log requires 32-bit raw words')\n"
        "     write(*,'(A,10(1X,I0),1X,Z8.8)') 'S10ZG', &\n"
        "       capture_step,lat,capture_last_site,capture_last_loop, &\n"
        "       capture_last_substep,i,k,2824,s10_pgdep_action, &\n"
        "       s10_pgdep_density_valid,transfer(pgdep(i,k),0_s10_pgdep_word_kind)\n"
        "   endif\n"
    )


def inject_guard(pair_overlay: str) -> str:
    """Guard one stage-2 quotient; leave all other terms and stores unchanged."""
    use = (
        "#ifndef KDM6_PROGB_VALIDITY_CAPTURE\n"
        '#error "KDM6_S10_EXACT_ZERO_PGDEP requires KDM6_PROGB_VALIDITY_CAPTURE"\n'
        "#endif\n"
        "#ifndef KDM6_S10_STAGE2_PAIR\n"
        '#error "KDM6_S10_EXACT_ZERO_PGDEP requires KDM6_S10_STAGE2_PAIR"\n'
        "#endif\n"
        "   use, intrinsic :: ieee_arithmetic, only : ieee_is_finite\n"
    )
    text = _replace_once(pair_overlay, USE_ANCHOR,
                         USE_ANCHOR + _mark("uses", use), "module uses")
    declarations = (
        "   integer, parameter :: s10_pgdep_word_kind = selected_int_kind(9)\n"
        "   integer :: s10_pgdep_action,s10_pgdep_density_valid\n"
    )
    text = _replace_once(text, pair._DECL_ANCHOR,
                         pair._DECL_ANCHOR + _mark("declarations", declarations),
                         "kdm62D declarations")
    if text.count(BRS_MIN_ANCHOR) != 1:
        raise ValueError("ProgB brs_min source pin changed; refusing copied S10ZF threshold")
    text = _replace_once(
        text, pair.COLD_BRS_ANCHOR,
        _mark("stage2_pgdep_guard", _guard_block() + _zg_log(), pair.COLD_BRS_ANCHOR),
        "stage2 pgdep/rhox consumer",
    )
    if strip_guard(text) != pair_overlay:
        raise ValueError("exact-zero macro-off source differs from S10PAIR overlay")
    if "KDM6_PROGB_POLICY_MIDPOINT" in text:
        raise ValueError("exact-zero overlay must not enable midpoint policy macro")
    block = text[text.index("! S10_EXACT_ZERO_BEGIN:stage2_pgdep_guard"):
                 text.index("! S10_EXACT_ZERO_END:stage2_pgdep_guard")]
    if "rho_mid" in block or "brs(i,k) = qrs(i,k,3)/rho_mid" in block:
        raise ValueError("exact-zero guard must not inject a midpoint fallback")
    zero_arm = block.split("            else\n", 1)[0]
    if "rhox" in zero_arm:
        raise ValueError("zero-pgdep arm must not read rhox")
    return text


def build(source: Path, output: Path, manifest: Path) -> dict:
    if len({source.resolve(), output.resolve(), manifest.resolve()}) != 3:
        raise ValueError("source, overlay, and manifest paths must be distinct")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".s10-exact-zero-pgdep-", dir=output.parent) as temp:
        temp_path = Path(temp)
        pair_path = temp_path / "s10_stage2_pair.F"
        pair_manifest = temp_path / "s10_stage2_pair.json"
        pair_record = pair.build(source, pair_path, pair_manifest)
        pair_overlay = pair_path.read_text(encoding="utf-8")
        guarded = inject_guard(pair_overlay)
        stripped_pair = pair.strip_pair(strip_guard(guarded))
        if validity.strip_capture(stripped_pair) != source.read_text(encoding="utf-8"):
            raise ValueError("combined exact-zero and S10PAIR strips do not restore canonical source")
    digest = hashlib.sha256(guarded.encode("utf-8")).hexdigest()
    output.write_text(guarded, encoding="utf-8")
    record = {
        "schema": "s10-exact-zero-pgdep-overlay-v1",
        "execution_status": "PREPARED_NOT_RUN",
        "canonical_source_sha256": pair_record["canonical_source_sha256"],
        "s10pair_overlay_sha256": pair_record["pair_overlay_sha256"],
        "guard_overlay_sha256": digest,
        "macro": MACRO,
        "midpoint_fallback": False,
        "macro_off_matches_s10pair_overlay": True,
        "strip_to_canonical_exact": True,
        "guard_site": {"consumer": "pgdep/rhox", "source_line": 2862},
        "predicate": "exact binary32 pgdep == 0; no qg test at post-mass consumer",
        "zero_arm_term": "pgdep numerator signed zero, followed by unchanged brs terms/order",
        "nonzero_arm": "requires preceding ProgB site 5 rhox assignment and finite-positive rhox before division",
        "action_log": "S10ZG action, raw pgdep word, density-valid bit; no numeric rhox",
        "first_fatal_log": "S10ZF logs unassigned-rhox fatal without capture or coordinate gate: step/site/loop/substep/lat/i/k, reason=2, assignment=0, pgdep/qg/brs/qcrmin/brs_min raw words",
        "s10pair_safe_logger_preserved": True,
        "other_rhox_consumers_changed": False,
        "native_build_or_run": False,
    }
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.output, args.manifest), indent=2))


if __name__ == "__main__":
    main()
