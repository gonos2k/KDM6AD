"""Log one cold graupel mass, volume and heat update in the opt-in S10 path."""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

try:
    import make_s10_entry_rho_init as entry
    import make_s10_stage2_pair as pair
except ModuleNotFoundError:
    from harness import make_s10_entry_rho_init as entry
    from harness import make_s10_stage2_pair as pair


MACRO = "KDM6_S10_ENTRY_BUDGET"
DECL_ANCHOR = "   real, dimension(its:ite,kts:kte)   :: lamdr_tmp, lamdc_tmp, lamdi_tmp, nrs_pre_diag\n"
MASS_MARKER = "! S10_HYBRID_BEGIN:qg_mass_snapshot_2\n"
HEAT_START = "            xlf = xls-xl(i,k)\n            xlwork2 = -xls*(psdep(i,k)+pgdep(i,k)+pidep(i,k)+pinud(i,k))"
HEAT_END = "            t(i,k) = t(i,k)-xlwork2/cpm(i,k)*dtcld\n"
TARGET = ("capture_step.eq.1", "lat.eq.84", "i.eq.117", "k.eq.17", "loop.eq.1")


def _block(label: str, body: str) -> str:
    return f"! S10_BUD_BEGIN:{label}\n#ifdef {MACRO}\n{body}#endif\n! S10_BUD_END:{label}\n"


DECL = _block("declarations", "#ifndef KDM6_S10_ENTRY_RHO_INIT\n"
              '#error "S10BUD requires the entry-volume candidate"\n'
              "#endif\n"
              "   integer, parameter :: s10bud_word_kind = selected_int_kind(9)\n"
              "   integer :: s10bud_rhox_valid\n"
              "   real :: s10bud_qg_before,s10bud_brs_before,s10bud_t_before,s10bud_rhox\n")
GATE = "capture_enabled .and. " + " .and. &\n       ".join(TARGET)
BEFORE = _block("before_mass", f"   if ({GATE}) then\n"
                "     s10bud_qg_before = qrs(i,k,3)\n"
                "     s10bud_brs_before = brs(i,k)\n"
                "     s10bud_t_before = t(i,k)\n"
                "   endif\n")

FIELDS = (
    "s10bud_qg_before", "s10bud_brs_before", "s10bud_t_before",
    "qrs(i,k,3)", "brs(i,k)", "t(i,k)", "dtcld", "s10bud_rhox",
    "cpm(i,k)", "xlwork2", "xlf", "xls", "xl(i,k)",
    *(f"{name}(i,k)" for name in pair.MASS_RATES),
    "delta2", "delta3",
    *(f"{name}(i,k)" for name in pair.BRS_RATES),
    *(f"{name}(i,k)" for name in (
        "prevp", "psdep", "pidep", "pinud", "pmulcs", "pmulcg",
        "pmulrs", "pmulrg", "piacw")),
)
if len(FIELDS) != 41:
    raise ValueError("S10BUD requires 41 raw REAL4 fields")


def _after() -> str:
    words = [f"transfer({field},0_s10bud_word_kind)" for field in FIELDS]
    lines = []
    for start in range(0, len(words), 2):
        suffix = ", &\n" if start + 2 < len(words) else "\n"
        lines.append("       " + ", ".join(words[start:start + 2]) + suffix)
    return _block("after_heat", f"   if ({GATE}) then\n"
                  "     s10bud_rhox = 0.\n"
                  "     s10bud_rhox_valid = 0\n"
                  "     if (capture_rhox_assigned(i,k)) then\n"
                  "       s10bud_rhox = rhox(i,k)\n"
                  "       s10bud_rhox_valid = 1\n"
                  "     endif\n"
                  "     if (storage_size(0_s10bud_word_kind).ne.32 .or. &\n"
                  "         storage_size(qrs(i,k,3)).ne.32 .or. &\n"
                  "         storage_size(t(i,k)).ne.32) &\n"
                  "       call wrf_error_fatal('S10BUD requires REAL4 words')\n"
                  "     write(*,'(A,8(1X,I0),41(1X,Z8.8))') 'S10BUD', &\n"
                  "       capture_step,lat,capture_last_site,capture_last_loop, &\n"
                  "       capture_last_substep,i,k,s10bud_rhox_valid, &\n"
                  + "".join(lines)
                  + "     flush(6)\n"
                  "   endif\n")


AFTER = _after()


def inject_budget(base: str) -> str:
    for label, anchor in (("declarations", DECL_ANCHOR), ("mass", MASS_MARKER),
                          ("heat start", HEAT_START)):
        if base.count(anchor) != 1:
            raise ValueError(f"S10BUD {label} anchor is not unique")
    heat_start = base.index(HEAT_START)
    heat_end = base.index(HEAT_END, heat_start) + len(HEAT_END)
    text = base[:heat_end] + AFTER + base[heat_end:]
    text = text.replace(MASS_MARKER, BEFORE + MASS_MARKER, 1)
    text = text.replace(DECL_ANCHOR, DECL_ANCHOR + DECL, 1)
    if text.replace(DECL, "", 1).replace(BEFORE, "", 1).replace(AFTER, "", 1) != base:
        raise ValueError("S10BUD removal does not restore the entry candidate")
    return text


def build(source: Path, output: Path, manifest: Path) -> dict:
    if len({source.resolve(), output.resolve(), manifest.resolve()}) != 3:
        raise ValueError("source, output and manifest paths must differ")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".s10-bud-", dir=output.parent) as tmp:
        base_path = Path(tmp) / "entry.F"
        entry.build(source, base_path, Path(tmp) / "entry.json")
        base = base_path.read_text()
    text = inject_budget(base)
    output.write_text(text)
    record = {
        "schema": "s10-entry-budget-overlay-v1",
        "status": "PREPARED_NOT_RUN",
        "canonical_source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "entry_source_sha256": hashlib.sha256(base.encode()).hexdigest(),
        "budget_source_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "macro": MACRO,
        "target": {"step": 1, "lat": 84, "i": 117, "k": 17, "loop": 1},
        "fields": list(FIELDS),
        "rhox_read_only_when_assigned": True,
        "operational_default_changed": False,
        "physical_policy_approved": False,
    }
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(record, indent=2) + "\n")
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
