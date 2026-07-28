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
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import g33_abc_protocol as abcp      # noqa: E402
import g33_derived as gdv            # noqa: E402
import g33_dump as gd                # noqa: E402
import g33_evidence_validate as gev  # noqa: E402
import g33_fixture_v1 as gfx         # noqa: E402
import g33_schedule_probe as gsp     # noqa: E402

_HEX64 = tuple("0123456789abcdef")
# Header fields that must be IDENTICAL across every container of one run — a bundle
# must not splice containers from separate executions that happen to share a
# schedule (owner P0-5).
_SAME_RUN = ("run_uuid", "process_id", "owner_thread_id", "producer_commit",
             "binary_sha256", "resolved_binary_sha256", "column_layout_id",
             "canonical_k_order", "column_index_map")


def _is_hex64(s) -> bool:
    return isinstance(s, str) and len(s) == 64 and all(c in _HEX64 for c in s)

COMPARATOR_CONTAINERS = ("L1_outer_pre", "L1_main_n1", "L1_surface")
_MAX_JSON_BYTES = 4 * 1024 * 1024
_MAX_SHA_BYTES = 1 * 1024 * 1024
_ALGOS = ("legacy", "conservative")


class BundleError(Exception):
    """The bundle is malformed, incomplete, or fails re-verification."""


def _freeze(obj):
    """Recursively make a parsed bundle read-only. `frozen=True` on the dataclass
    only protects the ATTRIBUTES — without this, a caller could still forge
    `leg.containers[cid]["records"][0]["payload"]` after verification while
    root_attested stayed True."""
    if isinstance(obj, dict):
        return MappingProxyType({k: _freeze(v) for k, v in obj.items()})
    if isinstance(obj, list):
        return tuple(_freeze(v) for v in obj)
    return obj


@dataclass(frozen=True)
class VerifiedCppLeg:
    """One C++ leg that has passed re-verification. `root_attested` is False from
    verify_cpp_evidence alone (structure + completeness + producer semantics +
    orientation) and only True after verify_cpp_bundle adds the root attestation
    (same-problem, A/B/C, diagnostic-binary). from_cpp_evidence requires it True, so
    the normalizer cannot be fed a leg that skipped the root gate."""
    contract: dict
    containers: dict
    mstep_range: tuple | None
    problem: dict | None = None              # fixture/parameter identity of the run
    actual_final_output: dict | None = None  # what the run RETURNED, per family
    root_attested: bool = False              # bundle-internal root manifest verified
    external_manifest_attested: bool = False  # root manifest pinned to an OUTSIDE SHA
    source_commit_attested: bool = False      # producer_commit pinned to a reviewed rev
    fixture_attested: bool = False            # the fixture was NAMED from outside
    #: How the sealed schedule was ESTABLISHED: the shipped probe stream, re-derived
    #: offline. None only when the contract is a single loop of single substeps, where
    #: there is nothing a probe could establish.
    probe_lineage: dict | None = None

    @property
    def verdict_ready(self) -> bool:
        """A C4 decision needs BOTH the internal verification and the external
        anchors — a bundle that rewrites its manifest and its own sidecars stays
        self-consistent, so internal checks alone cannot attest it."""
        return (self.root_attested and self.external_manifest_attested
                and self.source_commit_attested and self.fixture_attested)


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


def _no_symlink(p: Path):
    if p.is_symlink():
        raise BundleError(f"symlink not allowed in evidence tree: {p}")
    return p


def _verify_sha_manifest(scan: Path, sha_file: Path) -> dict:
    """Every listed file must exist, be a regular non-symlink file, and match; no
    unlisted file (incl. a stray .sha256 or stale .tmp) may sit alongside."""
    listed = _parse_sha_file(sha_file)
    for name, want in listed.items():
        f = _no_symlink(scan / name)
        if not f.is_file():
            raise BundleError(f"{sha_file.name} lists missing file {name}")
        if _sha256_file(f) != want:
            raise BundleError(f"{name} sha256 mismatch")
    allowed = set(listed) | {sha_file.name}       # the manifest itself is the only ok .sha256
    for p in scan.iterdir():
        _no_symlink(p)
        if p.name not in allowed:
            raise BundleError(f"unlisted file in {scan.name}: {p.name}")
    return listed


def _under(root: Path, child: Path) -> Path:
    r, c = root.resolve(), child.resolve()
    if not (c == r or r in c.parents):
        raise BundleError(f"path escapes bundle root: {child}")
    return c


def verify_cpp_evidence(evidence_dir, algorithm: str, expected_binary_sha=None,
                        expected_repo_commit=None,
                        allow_metric_floor=False) -> dict:
    """Re-verify one {algo}-C-evidence tree and return {contract, containers}.
"""
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

    _no_symlink(contract_path)
    _no_symlink(evidence_dir / "run_contract.sha256")
    dump = evidence_dir / "dump"
    parsed: dict[str, dict] = {}
    for p in dump.iterdir():                       # only .g33 regular files, no .tmp
        _no_symlink(p)
        if p.suffix != ".g33":
            raise BundleError(f"unexpected file in dump: {p.name}")
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

    # SAME-RUN invariants: every container shares one run identity (P0-5), and the
    # producing revision is a real commit (optionally pinned to a reviewed one).
    anchor = None
    for cid, c in parsed.items():
        commit = c["header"].get("producer_commit")
        if not (isinstance(commit, str) and len(commit) == 40
                and all(ch in _HEX64 for ch in commit)):
            raise BundleError(f"{cid} producer_commit is not a 40-hex commit")
        if expected_repo_commit is not None and commit != expected_repo_commit:
            raise BundleError(f"{cid} producer_commit != expected {expected_repo_commit}")
        sig = tuple(json.dumps(c["header"].get(k), sort_keys=True) for k in _SAME_RUN)
        if c["header"].get("canonical_k_order") != "top-first":
            raise BundleError(f"{cid} canonical_k_order != top-first")
        if anchor is None:
            anchor = sig
        elif sig != anchor:
            raise BundleError(f"{cid} run identity differs from other containers (spliced?)")

    # INDEPENDENT producer-flag recomputation: recompute mstep/gate/floor exactness
    # and the dtcld bit-binding from the raw native operands, so a producer that
    # FALSELY reports exact=1 (or a wrong dtcld) is rejected — never trusted (P0-1/P0-6).
    qcrmin, dtcld = schedule.get("qcrmin"), schedule.get("dtcld")
    mstep_vals, mstep_anchor = [], {}
    mstep_max, substeps_seen = {}, {}       # (outer_loop, chain) -> max / {n}
    for cid, c in parsed.items():
        subpre = [r for r in c["records"] if r.get("stage") == "substep_pre"]
        if not subpre:
            continue
        pre = {r["field"]: (r["dtype"], r["payload"]) for r in subpre}
        try:
            gdv.check_producer_flags(pre, subpre[0]["n"], qcrmin, dtcld)
        except gd.G33Corruption as e:
            raise BundleError(f"{cid} producer flags: {e}") from None
        # The shared fixture carries physically well-formed positive rho / dz, so no
        # metric floor may fire. check_producer_flags only verifies that a floor, IF
        # it fired, followed max(raw, qcrmin) — it does not object to it firing. A
        # floored metric silently changes the divisor the conservative transfer uses,
        # so on this fixture it is rejected outright; a deliberate numerical-edge
        # fixture must opt in with allow_metric_floor=True. (Fortran has no floor at
        # all, so a fired C++ floor is also a cross-tree asymmetry.)
        if not allow_metric_floor:
            for flag in ("dend_floor_active", "delz_floor_active"):
                if flag not in pre:
                    continue
                fired = sum(int(v) != 0 for v in gdv.unpack_values(*pre[flag]))
                if fired:
                    raise BundleError(
                        f"{cid}: {flag} fired in {fired} cell(s) — the metric floor "
                        f"must not engage on a well-formed fixture")
        # Derive the mstep range INDEPENDENTLY from the decoded evidence (P0-4), so
        # the manifest's mstep summary is attested, not trusted or hard-pinned to 1.
        for r in subpre:
            if r["field"] in ("mstep_decoded_i32", "mstep_native"):
                # The runtime computes the per-column mstep ONCE before the substep
                # loop and reuses it, so within one (outer_loop, chain) every substep
                # must carry the bit-identical vector. Per-container checks alone
                # would admit an mstep that drifts between n.
                anchor_key = (r["outer_loop"], r["chain"], r["field"])
                prev = mstep_anchor.setdefault(anchor_key, r["payload"])
                if prev != r["payload"]:
                    raise BundleError(
                        f"{cid}: {r['field']} differs from an earlier substep of "
                        f"{anchor_key[:2]} — the per-column mstep vector is not "
                        f"constant across the substep loop")
            if r["field"] == "mstep_decoded_i32":
                vals = [int(v) for v in gdv.unpack_values(r["dtype"], r["payload"])]
                mstep_vals.extend(vals)
                lc = (r["outer_loop"], r["chain"])
                mstep_max[lc] = max(mstep_max.get(lc, 0), max(vals))
                substeps_seen.setdefault(lc, set()).add(r["n"])
    # P0-2: the OBSERVED per-column mstep maximum must equal the schedule's declared
    # mstepmax for that (outer_loop, chain), and the substep containers must cover
    # exactly n = 1..that maximum. Otherwise a bundle whose columns really need n=3
    # can declare mstepmax=2, satisfy completeness against its own contract, and
    # simply omit the n=3 evidence.
    for (loop, chain), mx in sorted(mstep_max.items()):
        declared = schedule.get(f"mstepmax_{chain}")
        if not isinstance(declared, list) or len(declared) < loop:
            raise BundleError(f"schedule has no mstepmax_{chain}[{loop}]")
        if declared[loop - 1] != mx:
            raise BundleError(
                f"loop {loop} chain {chain}: observed mstep max {mx} != schedule "
                f"mstepmax_{chain}[{loop - 1}]={declared[loop - 1]}")
        if substeps_seen[(loop, chain)] != set(range(1, mx + 1)):
            raise BundleError(
                f"loop {loop} chain {chain}: substep containers "
                f"{sorted(substeps_seen[(loop, chain)])} != 1..{mx}")
    mstep_range = (min(mstep_vals), max(mstep_vals)) if mstep_vals else None
    return VerifiedCppLeg(contract=_freeze(contract), containers=_freeze(parsed),
                          mstep_range=mstep_range, root_attested=False)


def _verify_probe_lineage(bundle_dir, algo, meta, leg, diag_sha, authority):
    """Re-derive the sealed schedule from the probe stream the bundle SHIPS.

    The reproduce gate already runs in g33_fourcase_fixture_check, but at PRODUCTION
    time — and the probe stream never travelled with the bundle, so a later reader had
    the producer's word and nothing else. Here the derivation is redone from bytes the
    bundle carries: the stream's own fall speeds must imply the schedule the evidence
    was sealed with, and the evidence must show the same substeps the probe ran.

    A single-substep run needs no probe (there is nothing to derive), so lineage is
    required exactly when the contract declares more than one loop or substep. That is
    read from the CONTRACT, not from whether the bundle chose to ship a probe.
    """
    sched = leg.contract["schedule"]
    maxima = [*sched.get("mstepmax_main", []), *sched.get("mstepmax_ice", [])]
    needs_probe = int(sched.get("loops", 1)) > 1 or any(int(m) > 1 for m in maxima)
    if not meta.get("probe_dir"):
        if needs_probe:
            raise BundleError(
                f"{algo}: the contract declares loops={sched.get('loops')} "
                f"mstepmax={maxima}, which only a probe can establish, but the "
                f"bundle ships no probe lineage")
        return None

    d = _under(bundle_dir, bundle_dir / meta["probe_dir"])
    files = {}
    for name, key in ((gsp.PROBE_STREAM, "probe_stream_sha256"),
                      (gsp.PROBE_SCHEDULE, "schedule_sha256"),
                      (gsp.PROBE_MANIFEST, "probe_manifest_sha256")):
        f = _under(bundle_dir, d / name)
        got = _sha256_file(f)
        if got != meta.get(key):
            raise BundleError(f"{algo}: probe {name} sha256 {got} != manifest "
                              f"{meta.get(key)}")
        files[name] = f

    pm = _load_json(files[gsp.PROBE_MANIFEST], f"{algo} probe manifest")
    # The probe must have measured the SAME binary that produced the evidence.
    # Otherwise the schedule describes one build's substep decisions and the sealed
    # containers another's, which is the exact thing the two-pass design exists to rule
    # out.
    if pm.get("diagnostic_driver_sha256") != diag_sha:
        raise BundleError(
            f"{algo}: the probe measured driver {pm.get('diagnostic_driver_sha256')} "
            f"but the evidence came from {diag_sha}")
    if pm.get("algorithm") != algo:
        raise BundleError(f"{algo}: probe manifest is for {pm.get('algorithm')!r}")
    # both records of the stream, not just the root manifest's: a probe manifest
    # that describes a different stream than the one shipped beside it is a bundle
    # assembled from two runs
    if _sha256_file(files[gsp.PROBE_STREAM]) != pm.get("probe_stream_sha256"):
        raise BundleError(f"{algo}: probe stream != its own probe manifest")
    if _sha256_file(files[gsp.PROBE_SCHEDULE]) != pm.get("schedule_sha256"):
        raise BundleError(f"{algo}: probe schedule.json != its own probe manifest")

    # THE WHOLE SCHEDULE, not just its substep counts. Hashing schedule.json against
    # the probe manifest proves the file is the one the probe wrote; it says nothing
    # about whether the evidence was SEALED with it. qcrmin, dtcld, B/K,
    # species_scope, instrumented_stages and the case/pair ids could all differ while
    # mstepmax matched, and the run would have been sealed against a contract the
    # probe never produced (owner P0-9).
    probe_schedule = _load_json(files[gsp.PROBE_SCHEDULE], f"{algo} probe schedule")
    # compared in canonical JSON form: the verified contract has been deep-frozen, so
    # its lists are tuples, and a bare != would report every list-valued key as a
    # difference while saying nothing about the values
    canon = lambda d: json.loads(json.dumps(d, sort_keys=True, default=list))
    probe_canon, sched_canon = canon(probe_schedule), canon(dict(sched))
    if probe_canon != sched_canon:
        differing = sorted(
            k for k in set(probe_canon) | set(sched_canon)
            if probe_canon.get(k) != sched_canon.get(k))
        raise BundleError(
            f"{algo}: the sealed contract is not the schedule the probe derived — "
            f"they differ on {differing}")

    # the probe must also be OF the anchored fixture, not merely of some fixture
    if pm.get("fixture_id") != authority["fixture_id"]:
        raise BundleError(f"{algo}: probe is for fixture {pm.get('fixture_id')!r}, "
                          f"not {authority['fixture_id']!r}")
    if pm.get("fixture_manifest_sha256") != gfx.manifest_sha256(authority):
        raise BundleError(f"{algo}: probe fixture manifest sha != the anchored "
                          f"authority")
    if pm.get("noninvasiveness_checked") is not True:
        raise BundleError(
            f"{algo}: the probe did not run its non-invasiveness check, so the "
            f"schedule may describe a run the probe itself perturbed")
    stream = files[gsp.PROBE_STREAM].read_text()

    # THE re-derivation. probe_from_stream recomputes mstep from the raw fall speeds
    # and refuses a stream whose own mstep_native disagrees, so this is not a replay of
    # the producer's arithmetic.
    try:
        probe = gsp.probe_from_stream(stream)
    except gsp.ProbeError as e:
        raise BundleError(f"{algo}: shipped probe stream does not derive: {e}") from None
    derived = {}
    for (loop, chain), entry in probe.items():
        derived.setdefault(chain, {})[loop] = max(entry["mstep"])
    for chain in ("main", "ice"):
        declared = list(sched.get(f"mstepmax_{chain}", []))
        per_loop = derived.get(chain, {})
        if not per_loop:
            # A chain with no in-scope species emits nothing — no probe records and
            # no containers either way — so its declaration is inert and cannot be
            # corroborated. What matters is that the probe and the evidence agree on
            # which scopes exist at all, which assert_reproduced below enforces.
            continue
        got = [per_loop.get(i + 1) for i in range(len(declared))]
        if got != [int(m) for m in declared]:
            raise BundleError(
                f"{algo}: the shipped probe stream implies mstepmax_{chain}={got} "
                f"but the evidence was sealed with {declared}")

    # ...and the evidence must have made those same decisions substep for substep.
    try:
        gsp.assert_reproduced(probe, gsp.read_probe(leg.containers))
    except gsp.ProbeError as e:
        raise BundleError(f"{algo}: sealed evidence does not reproduce the shipped "
                          f"probe schedule: {e}") from None
    return {"probe_stream_sha256": meta["probe_stream_sha256"],
            "schedule_sha256": meta["schedule_sha256"],
            "diagnostic_driver_sha256": pm["diagnostic_driver_sha256"]}


def verify_cpp_bundle(bundle_dir, *, expected_manifest_sha256=None,
                      expected_repo_commit=None,
                      expected_fixture_id=None,
                      expected_fixture_manifest_sha256=None) -> dict:
    """Re-verify the whole C++ ABC bundle root incl. attestation. Returns
    {manifest, algorithms:{algo: VerifiedCppLeg}}.

    EXTERNAL ANCHORS (optional, but required for a decision-grade run): a bundle
    that rewrites its own manifest AND its sidecar hashes is still self-consistent,
    so tamper-evidence ultimately needs a value recorded OUTSIDE the bundle.
    `expected_manifest_sha256` pins the root manifest to a hash held elsewhere (a
    committed C4 evidence manifest / the owner's adjudication record), and
    `expected_repo_commit` pins every container's producer_commit to the reviewed
    source revision."""
    bundle_dir = Path(bundle_dir).resolve()
    manifest_path = bundle_dir / "cpp_abc_manifest.json"
    if expected_manifest_sha256 is not None:
        got = _sha256_file(manifest_path)
        if got != expected_manifest_sha256:
            raise BundleError(f"root manifest sha256 {got} != external anchor "
                              f"{expected_manifest_sha256}")
    manifest = _load_json(manifest_path, "manifest")
    if manifest.get("schema_version") != 1:
        raise BundleError(f"unexpected manifest schema_version {manifest.get('schema_version')!r}")
    algos = manifest.get("algorithms")
    if not isinstance(algos, dict) or set(algos) != set(_ALGOS):
        raise BundleError(f"manifest algorithms must be exactly {set(_ALGOS)}")
    diag_sha = manifest.get("diagnostic_driver_sha256")
    if not _is_hex64(diag_sha):                # P0-2: mandatory, well-formed
        raise BundleError("manifest diagnostic_driver_sha256 missing or not 64-hex")

    # The fixture is named by the CALLER, not read out of the bundle: a bundle that
    # declares its own fixture and is checked against that declaration attests
    # nothing. The named authority is the checked-in JSON, so the bundle must match a
    # fixture someone outside it chose.
    # Defaulting this would let any caller that simply omits it mint a
    # verdict-ready leg for whichever fixture happens to be the module default —
    # the CLI would be anchored while the API it calls was not.
    try:
        _, authority = gfx.load_fixture(
            expected_fixture_id or gfx.DEFAULT_FIXTURE_ID)
    except gfx.UnknownFixture as e:
        raise BundleError(str(e)) from None
    # CONTENT anchor. The id names a registry entry, but the verifier reads that
    # JSON from its OWN working tree — on a divergent or dirty tree that is not the
    # file anyone reviewed. expected_repo_commit does not close this either: it pins
    # the evidence PRODUCER's commit, not the fixture the verifier read.
    resolved = gfx.manifest_sha256(authority)
    if expected_fixture_manifest_sha256 and resolved != expected_fixture_manifest_sha256:
        raise BundleError(
            f"fixture manifest sha256 {resolved} != expected "
            f"{expected_fixture_manifest_sha256} — the verifier read a different "
            f"fixture file than the anchored one")

    want_fixture, want_param = gfx.fixture_sha256(authority), gfx.parameter_sha256(authority)
    # the SHAs bind the CONTENT; this binds the bundle's own label, so a manifest
    # cannot carry one fixture's hashes under another fixture's name
    if manifest.get("fixture_id") != authority["fixture_id"]:
        raise BundleError(f"manifest fixture_id {manifest.get('fixture_id')!r} != "
                          f"{authority['fixture_id']!r}")
    if manifest.get("fixture_manifest_sha256") != gfx.manifest_sha256(authority):
        raise BundleError(f"manifest fixture_manifest_sha256 != the checked-in "
                          f"{expected_fixture_id} authority")

    fixtures, params, out = set(), set(), {}
    for algo in _ALGOS:
        meta = algos[algo]
        if meta.get("abc_equal") is not True:
            raise BundleError(f"{algo}: abc_equal is not True")
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
        # P0-5: bind to the CHECKED-IN fixture authority, not just leg-vs-leg equality
        # — otherwise both legs sharing one WRONG fixture passes.
        if meta.get("fixture_sha256") != want_fixture:
            raise BundleError(f"{algo}: fixture_sha256 != checked-in authority")
        if meta.get("parameter_sha256") != want_param:
            raise BundleError(f"{algo}: parameter_sha256 != checked-in authority")
        fixtures.add(meta.get("fixture_sha256"))
        params.add(meta.get("parameter_sha256"))
        ev = _under(bundle_dir, bundle_dir / meta["evidence_dir"])
        leg = verify_cpp_evidence(ev, algo, expected_binary_sha=diag_sha,
                                  expected_repo_commit=expected_repo_commit)
        # P0-6: fully re-parse each lane against the ABC protocol (a prefix check
        # accepts a truncated lane whose hash merely matches its siblings), then
        # require the three PARSED structures to be identical. The case/B/K come
        # from the leg's own verified schedule.
        sched = leg.contract["schedule"]
        case_name = str(sched.get("case_id", "")).split("-", 1)[-1]
        parsed_lanes = []
        for lane in ("A", "B", "C"):
            raw = _under(bundle_dir, bundle_dir / f"{algo}-{lane}" / "stdout.abc").read_bytes()
            try:
                parsed_lanes.append(abcp.parse_abc_output(
                    raw, algo, case_name, sched["B"], sched["K"]))
            except gd.G33Corruption as e:
                raise BundleError(f"{algo}-{lane} stdout.abc: {e}") from None
        if parsed_lanes[0] != parsed_lanes[1] or parsed_lanes[0] != parsed_lanes[2]:
            raise BundleError(f"{algo}: parsed A/B/C outputs differ")
        # Keep what the run actually RETURNED. Structural A/B/C equality alone threw
        # these away, so the decision compared a value the harness re-derived instead
        # of the one the runtime handed back — the output path was never gated.
        actual = _freeze({f.split("_")[0]: tuple(parsed_lanes[2][f]["bits"])
                          for f in abcp.INCREMENT_FIELDS})
        # the manifest's declared mstep summary must equal what the raw evidence shows
        # (P0-4) — no [1,1] hard-pin, so a real multi-subcycle bundle is admissible.
        obs = leg.mstep_range
        if obs is None or obs[0] < 1 or (meta.get("mstep_min"), meta.get("mstep_max")) != obs:
            raise BundleError(f"{algo}: manifest mstep [{meta.get('mstep_min')},"
                              f"{meta.get('mstep_max')}] != evidence {obs}")
        lineage = _verify_probe_lineage(bundle_dir, algo, meta, leg, diag_sha,
                                        authority)
        out[algo] = replace(leg, root_attested=True, actual_final_output=actual,
                            probe_lineage=_freeze(lineage) if lineage else None,
                            problem={"fixture_sha256": meta.get("fixture_sha256"),
                                     "parameter_sha256": meta.get("parameter_sha256")},
                            external_manifest_attested=expected_manifest_sha256 is not None,
                            source_commit_attested=expected_repo_commit is not None,
                            # the NAME alone is not an anchor; the bytes are
                            fixture_attested=bool(expected_fixture_id
                                                  and expected_fixture_manifest_sha256))
    # SAME-PROBLEM: both legs share one fixture + one parameter set.
    if len(fixtures) != 1 or None in fixtures:
        raise BundleError(f"legs disagree on fixture_sha256: {fixtures}")
    if len(params) != 1 or None in params:
        raise BundleError(f"legs disagree on parameter_sha256: {params}")
    return {"manifest": manifest, "algorithms": out}
