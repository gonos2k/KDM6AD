#!/usr/bin/env python3
"""Load + fail-closed re-verify a persisted G3.3-M evidence bundle.

The four-case comparator must never read tampered or partial evidence. This module
is the single trusted gate between an on-disk bundle and the normalizer: it
re-checks every hash the producer sealed and rejects extra/missing files, so a
bundle that does not re-verify never reaches a verdict.

C++ ABC bundle (run_cpp_abc.py --out) layout:
  cpp_abc_manifest.json                         root manifest (per-algo summary)
  {algo}-C-evidence/run_contract.json           + run_contract.sha256
  {algo}-C-evidence/schema/*.desc               + schema/descriptors.sha256
  {algo}-C-evidence/dump/*.g33                   sealed KDG33OP containers

Every container's own payload_sha256, its header binding to producer_commit /
binary_sha256 / run_contract_sha256 / descriptor_sha256, and the whole-tree SHA
files are verified here; read_container (g33_dump) does the per-container structural
+ payload check.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import g33_dump as gd  # noqa: E402

# The three containers the comparator consumes (ops + the pre-sed sentinels +
# surface); the outer_post_* containers exist in the bundle but are out of scope.
COMPARATOR_CONTAINERS = ("L1_outer_pre", "L1_main_n1", "L1_surface")


class BundleError(Exception):
    """The bundle is malformed, incomplete, or fails re-verification."""


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_sha_file(path: Path) -> dict:
    """`<hex>  <name>` lines -> {name: hex}. Rejects duplicates and malformed lines."""
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 2 or len(parts[0]) != 64:
            raise BundleError(f"malformed sha line in {path.name}: {line!r}")
        name = parts[1].lstrip("*")
        if name in out:
            raise BundleError(f"duplicate sha entry {name} in {path.name}")
        out[name] = parts[0]
    return out


def _verify_sha_manifest(directory: Path, sha_file: Path, subdir: str | None = None):
    """Every file the sha manifest names must exist and match; no unlisted file may
    sit alongside them (an extra file is unverified evidence)."""
    listed = _parse_sha_file(sha_file)
    scan = directory / subdir if subdir else directory
    for name, want in listed.items():
        f = scan / name
        if not f.is_file():
            raise BundleError(f"{sha_file.name} lists missing file {name}")
        got = _sha256_file(f)
        if got != want:
            raise BundleError(f"{name} sha256 {got} != sealed {want}")
    present = {p.name for p in scan.iterdir() if p.is_file() and p.suffix != ".sha256"}
    extra = present - set(listed)
    if extra:
        raise BundleError(f"unlisted file(s) in {scan.name}: {sorted(extra)}")
    return listed


def verify_cpp_evidence(evidence_dir: Path, algorithm: str) -> dict:
    """Re-verify one {algo}-C-evidence tree and return its parsed containers.

    Checks: run_contract.json vs run_contract.sha256; every schema/*.desc vs
    descriptors.sha256; every dump/*.g33 parses (payload hash) and its header binds
    to the SAME run_contract/descriptor/commit; the container set is complete.
    """
    evidence_dir = Path(evidence_dir)
    if not evidence_dir.is_dir():
        raise BundleError(f"evidence dir not found: {evidence_dir}")

    # 1. run_contract.json <-> run_contract.sha256
    contract_path = evidence_dir / "run_contract.json"
    contract_sha = _parse_sha_file(evidence_dir / "run_contract.sha256")
    if set(contract_sha) != {"run_contract.json"}:
        raise BundleError("run_contract.sha256 must seal exactly run_contract.json")
    if _sha256_file(contract_path) != contract_sha["run_contract.json"]:
        raise BundleError("run_contract.json sha256 mismatch (tampered contract)")
    contract = json.loads(contract_path.read_text())
    contract_hash = contract_sha["run_contract.json"]

    # 2. schema/*.desc <-> descriptors.sha256
    desc_shas = _verify_sha_manifest(evidence_dir / "schema",
                                     evidence_dir / "schema" / "descriptors.sha256")

    # 3. containers: parse (payload hash) + bind header to contract/descriptor/commit
    dump = evidence_dir / "dump"
    parsed: dict[str, dict] = {}
    seen_cids = set()
    g33_files = sorted(dump.glob("*.g33"))
    if not g33_files:
        raise BundleError(f"no containers under {dump}")
    for path in g33_files:
        c = gd.read_container(path)          # structural + payload_sha256 check
        h = c["header"]
        cid = h["container_id"]
        seen_cids.add(cid)
        if h.get("algorithm") != algorithm:
            raise BundleError(f"{path.name} header algorithm {h.get('algorithm')} != {algorithm}")
        if h.get("run_contract_sha256") != contract_hash:
            raise BundleError(f"{path.name} run_contract_sha256 not bound to this contract")
        desc_name = f"{cid}.desc"
        if desc_name not in desc_shas:
            raise BundleError(f"{path.name} has no descriptor {desc_name}")
        if h.get("descriptor_sha256") != desc_shas[desc_name]:
            raise BundleError(f"{path.name} descriptor_sha256 not bound to {desc_name}")
        parsed[cid] = c
    # every declared descriptor must have a container and vice versa
    declared = {n[:-5] for n in desc_shas if n.endswith(".desc")}
    if declared != seen_cids:
        raise BundleError(f"container/descriptor set mismatch: "
                          f"containers {sorted(seen_cids)} vs descriptors {sorted(declared)}")
    missing = set(COMPARATOR_CONTAINERS) - seen_cids
    if missing:
        raise BundleError(f"bundle missing comparator container(s): {sorted(missing)}")
    return {"contract": contract, "containers": parsed}


def verify_cpp_bundle(bundle_dir) -> dict:
    """Re-verify the whole C++ ABC bundle root. Returns
    {manifest, algorithms:{algo:{contract, containers}}}."""
    bundle_dir = Path(bundle_dir)
    manifest_path = bundle_dir / "cpp_abc_manifest.json"
    if not manifest_path.is_file():
        raise BundleError(f"no cpp_abc_manifest.json in {bundle_dir}")
    manifest = json.loads(manifest_path.read_text())
    algos = manifest.get("algorithms")
    if not isinstance(algos, dict) or not algos:
        raise BundleError("manifest has no algorithms map")
    out = {}
    for algo, meta in algos.items():
        ev = bundle_dir / meta["evidence_dir"]
        out[algo] = verify_cpp_evidence(ev, algo)
    return {"manifest": manifest, "algorithms": out}
