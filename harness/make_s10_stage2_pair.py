"""Add one diagnostic-only stage-2 cold graupel pair to the S10 validity overlay."""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

try:
    import make_progb_validity_capture as validity
except ModuleNotFoundError:
    from harness import make_progb_validity_capture as validity

MACRO = "KDM6_S10_STAGE2_PAIR"
TARGET = {"step": 1, "lat": 2, "i": 142, "k": 17}
CALL_SITE_LINE = 418
COLD_QG_SITE = 2857
BRS_SITE_LINE = 2862
MASS_RATES = (
    "pgdep", "pgaut", "piacr", "praci", "psacr", "pracs", "pgaci",
    "paacw", "pgacr", "pgacs",
)
BRS_RATES = ("biacr", "braci", "bsacr", "bracs", "bgaci", "baacw", "bgacr")
# Do not read rhox for the density quotient: this tap must remain safe when its
# INTENT(OUT) producer was inactive. The resulting brs fields are a partial ledger.

_DECL_ANCHOR = "   real, dimension(its:ite,kts:kte)   :: falkc, work1c, work2c\n"
COLD_QG_ANCHOR = (
    "            qrs(i,k,3) = max(qrs(i,k,3)+(pgdep(i,k)+pgaut(i,k)                 &\n"
    "                           +piacr(i,k)*(1.-delta3)                             &\n"
    "                           +praci(i,k)*(1.-delta3)+psacr(i,k)*(1.-delta2)      &\n"
    "                           +pracs(i,k)*(1.-delta2)+pgaci(i,k)+paacw(i,k)       &\n"
    "                           +pgacr(i,k)+pgacs(i,k))*dtcld,0.)\n"
)
COLD_BRS_ANCHOR = (
    "            brs(i,k) = max(brs(i,k)+(pgdep(i,k)/rhox(i,k)+biacr(i,k)           &\n"
    "                           +braci(i,k)+bsacr(i,k)+bracs(i,k)+bgaci(i,k)        &\n"
    "                           +baacw(i,k)+bgacr(i,k))*dtcld,0.)\n"
)
_SHAPE_GENERIC_WRITE = (
    "         write(*,'(A,8(1X,I0),11(1X,ES24.16E3))') 'S10SHAPE', &\n"
    "           capture_step,lat,capture_last_site,capture_last_loop, &\n"
    "           capture_last_substep,i,k,merge(1,0,qrs_tmp(i,k,3).gt.qcrmin), &\n"
    "           qrs_tmp(i,k,3),brs(i,k),rhox(i,k),cmg(i,k),pidn0g(i,k), &\n"
    "           pvtg(i,k),bvtg(i,k),rslopegbmax(i,k),rslope(i,k,3), &\n"
    "           rslopeb(i,k,3),work1(i,k,3)\n"
)
_SHAPE_FIXED_BLOCK = (
    "   if (capture_enabled .and. capture_step.eq.1 .and. lat.eq.2) then\n"
    "     write(*,'(A,8(1X,I0),11(1X,ES24.16E3))') 'S10SHAPE', &\n"
    "       capture_step,lat,capture_last_site,capture_last_loop, &\n"
    "       capture_last_substep,142,17, &\n"
    "       merge(1,0,qrs_tmp(142,17,3).gt.qcrmin), &\n"
    "       qrs_tmp(142,17,3),brs(142,17),rhox(142,17), &\n"
    "       cmg(142,17),pidn0g(142,17),pvtg(142,17),bvtg(142,17), &\n"
    "       rslopegbmax(142,17),rslope(142,17,3),rslopeb(142,17,3), &\n"
    "       work1(142,17,3)\n"
    "   endif\n"
)


def _marker(label: str, code: str) -> str:
    return (f"! S10_PAIR_BEGIN:{label}\n#ifdef {MACRO}\n{code}"
            f"#endif\n! S10_PAIR_END:{label}\n")


def strip_pair(text: str) -> str:
    """Remove complete S10PAIR blocks and reject malformed leftovers."""
    while "! S10_PAIR_BEGIN:" in text:
        start = text.index("! S10_PAIR_BEGIN:")
        line_end = text.index("\n", start) + 1
        label = text[start + len("! S10_PAIR_BEGIN:"):line_end].strip()
        end_marker = f"! S10_PAIR_END:{label}\n"
        end = text.find(end_marker, line_end)
        if end < 0:
            raise ValueError(f"missing S10PAIR end marker for {label}")
        block = text[line_end:end]
        if not block.startswith(f"#ifdef {MACRO}\n") or not block.endswith("#endif\n"):
            raise ValueError(f"malformed S10PAIR block {label}")
        text = text[:start] + text[end + len(end_marker):]
    if f"#ifdef {MACRO}" in text:
        raise ValueError("unmarked S10PAIR preprocessor block remains")
    return text


def _replace_once(text: str, anchor: str, replacement: str, name: str) -> str:
    count = text.count(anchor)
    if count != 1:
        raise ValueError(f"{name}: expected one source anchor, found {count}")
    return text.replace(anchor, replacement, 1)


def _remove_s10shape_writes(text: str) -> tuple[str, int]:
    """Remove both potentially undefined-value S10SHAPE writes per slope site."""
    removed = 0
    for site in range(1, 8):
        begin = f"! S10_CAPTURE_BEGIN:slope_consumer_{site}\n"
        end_marker = f"! S10_CAPTURE_END:slope_consumer_{site}\n"
        start = text.find(begin)
        end = text.find(end_marker, start + len(begin)) if start >= 0 else -1
        if start < 0 or end < 0:
            raise ValueError(f"slope_consumer_{site}: expected one complete validity block")
        block = text[start:end + len(end_marker)]
        if block.count("'S10SHAPE'") != 2 or block.count("'S10SLP'") != 1:
            raise ValueError(f"slope_consumer_{site}: expected two S10SHAPE writes and one S10SLP")
        if block.count(_SHAPE_FIXED_BLOCK) != 1 or block.count(_SHAPE_GENERIC_WRITE) != 1:
            raise ValueError(f"slope_consumer_{site}: S10SHAPE source anchors changed")
        block = block.replace(_SHAPE_FIXED_BLOCK, "", 1)
        block = block.replace(_SHAPE_GENERIC_WRITE, "", 1)
        if "S10SHAPE" in block:
            raise ValueError(f"slope_consumer_{site}: unremoved S10SHAPE output remains")
        text = text[:start] + block + text[end + len(end_marker):]
        removed += 2
    if removed != 14 or text.count("'S10SHAPE'") != 0 or text.count("'S10SLP'") != 7:
        raise ValueError("pair overlay must remove exactly 7 callsites x 2 S10SHAPE writes")
    return text, removed


def _inject_pair(base_text: str) -> str:
    """Inject one cold stage-2 record around the canonical qg/brs assignments."""
    decl = (
        "#ifndef KDM6_PROGB_VALIDITY_CAPTURE\n"
        '#error "KDM6_S10_STAGE2_PAIR requires KDM6_PROGB_VALIDITY_CAPTURE"\n'
        "#endif\n"
        "   integer, parameter :: s10pair_word_kind = selected_int_kind(9)\n"
        "   real :: s10pair_qg_before, s10pair_brs_before\n"
    )
    text = _replace_once(base_text, _DECL_ANCHOR,
                         _DECL_ANCHOR + _marker("locals", decl), "locals")

    qg_before = (
        f"   if (capture_enabled .and. capture_step.eq.{TARGET['step']} .and. &\n"
        f"       lat.eq.{TARGET['lat']} .and. &\n"
        f"       i.eq.{TARGET['i']} .and. k.eq.{TARGET['k']}) then\n"
        "     s10pair_qg_before = qrs(i,k,3)\n"
        "     s10pair_brs_before = brs(i,k)\n"
        "   endif\n"
    )
    text = _replace_once(text, COLD_QG_ANCHOR,
                         _marker("cold_before", qg_before) + COLD_QG_ANCHOR,
                         "cold qg update")

    raw_fields = [
        "transfer(s10pair_qg_before,0_s10pair_word_kind)",
        "transfer(s10pair_brs_before,0_s10pair_word_kind)",
        "transfer(qrs(i,k,3),0_s10pair_word_kind)",
        "transfer(brs(i,k),0_s10pair_word_kind)",
        "transfer(dtcld,0_s10pair_word_kind)",
        *(f"transfer({name}(i,k),0_s10pair_word_kind)" for name in MASS_RATES),
        "transfer(delta2,0_s10pair_word_kind)",
        "transfer(delta3,0_s10pair_word_kind)",
        *(f"transfer({name}(i,k),0_s10pair_word_kind)" for name in BRS_RATES),
    ]
    if len(raw_fields) != 24:
        raise AssertionError("S10PAIR cold row must contain exactly 24 raw REAL(4) fields")
    raw_lines = []
    for start in range(0, len(raw_fields), 2):
        chunk = ", ".join(raw_fields[start:start + 2])
        continuation = ", &\n" if start + 2 < len(raw_fields) else "\n"
        raw_lines.append("       " + chunk + continuation)
    output = (
        f"   if (capture_enabled .and. capture_step.eq.{TARGET['step']} .and. &\n"
        f"       lat.eq.{TARGET['lat']} .and. &\n"
        f"       i.eq.{TARGET['i']} .and. k.eq.{TARGET['k']}) then\n"
        "     if (storage_size(0_s10pair_word_kind).ne.32 .or. &\n"
        "         storage_size(qrs(i,k,3)).ne.32) &\n"
        "       call wrf_error_fatal('S10PAIR requires 32-bit raw words')\n"
        "     write(*,'(A,12(1X,I0),24(1X,Z8.8))') 'S10PAIR', &\n"
        f"       capture_step,lat,{CALL_SITE_LINE},capture_last_site, &\n"
        f"       {COLD_QG_SITE},{BRS_SITE_LINE},loop, &\n"
        "       capture_last_loop,capture_last_substep,1,i,k, &\n"
        + "".join(raw_lines)
        + "   endif\n"
    )
    text = _replace_once(text, COLD_BRS_ANCHOR,
                         COLD_BRS_ANCHOR + _marker("cold_after", output),
                         "cold brs update")

    # Validate marker stripping first, then the existing overlay's own strip pass.
    if strip_pair(text) != base_text:
        raise ValueError("S10PAIR strip does not recover the validity overlay")
    raw_overlay = validity.strip_capture(strip_pair(text))
    if raw_overlay != validity.strip_capture(base_text):
        raise ValueError("combined strip does not recover canonical source")
    pair_blocks = []
    cursor = 0
    while True:
        start = text.find("! S10_PAIR_BEGIN:", cursor)
        if start < 0:
            break
        end = text.find("! S10_PAIR_END:", start)
        pair_blocks.append(text[start:end])
        cursor = end
    if any("rhox" in block.lower() for block in pair_blocks):
        raise ValueError("S10PAIR must not read or print rhox")
    return text


def build(source: Path, output: Path, manifest: Path) -> dict:
    resolved = (source.resolve(), output.resolve(), manifest.resolve())
    if len(set(resolved)) != 3:
        raise ValueError("source, overlay, and manifest paths must be distinct")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".s10-stage2-pair-", dir=output.parent) as temp:
        temp_path = Path(temp)
        base_path = temp_path / "module_mp_kdm6_cons.F"
        base_manifest = temp_path / "validity_manifest.json"
        base_record = validity.build(source, base_path, base_manifest, "mp237")
        base_text = base_path.read_text(encoding="utf-8")
        base_text, s10shape_removed = _remove_s10shape_writes(base_text)
        text = _inject_pair(base_text)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    output.write_text(text, encoding="utf-8")
    record = {
        "schema": "s10-stage2-cold-pair-overlay-v1",
        "execution_status": "PREPARED_NOT_RUN",
        "canonical_source_sha256": base_record["canonical_source_sha256"],
        "validity_overlay_sha256": base_record["capture_source_sha256"],
        "pair_base_overlay_sha256": hashlib.sha256(base_text.encode("utf-8")).hexdigest(),
        "pair_overlay_sha256": digest,
        "s10shape_numeric_writes_removed": s10shape_removed,
        "s10shape_numeric_writes_remaining": 0,
        "macro": MACRO,
        "strip_pair_exact": True,
        "strip_to_canonical_exact": True,
        "selection": TARGET,
        "context_fields": ["step", "lat", "kdm62D_call_site_line",
                           "preceding_progb_call_site", "qg_update_site_line",
                           "brs_update_site_line", "loop", "preceding_progb_loop",
                           "preceding_progb_substep_provenance", "phase", "i", "k"],
        "phase": {"1": "cold stage2 qg/brs update"},
        "cold_mass_rates": list(MASS_RATES),
        "delta_fields": ["delta2", "delta3"],
        "brs_nonrhox_volume_rate_fields": list(BRS_RATES),
        "unrecorded_brs_term": "pgdep/rhox (density OUT unassigned possible; never read by tap)",
        "state_fields": ["qg_before", "brs_before", "qg_after", "brs_after", "dtcld"],
        "numeric_encoding": "raw REAL(4) words as 8-digit hexadecimal via TRANSFER",
        "rhox_read_or_emitted_by_pair": False,
        "physical_updates_changed": False,
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
