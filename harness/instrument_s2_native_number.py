"""Generate a dump-only mp37 source copy for the bounded S2 rain-number trace.

The canonical private host source is read and SHA-pinned but is never edited.
Instrumentation writes only to stdout and is enabled by a compile-time macro;
the solver expressions stay in their original positions and source order.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import difflib
from pathlib import Path


CANONICAL_SHA256 = "fc0a72d33a5e61803fea56eb9118018039c6da8b5775813032b4861a2bd66eb5"
MACRO = "KDM6_S2_NUMBER_CAPTURE"
SOURCE_RELATIVE = Path("phys/module_mp_kdm6.F")
CELL = {"host_j": 153, "host_i": 144}
INTEGER_REAL32 = {"mstep(i)"}


def _one(text: str, anchor: str, replacement: str) -> str:
    count = text.count(anchor)
    if count != 1:
        raise ValueError(f"expected one anchored source site, found {count}: {anchor[:90]!r}")
    return text.replace(anchor, replacement, 1)


def _n(text: str, anchor: str, replacement: str, occurrence: int,
       expected: int, *, after: bool = False) -> str:
    count = text.count(anchor)
    if count != expected or not 1 <= occurrence <= count:
        raise ValueError(
            f"expected {expected} sites and occurrence {occurrence}; found {count}: "
            f"{anchor[:90]!r}")
    start = -len(anchor)
    for _ in range(occurrence):
        start = text.find(anchor, start + len(anchor))
    if after:
        start += len(anchor)
    return text[:start] + replacement + text[start:]


def _emit(tag: str, f32: tuple[str, ...] = (), f64: tuple[str, ...] = (),
          flags: tuple[str, ...] = (), *, host: bool = False,
          sub: str = "0", loop: str | None = None,
          lat: str | None = None) -> str:
    lat_expr = lat or ("j" if host else "lat")
    loop_expr = loop or ("0" if host else "loop")
    fmt = "(A,1X,A,6(1X,I0)"
    if flags:
        fmt += f",{len(flags)}(1X,I0)"
    if f32:
        fmt += f",{len(f32)}(1X,Z8.8)"
    if f64:
        fmt += f",{len(f64)}(1X,Z16.16)"
    fmt += ")"
    args = ["'S2NR'", f"'{tag}'", "s2_step", lat_expr, "i", loop_expr,
            sub, "k"]
    args += [f"merge(1,0,{flag})" for flag in flags]
    args += [f"transfer({x},0)" for x in f32]
    args += [f"transfer({x},0_8)" for x in f64]
    return ("#ifdef " + MACRO + "\n"
            + f"            if ({lat_expr}=={CELL['host_j']} .and. i=={CELL['host_i']}) then\n"
            + f"              write(*,'{fmt}') &\n"
            + "                " + ", &\n                ".join(args) + "\n"
            + "            endif\n#endif\n")


def _f32(tag: str, names: tuple[str, ...], *, flags: tuple[str, ...] = (),
         host: bool = False, sub: str = "0") -> str:
    return _emit(tag, tuple(names), flags=flags, host=host, sub=sub)


def instrument(source: Path, output: Path, manifest: Path) -> dict:
    source = source.resolve()
    if output.resolve() == source:
        raise ValueError("instrumentation output must not replace canonical source")
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != CANONICAL_SHA256:
        raise ValueError(f"canonical mp37 source SHA256 changed: {digest}")
    original = raw.decode("utf-8")
    text = original
    schemas: dict[str, dict[str, list[str]]] = {}

    def add(tag: str, f32: tuple[str, ...] = (), f64: tuple[str, ...] = (),
            flags: tuple[str, ...] = (), *, host: bool = False,
            sub: str = "0", loop: str | None = None,
            lat: str | None = None) -> str:
        value_order = [
            {"kind": "i32" if name in INTEGER_REAL32 else "f32", "expr": name}
            for name in f32
        ] + [{"kind": "f64", "expr": name} for name in f64]
        schemas[tag] = {
            "flags": list(flags),
            "integer32": [name for name in f32 if name in INTEGER_REAL32],
            "real32": [name for name in f32 if name not in INTEGER_REAL32],
            "real64": list(f64),
            "value_order": value_order,
        }
        return _emit(tag, f32, f64, flags, host=host, sub=sub,
                     loop=loop, lat=lat)

    # The only mutable module-level state is a step label for stdout records.
    decl = (f"#ifdef {MACRO}\n   integer, save :: s2_step = 0\n#endif\n")
    text = _one(text, "!\n    contains\n", "!\n" + decl + "    contains\n")
    begin = (f"#ifdef {MACRO}\n"
             "   s2_step = itimestep\n"
             "#endif\n")
    entry_anchor = ("   do j = jts,jte\n"
                    "     do k = kts,kte\n"
                    "       do i = its,ite\n"
                    "         t(i,k) = th(i,k,j)*pii(i,k,j)\n")
    text = _one(text, entry_anchor, begin + entry_anchor)

    # Host storage into the kernel and kernel storage back to the host.
    host_fields = ("nr(i,k,j)", "qr(i,k,j)", "qc(i,k,j)", "q(i,k,j)",
                   "den(i,k,j)", "delz(i,k,j)")
    host_entry = "         nrs(i,k,1) = nr(i,k,j)     \n"
    text = _one(text, host_entry,
                add("HOST_ENTRY", host_fields, host=True) + host_entry)
    local_entry = "       nrs(i,k,1) = max(nrs(i,k,1),0.0)\n"
    local_fields = ("nrs(i,k,1)", "qrs(i,k,1)", "qci(i,k,1)",
                    "q(i,k)", "den(i,k)", "delz(i,k)")
    text = _n(text, local_entry,
              add("KERNEL_ENTRY", local_fields, loop="0", lat="lat"),
              occurrence=1, expected=2, after=True)
    host_return = "         nr(i,k,j) = nrs(i,k,1)   \n"
    kernel_return_fields = ("nrs(i,k,1)", "qrs(i,k,1)", "qci(i,k,1)",
                            "q(i,k,j)", "den(i,k,j)", "delz(i,k,j)")
    kernel_return = add("KERNEL_RETURN", kernel_return_fields, host=True)
    text = _one(text, host_return,
                kernel_return + host_return
                + add("HOST_RETURN", host_fields, host=True))

    # Rain-number DSD gate before sedimentation consumers and its final rewrite.
    dsd_gate = "          if(qrs(i,k,1).ge.qcrmin .and. nrs(i,k,1) .ge. nrmin) then\n"
    gate_pre = ("qrs(i,k,1).ge.qcrmin .and. nrs(i,k,1).ge.nrmin",)
    dsd_inputs = ("nrs(i,k,1)", "qrs(i,k,1)", "den(i,k)", "qcrmin",
                  "nrmin", "lamdarmin", "lamdarmax", "pidnr", "dmr")
    # First active DSD reconstruction (before warm/cold rain-number sources).
    text = _n(text, dsd_gate,
              add("DSD_PRE_GATE", dsd_inputs, flags=gate_pre),
              occurrence=1, expected=3)
    dsd_raw_anchor = "            n0r(i,k) = (1./g1pmr)*DBLE(nrs(i,k,1))*lamdr_tmp(i,k)**(mur+1)\n"
    text = _n(text, dsd_raw_anchor,
              add("DSD_PRE_RAW", ("nrs(i,k,1)", "qrs(i,k,1)",
                                                     "den(i,k)", "lamdr_tmp(i,k)"),
                                   ("n0r(i,k)",)),
              occurrence=1, expected=6, after=True)
    # The same DSD construction is repeated after the phase updates. Keeping
    # both observations preserves the source order before and after producers.
    text = _n(text, dsd_gate,
              add("DSD_POSTFREEZE_GATE", dsd_inputs, flags=gate_pre),
              occurrence=2, expected=3)
    text = _n(text, dsd_raw_anchor,
              add("DSD_POSTFREEZE_RAW", ("nrs(i,k,1)", "qrs(i,k,1)",
                                           "den(i,k)", "lamdr_tmp(i,k)"),
                  ("n0r(i,k)",)),
              occurrence=4, expected=6, after=True)
    text = _n(text, dsd_gate,
              add("DSD_FINAL_GATE", dsd_inputs, flags=gate_pre),
              occurrence=3, expected=3)
    dsd_lambda_end = "                         /(den(i,k)*qrs(i,k,1))))*(1./dmr))\n"
    text = _n(text, dsd_lambda_end,
              add("DSD_FINAL_RAW", ("nrs(i,k,1)", "qrs(i,k,1)",
                                     "den(i,k)", "qcrmin", "nrmin",
                                     "lamdarmin", "lamdarmax", "pidnr", "dmr",
                                     "lamdr_tmp(i,k)"),
                  flags=gate_pre),
              occurrence=3, expected=3, after=True)
    dsd_end = ("          endif\n"
               "          if(qci(i,k,1).ge.qmin .and. nci(i,k,1) .ge. ncmin ) then\n")
    post_dsd_fields = ("nrs(i,k,1)", "qrs(i,k,1)", "den(i,k)",
                       "qcrmin", "nrmin", "nrmax")
    for occurrence, tag in enumerate(("DSD_PRE_POST", "DSD_POSTFREEZE_POST",
                                      "DSD_FINAL_POST"), 1):
        text = _n(text, dsd_end, add(tag, post_dsd_fields, flags=gate_pre),
                  occurrence=occurrence, expected=3, after=True)
    nr_max_gate = "            if( nrs(i,k,1).gt.nrmax ) then\n"
    nr_max_fields = ("nrs(i,k,1)", "nrmax", "qrs(i,k,1)", "den(i,k)",
                     "lamdarmax", "pidnr", "dmr")
    text = _one(text, nr_max_gate,
                add("NR_MAX_GATE", nr_max_fields,
                    flags=("nrs(i,k,1).gt.nrmax",)) + nr_max_gate)

    # Rain-number autoconversion and the source-ordered donor-floor scaling.
    praut_gate = "         if(qci(i,k,1).gt.qcr(i,k) .and. nci(i,k,1).gt.ncmin) then\n"
    praut_inputs = ("nrs(i,k,1)", "qrs(i,k,1)", "qci(i,k,1)",
                    "nci(i,k,1)", "den(i,k)", "dtcld", "qcr(i,k)",
                    "ncmin", "nrmin", "qcrmin", "lenconcr")
    text = _one(text, praut_gate,
                add("NRAUT_GATE", praut_inputs,
                    flags=("qci(i,k,1).gt.qcr(i,k)",
                           "nci(i,k,1).gt.ncmin")) + praut_gate)
    raw_nraut = "           nraut(i,k) = (3.5e9)*den(i,k)*praut(i,k)\n"
    text = _one(text, raw_nraut,
                raw_nraut + add("NRAUT_BASE", ("praut(i,k)", "nraut(i,k)",
                                                "den(i,k)", "nrs(i,k,1)",
                                                "qrs(i,k,1)")))
    proportional_nraut = ("           if(qrs(i,k,1).gt.lenconcr)                                           &\n"
                          "           nraut(i,k) = nrs(i,k,1)/qrs(i,k,1)*praut(i,k)\n")
    text = _one(text, proportional_nraut,
                proportional_nraut + add("NRAUT_DSD_BRANCH",
                                          ("praut(i,k)", "nraut(i,k)",
                                           "nrs(i,k,1)", "qrs(i,k,1)",
                                           "lenconcr"),
                                          flags=("qrs(i,k,1).gt.lenconcr",)))
    nraut_cap = "           nraut(i,k) = min(nraut(i,k),nci(i,k,1)/dtcld)\n"
    text = _one(text, nraut_cap,
                nraut_cap + add("NRAUT_DONOR_CAP", ("nraut(i,k)",
                                                      "nci(i,k,1)", "dtcld")))

    # The floor cap used when applying the rain-number process bundle.
    rain_value = "            value = max(nrmin,nrs(i,k,1))\n"
    rain_source = ("            source = (-nraut(i,k)+nraci(i,k)+nrcol(i,k)+niacr(i,k)+nsacr(i,k)+ngacr(i,k))*dtcld\n"
                   "            if (source.gt.value) then\n")
    limit_fields = ("nrs(i,k,1)", "nrmin", "value", "source", "dtcld",
                    "nraut(i,k)", "nraci(i,k)", "nrcol(i,k)",
                    "niacr(i,k)", "nsacr(i,k)", "ngacr(i,k)")
    rain_source_value = "            source = (-nraut(i,k)+nraci(i,k)+nrcol(i,k)+niacr(i,k)+nsacr(i,k)+ngacr(i,k))*dtcld\n"
    text = _one(text, rain_source_value,
                rain_source_value + add("NR_LIMIT_PRE", limit_fields,
                                        flags=("source.gt.value",)))
    # Record all scaled rates after the cap, including the no-cap branch.
    limit_end = "            endif\n\n            work2(i,k)=-(prevp(i,k)+psdep(i,k)+pgdep(i,k)+pinud(i,k)+pidep(i,k))\n"
    text = _one(text, limit_end,
                "            endif\n" + add("NR_LIMIT_POST", limit_fields,
                                           flags=("source.gt.value",))
                + "\n            work2(i,k)=-(prevp(i,k)+psdep(i,k)+pgdep(i,k)+pinud(i,k)+pidep(i,k))\n")
    cold_source = ("            source = (-nraut(i,k)+nrcol(i,k)-nseml(i,k)-ngeml(i,k)             &\n"
                   "                      )*dtcld\n")
    cold_limit_fields = ("nrs(i,k,1)", "nrmin", "value", "source", "dtcld",
                         "nraut(i,k)", "nrcol(i,k)", "nseml(i,k)", "ngeml(i,k)")
    text = _one(text, cold_source,
                cold_source + add("NR_LIMIT_COLD_PRE", cold_limit_fields,
                                  flags=("source.gt.value",)))
    cold_limit_end = ("            endif\n!\n"
                      "            work2(i,k)=-(prevp(i,k)+psevp(i,k)+pgevp(i,k))\n")
    text = _one(text, cold_limit_end,
                "            endif\n" + add("NR_LIMIT_COLD_POST", cold_limit_fields,
                                           flags=("source.gt.value",))
                + "!\n            work2(i,k)=-(prevp(i,k)+psevp(i,k)+pgevp(i,k))\n")

    # Actual source-ordered rain-number state update in warm and cold branches.
    warm_update = ("            nrs(i,k,1) = max(nrs(i,k,1)+(nraut(i,k)-nrcol(i,k)-niacr(i,k)      &\n"
                    "                           -nraci(i,k)-nsacr(i,k)-ngacr(i,k))*dtcld,0.)\n")
    update_fields = ("nrs(i,k,1)", "nraut(i,k)", "nrcol(i,k)", "niacr(i,k)",
                     "nraci(i,k)", "nsacr(i,k)", "ngacr(i,k)", "dtcld")
    text = _one(text, warm_update,
                add("NR_UPDATE_WARM_PRE", update_fields) + warm_update
                + add("NR_UPDATE_WARM_POST", update_fields))
    cold_update = ("            nrs(i,k,1) = max(nrs(i,k,1)+(nraut(i,k)-nrcol(i,k)+nseml(i,k)      &\n"
                    "                           +ngeml(i,k))*dtcld,0.)\n")
    cold_fields = ("nrs(i,k,1)", "nraut(i,k)", "nrcol(i,k)", "nseml(i,k)",
                   "ngeml(i,k)", "dtcld")
    text = _one(text, cold_update,
                add("NR_UPDATE_COLD_PRE", cold_fields) + cold_update
                + add("NR_UPDATE_COLD_POST", cold_fields))

    # Number added to rain by direct snow/graupel melting and removed by freezing.
    snow_melt = "                nrs(i,k,1) = nrs(i,k,1) - sfac*psmlt(i,k)\n"
    melt_fields = ("nrs(i,k,1)", "sfac", "psmlt(i,k)", "qrs(i,k,2)",
                   "qcrmin", "den(i,k)", "q(i,k)")
    text = _one(text, snow_melt,
                add("NR_SNOW_MELT_PRE", melt_fields) + snow_melt
                + add("NR_SNOW_MELT_POST", melt_fields))
    graup_melt = "                nrs(i,k,1) = nrs(i,k,1) - gfac*pgmlt(i,k)\n"
    graup_fields = ("nrs(i,k,1)", "gfac", "pgmlt(i,k)", "qrs(i,k,3)",
                    "qcrmin", "den(i,k)", "q(i,k)")
    text = _one(text, graup_melt,
                add("NR_GRAUPEL_MELT_PRE", graup_fields) + graup_melt
                + add("NR_GRAUPEL_MELT_POST", graup_fields))
    freeze_nr = ("              nrs(i,k,1) = nrs(i,k,1) - nfrzdtr\n")
    freeze_fields = ("nrs(i,k,1)", "nfrzdtr", "n0r(i,k)", "qrs(i,k,1)",
                     "den(i,k)", "nrmin", "q(i,k)")
    text = _one(text, freeze_nr,
                add("NR_FREEZE_PRE", ("nrs(i,k,1)", "qrs(i,k,1)",
                                       "den(i,k)", "nrmin", "q(i,k)"),
                    ("nfrzdtr", "n0r(i,k)")) + freeze_nr
                + add("NR_FREEZE_POST", ("nrs(i,k,1)", "qrs(i,k,1)",
                                          "den(i,k)", "nrmin", "q(i,k)"),
                      ("nfrzdtr", "n0r(i,k)")))

    # Applied top loss and paired interior mass/number transfers.
    top_nr = "           nrs(i,k,1) = max(nrs(i,k,1)-falkn(i,k,1)*dtcld,0.)\n"
    top_fields = ("nrs(i,k,1)", "falkn(i,k,1)", "falk(i,k,1)",
                  "den(i,k)", "dend(i,k)",
                  "q(i,k)", "delz(i,k)", "mstep(i)", "dtcld", "qrs(i,k,1)")
    top_before = add("NR_TOP_PRE", top_fields, host=False, sub="n")
    top_after = add("NR_TOP_POST", top_fields, host=False, sub="n")
    before_qr_top = "           qrs(i,k,1) = max(qrs(i,k,1)-falk(i,k,1)*dtcld/dend(i,k),0.)\n"
    text = _one(text, before_qr_top, top_before + before_qr_top)
    text = _one(text, top_nr, top_nr + top_after)

    face_nr = "             nrs(i,k,1) = max(nrs(i,k,1)-dnr(i,k)+dnr(i,k+1),0.)\n"
    face_qr = "             qrs(i,k,1) = max(qrs(i,k,1)-dqr(i,k)+dqr(i,k+1),0.)\n"
    face_fields = ("nrs(i,k,1)", "dnr(i,k)", "dnr(i,k+1)",
                   "nrs(i,k+1,1)",
                   "qrs(i,k,1)", "dqr(i,k)", "dqr(i,k+1)",
                   "qrs(i,k+1,1)",
                   "falkn(i,k,1)", "falkn(i,k+1,1)",
                   "falk(i,k,1)", "falk(i,k+1,1)",
                   "den(i,k)", "den(i,k+1)", "dend(i,k)", "dend(i,k+1)",
                   "q(i,k)", "q(i,k+1)", "delz(i,k)", "delz(i,k+1)",
                   "mstep(i)", "dtcld")
    face_pre = add("NR_FACE_PRE", face_fields, sub="n")
    face_post = add("NR_FACE_POST", face_fields, sub="n")
    text = _one(text, face_nr, face_pre + face_nr)
    text = _one(text, face_qr, face_qr + face_post)

    # Host return is before the Fortran caller resumes its RK/dynamics work.
    end_anchor = "   end subroutine kdm6\n"
    text = _one(text, end_anchor, end_anchor)

    # All additions are removable as CPP capture blocks. The underlying solver
    # source must be byte-for-byte recoverable after removing only these blocks.
    stripped = re.sub(rf"#ifdef {MACRO}\n.*?#endif\n", "", text, flags=re.S)
    if stripped != original:
        diff = "".join(list(difflib.unified_diff(original.splitlines(True),
                                                  stripped.splitlines(True)))[:60])
        raise ValueError("capture insertion changed source outside CPP-guarded blocks:\n" + diff)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text)
    result = {
        "schema": "s2-mp37-number-capture-source-v1",
        "canonical_source": str(source),
        "canonical_source_sha256": digest,
        "capture_source": str(output.resolve()),
        "capture_source_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "macro": MACRO,
        "selected_host_cell_1_based": CELL,
        "stripped_exact": True,
        "tags": schemas,
    }
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host-root", type=Path, required=True,
                    help="private KIM-meso_v1.0 tree; read-only")
    ap.add_argument("--output", type=Path, required=True,
                    help="isolated shadow source destination")
    ap.add_argument("--manifest", type=Path, required=True)
    args = ap.parse_args()
    print(json.dumps(instrument(args.host_root / SOURCE_RELATIVE,
                                args.output, args.manifest), indent=2))


if __name__ == "__main__":
    main()
