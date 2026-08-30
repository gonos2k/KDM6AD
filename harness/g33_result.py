"""The result record of one refinement run: five fields, one file.

    {
      "commit":        "<git sha>"  or  "<git sha>+dirty",
      "command":       ["--fixture", ..., "--algo", ..., ...],   the producer's own argv
      "binary_sha256": sha256 of the driver executable that ran,
      "input_sha256":  sha256 over (fixture bytes, kernel module bytes, rho profile),
      "result":        {"members": [...], "analyses": [...]}   the files the run left, digested
    }

That is what a bundle says about itself. `identity()` is a digest of the first
four; two runs with the same identity are the same experiment and share one
immutable bundle. `verify()` holds a bundle to its record: every file the
record names is present, inside the bundle, and has the digest recorded.

`convert()` reads the manifest.json of a bundle made before this format and
writes the same five fields; the raw streams and analysis files are untouched.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import g33_refine_analyze as ra   # noqa: E402  the strict member parser

FILE = "result.json"

#: Which analyses are DEFINED at which precision. An analysis not listed is
#: refused rather than assumed valid everywhere.
ANALYSIS_PRECISIONS = {
    "matched_closure": ("f32", "f64"),
    "cap_interface": ("f32", "f64"),
    "extension_protocol": ("f32", "f64"),
    "dual_ledger": ("f32", "f64"),
    "defect_magnitude": ("f32", "f64"),
    "substep_schedule": ("f32", "f64"),
    "water_enthalpy_basis": ("f32", "f64"),
    "internal_cap_enthalpy": ("f32", "f64"),
    "metric_trajectory": ("f32",),
    "ncmin_locality": ("f32",),
    "qr_process_ledger": ("f32",),
}


#: The analyses an INSTRUMENTED (--nflux) bundle carries for every member.
REQUIRED_WHEN_INSTRUMENTED = ("matched_closure", "cap_interface",
                              "extension_protocol", "dual_ledger",
                              "defect_magnitude", "internal_cap_enthalpy",
                              "substep_schedule", "water_enthalpy_basis")


def applicable(analysis: str, precision: str) -> bool:
    if analysis not in ANALYSIS_PRECISIONS:
        raise KeyError(f"{analysis!r} has no declared precision applicability; "
                       f"add it to ANALYSIS_PRECISIONS rather than letting it "
                       f"default to valid")
    return precision in ANALYSIS_PRECISIONS[analysis]


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(*args, cwd=None) -> str | None:
    """git's answer, or None when git cannot answer (no repo, no HEAD)."""
    r = subprocess.run(["git", *args], cwd=cwd or HERE.parent,
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def repo_relative(path: Path) -> str:
    p = Path(path).resolve()
    try:
        return str(p.relative_to(HERE.parent))
    except ValueError:
        return str(p)


_NAME = re.compile(r"^n(\d+)\.(carry|rezero)\.txt$")


def member_entry(path: Path, reader=None) -> dict:
    """One raw member, admitted through the STRICT parser. `reader` describes
    a member that is not G33R (the f64 instrument arm)."""
    if reader is not None:
        return reader(path)
    m = _NAME.match(path.name)
    if not m:
        raise ra.RefineError(f"{path.name}: not n<N>.<carry|rezero>.txt")
    r = ra.read(path, nsplit=int(m.group(1)))      # raises on anything malformed
    if r[("meta", "mode")] != m.group(2):
        raise ra.RefineError(f"{path.name}: filename says mode {m.group(2)}, "
                             f"stream says {r[('meta', 'mode')]}")
    out = {"file": path.name, "sha256": sha256(path),
           "nsplit": r[("meta", "nsplit")], "mode": r[("meta", "mode")],
           "algorithm": r[("meta", "algorithm")]}
    for k in ("delt", "loops", "dtcld"):
        if ("meta", k) in r:
            out[k] = r[("meta", k)]
    return out


def input_digest_from(fixture_sha256: str, module_sha256: str,
                      rho_profile: str) -> str:
    return hashlib.sha256(
        f"{fixture_sha256}\n{module_sha256}\n{rho_profile}\n".encode()).hexdigest()


def input_digest(fixture: Path, module: Path, rho_profile: str) -> str:
    return input_digest_from(sha256(fixture), sha256(module), rho_profile)


def record(*, commit: str | None, dirty: bool, command: list,
           binary_sha256: str, input_sha256: str,
           members: list, analyses: list) -> dict:
    if not commit:
        raise SystemExit("REFUSED: git could not name the commit, so the record "
                         "cannot say what code ran")
    return {
        "commit": commit + ("+dirty" if dirty else ""),
        "command": list(command),
        "binary_sha256": binary_sha256,
        "input_sha256": input_sha256,
        "result": {"members": list(members), "analyses": list(analyses)},
    }


def identity(rec: dict) -> str:
    """Same commit, same command, same binary, same input: the same run. A
    dirty tree does not change the identity -- it is recorded, not hashed --
    so an unrelated edit does not re-publish an experiment."""
    core = {"commit": rec["commit"].split("+")[0], "command": rec["command"],
            "binary_sha256": rec["binary_sha256"],
            "input_sha256": rec["input_sha256"]}
    return hashlib.sha256(json.dumps(core, sort_keys=True).encode()).hexdigest()


def write(bundle: Path, rec: dict) -> Path:
    p = Path(bundle) / FILE
    p.write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n")
    return p


def load(bundle: Path) -> dict:
    p = Path(bundle) / FILE
    if not p.is_file():
        raise SystemExit(f"REFUSED: {bundle} has no {FILE}")
    try:
        rec = json.loads(p.read_text())
    except ValueError as e:
        raise SystemExit(f"REFUSED: {p} will not parse: {e}")
    missing = [k for k in ("commit", "command", "binary_sha256",
                           "input_sha256", "result") if k not in rec]
    if missing:
        raise SystemExit(f"REFUSED: {p} lacks {missing}")
    return rec


def payload_state(p: Path, want: str, root: Path) -> str:
    """Presence, containment and digest of one payload, in one answer."""
    if p.is_symlink() or (p.exists() and not p.is_file()):
        return "NOT-SELF-CONTAINED"
    if not p.is_file():
        return "absent"
    try:
        if p.resolve().parent != root.resolve():
            return "NOT-SELF-CONTAINED"
    except OSError:
        return "NOT-SELF-CONTAINED"
    return "matches" if sha256(p) == want else "MISMATCH"


def _entries(rec: dict):
    res = rec.get("result") or {}
    for row in (res.get("members") or []) + (res.get("analyses") or []):
        if isinstance(row, dict) and row.get("file"):
            yield row["file"], row.get("sha256") or row.get("output_sha256")
            for src in row.get("inputs") or []:
                if isinstance(src, dict) and src.get("file"):
                    yield src["file"], src.get("sha256")


def verify(bundle: Path) -> list:
    """Every file the record names, held to the record. Empty means sound."""
    bundle = Path(bundle)
    rec = load(bundle)
    bad = []
    exe = bundle / "g33_refine_driver"
    st = payload_state(exe, rec["binary_sha256"], bundle)
    if st != "matches":
        bad.append(f"g33_refine_driver: {st} (binary_sha256 names another executable)")
    for name, want in _entries(rec):
        st = payload_state(bundle / name, want, bundle)
        if st != "matches":
            bad.append(f"{name}: {st}")
    return bad


_PIN_KEYS = ("analyzer", "analyzer_sha256", "analyzer_commit", "analyzer_blob_sha")


def convert(man: dict) -> dict:
    """The five fields, read out of a pre-format manifest.json."""
    members = [dict(m) for m in man.get("members") or []]
    for m in members:
        if "output_sha256" in m and "sha256" not in m:
            m["sha256"] = m.pop("output_sha256")
    analyses = [{k: v for k, v in a.items() if k not in _PIN_KEYS}
                for a in man.get("analyses") or []]
    fixture = Path(man.get("fixture_path") or "").stem
    modes = sorted({m.get("mode") for m in members if m.get("mode")})
    nsplits = sorted({int(m["nsplit"]) for m in members if "nsplit" in m})
    command = ["--fixture", fixture, "--algo", man.get("algorithm") or "legacy"]
    if modes:
        command += ["--mode", modes[0]]
    if nsplits:
        command += ["--nsplit", ",".join(map(str, nsplits))]
    if man.get("instrumented"):
        command += ["--nflux"]
    command += ["--rho-profile", man.get("rho_profile") or "as-is",
                "--arm", man.get("arm") or "reference"]
    if man.get("nonstandard_module"):
        command += ["--module-override", man.get("module_path") or "?"]
    binary = None
    for a in man.get("build_artifacts") or []:
        if isinstance(a, dict) and a.get("file") == "g33_refine_driver":
            binary = a.get("sha256")
    if binary is None:
        binary = ((man.get("build_provenance") or {}).get("executable_sha256")
                  or "unrecorded")
    return record(commit=man.get("repo_commit"), dirty=bool(man.get("tree_dirty")),
                  command=command, binary_sha256=binary,
                  input_sha256=input_digest_from(man.get("fixture_sha256") or "",
                                                 man.get("module_sha256") or "",
                                                 man.get("rho_profile") or "as-is"),
                  members=members, analyses=analyses)


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("convert", help="write result.json from a bundle's manifest.json")
    c.add_argument("bundle", type=Path, nargs="+")
    v = sub.add_parser("verify", help="hold a bundle to its result.json")
    v.add_argument("bundle", type=Path, nargs="+")
    a = ap.parse_args(argv)
    rc = 0
    for b in a.bundle:
        if a.cmd == "convert":
            man = json.loads((b / "manifest.json").read_text())
            rec = convert(man)
            if (b / "g33_refine_driver").is_file():
                rec["binary_sha256"] = sha256(b / "g33_refine_driver")
            write(b, rec)
            print(f"{b}: {FILE} written, identity {identity(rec)[:16]}")
        else:
            bad = verify(b)
            print(f"{b}: " + ("sound" if not bad else "\n  " + "\n  ".join(bad)))
            rc |= bool(bad)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
