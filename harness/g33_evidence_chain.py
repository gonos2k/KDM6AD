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
    out, cur, in_art, folded, section = [], None, False, None, None
    for line in REGISTRY.read_text().splitlines():
        if re.match(r"^  - id: ", line):
            section = None
            cur = {"id": line.split("id:", 1)[1].strip(),
                   "evidence": [], "artifacts": {}, "expected_values": [],
                   "expected_predicates": [], "unbound": []}
            out.append(cur)
            in_art = folded = None or False
        elif cur is None:
            continue
        elif (m := re.match(r"^    (\w+):\s*(.*)$", line)):
            folded = None
            in_art = m.group(1) in ("artifacts", "expected_values",
                                    "expected_predicates")
            section = m.group(1)
            if m.group(1) == "binding_status":
                # COMPUTED now, from what the claim binds and what it declares
                # it does not -- see `_binding_status`. Twice a claim declared
                # `full` beside a comment saying a figure was unbound, which is
                # what a self-declaration buys you. Refused here rather than
                # ignored: a field the tool no longer reads, left in the file,
                # goes on reading as the answer to a reviewer (owner §16-7).
                raise ValueError(
                    f"{cur['id']}: `binding_status` is computed, not declared "
                    f"-- list what the claim does NOT bind under `unbound:` "
                    f"and the status follows from it")
            if m.group(1) == "evidence":
                cur["evidence"] = re.findall(r"[\w.]+\.md", m.group(2))
            elif m.group(1) in ("status", "artifact_status", "evidence_kind",
                                "blocker_kind", "migration_blocker"):
                cur[m.group(1)] = m.group(2).strip()
                # A FOLDED value (`key: >`) continues on the indented lines
                # below. Capturing only the first line took the `>` itself as
                # the value -- truthy, so the field looked present while saying
                # nothing. Long text has to be folded here: an unquoted scalar
                # containing ": " is invalid YAML, which is how a one-line
                # blocker broke the file (Codex).
                folded = m.group(1) if m.group(2).strip() == ">" else None
                if folded:
                    # An EMPTY folded block must read as absent. Leaving the
                    # ">" as the value made a blocker with no body truthy and
                    # non-empty, so "declares a kind but no reason" passed on a
                    # claim whose reason had been deleted.
                    cur[folded] = ""
        elif folded and line.startswith("      ") and line.strip():
            cur[folded] = (cur[folded] + " " + line.strip()).lstrip("> ").strip()
        elif in_art and section == "artifacts" and (
                m := re.match(r"^      - +(\S+):\s*([0-9a-f]+)\s*$", line)):
            cur["artifacts"][m.group(1)] = m.group(2)
        elif in_art and section == "expected_values" and (
                m := re.match(r"^      - +([^#\s]+)#([^:\s]+):\s*(\S+)"
                              r"(?:\s+~\s+(\S+))?\s*$", line)):
            cur["expected_values"].append(
                {"file": m.group(1), "path": m.group(2),
                 "value": float(m.group(3)),
                 "tolerance": float(m.group(4)) if m.group(4) else 0.0})
        elif in_art and section == "expected_predicates" and (
                m := re.match(r"^      - +([^#\s]+)#([^:\s]+):\s*(.+?)\s*$", line)):
            # NON-NUMERIC load-bearing facts. `expected_values` takes floats,
            # so `causal_attribution_valid: true` and `comparable: true` sat in
            # the artifact unbound -- a claim could rest on them and the chain
            # had no way to say so (owner §7.3).
            cur["expected_predicates"].append(
                {"file": m.group(1), "path": m.group(2),
                 "want": _literal(m.group(3))})
        elif section == "unbound" and not (
                not line.strip() or line.lstrip().startswith("#")):
            # A figure the claim's TEXT publishes and the claim does NOT bind,
            # with the reason. This is where the author's judgement about what
            # counts as a load-bearing figure enters as DATA -- the owner ruled
            # out scanning the prose for numeric literals, because deciding
            # which numbers are figures (`F:2922`, `31/144`, `12 fields x 3
            # columns`) is exactly that judgement (owner D5).
            #
            # Every line in the block must match one of the three shapes. An
            # unrecognised line used to fall off the end of this chain and be
            # ignored, which is how a mistyped key silently unbinds a fact.
            if (m := re.match(r"^      - +figure: +(\S.*?)\s*$", line)):
                cur["unbound"].append({"figure": m.group(1), "why": ""})
            elif cur["unbound"] and (
                    m := re.match(r"^        why: +(\S.*?)\s*$", line)):
                cur["unbound"][-1]["why"] = m.group(1)
            elif cur["unbound"] and (m := re.match(r"^ {10,}(\S.*?)\s*$", line)):
                # A continuation of the plain scalar above it, joined with a
                # space -- what a YAML load does with the same lines.
                last = cur["unbound"][-1]
                last["why" if last["why"] else "figure"] += " " + m.group(1)
            else:
                raise ValueError(
                    f"{cur['id']}: unparseable `unbound` entry: {line.strip()!r}")
        elif cur is not None and re.match(r"^\s+-\s", line):
            # An ORPHAN list item: it is not inside a folded block (that branch
            # ran first) and it matched no binding shape. Two ways to get here
            # and both were silent:
            #
            #   * a malformed entry under a good header -- a missing "#", a
            #     missing value -- which unbound one fact;
            #   * a header that is mistyped or mis-indented, which orphans the
            #     WHOLE block. `expected_predicate:` singular dropped two
            #     declarations and the claim still read as bound (Codex).
            #
            # The first version only caught the first, because it required
            # `in_art` -- which is exactly what a bad header switches off. The
            # second still demanded ONE space after the dash, so
            # `-  file#path: 0.5` -- valid YAML -- parsed as nothing and
            # tripped nothing (Codex).
            #
            # The shapes take ` +`, SPACES only. A tab is not valid YAML
            # anywhere in indentation and `yaml.safe_load` refuses it, so
            # accepting one here would put this parser ahead of the canonical
            # one and the registry would pass a check the CI's YAML load
            # fails. A tab-separated item therefore reaches this branch and is
            # refused, which is what pyyaml does with it (Codex).
            raise ValueError(
                f"{cur['id']}: unparseable `{section}` entry: {line.strip()!r}")
    return out


def _literal(raw: str):
    """The declared value: true/false/null, a number, or a bare string."""
    low = raw.strip().strip('"\'')
    if raw.strip() in ("true", "false"):
        return raw.strip() == "true"
    if raw.strip() == "null":
        return None
    try:
        return int(raw.strip())
    except ValueError:
        pass
    try:
        return float(raw.strip())
    except ValueError:
        return low


def bundles() -> dict:
    """{bundle_path: manifest} for every published bundle present on this host."""
    out = {}
    for root in bundle_roots():
        for mf in sorted(root.glob("*/manifest.json")):
            try:
                out[f"{root.name}/{mf.parent.name}"] = json.loads(mf.read_text())
            except (OSError, ValueError):
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
        return [{"file": manifest.name, "scope": "bundle",
                 "state": "MANIFEST-UNREADABLE", "detail": str(e)}]
    except ValueError as e:
        # ValueError, not json.JSONDecodeError: a non-UTF-8 manifest raises
        # UnicodeDecodeError from `read_text`, which is a ValueError but NOT a
        # JSONDecodeError -- so it escaped BOTH clauses and crashed the whole
        # chain walk instead of reporting the corruption it is (Codex).
        return [{"file": manifest.name, "scope": "bundle",
                 "state": "MANIFEST-UNREADABLE", "detail": f"not JSON: {e}"}]
    if not isinstance(man, dict):
        return [{"file": manifest.name, "scope": "bundle", "state": "MANIFEST-SCHEMA-MISMATCH",
                 "detail": f"top level is {type(man).__name__}, not an object"}]
    # `members` is the one block every schema has carried. Its ABSENCE is a
    # different statement from an empty list, and only the second is a bundle
    # that legitimately published none.
    if "members" not in man:
        return [{"file": manifest.name, "scope": "bundle", "state": "MANIFEST-MISSING-MEMBERS",
                 "detail": f"keys: {sorted(man)[:8]}"}]
    bad = _schema_violations(man)
    if bad:
        return [{"file": manifest.name, "scope": "bundle", "state": "MANIFEST-SCHEMA-MISMATCH",
                 "detail": "; ".join(bad)}]
    for mem in man.get("members", []):
        p = manifest.parent / mem["file"]
        out.append({"file": mem["file"],
                    "scope": "bundle", "origin": "member", "state": ("absent" if not p.is_file() else
                              "matches" if sha256(p) == mem.get("output_sha256")
                              else "MISMATCH")})
    # The ANALYSES too (owner §14-4). A claim quotes a table, and the table comes
    # from an analysis -- so a chain that stopped at the raw stream stopped one
    # step short of the number being cited. This includes the ARM STREAMS, which
    # the manifest records with analysis == "arm_stream": those are the raw runs
    # the multi-arm decomposition was computed from, and without them the chain
    # stopped at a derived JSON (owner §4).
    # The BINARY that produced the numbers, and its provenance. Both are in the
    # bundle; nothing followed them (owner §7).
    for a in man.get("build_artifacts", []):
        p = manifest.parent / a["file"]
        out.append({"file": a["file"],
                    "scope": "bundle", "origin": "build_artifact", "state": ("absent" if not p.is_file() else
                              "matches" if sha256(p) == a.get("sha256")
                              else "MISMATCH")})
    for an in man.get("analyses", []):
        p = manifest.parent / an["file"]
        out.append({"file": an["file"],
                    "scope": "bundle", "origin": "analysis", "state": ("absent" if not p.is_file() else
                              "matches" if sha256(p) == an.get("sha256")
                              else "MISMATCH")})
        # The RAW STREAMS a multi-run analysis read. They were written into the
        # bundle with a digest each and then never re-hashed by anything, so a
        # kept stream could be edited or deleted and the chain said nothing:
        # the derived JSON still matched, and it is the JSON every binding
        # resolves against (owner §5.3).
        #
        # Measured before this: appending one byte to `mr.*.txt`, and removing
        # it outright, both left values, predicates, artifacts and members
        # entirely clean.
        for src in an.get("inputs") or []:
            if not isinstance(src, dict) or not isinstance(src.get("file"), str):
                out.append({"file": f"{an['file']}#inputs",
                            "scope": "bundle", "origin": "multi_run_input",
                            "state": "MANIFEST-SCHEMA-MISMATCH",
                            "detail": f"malformed input entry: {src!r}"[:120]})
                continue
            q = manifest.parent / src["file"]
            out.append({"file": src["file"], "scope": "bundle",
                        "origin": "multi_run_input",
                        "state": ("absent" if not q.is_file() else
                                  "matches" if sha256(q) == src.get("sha256")
                                  else "MISMATCH")})
        # The manifest's `ran` block against the one INSIDE the analysis it
        # describes. The producer copies it across, so they are two records of
        # one fact -- and two records never checked against each other are one
        # record and one decoration (Codex).
        if "ran" in an and p.is_file():
            out.append({"file": an["file"], "scope": "bundle",
                        "origin": "run_identity", "state": _ran_state(p, an)})
        # The ANALYZER the manifest names, by digest. It was recorded and never
        # checked, so an analyzer could change under a published analysis with
        # nothing reporting it (owner §8.2). Absent is reported, not failed: the
        # analyzer lives in the repo, and an OLD bundle legitimately names a
        # path that a later refactor moved.
        # ONLY for derived analyses. An `arm_stream` is a raw driver run and
        # has no analyzer BY DESIGN -- the schema's tagged union says so -- yet
        # this reported "no analyzer recorded" for every one of them, and
        # --require-available turned that into a closeout blocker demanding
        # something that must not exist. A blocker with no resolution is not a
        # blocker, it is noise that hides the real ones.
        if an.get("analysis") != "arm_stream":
            out.append({"scope": "repo", "origin": "analyzer",
                        **_analyzer_state(an)})
    # ORIGIN, not path. Every analyzer path is ALSO a producer_modules pin --
    # all six of them on the real bundle -- so counting rows by `file` cannot
    # tell an analyzer row from a module-pin row, and a missing analyzer row is
    # masked by the module row at the same path (Codex).
    out.extend({"scope": "repo", "origin": "module_pin", **m}
               for m in _module_states(man))
    out.extend({"scope": "repo", "origin": "commit_anchor", **c}
               for c in _commit_states(man))
    return out


#: (repo, commit) -> reachable. `--contains` walks history and the bundles share
#: a handful of commits, so the same question was asked once per bundle per
#: walk. Measured, this is small -- one `chain()` goes from 670 git subprocesses
#: to 660, the other 660 being the pre-existing `cat-file` blob resolutions --
#: but it is per-bundle work that grows as bundles accumulate, and the answer
#: cannot change within a run. Keyed on REPO as well as the commit because the
#: regression points it at a throwaway repo, and a cache keyed on the sha alone
#: would answer for the wrong one.
_REACHABLE: dict = {}


def _reachable(commit: str) -> bool:
    """Is `commit` reachable from a ref, or merely still in the object database?

    `git cat-file -e` answers the wrong question. A commit discarded by a
    rebase or a squash survives as a loose object until gc, so every blob
    pinned through it keeps resolving and every content digest keeps matching
    -- the whole chain stays green while the anchor is already dangling.
    """
    key = (str(REPO), commit)
    if key not in _REACHABLE:
        r = subprocess.run(["git", "for-each-ref", "--contains", commit,
                            "--count=1"], cwd=REPO, capture_output=True,
                           text=True)
        _REACHABLE[key] = r.returncode == 0 and bool(r.stdout.strip())
    return _REACHABLE[key]


def _commit_states(man: dict) -> list:
    """Every commit this manifest anchors a pin to, checked for reachability.

    A bundle was produced, and the WIP commits it recorded were then squashed
    into one. The bundle's content pins all still verified -- the bytes had not
    changed -- but `repo_commit` and all three pin blocks named a commit no ref
    contained, so nothing could fetch the history the pins point into and gc
    would drop it (Codex). The point of pinning a commit is that a reader can
    go and get it.
    """
    seen: dict = {}
    if isinstance(man.get("repo_commit"), str) and man["repo_commit"]:
        seen.setdefault(man["repo_commit"], set()).add("repo_commit")
    for key, _field in _PIN_BLOCKS:
        for e in man.get(key) or []:
            c = e.get("commit")
            if isinstance(c, str) and c:
                seen.setdefault(c, set()).add(key)
    out = []
    for c, keys in sorted(seen.items()):
        ok = _reachable(c)
        out.append({
            "file": f"{c[:12]} [{'+'.join(sorted(keys))}]",
            "state": "matches" if ok else "COMMIT-UNREACHABLE",
            "detail": "" if ok else
                      f"no ref contains {c[:12]} -- this pin anchors to a "
                      f"commit discarded by a rebase or squash. It resolves "
                      f"today only because gc has not run"})
    return out


def _blob_at(commit: str, path: str) -> str | None:
    """The git blob SHA of `path` as of `commit`, or None if it does not resolve."""
    r = subprocess.run(["git", "rev-parse", f"{commit}:{path}"], cwd=REPO,
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


#: Where a row's digest was actually verified. `bundle` means the file was
#: hashed at <bundle>/<file>; `repo` means it was resolved from a pinned commit
#: in the source tree. Joining a `repo` path under the bundle names a location
#: NOTHING ever hashed, so a figure bound there would inherit a guarantee made
#: about a different file entirely (Codex).
def _ran_state(path: Path, an: dict) -> str:
    """Does the analysis file agree with the manifest about what it ran?"""
    try:
        doc = json.loads(path.read_text())
    except (OSError, ValueError):
        # ValueError, not json.JSONDecodeError: a non-UTF-8 file raises
        # UnicodeDecodeError from `read_text`, which is a ValueError but NOT a
        # JSONDecodeError, so the narrower catch let it escape as a crash
        # (Codex). Both mean the same thing here -- the file cannot be read as
        # the JSON it claims to be.
        return "RUN-IDENTITY-UNREADABLE"
    if not isinstance(doc, dict) or "ran" not in doc:
        return "RUN-IDENTITY-ABSENT"
    return "matches" if doc["ran"] == an["ran"] else "RUN-IDENTITY-MISMATCH"


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
    # The TRIPLE must agree. `content_sha256` records what RAN and `blob_sha`
    # names what is RECOVERABLE; resolving the blob alone cannot tell the two
    # apart, so a bundle built from an uncommitted file passed while its own
    # manifest recorded the disagreement (owner P0-2).
    content = an.get("analyzer_sha256")
    if content:
        raw = subprocess.run(["git", "cat-file", "blob", blob], cwd=REPO,
                             capture_output=True)
        if raw.returncode != 0:
            return {"file": path, "state": "ANALYZER-UNRESOLVABLE",
                    "detail": f"blob {blob[:12]} is not readable in this clone"}
        recovered = hashlib.sha256(raw.stdout).hexdigest()
        if recovered != content:
            return {"file": path, "state": "PIN-INCONSISTENT",
                    "detail": f"ran {content[:12]}, the pinned blob is "
                              f"{recovered[:12]} -- the pin names a file that "
                              f"did not run"}
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


def flatten(obj, prefix="") -> dict:
    """{dotted path: leaf value} for one analysis JSON."""
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(flatten(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = obj
    return out


def covered_files(artifacts: list) -> set:
    """The files a claim's pinned artifacts actually VOUCH for.

    ONLY rows whose digest was verified AT <bundle>/<file>. The provenance rows
    are verified in the SOURCE TREE, so joining their paths under the bundle
    names a location nothing ever hashed -- a figure bound to
    <bundle>/harness/g33_refine_analyze.py would have inherited a guarantee made
    about the repo file of that name (Codex).

    A function, not an expression inlined in `chain()`, so the regression test
    can exercise THIS filter. The first version of that test re-derived its own
    (`"/harness/" not in c`) and would have passed with the real one deleted --
    the weaker-check-beside-the-real-one failure this repo keeps finding.
    """
    return {f"{Path(a['path']).parent}/{m['file']}"
            for a in artifacts if a["state"] == "matches"
            for m in a["members"]
            if m["state"] == "matches" and m.get("scope") == "bundle"}


def _resolve(want: dict, covered: set, bundles: dict, kind: str, compare):
    """Look up ONE declared fact in the artifact it is declared against.

    Declared, never discovered. Searching the JSONs for a number equal to the
    published one would bind a claim to whatever value happened to sit near it
    -- on this fixture five unrelated fields across two files carry 1.0, so
    "100.00%" would have matched all of them.

    `covered` is the set of files whose DIGEST was verified: members, analyses
    and build artifacts of a pinned manifest that itself matched. Requiring only
    that the file sit in a pinned bundle DIRECTORY was not the same thing at
    all -- a JSON dropped beside the manifest, covered by no digest, resolved
    and reported `value-matches` (Codex). Beside the evidence is not the
    evidence.

    ONE rule, two bindings. Figures and predicates were two functions that
    said the same thing, and three findings in a single cycle were "the fix
    reached one and not the other" (owner D3):

      * `read_cells` refused duplicate rows, `read_state` did not;
      * MANIFEST-ABSENT-IN-PRESENT-BUNDLE was seen by values, not predicates;
      * the predicate resolver keyed the excusable case on a PREFIX SCAN over
        bundle names while the value resolver keyed it on the artifact's own
        state -- a lookalike, not the rule. They disagreed on the same input: a
        deleted analysis file resolved VALUE-UNPINNED-FILE and failed, while
        the predicate beside it resolved `predicate-unavailable` and passed.
        Its docstring said "resolved exactly like a value" throughout.

    So `kind` names the binding and `compare` is the only thing that differs.
    The comparison owns its own state names because it owns its own failures
    -- a figure can be non-numeric, a predicate cannot -- and everything
    before it is shared code, which is the point.
    """
    def out(state, got=None):
        return {**want, "state": state, "got": got}

    if want["file"] not in covered:
        # Not covered has two causes, and only one is a defect. On a host
        # without the private bundles NOTHING is covered, so failing here would
        # fail the routine check everywhere the evidence legitimately is not --
        # the very thing --require-available exists to keep separate.
        if bundles.get(str(Path(want["file"]).parent)) == "unavailable":
            return out(f"{kind.lower()}-unavailable")
        return out(f"{kind}-UNPINNED-FILE")
    f = HOME / want["file"]
    if not f.is_file():
        return out(f"{kind}-FILE-ABSENT")
    try:
        doc = json.loads(f.read_text())
    except (OSError, ValueError):
        return out(f"{kind}-FILE-UNREADABLE")
    if any("." in str(k) for k in _keys_of(doc)):
        return out(f"{kind}-PATH-AMBIGUOUS")
    flat = flatten(doc)
    if want["path"] not in flat:
        return out(f"{kind}-PATH-ABSENT")
    got = flat[want["path"]]
    return out(compare(want, got), got)


def _compare_value(want: dict, got) -> str:
    if isinstance(got, bool) or not isinstance(got, (int, float)):
        return "VALUE-NOT-NUMERIC"
    ok = (got == want["value"] if want["tolerance"] == 0.0
          else abs(got - want["value"]) <= want["tolerance"])
    return "value-matches" if ok else "VALUE-MISMATCH"


def _compare_predicate(want: dict, got) -> str:
    # EXACT, and type-sensitive: `True == 1` in Python, so a bool declared
    # against a numeric 1 would pass while saying something different.
    ok = type(got) is type(want["want"]) and got == want["want"]
    return "predicate-matches" if ok else "PREDICATE-MISMATCH"


def resolve_value(want: dict, covered: set, bundles: dict) -> dict:
    """One declared FIGURE, compared numerically within its tolerance."""
    return _resolve(want, covered, bundles, "VALUE", _compare_value)


def resolve_predicate(want: dict, covered: set, bundles: dict) -> dict:
    """One declared non-numeric FACT, compared exactly and by type.

    `expected_values` takes floats, so `causal_attribution_valid: true` and
    `comparable: true` sat in their artifacts unbound while claims rested on
    them (owner §7.3).
    """
    return _resolve(want, covered, bundles, "PREDICATE", _compare_predicate)


def _keys_of(obj) -> list:
    """Every dict key anywhere in `obj`. A key containing "." would make the
    flattened path ambiguous, so resolution refuses rather than guessing."""
    if isinstance(obj, dict):
        return list(obj) + [k for v in obj.values() for k in _keys_of(v)]
    if isinstance(obj, list):
        return [k for v in obj for k in _keys_of(v)]
    return []


#: Every answer `_binding_status` can give, plus "" for a claim the question
#: does not apply to. A SECOND vocabulary, deliberately separate from the
#: artifact states: those say whether a file is what it was pinned as, these
#: say how much of a claim rests on one. Enumerated for the same reason --
#: "nobody classified this" must not read as "this is fine".
BINDING_STATUSES = frozenset({"full", "partial", "none", "UNDECLARED"})


def _binding_status(rows: list, unbound: list, pinned: bool) -> str:
    """How completely a claim's figures are bound -- DERIVED, never declared.

    Separate from `artifact_status`, which says the artifact is pinned and its
    digest verified and never said a single figure in the text was checked
    against it.

    It was a declared field for one cycle and the declaration went wrong twice
    in that cycle, both times the same way: `full` written beside a comment
    admitting a figure was unbound. A status a claim asserts about itself
    cannot catch that, because the assertion IS the thing being checked. So
    the registry now records only what it does NOT bind, and this reads:

      no bindings and no admission  UNDECLARED -- the claim says nothing, which
                                    is not the same as saying `none`
      nothing bound and verified    none
      an admission, or a binding
      that did not verify           partial
      otherwise                     full

    A binding that FAILS also cannot leave a claim `full`, which the declared
    field could not express at all: it was written once and never revisited
    when the evidence moved under it.

    Empty for a claim with no verified artifact: "how completely are this
    claim's figures bound" is a question about a claim that HAS an artifact,
    and answering it for one that does not would report the same word for a
    claim missing its evidence and a claim whose evidence binds nothing.
    """
    if not pinned:
        return ""
    if not rows and not unbound:
        return "UNDECLARED"
    bound = sum(1 for r in rows if not verdict(r["state"]))
    if not bound:
        return "none"
    return "partial" if (unbound or bound < len(rows)) else "full"


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
            # `unavailable` conflated two different facts: the bundle is not on
            # this host -- correct and expected on a public clone -- and the
            # bundle IS here with its manifest missing, which is corruption.
            # Both read as "nothing to check", so a claim bound to a gutted
            # bundle passed exactly like one on a machine that never had it
            # (Codex).
            #
            # The bundle DIRECTORY separates them, and it is the same
            # absent-versus-broken distinction as `exists()` against `lexists()`
            # on the store's symlink.
            if p.is_file():
                state = "matches" if sha256(p)[:len(want)] == want else "MISMATCH"
            elif p.parent.is_dir():
                state = "MANIFEST-ABSENT-IN-PRESENT-BUNDLE"
            else:
                state = "unavailable"
            a = {"path": rel, "pinned": want, "state": state, "members": []}
            if state == "matches" and p.name == "manifest.json":
                a["members"] = members_of(p)
            arts.append(a)
        # A figure may only be bound to a file whose DIGEST this claim's
        # pinned manifest verified. `members_of` already did that work; the
        # binding follows the same link rather than re-deriving a weaker one.
        covered = covered_files(arts)
        bundle_states = {str(Path(a["path"]).parent): a["state"] for a in arts}
        values = [resolve_value(w, covered, bundle_states)
                  for w in c["expected_values"]]
        # `.get`, because a synthetic claim in a test may predate the field.
        # Safe rather than fail-open: `claims()` initialises the key on every
        # real claim, so a missing one cannot come from the registry.
        #
        # `bundle_states`, the SAME namespace the values use. This passed
        # `have`, whose keys are the store's symlink names
        # (`kdm6ad-g33m-migrate/ncmin-001`) while a pinned path is
        # `.../ncmin-001.bundles/<digest>/...` -- so the "is this file inside a
        # bundle we pinned?" test never matched and every damaged or missing
        # file fell through to `predicate-unavailable`, which passes. The same
        # file resolved VALUE-UNPINNED-FILE and failed (Codex).
        preds = [resolve_predicate(w, covered, bundle_states)
                 for w in c.get("expected_predicates", [])]
        out.append({
            "id": c["id"], "status": c.get("status", "?"), "values": values,
            "predicates": preds,
            # COMPUTED from the two lines above and the claim's own list of
            # what it does not bind -- see `_binding_status` (owner §16-7).
            "binding_status": _binding_status(
                values + preds, c.get("unbound", []),
                c.get("artifact_status") == "pinned"),
            "unbound": c.get("unbound", []),
            "artifact_status": c.get("artifact_status", "?"),
            "migration_blocker": c.get("migration_blocker", ""),
            # DECLARED, not sniffed out of the prose. The kinds were inferred
            # by substring until rewriting nine blockers changed the wording
            # and every one of them stopped classifying -- the same failure as
            # inferring a member's identity from its path.
            "blocker_kind": c.get("blocker_kind", ""),
            "evidence_kind": c.get("evidence_kind", "?"),
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
    print(f"  {'claim':22} {'status':10} {'artifacts':>10} {'bound':>10}  runs")
    for r in rows:
        st = ",".join(sorted({a["state"] for a in r["artifacts"]})) or "-"
        # The DERIVED binding status, beside the artifact states it is derived
        # from. It answers the question `pinned` was silently taken to answer.
        print(f"  {r['id']:22} {r['status']:10} {st:>10} "
              f"{r['binding_status'] or '-':>10}  {','.join(r['runs']) or '-'}")
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
    "value-matches",
    "predicate-matches",
    "predicate-unavailable",   # the bundle the fact is declared against is absent
    "value-unavailable",       # the bundle the figure is declared against is not here
})
FAILING_STATES = frozenset({
    "MISMATCH", "absent", "PIN-INCONSISTENT",
    "ANALYZER-UNRESOLVABLE", "ANALYZER-BLOB-MISMATCH",
    "MANIFEST-UNREADABLE", "MANIFEST-SCHEMA-MISMATCH", "MANIFEST-MISSING-MEMBERS",
    "PREDICATE-MISMATCH", "PREDICATE-PATH-ABSENT", "PREDICATE-FILE-ABSENT",
    "PREDICATE-PATH-AMBIGUOUS", "PREDICATE-UNPINNED-FILE",
    "PREDICATE-FILE-UNREADABLE",
    "VALUE-MISMATCH", "VALUE-PATH-ABSENT", "VALUE-FILE-ABSENT",
    "VALUE-PATH-AMBIGUOUS", "VALUE-NOT-NUMERIC", "VALUE-UNPINNED-FILE",
    "VALUE-FILE-UNREADABLE",
    "RUN-IDENTITY-MISMATCH", "RUN-IDENTITY-ABSENT", "RUN-IDENTITY-UNREADABLE",
    "COMMIT-UNREACHABLE",
    # The bundle directory is here and its manifest is not. Absence of the
    # whole bundle is excusable on a clone; absence of the manifest INSIDE one
    # is a broken bundle, and it must not read as the former.
    "MANIFEST-ABSENT-IN-PRESENT-BUNDLE",
})


#: The states that pass ONLY because the evidence is not there to check.
#:
#: For a routine run they are correct passes -- the decision-grade bundles live
#: outside the repo by design, and a check cannot demand what was never
#: committed. For a CLOSEOUT they are the opposite: "we could not check this"
#: recorded as "we checked and it is fine" is exactly the reading a closeout
#: must not permit. `--require-available` fails them (owner priority 6).
EXCUSED_BY_ABSENCE = frozenset({
    "unavailable",
    "absent-finding",
    "analyzer-unpinned",
    "modules-unpinned",
    "legacy-analyzer-absent",
    # No commit pin, only a content digest, and the working-tree file no longer
    # matches it: the exact analyzer bytes that produced the analysis cannot be
    # recovered from anywhere. Absent in the only sense that matters here.
    # Reportable in a routine run -- old bundles legitimately predate the pin --
    # and a blocker in a closeout, like every other unrecoverable entry
    # (owner §10).
    "legacy-analyzer-changed",
    "value-unavailable",
    # Added with `expected_predicates` and, at first, only to PASSING_STATES --
    # so a closeout failed a FIGURE whose bundle was absent and passed a FACT
    # whose bundle was equally absent. The two say the same thing about what
    # was checked, and only one said it (Codex).
    #
    # This is the failure the note above PASSING_STATES describes, committed
    # while quoting it: a state was added to a producer and half-wired into
    # the verdict.
    "predicate-unavailable",
})


def verdict(state: str, require_available: bool = False) -> bool:
    """True if `state` fails the check. An unclassified state fails."""
    if require_available and state in EXCUSED_BY_ABSENCE:
        return True
    return state not in PASSING_STATES


def _why(state: str, require_available: bool) -> str:
    """Say WHICH rule failed a state, so a closeout failure is not read as a
    mismatch and chased as one."""
    if require_available and state in EXCUSED_BY_ABSENCE:
        return "  [absent -- passes a routine check, fails --require-available]"
    if state in FAILING_STATES:
        return ""
    return "  [UNCLASSIFIED state -- failing by default]"


def check(require_available: bool = False) -> int:
    """Fail only on the live direction: a pinned artifact that is present and
    differs. Absent artifacts and divergent snapshots are not failures.

    With `require_available`, absence stops being an excuse -- see
    EXCUSED_BY_ABSENCE. That is the closeout question, not the CI one.
    """
    bad = []
    for r in chain():
        # A claim carrying NO artifacts yields no rows below, so the walk alone
        # cannot see the largest absence there is: a measurement whose run was
        # never pinned. It declares that itself, and in a closeout the
        # declaration is the finding (owner priority 6).
        if require_available and r["artifact_status"] == "historical_unavailable":
            why = (r["migration_blocker"]
                   or "not yet assessed -- no migration_blocker recorded")
            bad.append(f"{r['id']}: artifact_status=historical_unavailable "
                       f"({r['evidence_kind']}) -- {why}"
                       f"  [fails --require-available]")
        # A pinned claim that binds nothing and admits nothing. Not an absence
        # of evidence -- the evidence is attached and verified -- but a claim
        # that has not said which of its figures it checks against it, which
        # reads exactly like one that checks them all (owner §16-7).
        if r["binding_status"] == "UNDECLARED":
            bad.append(f"{r['id']}: pins an artifact but binds no figure and "
                       f"declares no `unbound:` entry -- `pinned` would be "
                       f"read as `checked`")
        for u in r["unbound"]:
            if not u["why"]:
                bad.append(f"{r['id']}: unbound figure {u['figure']!r} gives "
                           f"no reason -- an unexplained gap is indistinguishable "
                           f"from an oversight")
        for v in r["values"]:
            if verdict(v["state"], require_available):
                bad.append(f"{r['id']}: {v['file']}#{v['path']} -> {v['state']}"
                           f" (claim says {v['value']!r}, artifact has "
                           f"{v['got']!r}){_why(v['state'], require_available)}")
        for w in r["predicates"]:
            if verdict(w["state"], require_available):
                bad.append(f"{r['id']}: {w['file']}#{w['path']} -> {w['state']}"
                           f" (claim says {w['want']!r}, artifact has "
                           f"{w['got']!r}){_why(w['state'], require_available)}")
        for a in r["artifacts"]:
            if verdict(a["state"], require_available):
                bad.append(f"{r['id']}: {a['path']} -> {a['state']}"
                           + _why(a["state"], require_available))
            # ABSENT is a failure HERE, unlike an absent top-level manifest
            # (owner P0-4). Once the parent manifest is present and matches, the
            # bundle has declared these files exist; one of them missing is a
            # corrupt or incomplete bundle, not an unavailable one.
            for m in a["members"]:
                if not verdict(m["state"], require_available):
                    continue
                extra = _why(m["state"], require_available)
                bad.append(f"{r['id']}: {a['path']} -> {m.get('file', '?')}: "
                           f"{m['state']} {m.get('detail', '')}{extra}".rstrip())
    print("\n".join(bad))
    if bad and require_available:
        print(f"\n{len(bad)} blocker(s) under --require-available. A routine "
              f"--check passes all of these:\nevidence that is not there cannot "
              f"be checked, which is the right answer for CI and the wrong one\n"
              f"for a closeout.")
    return 1 if bad else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    raise SystemExit(check("--require-available" in args)
                     if "--check" in args else (report(), 0)[1])
