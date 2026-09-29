#!/usr/bin/env python3
"""Replay the selected S5 calc_ww_cp words with only the i call bounds changed.

The private routine is extracted from a pinned host source at run time; this
public script carries no private Fortran source or host inputs. Its result is a
local routine counterfactual, not a complete host or MPI recertification.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np


ROOT = Path(__file__).resolve().parent
TRACE = ROOT / "evidence/data/S5_G4_exact2_halo_stencil_trace_2026-09-25.npz"
SOURCE_SHA = "27ce690b27b24c80247a5551b48d37fc32fc47470d806cbef1bb859d58edc31c"
TRACE_SHA = "64488506cfb144a2383107ba250660deb2868b9d8fb7f0f7c7131528842ed1d7"
COLUMNS = (116, 117, 118, 233, 234, 235)
FLAGS = {
    "baseline": (),
    "novec": ("-fno-tree-vectorize",),
    "nocontract": ("-ffp-contract=off",),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def words(trace, column, field):
    key = f"serial__arg_s0_i{column}_{field}"
    other = f"x2__arg_s0_i{column}_{field}"
    a, b = trace[key], trace[other]
    if a.dtype != np.dtype(">u4") or not np.array_equal(a, b):
        raise ValueError(f"caller input differs or is not raw f32 words: {key}")
    return a.astype("<u4").view("<f4")


def make_input(trace, path):
    def full(shape, fill):
        return np.full(shape, fill, dtype="<f4", order="F")

    u, v = full((245, 40, 293), 0), full((245, 40, 293), 0)
    two_d = {name: full((245, 293), 1 if name != "mub" else 0)
             for name in ("mu_2", "mub", "msftx", "msfty", "msfux",
                          "msfuy", "msfvx", "msfvx_inv", "msfvy")}
    vertical = {name: full((40,), 0) for name in ("c1h", "c2h", "dnw")}
    for i in COLUMNS:
        prefix = i + 4                 # Fortran memory bound ims=-4
        u[prefix, :39, 4:288] = words(trace, i, "u_2")
        v[prefix, :39, 4:288] = words(trace, i, "v_2")
        for name, array in two_d.items():
            array[prefix, 4:288] = words(trace, i, name)
        # Check every declared input even where the routine uses a shared value.
        for name in vertical:
            if not np.array_equal(words(trace, i, name), words(trace, COLUMNS[0], name)):
                raise ValueError(f"vertical input {name} differs by column")
        for name in ("rdx", "rdy"):
            if not np.array_equal(words(trace, i, name), words(trace, COLUMNS[0], name)):
                raise ValueError(f"grid coefficient {name} differs by column")
    for name, array in vertical.items():
        array[:39] = words(trace, COLUMNS[0], name)
    first = COLUMNS[0]
    arrays = (u, v, two_d["mu_2"], two_d["mub"], vertical["c1h"],
              vertical["c2h"], two_d["msftx"], two_d["msfty"],
              two_d["msfux"], two_d["msfuy"], two_d["msfvx"],
              two_d["msfvx_inv"], two_d["msfvy"], vertical["dnw"],
              words(trace, first, "rdx"), words(trace, first, "rdy"))
    with path.open("wb") as stream:
        for array in arrays:
            stream.write(np.asfortranarray(array).tobytes(order="F"))


def extract_source(source, out):
    if sha(source) != SOURCE_SHA:
        raise ValueError("private calc_ww_cp source SHA does not match the S5 pin")
    text = source.read_text(encoding="ascii")
    begin = text.index("SUBROUTINE calc_ww_cp (")
    end = text.index("END SUBROUTINE calc_ww_cp", begin) + len("END SUBROUTINE calc_ww_cp")
    if text.find("SUBROUTINE calc_ww_cp (", begin + 1) != -1:
        raise ValueError("calc_ww_cp occurs more than once")
    out.write_text(text[begin:end] + "\n", encoding="ascii")


def compile_run(compiler, source, input_path, out, variant):
    folder = out / variant
    folder.mkdir()
    command = [compiler, "-O2", "-ftree-vectorize", "-funroll-loops",
               *FLAGS[variant], "-ffree-line-length-none", str(source),
               str(ROOT / "s5_calcww_bounds_driver.f90"), "-o", str(folder / "probe")]
    subprocess.run(command, check=True, cwd=folder)
    subprocess.run([str(folder / "probe"), str(input_path)], check=True, cwd=folder)
    return command


def output(out, variant, pair):
    a, b = (np.fromfile(out / variant / f"out{n}.bin", dtype="<u4")
            .reshape((40, 283), order="F") for n in pair)
    return np.concatenate((a[:, :142], b[:, 142:282]), axis=1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True,
                        help="private host dyn_em/module_big_step_utilities_em.F")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--compiler", default="/opt/homebrew/bin/gfortran")
    args = parser.parse_args()
    args.out = args.out.resolve()
    if args.out.exists():
        raise ValueError(f"output already exists: {args.out}")
    if sha(TRACE) != TRACE_SHA:
        raise ValueError("the checked-in S5 trace changed")
    args.out.mkdir(parents=True)
    extracted, input_path = args.out / "calc_ww_cp.f90", args.out / "input.bin"
    extract_source(args.source, extracted)
    with np.load(TRACE) as trace:
        make_input(trace, input_path)
        commands = {variant: compile_run(args.compiler, extracted, input_path,
                                         args.out, variant) for variant in FLAGS}
        results = {}
        for target, serial, x2 in ((117, (1, 3), (2, 4)),
                                   (234, (5, 7), (6, 8))):
            base_s, base_x = output(args.out, "baseline", serial), output(args.out, "baseline", x2)
            for label, got in (("serial", base_s), ("x2", base_x)):
                archived = trace[f"{label}__out_s2_g2_i{target}_ww"].astype("<u4")
                if not np.array_equal(got, archived):
                    raise ValueError(f"baseline {target} {label} does not replay archived stage-2 ww")
            row = {"baseline_bound_diffs": int(np.count_nonzero(base_s != base_x))}
            for variant in ("novec", "nocontract"):
                s, x = output(args.out, variant, serial), output(args.out, variant, x2)
                row[variant] = {
                    "bound_diffs": int(np.count_nonzero(s != x)),
                    "serial_vs_baseline": int(np.count_nonzero(s != base_s)),
                    "x2_vs_baseline": int(np.count_nonzero(x != base_x)),
                }
            results[str(target)] = row
    report = {"scope": "isolated_extracted_routine", "source_sha256": SOURCE_SHA,
              "trace_sha256": TRACE_SHA, "extracted_sha256": sha(extracted),
              "input_sha256": sha(input_path),
              "driver_sha256": sha(ROOT / "s5_calcww_bounds_driver.f90"),
              "compiler": args.compiler,
              "compiler_version": subprocess.check_output([args.compiler, "--version"], text=True).splitlines()[0],
              "commands": commands, "results": results}
    (args.out / "result.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
