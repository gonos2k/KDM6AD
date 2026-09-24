"""Make an isolated, dump-only mp37 source for one selected phase event.

The canonical private host source is read but never edited. The original
expressions remain in place; duplicate raw-request expressions are evaluated
only for diagnostics. A control-vs-instrumented native run must establish
noninterference before these records can be used as evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

CANONICAL_SHA256 = "fc0a72d33a5e61803fea56eb9118018039c6da8b5775813032b4861a2bd66eb5"
CONDITION = "lat.eq.97 .and. i.eq.173 .and. k.eq.22"


def _one(text: str, anchor: str, replacement: str) -> str:
    if text.count(anchor) != 1:
        raise ValueError(f"expected exactly one anchored source site: {anchor[:70]!r}")
    return text.replace(anchor, replacement, 1)


def _raw_min_arg(text: str, name: str, reservoir: str) -> str:
    prefix = f"            {name} = min("
    if text.count(prefix) != 1:
        raise ValueError(f"expected one {name} request source")
    start = text.index(prefix) + len(prefix)
    end = text.index(f",{reservoir})", start)
    expression = text[start:end]
    lines = [line for line in expression.splitlines()
             if not line.lstrip().startswith("!")]
    clean = "\n".join(lines).rstrip()
    if clean.endswith("&"):
        clean = clean[:-1].rstrip()
    return clean


def _hex4(expr: str) -> str:
    return f"transfer({expr},0)"


def _hex8(expr: str) -> str:
    return f"transfer({expr},0_8)"


def _emit(stage: str, f32: tuple[str, ...], f64: tuple[str, ...] = (),
          *, fixed_cell: bool = False, flags: tuple[str, ...] = ()) -> str:
    fmt = f"(A,1X,A,4(1X,I0)"
    if flags:
        fmt += f",{len(flags)}(1X,I0)"
    fmt += f",{len(f32)}(1X,Z8.8)"
    if f64:
        fmt += f",{len(f64)}(1X,Z16.16)"
    fmt += ")"
    args = ["'X2PHASE'", f"'{stage}'", "loop", "lat",
            "173" if fixed_cell else "i", "22" if fixed_cell else "k"]
    args += list(flags)
    args += [_hex4(x) for x in f32]
    args += [_hex8(x) for x in f64]
    # Continuation lines prevent a diagnostic line from depending on the
    # compiler's free-form source-line limit.
    return (f"            write(*,'{fmt}') &\n"
            + "              " + ", &\n              ".join(args) + "\n")


def build(source: Path, output: Path, manifest: Path) -> dict:
    original = source.read_bytes()
    digest = hashlib.sha256(original).hexdigest()
    if digest != CANONICAL_SHA256:
        raise ValueError(f"canonical mp37 source SHA256 changed: {digest}")
    text = original.decode("utf-8")
    request = {
        "pinuc": _raw_min_arg(text, "pinuc", "qci(i,k,1)"),
        "ninuc": _raw_min_arg(text, "ninuc", "nci(i,k,1)"),
        "pfrzdtc": _raw_min_arg(text, "pfrzdtc", "qci(i,k,1)"),
        "nfrzdtc": _raw_min_arg(text, "nfrzdtc", "nci(i,k,1)"),
    }
    declaration = ("#ifdef KDM6_PHASE_CAPTURE\n"
                   "   double precision :: phase_pinuc_raw, phase_ninuc_raw\n"
                   "   double precision :: phase_pfrzdtc_raw, phase_nfrzdtc_raw\n"
                   "   double precision :: phase_ninuc_applied, phase_nfrzdtc_applied\n"
                   "   logical :: phase_ninuc_valid, phase_nfrzdtc_valid\n"
                   "#endif\n")
    text = _one(text, "   double precision   :: pinuc,ninuc\n",
                "   double precision   :: pinuc,ninuc\n" + declaration)
    before2 = ("#ifdef KDM6_PHASE_CAPTURE\n"
               f"          if ({CONDITION}) then\n"
               f"            phase_pinuc_raw = {request['pinuc']}\n"
               "            phase_ninuc_raw = 0.d0\n"
               "            phase_ninuc_valid = nci(i,k,1).gt.ncmin\n"
               "            if (phase_ninuc_valid) then\n"
               f"              phase_ninuc_raw = {request['ninuc']}\n"
               "            endif\n"
               + _emit("D2_PRE", ("qci(i,k,1)", "qci(i,k,2)",
                                  "nci(i,k,1)", "nci(i,k,2)", "t(i,k)",
                                  "xlf", "cpm(i,k)"),
                       ("phase_pinuc_raw", "phase_ninuc_raw"),
                       flags=("merge(1,0,phase_ninuc_valid)",))
               + "          endif\n#endif\n")
    text = _one(text, "            pinuc = min(", before2 + "            pinuc = min(")
    post2_anchor = "            t(i,k) = t(i,k) + xlf/cpm(i,k)*pinuc \n"
    after2 = ("#ifdef KDM6_PHASE_CAPTURE\n"
              f"          if ({CONDITION}) then\n"
              "            phase_ninuc_applied = 0.d0\n"
              "            if (phase_ninuc_valid) phase_ninuc_applied = ninuc\n"
              + _emit("D2_POST", ("qci(i,k,1)", "qci(i,k,2)",
                                    "nci(i,k,1)", "nci(i,k,2)", "t(i,k)"),
                      ("pinuc", "phase_ninuc_applied"),
                      flags=("merge(1,0,phase_ninuc_valid)",))
              + "          endif\n#endif\n")
    text = _one(text, post2_anchor, post2_anchor + after2)
    before3 = ("#ifdef KDM6_PHASE_CAPTURE\n"
               f"          if ({CONDITION}) then\n"
               f"            phase_pfrzdtc_raw = {request['pfrzdtc']}\n"
               "            phase_nfrzdtc_raw = 0.d0\n"
               "            phase_nfrzdtc_valid = nci(i,k,1).gt.ncmin\n"
               "            if (phase_nfrzdtc_valid) then\n"
               f"              phase_nfrzdtc_raw = {request['nfrzdtc']}\n"
               "            endif\n"
               + _emit("D3_PRE", ("qci(i,k,1)", "qci(i,k,2)",
                                  "nci(i,k,1)", "nci(i,k,2)", "t(i,k)",
                                  "xlf", "cpm(i,k)"),
                       ("phase_pfrzdtc_raw", "phase_nfrzdtc_raw"),
                       flags=("merge(1,0,phase_nfrzdtc_valid)",))
               + "          endif\n#endif\n")
    text = _one(text, "            pfrzdtc = min(", before3 + "            pfrzdtc = min(")
    post3_anchor = "            t(i,k) = t(i,k) + xlf/cpm(i,k)*(pfrzdtc)\n"
    after3 = ("#ifdef KDM6_PHASE_CAPTURE\n"
              f"          if ({CONDITION}) then\n"
              "            phase_nfrzdtc_applied = 0.d0\n"
              "            if (phase_nfrzdtc_valid) phase_nfrzdtc_applied = nfrzdtc\n"
              + _emit("D3_POST", ("qci(i,k,1)", "qci(i,k,2)",
                                    "nci(i,k,1)", "nci(i,k,2)", "t(i,k)"),
                      ("pfrzdtc", "phase_nfrzdtc_applied"),
                      flags=("merge(1,0,phase_nfrzdtc_valid)",))
              + "          endif\n#endif\n")
    text = _one(text, post3_anchor, post3_anchor + after3)
    # Later stages are separate measurements, never added to D2/D3's ledger.
    later_condition = ("lat.eq.97 .and. its.le.173 .and. ite.ge.173 "
                       ".and. kts.le.22 .and. kte.ge.22")
    later = lambda stage: ("#ifdef KDM6_PHASE_CAPTURE\n"
                           f"   if ({later_condition}) then\n"
                           + _emit(stage, ("qci(173,22,1)", "qci(173,22,2)",
                                           "nci(173,22,1)", "nci(173,22,2)",
                                           "t(173,22)"), fixed_cell=True)
                           + "   endif\n#endif\n")
    state_anchor = "   call slope_kdm6(qrs_tmp,qci_tmp,nrs_tmp,nci_tmp,den_tmp,denfac,t,rslope,  &\n"
    # The source calls slope_kdm6 more than once. Target the unique post-state
    # dump landmark, immediately before the later slope call.
    landmark = "   ! per-substep parity dump: POST-STATE-UPDATE"
    at = text.index(landmark)
    pos = text.index(state_anchor, at)
    text = text[:pos] + later("POST_STATE_UPDATE") + text[pos:]
    final_anchor = "   enddo                  ! big loops\n"
    text = _one(text, final_anchor, later("FINAL") + final_anchor)
    if output.resolve() == source.resolve():
        raise ValueError("instrumentation must not overwrite canonical source")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text)
    result = {
        "source_sha256": digest,
        "instrumented_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "selection_fortran_1_based": {"j": 97, "i": 173, "k": 22},
        "macro": "KDM6_PHASE_CAPTURE",
        "records_per_executed_event": ["D2_PRE", "D2_POST", "D3_PRE", "D3_POST",
                                       "POST_STATE_UPDATE", "FINAL"],
        "unmodified_solver_min_expressions": True,
    }
    manifest.write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    a = parser.parse_args()
    print(json.dumps(build(a.source, a.output, a.manifest), indent=2))


if __name__ == "__main__":
    main()
