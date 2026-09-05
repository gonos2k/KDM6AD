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
immutable bundle. `load()` checks this record shape and requires at least one
declared output. `verify()` then holds the declared files to their digests;
unlisted extra files are outside this result-record contract.

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
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


class ResultShapeError(ValueError):
    """A result record is JSON, but not a record of the promised shape."""


def _no_duplicate_json_keys(pairs):
    """Use JSON's object-pairs hook so a later key cannot replace evidence."""
    out = {}
    for key, value in pairs:
        if key in out:
            raise ResultShapeError(f"duplicate JSON key {key!r}")
        out[key] = value
    return out


def _digest(value, where: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ResultShapeError(f"{where} must be a 64-hex SHA-256 string")
    return value


def _remember_digest(declared: dict[str, str], name: str, digest: str,
                     where: str) -> None:
    old = declared.get(name)
    if old is not None and old.lower() != digest.lower():
        raise ResultShapeError(
            f"{where} conflicts with the previously declared digest for {name!r}")
    declared[name] = digest.lower()


def _artifact_rows(rows, label: str, declared: dict[str, str]) -> set[str]:
    if not isinstance(rows, list):
        raise ResultShapeError(f"result.{label} must be a list")
    names = set()
    for i, row in enumerate(rows):
        where = f"result.{label}[{i}]"
        if not isinstance(row, dict):
            raise ResultShapeError(f"{where} must be an object")
        name = row.get("file")
        if (not isinstance(name, str) or not name or
                Path(name).name != name or name in (".", "..")):
            raise ResultShapeError(f"{where}.file must name a bundle-root file")
        if name in names:
            raise ResultShapeError(f"{where}.file {name!r} is declared twice")
        names.add(name)
        digests = [row[key] for key in ("sha256", "output_sha256") if key in row]
        if not digests:
            raise ResultShapeError(f"{where} lacks sha256/output_sha256")
        checked = [_digest(value, f"{where}.{key}")
                   for key, value in row.items()
                   if key in ("sha256", "output_sha256")]
        if len(checked) == 2 and checked[0].lower() != checked[1].lower():
            raise ResultShapeError(f"{where} has conflicting digest fields")
        _remember_digest(declared, name, checked[0], where)
        inputs = row.get("inputs", [])
        if not isinstance(inputs, list):
            raise ResultShapeError(f"{where}.inputs must be a list")
        input_digests = {}
        for j, source in enumerate(inputs):
            sw = f"{where}.inputs[{j}]"
            if not isinstance(source, dict):
                raise ResultShapeError(f"{sw} must be an object")
            sname = source.get("file")
            if (not isinstance(sname, str) or not sname or
                    Path(sname).name != sname or sname in (".", "..")):
                raise ResultShapeError(f"{sw}.file must name a bundle-root file")
            if "sha256" not in source:
                raise ResultShapeError(f"{sw} lacks sha256")
            sdigest = _digest(source["sha256"], f"{sw}.sha256")
            if sname in input_digests and input_digests[sname].lower() != sdigest.lower():
                raise ResultShapeError(f"{where} has conflicting input digest for {sname!r}")
            input_digests[sname] = sdigest
            _remember_digest(declared, sname, sdigest, sw)
    return names


def _validate_record_shape(rec: dict, path: Path) -> None:
    if not isinstance(rec, dict):
        raise ResultShapeError(f"{path} top level must be an object")
    wanted = {"commit", "command", "binary_sha256", "input_sha256", "result"}
    extra = sorted(set(rec) - wanted)
    if extra:
        raise ResultShapeError(f"{path} has unknown top-level fields {extra}")
    missing = sorted(wanted - set(rec))
    if missing:
        raise ResultShapeError(f"{path} lacks {missing}")
    if not isinstance(rec["commit"], str) or not rec["commit"]:
        raise ResultShapeError(f"{path}.commit must be a non-empty string")
    if (not isinstance(rec["command"], list) or
            not rec["command"] or
            not all(isinstance(arg, str) for arg in rec["command"])):
        raise ResultShapeError(f"{path}.command must be a non-empty string list")
    _digest(rec["binary_sha256"], f"{path}.binary_sha256")
    _digest(rec["input_sha256"], f"{path}.input_sha256")
    result = rec["result"]
    if not isinstance(result, dict):
        raise ResultShapeError(f"{path}.result must be an object")
    if set(result) != {"members", "analyses"}:
        raise ResultShapeError(
            f"{path}.result must contain exactly members and analyses")
    declared_digests = {}
    member_names = _artifact_rows(result["members"], "members", declared_digests)
    analysis_names = _artifact_rows(result["analyses"], "analyses", declared_digests)
    overlap = sorted(member_names & analysis_names)
    if overlap:
        raise ResultShapeError(
            f"result members/analyses declare the same output file(s): {overlap}")
    # An analysis may legitimately have no rows (for example a clear-only run),
    # but a result record with neither an output member nor an analysis is not a
    # sound empty diagnostic: it has no declared evidence to verify.
    if not result["members"] and not result["analyses"]:
        raise ResultShapeError(f"{path}.result declares no output artifacts")


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
        rec = json.loads(p.read_text(), object_pairs_hook=_no_duplicate_json_keys)
        _validate_record_shape(rec, p)
    except (OSError, ValueError, TypeError) as e:
        raise SystemExit(f"REFUSED: {p} will not parse: {e}")
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
    return "matches" if sha256(p).lower() == str(want).lower() else "MISMATCH"


def payloads(rec: dict) -> dict:
    """file -> digest, for every file the record names. This is WHAT THE RUN
    PRODUCED, apart from how the record describes it: two records with the same
    payload map hold the same bytes."""
    out = {}
    r = rec.get("result") or {}
    for row in (r.get("members") or []) + (r.get("analyses") or []):
        if isinstance(row, dict) and row.get("file"):
            out[row["file"]] = row.get("sha256") or row.get("output_sha256")
            for src in row.get("inputs") or []:
                if isinstance(src, dict) and src.get("file"):
                    out.setdefault(src["file"], src.get("sha256"))
    return out


def verify(bundle: Path) -> list:
    """Validate every declared output file against its recorded digest.

    This is a content-addressed record check, not a directory inventory: files
    not listed by ``result.members``/``result.analyses`` are intentionally ignored.
    """
    bundle = Path(bundle)
    rec = load(bundle)
    bad = []
    exe = bundle / "g33_refine_driver"
    st = payload_state(exe, rec["binary_sha256"], bundle)
    if st != "matches":
        bad.append(f"g33_refine_driver: {st} (binary_sha256 names another executable)")
    for name, want in payloads(rec).items():
        st = payload_state(bundle / name, want, bundle)
        if st != "matches":
            bad.append(f"{name}: {st}")
    return bad


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("bundle", type=Path, nargs="+",
                    help="hold each bundle to its result.json")
    a = ap.parse_args(argv)
    rc = 0
    for b in a.bundle:
        bad = verify(b)
        print(f"{b}: " + ("sound" if not bad else "\n  " + "\n  ".join(bad)))
        rc |= bool(bad)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
