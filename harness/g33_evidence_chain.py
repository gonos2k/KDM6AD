#!/usr/bin/env python3
"""Walk claim -> finding -> run, and report where the chain stops (owner §9.2).

`test_g33_claims` pins each claim's FINDING digest and fails when it drifts, so
that link cannot rot. The link past it -- to the RUN whose numbers the finding
quotes -- is not pinned at all, so a finding can outlive the bundle that produced
it with no signal anywhere.

Three links exist and they are in three different states:

    claim  -> finding    pinned, CHECKED by test_g33_claims
    claim  -> run        NOT PINNED -- what `artifacts:` adds here
    bundle -> finding    pinned, unchecked, and structurally a SNAPSHOT

That last one deserves care. A published bundle is content-addressed and
immutable, so the finding digest inside its manifest can never be updated. When a
finding is later revised -- a correction, or the claim-status stamper writing its
block -- it diverges from that pin permanently. That is legitimate history, not
rot: the pin records the finding AS IT READ when the run was published. The defect
is only that nothing surfaces the divergence, so a reviewer cannot tell whether a
revision changed the prose or the numbers.

So this tool REPORTS divergence and REFUSES to treat it as failure. What it fails
on is the direction that is supposed to be live: a claim pinning an artifact that
is present and does not match.

    python g33_evidence_chain.py           # the chain, and where it stops
    python g33_evidence_chain.py --check    # exit 1 on a live artifact mismatch

Bundles live outside the repo (`~/kdm6ad-g33m-*`), so an absent bundle is
`unavailable`, never a failure -- the same local-only posture the Fortran leg has.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import g33_refine_manifest as rm  # noqa: E402

EVIDENCE = HERE / "evidence"
REGISTRY = EVIDENCE / "CLAIMS.yaml"
REPO = HERE.parent
#: where published bundles land; outside the repo and gitignored by design.
#: A module constant rather than a call inside each function, so a test can point
#: the whole tool at a fixture tree instead of the real home directory.
HOME = Path.home()


def bundle_roots() -> list[Path]:
    return sorted(HOME.glob("kdm6ad-g33m-*"))


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def claims() -> list[dict]:
    """[{id, evidence[], artifacts{path: digest}}].

    Parsed here rather than imported so this tool cannot inherit the stamper's
    parsing, which deliberately reads only what stamping needs.
    """
    out, cur, in_art = [], None, False
    for line in REGISTRY.read_text().splitlines():
        if re.match(r"^  - id: ", line):
            cur = {"id": line.split("id:", 1)[1].strip(),
                   "evidence": [], "artifacts": {}}
            out.append(cur)
            in_art = False
        elif cur is None:
            continue
        elif (m := re.match(r"^    (\w+):\s*(.*)$", line)):
            in_art = m.group(1) == "artifacts"
            if m.group(1) == "evidence":
                cur["evidence"] = re.findall(r"[\w.]+\.md", m.group(2))
            elif m.group(1) == "status":
                cur["status"] = m.group(2).strip()
        elif in_art and (m := re.match(r"^      - (\S+):\s*([0-9a-f]+)\s*$", line)):
            cur["artifacts"][m.group(1)] = m.group(2)
    return out


def bundles() -> dict:
    """{bundle_path: manifest} for every published bundle present on this host."""
    out = {}
    for root in bundle_roots():
        for mf in sorted(root.glob("*/manifest.json")):
            try:
                out[f"{root.name}/{mf.parent.name}"] = json.loads(mf.read_text())
            except (OSError, json.JSONDecodeError):
                continue
    return out


def snapshots() -> list[dict]:
    """Every bundle -> finding pin, and whether the finding still reads that way.

    `divergent` is INFORMATION, not failure: the bundle is immutable, so a
    revised finding must diverge from it.
    """
    out = []
    for name, man in bundles().items():
        for f in man.get("findings", []):
            p = REPO / f["path"]
            out.append({
                "bundle": name, "finding": Path(f["path"]).name,
                "pinned": f["sha256"],
                "state": ("absent" if not p.is_file() else
                          "matches" if sha256(p) == f["sha256"] else "divergent"),
            })
    return out


def _schema_violations(man: dict) -> list:
    """What this manifest fails to satisfy, from the SCHEMA'S OWN validator.

    The checker had its own copy, which tested only truthiness -- so `[{}]`
    counted as a pin block and a v2 bundle carrying two empty dicts checked out
    clean via the legacy-compatible `analyzer-unpinned` state. One validator,
    called by the producer before publishing and by this checker before
    believing anything, is what stops a bundle being valid to one and invalid to
    the other (owner P0-2).
    """
    return rm.validate(man)


def members_of(manifest: Path) -> list[dict]:
    """Each member beside `manifest`, checked against the digest it recorded.

    Pinning a manifest is only worth as much as the manifest's own pins: it
    carries every member's `output_sha256`, so following that link is what turns
    "this claim names a run" into "this claim names these exact raw streams".
    """
    out = []
    # A manifest whose own digest MATCHES but whose content is unreadable used
    # to return an empty child list, which reads as an artifact with nothing to
    # check -- indistinguishable from a clean one (owner P0-5). Parsing failure
    # is corruption, not absence of work.
    try:
        man = json.loads(manifest.read_text())
    except OSError as e:
        return [{"file": manifest.name, "state": "MANIFEST-UNREADABLE",
                 "detail": str(e)}]
    except json.JSONDecodeError as e:
        return [{"file": manifest.name, "state": "MANIFEST-UNREADABLE",
                 "detail": f"not JSON: {e}"}]
    if not isinstance(man, dict):
        return [{"file": manifest.name, "state": "MANIFEST-SCHEMA-MISMATCH",
                 "detail": f"top level is {type(man).__name__}, not an object"}]
    # `members` is the one block every schema has carried. Its ABSENCE is a
    # different statement from an empty list, and only the second is a bundle
    # that legitimately published none.
    if "members" not in man:
        return [{"file": manifest.name, "state": "MANIFEST-MISSING-MEMBERS",
                 "detail": f"keys: {sorted(man)[:8]}"}]
    bad = _schema_violations(man)
    if bad:
        return [{"file": manifest.name, "state": "MANIFEST-SCHEMA-MISMATCH",
                 "detail": "; ".join(bad)}]
    for mem in man.get("members", []):
        p = manifest.parent / mem["file"]
        out.append({"file": mem["file"],
                    "state": ("absent" if not p.is_file() else
                              "matches" if sha256(p) == mem.get("output_sha256")
                              else "MISMATCH")})
    # The ANALYSES too (owner §14-4). A claim quotes a table, and the table comes
    # from an analysis -- so a chain that stopped at the raw stream stopped one
    # step short of the number being cited. This includes the ARM STREAMS, which
    # the manifest records with analysis == "arm_stream": those are the raw runs
    # the multi-arm decomposition was computed from, and without them the chain
    # stopped at a derived JSON (owner §4).
    for an in man.get("analyses", []):
        p = manifest.parent / an["file"]
        out.append({"file": an["file"],
                    "state": ("absent" if not p.is_file() else
                              "matches" if sha256(p) == an.get("sha256")
                              else "MISMATCH")})
        # The ANALYZER the manifest names, by digest. It was recorded and never
        # checked, so an analyzer could change under a published analysis with
        # nothing reporting it (owner §8.2). Absent is reported, not failed: the
        # analyzer lives in the repo, and an OLD bundle legitimately names a
        # path that a later refactor moved.
        out.append(_analyzer_state(an))
    out.extend(_module_states(man))
    return out


def _blob_at(commit: str, path: str) -> str | None:
    """The git blob SHA of `path` as of `commit`, or None if it does not resolve."""
    r = subprocess.run(["git", "rev-parse", f"{commit}:{path}"], cwd=REPO,
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def _analyzer_state(an: dict) -> dict:
    """Whether the analyzer this analysis ran can still be RECOVERED.

    Resolved from the pinned commit, NOT compared against the working tree
    (owner §16-6). Comparing against today's file could only ever say "still the
    same", so an analyzer that legitimately moved on made the bundle
    unverifiable -- which is why the old check reported and never failed.

    A pin that does not resolve is a FAILURE: the commit was rewritten, the file
    was deleted from history, or the pin was wrong. Bundles published before
    this pin existed keep the old report-only behaviour, named as legacy.
    """
    path = an.get("analyzer")
    if not path:
        return {"file": "<no analyzer recorded>", "state": "analyzer-unpinned"}
    commit, blob = an.get("analyzer_commit"), an.get("analyzer_blob_sha")
    if not (commit and blob):
        src = REPO / path
        return {"file": path, "state": (
            "legacy-analyzer-absent" if not src.is_file()
            else "matches" if sha256(src) == an.get("analyzer_sha256")
            else "legacy-analyzer-changed")}
    got = _blob_at(commit, path)
    if got is None:
        return {"file": path, "state": "ANALYZER-UNRESOLVABLE",
                "detail": f"{commit[:12]}:{path} does not resolve in this repo"}
    if got != blob:
        return {"file": path, "state": "ANALYZER-BLOB-MISMATCH",
                "detail": f"pinned {blob[:12]}, {commit[:12]} holds {got[:12]}"}
    return {"file": path, "state": "matches"}


#: manifest key -> the field naming the module, since the analyzer entries call
#: it `analyzer` and the parser/producer entries call it `path`.
_PIN_BLOCKS = (("member_parsers", "path"), ("producer_modules", "path"),
               ("tracked_build_inputs", "path"))


def _module_states(man: dict) -> list:
    """The parsers and producer modules, pinned exactly like the analyzers.

    An analysis is only as good as the stream its parser admitted, so a parser
    recorded by content digest alone was checkable against today's working tree
    and nothing else -- the defect §16-6 fixed one layer up (owner P0-2).
    """
    out = []
    for key, field in _PIN_BLOCKS:
        entries = man.get(key) or []
        if not entries:
            # PER BLOCK. An `any()` across both let a bundle carrying parsers
            # but no producer_modules satisfy the combined check, and the
            # missing block vanished from the report -- no rows at all reads as
            # "nothing to check", which is how a bundle that pinned nothing
            # looked exactly like one that checked out (Codex).
            out.append({"file": f"<{key}>", "state": "modules-unpinned"})
            continue
        for e in entries:
            if not isinstance(e, dict):
                # A crash is not a verdict: garbage in a pin block used to raise
                # AttributeError out of `--check` rather than failing the bundle.
                out.append({"file": f"<{key}>", "state": "MANIFEST-SCHEMA-MISMATCH",
                            "detail": f"entry is {type(e).__name__}, not an object"})
                continue
            out.append(_analyzer_state({"analyzer": e.get(field),
                                        "analyzer_sha256": e.get("content_sha256")
                                        or e.get("sha256"),
                                        "analyzer_commit": e.get("commit"),
                                        "analyzer_blob_sha": e.get("blob_sha")}))
    return out


def chain() -> list[dict]:
    """Per claim: its findings, its pinned artifacts, and each artifact's state."""
    have = bundles()
    named = {}
    for name, man in have.items():
        for f in man.get("findings", []):
            named.setdefault(Path(f["path"]).name, []).append(name)
    out = []
    for c in claims():
        arts = []
        for rel, want in c["artifacts"].items():
            p = HOME / rel
            state = ("unavailable" if not p.is_file() else
                     "matches" if sha256(p)[:len(want)] == want else "MISMATCH")
            a = {"path": rel, "pinned": want, "state": state, "members": []}
            if state == "matches" and p.name == "manifest.json":
                a["members"] = members_of(p)
            arts.append(a)
        out.append({
            "id": c["id"], "status": c.get("status", "?"),
            "evidence": c["evidence"], "artifacts": arts,
            # A run that names this claim's finding, if one was ever published.
            "runs": sorted({b for d in c["evidence"] for b in named.get(d, [])}),
        })
    return out


def report() -> None:
    rows = chain()
    pinned = [r for r in rows if r["artifacts"]]
    traceable = [r for r in rows if r["runs"]]
    print(f"  {len(rows)} claims: {len(pinned)} pin a run artifact, "
          f"{len(traceable)} cite a finding some published run names.\n")
    print(f"  {'claim':22} {'status':10} {'artifacts':>10}  runs")
    for r in rows:
        st = ",".join(sorted({a["state"] for a in r["artifacts"]})) or "-"
        print(f"  {r['id']:22} {r['status']:10} {st:>10}  "
              f"{','.join(r['runs']) or '-'}")
    for r in rows:
        for a in r["artifacts"]:
            if a["state"] == "MISMATCH":
                print(f"    !! {r['id']}: {a['path']} does not match its pin")
            for m in a["members"]:
                mark = "!!" if m["state"] == "MISMATCH" else "  "
                print(f"    {mark} {r['id']}: {a['path'].rsplit('/', 2)[-2]}/"
                      f"{m['file']} {m['state']}")

    snaps = snapshots()
    if snaps:
        print(f"\n  bundle -> finding snapshots ({len(snaps)}). `divergent` means the")
        print("  finding was revised after the run; the bundle is immutable, so this")
        print("  is history, not rot. It is reported so a reviewer can ask whether the")
        print("  revision changed the prose or the numbers.")
        for s in snaps:
            print(f"    {s['state']:10} {s['bundle']:26} {s['finding']}")
    if not bundles():
        print("\n  No bundles present on this host: run linkage is unavailable, "
              "not failing.")


#: Every state the chain can produce, classified. An UNLISTED state FAILS.
#:
#: Both fail-open holes found here were the same shape: a state was added to a
#: producer and never wired into the verdict, so it fell through an if/elif
#: chain and passed. Enumerating the vocabulary and failing anything outside it
#: closes the CLASS rather than the two instances -- "nobody classified this"
#: must not read as "this is fine".
PASSING_STATES = frozenset({
    "matches",
    "unavailable",             # the bundle lives outside the repo, by design
    "divergent",               # a finding revised after its immutable bundle
    "absent-finding",          # the finding a snapshot names is gone from the repo
    "analyzer-unpinned",       # reported: the entry names no analyzer at all
    "modules-unpinned",        # reported: the bundle predates the module pins
    "legacy-analyzer-changed",
    "legacy-analyzer-absent",
})
FAILING_STATES = frozenset({
    "MISMATCH", "absent",
    "ANALYZER-UNRESOLVABLE", "ANALYZER-BLOB-MISMATCH",
    "MANIFEST-UNREADABLE", "MANIFEST-SCHEMA-MISMATCH", "MANIFEST-MISSING-MEMBERS",
})


def verdict(state: str) -> bool:
    """True if `state` fails the check. An unclassified state fails."""
    if state in PASSING_STATES:
        return False
    return True


def check() -> int:
    """Fail only on the live direction: a pinned artifact that is present and
    differs. Absent artifacts and divergent snapshots are not failures."""
    bad = []
    for r in chain():
        for a in r["artifacts"]:
            if verdict(a["state"]):
                bad.append(f"{r['id']}: {a['path']} -> {a['state']}"
                           + ("" if a["state"] in FAILING_STATES
                              else "  [UNCLASSIFIED state -- failing by default]"))
            # ABSENT is a failure HERE, unlike an absent top-level manifest
            # (owner P0-4). Once the parent manifest is present and matches, the
            # bundle has declared these files exist; one of them missing is a
            # corrupt or incomplete bundle, not an unavailable one.
            for m in a["members"]:
                if not verdict(m["state"]):
                    continue
                extra = "" if m["state"] in FAILING_STATES else \
                    "  [UNCLASSIFIED state -- failing by default]"
                bad.append(f"{r['id']}: {a['path']} -> {m.get('file', '?')}: "
                           f"{m['state']} {m.get('detail', '')}{extra}".rstrip())
    print("\n".join(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(check() if "--check" in sys.argv[1:] else (report(), 0)[1])
