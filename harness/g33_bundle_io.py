#!/usr/bin/env python3
"""Load + fail-closed re-verify a persisted G3.3-M evidence bundle.

The four-case comparator must never read tampered, partial, or wrong-problem
evidence. This module is the single trusted gate between an on-disk bundle and the
normalizer. It re-checks, INDEPENDENTLY:
  * every sealed hash (run_contract, descriptors, container payloads, A/B/C stdout,
    diagnostic-binary) and the root manifest attestation;
  * that the record universe is EXACTLY the sealed schedule's (via
    g33_evidence_validate — the same check the live A/B/C gate runs), not merely a
    set of internally-valid containers;
  * that both algorithm legs describe the SAME fixture + parameters (same problem);
  * that no path escapes the bundle root and no unlisted/extra file rides along.
A bundle that does not re-verify never reaches a verdict.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import g33_dump as gd                # noqa: E402
import g33_evidence_validate as gev  # noqa: E402

COMPARATOR_CONTAINERS = ("L1_outer_pre", "L1_main_n1", "L1_surface")
_MAX_JSON_BYTES = 4 * 1024 * 1024
_MAX_SHA_BYTES = 1 * 1024 * 1024
_ALGOS = ("legacy", "conservative")


class BundleError(Exception):
    """The bundle is malformed, incomplete, or fails re-verification."""


def _no_dup_keys(pairs):
    seen = {}
    for k, v in pairs:
        if k in seen:
            raise BundleError(f"duplicate JSON key {k!r}")
        seen[k] = v
    return seen


def _load_json(path: Path, what: str):
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise BundleError(f"cannot read {what} {path.name}: {e}") from None
    if len(raw) > _MAX_JSON_BYTES:
        raise BundleError(f"{what} {path.name} exceeds size bound")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_no_dup_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise BundleError(f"{what} {path.name} is not valid JSON: {e}") from None


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_name(name: str, where: str) -> str:
    if not name or name.startswith(("/", "\\")) or ".." in name.replace("\\", "/").split("/") \
            or "/" in name or "\\" in name:
        raise BundleError(f"unsafe filename {name!r} in {where}")
    return name


def _parse_sha_file(path: Path) -> dict:
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise BundleError(f"cannot read {path.name}: {e}") from None
    if len(raw) > _MAX_SHA_BYTES:
        raise BundleError(f"{path.name} exceeds size bound")
    out: dict[str, str] = {}
    for line in raw.decode("utf-8", "replace").splitlines():
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 2 or len(parts[0]) != 64 or any(c not in "0123456789abcdef" for c in parts[0]):
            raise BundleError(f"malformed sha line in {path.name}: {line!r}")
        name = _safe_name(parts[1].lstrip("*"), path.name)
        if name in out:
            raise BundleError(f"duplicate sha entry {name} in {path.name}")
        out[name] = parts[0]
    return out


def _verify_sha_manifest(scan: Path, sha_file: Path) -> dict:
    """Every listed file must exist and match; no unlisted non-.sha256 file may sit
    alongside (an extra file is unverified evidence)."""
    listed = _parse_sha_file(sha_file)
    for name, want in listed.items():
        f = scan / name
        if not f.is_file():
            raise BundleError(f"{sha_file.name} lists missing file {name}")
        if _sha256_file(f) != want:
            raise BundleError(f"{name} sha256 mismatch")
    present = {p.name for p in scan.iterdir() if p.is_file() and p.suffix != ".sha256"}
    extra = present - set(listed)
    if extra:
        raise BundleError(f"unlisted file(s) in {scan.name}: {sorted(extra)}")
    return listed


def _under(root: Path, child: Path) -> Path:
    r, c = root.resolve(), child.resolve()
    if not (c == r or r in c.parents):
        raise BundleError(f"path escapes bundle root: {child}")
    return c


def verify_cpp_evidence(evidence_dir, algorithm: str, expected_binary_sha=None) -> dict:
    """Re-verify one {algo}-C-evidence tree and return {contract, containers}."""
    evidence_dir = Path(evidence_dir)
    if not evidence_dir.is_dir():
        raise BundleError(f"evidence dir not found: {evidence_dir}")

    contract_path = evidence_dir / "run_contract.json"
    contract_sha = _parse_sha_file(evidence_dir / "run_contract.sha256")
    if set(contract_sha) != {"run_contract.json"}:
        raise BundleError("run_contract.sha256 must seal exactly run_contract.json")
    if _sha256_file(contract_path) != contract_sha["run_contract.json"]:
        raise BundleError("run_contract.json sha256 mismatch (tampered contract)")
    contract = _load_json(contract_path, "run_contract")
    contract_hash = contract_sha["run_contract.json"]
    schedule = contract.get("schedule")
    if not isinstance(schedule, dict):
        raise BundleError("run_contract has no schedule object")
    if schedule.get("algorithm") != algorithm or schedule.get("backend") != "cpp":
        raise BundleError(f"contract schedule algorithm/backend != {algorithm}/cpp")

    desc_shas = _verify_sha_manifest(evidence_dir / "schema",
                                     evidence_dir / "schema" / "descriptors.sha256")

    dump = evidence_dir / "dump"
    parsed: dict[str, dict] = {}
    g33_files = sorted(dump.glob("*.g33"))
    if not g33_files:
        raise BundleError(f"no containers under {dump}")
    for path in g33_files:
        c = gd.read_container(path)          # structural + payload_sha256 check
        h = c["header"]
        cid = h["container_id"]
        if cid in parsed:
            raise BundleError(f"duplicate container id {cid}")
        want = {"algorithm": algorithm, "backend": "cpp",
                "case_id": schedule.get("case_id"), "pair_id": schedule.get("pair_id"),
                "B": schedule.get("B"), "K": schedule.get("K"),
                "run_contract_sha256": contract_hash}
        for k, v in want.items():
            if h.get(k) != v:
                raise BundleError(f"{path.name} header {k}={h.get(k)!r} != {v!r}")
        desc_name = f"{cid}.desc"
        if desc_name not in desc_shas or h.get("descriptor_sha256") != desc_shas[desc_name]:
            raise BundleError(f"{path.name} descriptor binding mismatch")
        if expected_binary_sha is not None and h.get("binary_sha256") != expected_binary_sha:
            raise BundleError(f"{path.name} binary_sha256 != manifest diagnostic driver sha")
        parsed[cid] = c

    declared = {n[:-5] for n in desc_shas if n.endswith(".desc")}
    if declared != set(parsed):
        raise BundleError(f"container/descriptor set mismatch: {sorted(parsed)} vs {sorted(declared)}")
    missing = set(COMPARATOR_CONTAINERS) - set(parsed)
    if missing:
        raise BundleError(f"bundle missing comparator container(s): {sorted(missing)}")

    # INDEPENDENT completeness — same gate as the live A/B/C checker (P0-2).
    try:
        gev.validate_evidence(schedule, contract.get("containers", []), list(parsed.values()))
    except gd.G33Corruption as e:
        raise BundleError(f"evidence completeness: {e}") from None
    return {"contract": contract, "containers": parsed}


def verify_cpp_bundle(bundle_dir) -> dict:
    """Re-verify the whole C++ ABC bundle root incl. attestation (P0-3). Returns
    {manifest, algorithms:{algo:{contract, containers}}}."""
    bundle_dir = Path(bundle_dir).resolve()
    manifest = _load_json(bundle_dir / "cpp_abc_manifest.json", "manifest")
    if manifest.get("schema_version") != 1:
        raise BundleError(f"unexpected manifest schema_version {manifest.get('schema_version')!r}")
    algos = manifest.get("algorithms")
    if not isinstance(algos, dict) or set(algos) != set(_ALGOS):
        raise BundleError(f"manifest algorithms must be exactly {set(_ALGOS)}")
    diag_sha = manifest.get("diagnostic_driver_sha256")

    fixtures, params, out = set(), set(), {}
    for algo in _ALGOS:
        meta = algos[algo]
        if meta.get("abc_equal") is not True:
            raise BundleError(f"{algo}: abc_equal is not True")
        if not (meta.get("mstep_min") == meta.get("mstep_max") == 1):
            raise BundleError(f"{algo}: mstep range is not [1,1]")
        # A/B/C stdout must rehash to the sealed value AND be byte-equal to each other.
        seen = set()
        for lane in ("A", "B", "C"):
            f = _under(bundle_dir, bundle_dir / f"{algo}-{lane}" / "stdout.abc")
            got = _sha256_file(f)
            if got != (meta.get("stdout_sha256") or {}).get(lane):
                raise BundleError(f"{algo}-{lane} stdout sha != sealed")
            seen.add(got)
        if len(seen) != 1:
            raise BundleError(f"{algo}: A/B/C stdout not byte-identical")
        fixtures.add(meta.get("fixture_sha256"))
        params.add(meta.get("parameter_sha256"))
        ev = _under(bundle_dir, bundle_dir / meta["evidence_dir"])
        out[algo] = verify_cpp_evidence(ev, algo, expected_binary_sha=diag_sha)
    # SAME-PROBLEM: both legs share one fixture + one parameter set.
    if len(fixtures) != 1 or None in fixtures:
        raise BundleError(f"legs disagree on fixture_sha256: {fixtures}")
    if len(params) != 1 or None in params:
        raise BundleError(f"legs disagree on parameter_sha256: {params}")
    return {"manifest": manifest, "algorithms": out}
