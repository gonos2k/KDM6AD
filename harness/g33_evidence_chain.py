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
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
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


def members_of(manifest: Path) -> list[dict]:
    """Each member beside `manifest`, checked against the digest it recorded.

    Pinning a manifest is only worth as much as the manifest's own pins: it
    carries every member's `output_sha256`, so following that link is what turns
    "this claim names a run" into "this claim names these exact raw streams".
    """
    out = []
    try:
        man = json.loads(manifest.read_text())
    except (OSError, json.JSONDecodeError):
        return out
    for mem in man.get("members", []):
        p = manifest.parent / mem["file"]
        out.append({"file": mem["file"],
                    "state": ("absent" if not p.is_file() else
                              "matches" if sha256(p) == mem.get("output_sha256")
                              else "MISMATCH")})
    # The ANALYSES too (owner §14-4). A claim quotes a table, and the table comes
    # from an analysis -- so a chain that stopped at the raw stream stopped one
    # step short of the number being cited.
    for an in man.get("analyses", []):
        p = manifest.parent / an["file"]
        out.append({"file": an["file"],
                    "state": ("absent" if not p.is_file() else
                              "matches" if sha256(p) == an.get("sha256")
                              else "MISMATCH")})
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


def check() -> int:
    """Fail only on the live direction: a pinned artifact that is present and
    differs. Absent artifacts and divergent snapshots are not failures."""
    bad = []
    for r in chain():
        for a in r["artifacts"]:
            if a["state"] == "MISMATCH":
                bad.append(f"{r['id']}: {a['path']} does not match its pinned "
                           f"digest {a['pinned']}")
            bad += [f"{r['id']}: {a['path']} -> {m['file']} does not match the "
                    f"digest the manifest recorded" for m in a["members"]
                    if m["state"] == "MISMATCH"]
    print("\n".join(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(check() if "--check" in sys.argv[1:] else (report(), 0)[1])
