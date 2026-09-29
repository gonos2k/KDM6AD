"""Generate an opt-in midpoint ProgB source with safe zero-rate quotients."""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

try:
    from make_progb_policy_counterfactual import _midpoint_policy
    from make_progb_validity_capture import build as build_validity
except ModuleNotFoundError:
    from harness.make_progb_policy_counterfactual import _midpoint_policy
    from harness.make_progb_validity_capture import build as build_validity

MACRO = "KDM6_S10_MIDPOINT_RATE_ZERO"
USE_ANCHOR = "   use module_model_constants, only : RE_QC_BG, RE_QI_BG, RE_QS_BG\n"
DECL_ANCHOR = "   real, dimension(its:ite,kts:kte)   :: lamdr_tmp, lamdc_tmp, lamdi_tmp, nrs_pre_diag\n"

SITES = (
    (1418, "pgmlt(i,k)", "              brs(i,k) = brs(i,k) + (pgmlt(i,k)/rhox(i,k))\n",
     "              brs(i,k) = brs(i,k) + (pgmlt(i,k))\n"),
    (2824, "pgdep(i,k)",
     "            brs(i,k) = max(brs(i,k)+(pgdep(i,k)/rhox(i,k)+biacr(i,k)           &\n"
     "                           +braci(i,k)+bsacr(i,k)+bracs(i,k)+bgaci(i,k)        &\n"
     "                           +baacw(i,k)+bgacr(i,k))*dtcld,0.)\n",
     "            brs(i,k) = max(brs(i,k)+(pgdep(i,k)+biacr(i,k)           &\n"
     "                           +braci(i,k)+bsacr(i,k)+bracs(i,k)+bgaci(i,k)        &\n"
     "                           +baacw(i,k)+bgacr(i,k))*dtcld,0.)\n"),
    (2915, "pgevp(i,k)", "            bgevp(i,k)=pgevp(i,k)/rhox(i,k)\n",
     "            bgevp(i,k)=pgevp(i,k)\n"),
    (2916, "pgeml(i,k)", "            bgeml(i,k)=pgeml(i,k)/rhox(i,k)\n",
     "            bgeml(i,k)=pgeml(i,k)\n"),
)

# Snapshot qg immediately before each mass-store group that contains one of the
# guarded consumers.  The guard itself runs at the later volume store, after
# the mass update has already changed qrs(:,:,3).
QG_MASS_SNAPSHOTS = (
    "              qrs(i,k,3) = qrs(i,k,3) + pgmlt(i,k)\n",
    "            qrs(i,k,3) = max(qrs(i,k,3)+(pgdep(i,k)+pgaut(i,k)                 &\n"
    "                           +piacr(i,k)*(1.-delta3)                             &\n"
    "                           +praci(i,k)*(1.-delta3)+psacr(i,k)*(1.-delta2)      &\n"
    "                           +pracs(i,k)*(1.-delta2)+pgaci(i,k)+paacw(i,k)       &\n"
    "                           +pgacr(i,k)+pgacs(i,k))*dtcld,0.)\n",
    "            qrs(i,k,3) = max(qrs(i,k,3)+(pgacs(i,k)+pgevp(i,k)                 &\n"
    "                    +pgeml(i,k))*dtcld,0.)\n",
)

WARM_BRS_STORE = (
    "            brs(i,k) = max(brs(i,k)+(bgevp(i,k)+bgeml(i,k))*dtcld,0.)\n"
)


def _once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"expected one source anchor, found {text.count(old)}: {old[:80]!r}")
    return text.replace(old, new, 1)


def _wrap(label: str, enabled: str, original: str = "") -> str:
    return (f"! S10_HYBRID_BEGIN:{label}\n#ifdef {MACRO}\n{enabled}"
            f"#else\n{original}#endif\n! S10_HYBRID_END:{label}\n")


def strip_hybrid(text: str) -> str:
    while "! S10_HYBRID_BEGIN:" in text:
        start = text.index("! S10_HYBRID_BEGIN:")
        first_end = text.index("\n", start) + 1
        label = text[start + len("! S10_HYBRID_BEGIN:"):first_end].strip()
        end_marker = f"! S10_HYBRID_END:{label}\n"
        end = text.index(end_marker, first_end)
        block = text[first_end:end]
        prefix = f"#ifdef {MACRO}\n"
        if not block.startswith(prefix) or not block.endswith("#endif\n"):
            raise ValueError(f"malformed hybrid block: {label}")
        body = block[len(prefix):-len("#endif\n")]
        if body.count("#else\n") != 1:
            raise ValueError(f"malformed hybrid else arm: {label}")
        original = body.split("#else\n", 1)[1]
        text = text[:start] + original + text[end + len(end_marker):]
    return text


def _failure(consumer_id: int, rate: str, reason: int, message: str) -> str:
    return (
        "                if (storage_size(0_s10_hybrid_word_kind).ne.32 .or. &\n"
        "                    storage_size(" + rate + ").ne.32) &\n"
        "                  call wrf_error_fatal('S10 hybrid requires REAL4 raw words')\n"
        "                write(*,'(A,10(1X,I0),1X,Z8.8)') 'S10HYFAIL', &\n"
        "                  capture_step,lat,capture_last_site,capture_last_loop, &\n"
        "                  capture_last_substep,i,k," + str(consumer_id) + "," + str(reason) + ", &\n"
        "                  merge(1,0,capture_rhox_assigned(i,k)), &\n"
        "                  transfer(" + rate + ",0_s10_hybrid_word_kind)\n"
        "                flush(6)\n"
        "                call wrf_error_fatal('" + message + "')\n"
    )


def _event_row(consumer_id: int, rate_slot: str) -> str:
    """Bounded selected-cell REAL4 receipt for the actual guarded store."""
    return (
        "              if (capture_enabled .and. capture_step.eq.1 .and. &\n"
        "                  ((lat.eq.73 .and. (i.eq.113 .or. i.eq.115)) .or. &\n"
        "                   (lat.eq.2 .and. i.eq.142 .and. k.eq.17))) then\n"
        "                if (storage_size(0_s10_hybrid_word_kind).ne.32 .or. &\n"
        "                    storage_size(qrs(i,k,3)).ne.32 .or. &\n"
        "                    storage_size(brs(i,k)).ne.32 .or. &\n"
        "                    storage_size(" + rate_slot + "_rate).ne.32 .or. &\n"
        "                    storage_size(" + rate_slot + "_rhox).ne.32 .or. &\n"
        "                    storage_size(dtcld).ne.32) &\n"
        "                  call wrf_error_fatal('S10HYACT requires REAL4 words')\n"
        "                write(*,'(A,10(1X,I0),8(1X,Z8.8))') 'S10HYACT', &\n"
        "                  capture_step,lat,capture_last_site,capture_last_loop, &\n"
        "                  capture_last_substep,i,k," + str(consumer_id) + ", &\n"
        "                  " + rate_slot + "_action," + rate_slot + "_rhox_assigned, &\n"
        "                  transfer(s10_hybrid_qg_before,0_s10_hybrid_word_kind), &\n"
        "                  transfer(qrs(i,k,3),0_s10_hybrid_word_kind), &\n"
        "                  transfer(" + rate_slot + "_rate,0_s10_hybrid_word_kind), &\n"
        "                  transfer(" + rate_slot + "_rhox,0_s10_hybrid_word_kind), &\n"
        "                  transfer(" + rate_slot + "_term,0_s10_hybrid_word_kind), &\n"
        "                  transfer(s10_hybrid_brs_before,0_s10_hybrid_word_kind), &\n"
        "                  transfer(brs(i,k),0_s10_hybrid_word_kind), &\n"
        "                  transfer(dtcld,0_s10_hybrid_word_kind)\n"
        "                flush(6)\n"
        "              endif\n"
    )


def _guard(consumer_id: int, rate: str, original: str, zero: str,
           *, slot: str, log_after_store: bool) -> str:
    log_gate = (
        "capture_enabled .and. capture_step.eq.1 .and. &\n"
        "                  ((lat.eq.73 .and. (i.eq.113 .or. i.eq.115)) .or. &\n"
        "                   (lat.eq.2 .and. i.eq.142 .and. k.eq.17))"
    )
    density_check = (
        "              s10_hybrid_density_valid = .false.\n"
        "              if (capture_rhox_assigned(i,k)) then\n"
        "                if (ieee_is_finite(rhox(i,k))) then\n"
        "                  s10_hybrid_density_valid = rhox(i,k).gt.0.\n"
        "                endif\n"
        "              endif\n"
        "              if (.not.s10_hybrid_density_valid) then\n"
        + _failure(consumer_id, rate, 2, "S10 nonzero rate lacks valid rhox")
        + "              endif\n"
    )
    # B defines rhox on every branch, including zero. The first predicate is
    # still retained so the producer/consumer provenance must agree.
    density_snapshot = (
        "            if (" + log_gate + ") then\n"
        "              s10_hybrid_brs_before = brs(i,k)\n"
        "              " + slot + "_rate = " + rate + "\n"
        "              " + slot + "_rhox = 0.\n"
        "              " + slot + "_rhox_assigned = 0\n"
        "              if (capture_rhox_assigned(i,k)) then\n"
        "                " + slot + "_rhox = rhox(i,k)\n"
        "                " + slot + "_rhox_assigned = 1\n"
        "              endif\n"
        "            endif\n"
    )
    event_save = (
        "            if (" + log_gate + ") then\n"
        f"              if ({rate}.eq.0.) then\n"
        "                " + slot + "_action = 1\n"
        "                " + slot + "_term = " + rate + "\n"
        "              else\n"
        "                " + slot + "_action = 0\n"
        "                " + slot + "_term = " + rate + "/rhox(i,k)\n"
        "              endif\n"
        "            endif\n"
    )
    guard = (
        f"            if (.not.ieee_is_finite({rate})) then\n"
        + _failure(consumer_id, rate, 1, "S10 nonfinite process rate")
        + "            endif\n"
        + density_snapshot
        + f"            if ({rate}.eq.0.) then\n"
        + zero
        + "            else\n" + density_check
        + original
        + "            endif\n"
        + event_save
    )
    if not log_after_store:
        guard += _event_row(consumer_id, slot)
    return _wrap(str(consumer_id), guard, original)


def inject_hybrid(midpoint_source: str) -> str:
    uses = (
        "#ifndef KDM6_PROGB_VALIDITY_CAPTURE\n"
        '#error "S10 hybrid requires ProgB validity capture"\n'
        "#endif\n"
        "#ifndef KDM6_PROGB_POLICY_MIDPOINT\n"
        '#error "S10 hybrid requires midpoint policy"\n'
        "#endif\n"
        "   use, intrinsic :: ieee_arithmetic, only : ieee_is_finite\n"
    )
    text = _once(midpoint_source, USE_ANCHOR, USE_ANCHOR + _wrap("uses", uses))
    text = _once(text, DECL_ANCHOR, DECL_ANCHOR + _wrap(
        "word_kind", "   integer, parameter :: s10_hybrid_word_kind = selected_int_kind(9)\n"
        "   logical :: s10_hybrid_density_valid\n"
        "   integer :: pgmlt_action, pgdep_action\n"
        "   integer :: pgevp_action, pgeml_action\n"
        "   integer :: pgmlt_rhox_assigned, pgdep_rhox_assigned\n"
        "   integer :: pgevp_rhox_assigned, pgeml_rhox_assigned\n"
        "   real :: s10_hybrid_qg_before, s10_hybrid_brs_before\n"
        "   real :: pgmlt_rate, pgmlt_rhox, pgmlt_term\n"
        "   real :: pgdep_rate, pgdep_rhox, pgdep_term\n"
        "   real :: pgevp_rate, pgevp_rhox, pgevp_term\n"
        "   real :: pgeml_rate, pgeml_rhox, pgeml_term\n"))
    for index, anchor in enumerate(QG_MASS_SNAPSHOTS, 1):
        text = _once(
            text, anchor,
            _wrap(f"qg_mass_snapshot_{index}",
                  "            if (capture_enabled .and. capture_step.eq.1 .and. &\n"
                  "                ((lat.eq.73 .and. (i.eq.113 .or. i.eq.115)) .or. &\n"
                  "                 (lat.eq.2 .and. i.eq.142 .and. k.eq.17))) then\n"
                  "              s10_hybrid_qg_before = qrs(i,k,3)\n"
                  "            endif\n" + anchor, anchor),
        )
    for consumer_id, rate, original, zero in SITES:
        slot = {1418: "pgmlt", 2824: "pgdep", 2915: "pgevp", 2916: "pgeml"}[consumer_id]
        text = _once(text, original, _guard(
            consumer_id, rate, original, zero, slot=slot,
            log_after_store=consumer_id in {2915, 2916}))
    warm_store = WARM_BRS_STORE
    warm_rows = (
        "            if (capture_enabled .and. capture_step.eq.1 .and. &\n"
        "                ((lat.eq.73 .and. (i.eq.113 .or. i.eq.115)) .or. &\n"
        "                 (lat.eq.2 .and. i.eq.142 .and. k.eq.17))) then\n"
        "              s10_hybrid_brs_before = brs(i,k)\n"
        "            endif\n" + warm_store
        + _event_row(2915, "pgevp")
        + _event_row(2916, "pgeml")
    )
    text = _once(text, warm_store, _wrap("warm_success_ledger", warm_rows, warm_store))
    if strip_hybrid(text) != midpoint_source:
        raise ValueError("hybrid macro-off source differs from B-only source")
    return text


def build(source: Path, output: Path, manifest: Path) -> dict:
    if len({source.resolve(), output.resolve(), manifest.resolve()}) != 3:
        raise ValueError("source, output, and manifest paths must differ")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".s10-hybrid-", dir=output.parent) as temp:
        base = Path(temp) / "validity.F"
        build_validity(source, base, Path(temp) / "validity.json", "mp237")
        midpoint, _ = _midpoint_policy(base.read_text(encoding="utf-8"))
    hybrid = inject_hybrid(midpoint)
    output.write_text(hybrid, encoding="utf-8")
    record = {
        "schema": "s10-midpoint-rate-zero-source-v1",
        "status": "PREPARED_NOT_RUN",
        "canonical_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "midpoint_sha256": hashlib.sha256(midpoint.encode()).hexdigest(),
        "hybrid_sha256": hashlib.sha256(hybrid.encode()).hexdigest(),
        "macro": MACRO,
        "midpoint_approved": False,
        "operational_default_changed": False,
        "macro_off_restores_midpoint_source": True,
        "consumers": [site[0] for site in SITES],
        "success_tag": "S10HYACT",
        "success_quantities": {
            "1418": "pgmlt is a capped mass amount; its qg/qr/temperature stores already used it without another dtcld",
            "2824": "pgdep is a mass rate; the qg/brs stores multiply the rate by dtcld",
            "2915": "pgevp is a mass rate; the later qg/brs/temperature stores multiply it by dtcld",
            "2916": "pgeml is a mass rate; the later qg/brs/temperature stores multiply it by dtcld",
        },
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
