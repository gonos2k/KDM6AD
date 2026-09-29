"""Build an isolated S10 host-entry volume initialization candidate."""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

try:
    from make_s10_midpoint_rate_zero import build as build_hybrid
except ModuleNotFoundError:
    from harness.make_s10_midpoint_rate_zero import build as build_hybrid


MACRO = "KDM6_S10_ENTRY_RHO_INIT"
ANCHOR = "! S10_CAPTURE_BEGIN:progb_site_1\n"
RHO_DECL = "  real, parameter   :: rho_mid = 400.      !kg m-3,  default graupel density\n"
ENTRY = (
    "! S10_ENTRY_RHO_BEGIN\n"
    f"#ifdef {MACRO}\n"
    "#ifndef KDM6_S10_MIDPOINT_RATE_ZERO\n"
    '#error "S10 entry rho initialization requires the hybrid guard"\n'
    "#endif\n"
    "   if (loop.eq.1) then\n"
    "   do k = kts, kte\n"
    "     do i = its, ite\n"
    "       if (qrs_tmp(i,k,3).gt.0. .and. brs(i,k).eq.0.) then\n"
    "         brs(i,k) = qrs_tmp(i,k,3)/400.\n"
    "         if (capture_enabled .and. capture_step.eq.1 .and. &\n"
    "             ((lat.eq.73 .and. (i.eq.113 .or. i.eq.115)) .or. &\n"
    "              (lat.eq.2 .and. i.eq.142 .and. k.eq.17))) then\n"
    "           if (storage_size(0_s10_hybrid_word_kind).ne.32 .or. &\n"
    "               storage_size(qrs_tmp(i,k,3)).ne.32 .or. &\n"
    "               storage_size(brs(i,k)).ne.32) &\n"
    "             call wrf_error_fatal('S10ENTRY requires REAL4 words')\n"
    "           write(*,'(A,5(1X,I0),2(1X,Z8.8))') 'S10ENTRY', &\n"
    "             capture_step,lat,i,k,1, &\n"
    "             transfer(qrs_tmp(i,k,3),0_s10_hybrid_word_kind), &\n"
    "             transfer(brs(i,k),0_s10_hybrid_word_kind)\n"
    "           flush(6)\n"
    "         endif\n"
    "       endif\n"
    "     enddo\n"
    "   enddo\n"
    "   endif\n"
    "#endif\n"
    "! S10_ENTRY_RHO_END\n"
)


def inject_entry(hybrid_source: str) -> str:
    if hybrid_source.count(ANCHOR) != 1 or hybrid_source.count(RHO_DECL) != 1:
        raise ValueError("missing unique S10 entry anchor or source rho_mid declaration")
    return hybrid_source.replace(ANCHOR, ENTRY + ANCHOR, 1)


def build(source: Path, output: Path, manifest: Path) -> dict:
    if len({source.resolve(), output.resolve(), manifest.resolve()}) != 3:
        raise ValueError("source, output, and manifest paths must differ")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".s10-entry-", dir=output.parent) as tmp:
        base = Path(tmp) / "hybrid.F"
        build_hybrid(source, base, Path(tmp) / "hybrid.json")
        hybrid = base.read_text(encoding="utf-8")
    rendered = inject_entry(hybrid)
    if rendered.replace(ENTRY, "", 1) != hybrid:
        raise ValueError("entry macro-off source differs from the hybrid")
    output.write_text(rendered, encoding="utf-8")
    record = {
        "schema": "s10-entry-rho-init-source-v1",
        "status": "PREPARED_NOT_RUN",
        "canonical_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "hybrid_base_sha256": hashlib.sha256(hybrid.encode()).hexdigest(),
        "candidate_sha256": hashlib.sha256(rendered.encode()).hexdigest(),
        "macro": MACRO,
        "entry_rule": "at loop 1 before first ProgB, when qg>0 and post-clamp brs=0 set brs=qg/400; includes active and trace qg",
        "rho_kg_m3": 400,
        "operational_default_changed": False,
        "physical_policy_approved": False,
        "macro_off_restores_hybrid_source": True,
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
