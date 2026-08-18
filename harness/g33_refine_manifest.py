#!/usr/bin/env python3
"""Provenance for a refinement experiment, under its own schema (§9).

Writing NO provenance -- the first attempt -- made the experiment irreproducible.
The fix is a DIFFERENT schema, not the absence of one: `decision_eligible` is a
constant False with no parameter that sets it, so the distinction from a decision
artifact is structural, not a matter of where the file was written.

Deliberately not sharing the decision provenance builder: one edit there could
make an experiment look decision-grade.
"""
from __future__ import annotations

import ast
import hashlib
import json
import math
import re
import struct
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import g33_refine_analyze as ra   # noqa: E402

#: v2 REQUIRES the commit+blob pin blocks and a non-empty member list. Under v1
#: those were optional metadata, so deleting them downgraded a new bundle to the
#: legacy contract and the checker reported rather than failed -- a contract you
#: can opt out of by omission is not a contract (owner P0-E2).
#:
#: v3 REQUIRES a typed `ran` block on every arm stream. Under v2 an arm carried
#: only `runtime_argv`, four strings of which the schema compared two, so the
#: carry mode and the domain width were recorded and never read (owner priority
#: 5). A VERSION rather than a new required field, because five published
#: bundles carry v2 arm streams and adding the requirement to v2 would either
#: invalidate them or have to be opt-out-by-omission -- which is the defect the
#: v2 bump itself was for.
SCHEMA = "refinement_experiment_v6"


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


#: Manifest keys that record WHERE a run happened, not WHAT was built. They are
#: kept in the document and excluded from the content address, so two runs of the
#: same experiment in different temp directories address the same bundle
#: (owner §10.3).
DIAGNOSTIC_KEYS = ("diagnostic",)

#: Build artifacts whose RAW digest is PAYLOAD, not identity.
#:
#: Both files embed the output directory, which is a fresh temporary path every
#: run. Stripping `diagnostic` KEYS inside the manifest did nothing for them,
#: because a file digest is just a string field -- so two identical experiments
#: produced different addresses and "an identical rerun reuses the bundle" held
#: only under fake provenance, which is exactly the property the content address
#: exists to provide (owner P0-1). Measured: two real builds of the same
#: experiment in different tmpdirs differed in these two entries and NOTHING
#: else, `g33_refine_driver` included.
#:
#: Their science content still reaches identity -- `build_provenance` is carried
#: as an object with its diagnostic keys stripped -- and their integrity is
#: still checked, because the evidence chain verifies every build_artifacts
#: digest. Payload, not identity.
LOCATION_DEPENDENT_ARTIFACTS = frozenset({"build_provenance.json",
                                          "commands.txt"})

#: Also not identity: the producer REFUSES to run when any byte that will run
#: differs from HEAD, so a dirty tree here can only mean unrelated files were
#: modified. Letting an edited README change the experiment's address
#: contradicts the producer's own rule for what makes a run the same run.
NON_IDENTITY_KEYS = ("tree_dirty",)


#: The self-containment rule for one bundle payload. The producer's reuse
#: check and the evidence chain held DIFFERENT rules: the producer looked at
#: `is_file()` and the digest, and both follow symlinks, so a link to a file
#: outside the bundle satisfied its digest and was republished -- while the
#: chain called the same bundle NOT-SELF-CONTAINED. Reproduced, so the rule
#: lives once (owner §6). The vocabulary is the chain's state strings.
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


def identity_digest(man: dict) -> str:
    """The content address: a digest over everything except the diagnostics."""
    def strip(x):
        if isinstance(x, dict):
            return {k: strip(v) for k, v in x.items()
                    if k not in DIAGNOSTIC_KEYS and k not in NON_IDENTITY_KEYS}
        if isinstance(x, list):
            return [strip(v) for v in x]
        return x
    m = strip(man)
    if "build_artifacts" in m:
        m["build_artifacts"] = [
            {k: v for k, v in a.items()
             if not (k == "sha256"
                     and a.get("file") in LOCATION_DEPENDENT_ARTIFACTS)}
            for a in m["build_artifacts"]]
    return hashlib.sha256(
        json.dumps(m, sort_keys=True).encode()).hexdigest()


def _git(*a) -> str:
    return subprocess.run(("git",) + a, capture_output=True,
                          text=True).stdout.strip()


_NAME = re.compile(r"^n(\d+)\.(carry|rezero)\.txt$")


def _member(path: Path) -> dict:
    """One member, via the analyzer's STRICT parser (owner §9).

    Reading only the BEGIN line would admit a truncated, duplicated or ragged
    member into the manifest -- exactly what the strict reader exists to reject,
    and the manifest is what says the table is reproducible. delt/loops/dtcld are
    READ from the stream, not recomputed from N: deriving them would restate the
    assumption the experiment exists to check.
    """
    # The FILENAME is bound to the stream: `read(nsplit=)` refuses a member whose
    # BEGIN disagrees with what it is called, and the mode in the name must be the
    # mode it ran. A mislabelled member is how two experiments become one table.
    m = _NAME.match(path.name)
    if not m:
        raise ra.RefineError(f"{path.name}: not n<N>.<carry|rezero>.txt")
    r = ra.read(path, nsplit=int(m.group(1)))   # raises on anything malformed
    if r[("meta", "mode")] != m.group(2):
        raise ra.RefineError(
            f"{path.name}: filename says mode {m.group(2)}, stream says "
            f"{r[('meta', 'mode')]}")
    out = {"file": path.name, "output_sha256": sha256(path),
           "nsplit": r[("meta", "nsplit")], "mode": r[("meta", "mode")],
           "algorithm": r[("meta", "algorithm")]}
    for k in ("delt", "loops", "dtcld"):
        if ("meta", k) in r:
            out[k] = r[("meta", k)]
    return out


def build(outputs: Path, *, module: Path, fixture: Path, compiler: str,
          analyzer: Path | None = None, build_provenance: Path | None = None,
          findings=(), member_reader=None) -> dict:
    """`member_reader` describes one output file, defaulting to the G33R reader.

    The f64 instrument arm emits no G33R at all, so it supplies the G33P reader
    instead. The hook exists because an f64 member IS a different artifact -- not
    because the contract is negotiable: both readers are strict, and the
    G33R-shaped cross-member checks below are skipped only when the members are
    not G33R (owner priority 2).
    """
    read_member = member_reader or _member
    paths = sorted(outputs.glob("n*.txt"))
    members = [read_member(p) for p in paths]
    # One experiment, not several (owner P0-2). Every cross-member check the
    # analyzer applies before it will produce a table is applied before the
    # manifest will claim one is reproducible: same record universe, one
    # algorithm and mode, one integration horizon, no repeated step.
    # Keyed by nsplit, so `n3.rezero.txt` beside `n3.carry.txt` would collapse to
    # one entry and the cross-member checks -- including the mode check -- would
    # run on whichever survived (owner §7.3).
    ns = [int(_NAME.match(p.name).group(1)) for p in paths]
    # Regardless of the reader: two members for one nsplit collapse to one
    # entry whichever parser read them (owner §8.4).
    if len(ns) != len(set(ns)):
        dup = sorted({n for n in ns if ns.count(n) > 1})
        raise ra.RefineError(
            f"bundle contains more than one member for nsplit {dup} — a chain has "
            f"one member per step, and keying by nsplit would hide the others")
    runs = ({} if member_reader is not None
            else {n: ra.read(p, nsplit=n) for n, p in zip(ns, paths)})
    if len(runs) > 1:
        ra.require_same_universe(runs)
    steps = [m.get("dtcld") for m in members]
    man = {
        "artifact_type": "refinement_experiment",
        # A CONSTANT. No argument sets it, so no invocation can produce an
        # experiment manifest that claims decision eligibility.
        "decision_eligible": False,
        "schema": SCHEMA,
        "repo_commit": _git("rev-parse", "HEAD"),
        "tree_dirty": bool(_git("status", "--porcelain")),
        "module_sha256": sha256(module),
        "module_path": str(module),
        "fixture_sha256": sha256(fixture),
        "fixture_path": str(fixture),
        # A human label. The compiler that actually ran is in build_provenance,
        # by digest -- two hosts print this same string and produce different
        # numbers. `null` there means the build recorded nothing, which is a
        # different statement from an empty command list.
        "compiler": compiler,
        "build_provenance": (json.loads(build_provenance.read_text())
                             if build_provenance and build_provenance.exists()
                             else None),
        "analyzer_sha256": sha256(analyzer) if analyzer else None,
        # The documents that draw conclusions from these members. A finding that
        # cites a table nobody can tie to the run it came from is unreviewable.
        "findings": [{"path": str(f), "sha256": sha256(f)} for f in findings],
        "members": members,
    }
    # Recorded, not asserted. A sweep that does not halve dtcld is still a run
    # worth keeping -- the N=1/N=3 policy control is exactly such a sweep -- but
    # whether it refines should be a property a reader can see rather than infer.
    #
    # Ordered by ACTUAL step, not by N: N = 1,2,3 run 100, 150, 100 s, so an
    # N-ordered chain need not be step-ordered and sorting the VALUES alone would
    # call an arbitrary bag of members a chain as long as the numbers happened to
    # halve (owner P0-2).
    by_step = [m["dtcld"] for m in sorted(members, key=lambda m: -m.get("dtcld", 0))
               ] if all(s is not None for s in steps) else []
    man["is_refinement_chain"] = (
        len(by_step) > 1
        and all(abs(a - 2 * b) < 1e-9 for a, b in zip(by_step, by_step[1:])))
    # The provenance must describe THESE sources, not some other build's.
    bp = man["build_provenance"]
    if bp:
        for field in ("module_sha256", "fixture_sha256"):
            if bp.get(field) != man[field]:
                raise ra.RefineError(
                    f"build_provenance.{field} does not match the {field} this "
                    f"manifest records — the provenance is from a different build")
    return man


#: NO standalone CLI (owner P0-3). `build()` produces the CORE of a manifest;
#: the v2-required blocks -- `instrumented`, `arm`, `precision`,
#: `member_parsers`, `producer_modules`, `tracked_build_inputs`, `analyses` --
#: are added by `g33_refine_experiment.produce()`, which then validates and
#: publishes atomically.
#:
#: A CLI here emitted that core, stamped it `refinement_experiment_v2`, and
#: exited. Worse, `validate()` was defined BELOW the `__main__` block, so the
#: entry point could not have called it even if it wanted to: the one path that
#: skipped validation was the one a person could run by hand.
#:
#: The producer is the only way to make a bundle. Anything else is a draft.


#: What a v2 manifest must satisfy, in one place. The producer calls it before
#: publishing and the evidence checker calls it before believing anything, so a
#: bundle cannot be valid to one and invalid to the other (owner P0-2).
_ARMS = ("reference", "probe", "f64")
_PRECISIONS = ("f32", "f64")
#: The driver's own `ALGOTAG` vocabulary. It error-stops on anything else, so
#: a manifest declaring another word names a run that could not have happened.
_ALGOS = ("legacy", "conservative")
KNOWN_SCHEMAS = ("refinement_experiment_v1", "refinement_experiment_v2",
                 "refinement_experiment_v3", "refinement_experiment_v4",
                 "refinement_experiment_v5", "refinement_experiment_v6")
#: Schemas carrying the v2 contract or better. Ordered, so "at least v3" is a
#: comparison rather than a list someone extends by hand at each bump.
_SCHEMA_RANK = {s: i for i, s in enumerate(KNOWN_SCHEMAS)}


def at_least(schema: str, floor: str) -> bool:
    """Whether `schema` carries `floor`'s contract."""
    return _SCHEMA_RANK.get(schema, -1) >= _SCHEMA_RANK[floor]


def _hexlen(v, n) -> bool:
    return isinstance(v, str) and len(v) == n and \
        all(c in "0123456789abcdef" for c in v.lower())


#: The layered-identity block a v3 bundle must carry, so its ids are
#: reproducible FROM THE ARCHIVE rather than from whatever tree reads it.
#: Spelled here rather than imported from `g33_identity`: that module imports
#: the producer, which imports this one, and the requirement is a property of
#: the DOCUMENT either way.
IDENTITY_SCHEMA = "g33_layered_identity_v4"
#: ...and the tags a bundle may legitimately carry. A document is held to the
#: id semantics it was PRODUCED under: v3 moved `expected_run` and
#: `kernel_geometry` into the recipe id, which is a different question about
#: the same manifest, and demanding it of an artifact published before it
#: would be a blocker with no resolution but re-production.
KNOWN_IDENTITY_SCHEMAS = ("g33_layered_identity_v2",
                          "g33_layered_identity_v3",
                          "g33_layered_identity_v4")


#: The roles a module can carry. `_by_role` filters on these words, so one it
#: does not know silently removes a module from every id.
_ROLES = ("run", "analysis")


#: The three blocks a file can be pinned under. One file may legitimately be
#: pinned in several -- `g33_number_transport` is a producer module AND a
#: member parser -- and those pins are two records of one fact.
_PIN_BLOCK_KEYS = ("producer_modules", "member_parsers", "tracked_build_inputs")


def resolved_pins(man: dict) -> dict:
    """repo path -> its ONE consistent pin, from every block that carries it.

    The pin collectors keyed by basename STEM, so when one file was pinned in
    two blocks the later block silently overwrote the earlier -- and the graph
    check could read one blob while the id digested the other pin. Measured on
    the real f64 manifest: `g33_number_transport.py` and `g33_probe_read.py`
    are each pinned in producer_modules AND member_parsers, and a divergent
    duplicate passed `validate()` clean (owner review §5).

    So the table is keyed by the FULL repo path, and refuses:

      the same path pinned with different content anywhere in the document --
      two records of one fact that disagree are one record and one lie;
      two different paths whose basename gives the same Python module name --
      the import graph is keyed by module name, so they would collide in it.
    """
    table, bad = {}, []
    for key in _PIN_BLOCK_KEYS:
        for e in man.get(key) or []:
            if not (isinstance(e, dict) and isinstance(e.get("path"), str)):
                continue
            path = e["path"]
            body = {"content_sha256": e.get("content_sha256"),
                    "blob_sha": e.get("blob_sha")}
            if path in table and table[path] != body:
                bad.append(f"{path} is pinned as {table[path]['blob_sha'] and table[path]['blob_sha'][:12]}"
                           f" in one block and {body['blob_sha'] and body['blob_sha'][:12]} in {key}"
                           f" -- two records of one fact that disagree")
            table[path] = body
    stems = {}
    for path in table:
        if path.endswith(".py"):
            stem = path.rsplit("/", 1)[-1][:-3]
            if stem in stems and stems[stem] != path:
                bad.append(f"{stems[stem]} and {path} both import as "
                           f"{stem!r} -- the import graph is keyed by module "
                           f"name and cannot hold both")
            stems[stem] = path
    if bad:
        raise PinConflict("; ".join(sorted(set(bad))))
    return table


class PinConflict(Exception):
    """The document pins one file two ways, or two files under one name."""


def pin_conflicts(man: dict) -> list:
    """`resolved_pins` as a violation list, for the validator."""
    try:
        resolved_pins(man)
        return []
    except PinConflict as e:
        return [str(e)]


def _pinned_modules(man: dict) -> set:
    """Every PYTHON module this bundle pins, under any of the three pin blocks.

    All three, because `make_fortran_overlay` and `g33_fortran_bindings` are
    tracked BUILD INPUTS rather than producer modules and they do carry roles --
    so "is this module pinned" is a question about the whole document.

    Python only, because the role graph is about modules. The build inputs also
    pin `refine_build.sh`, the driver and the fixture `.f90`: real, pinned, and
    not things an import closure has a role for. Including them would demand a
    role for every file and get one invented.
    """
    return {p.rsplit("/", 1)[-1][:-3] for p in resolved_pins(man)
            if p.endswith(".py")}


def _identity_violations(man: dict) -> list:
    """The recorded role graph, checked for presence, shape AND TRUTHFULNESS.

    Shape alone is fail-open, and not mildly: `_by_role` filters the bundle's
    module pins THROUGH this graph, so a manifest declaring a thin one gets a
    recipe id over a subset of its own pins, and one declaring every module
    `analysis`-only gets a recipe id over NOTHING. Measured on a real manifest:
    19 pins, and a fabricated graph brings 0 of them into `run_recipe_id` --
    after which no run-role module's bytes can move it. That is strictly worse
    than the coupling the block was added to remove, because it is forgeable
    (Codex stop-time review).

    So the graph has to agree with the rest of the document: every module the
    bundle PINS carries a role, every module the graph NAMES is pinned, the
    roles come from a known vocabulary, and somebody is in the run role.
    """
    ident = man.get("identity")
    if not isinstance(ident, dict):
        return ["identity must be an object recording the role graph the ids "
                "were derived under -- without it they follow the checkout"]
    bad = []
    if ident.get("schema") not in KNOWN_IDENTITY_SCHEMAS:
        bad.append(f"identity.schema {ident.get('schema')!r} is not one of "
                   f"{KNOWN_IDENTITY_SCHEMAS}")
    elif (at_least(man.get("schema"), "refinement_experiment_v6")
            and ident["schema"] != IDENTITY_SCHEMA):
        bad.append(f"identity.schema {ident['schema']!r} is not "
                   f"{IDENTITY_SCHEMA!r}, which {man.get('schema')!r} "
                   f"records its ids under")
    for key in ("role_graph", "analysis_seeds", "analysis_reach"):
        v = ident.get(key)
        if not isinstance(v, dict) or not v:
            bad.append(f"identity.{key} must be a non-empty object")
            continue
        for name, val in v.items():
            # `analysis_seeds` maps a name to ONE module; the other two map to
            # lists. One loop, because "non-empty and made of module names" is
            # the same requirement either way.
            ok = (isinstance(val, str) and val) if key == "analysis_seeds" else (
                isinstance(val, list) and val
                and all(isinstance(x, str) for x in val))
            if not ok:
                bad.append(f"identity.{key}[{name!r}] must be a non-empty "
                           f"{'module name' if key == 'analysis_seeds' else 'list'}")
                break
    if bad:
        return bad

    graph, reach = ident["role_graph"], ident["analysis_reach"]
    seeds = ident["analysis_seeds"]
    if set(seeds) != set(reach):
        bad.append(f"identity.analysis_seeds and analysis_reach describe "
                   f"different analyses: {sorted(set(seeds) ^ set(reach))}")
    unknown = sorted({r for v in graph.values() for r in v} - set(_ROLES))
    if unknown:
        bad.append(f"identity.role_graph uses roles {unknown}, not in {_ROLES} "
                   f"-- `_by_role` filters on these words, so one it does not "
                   f"know removes a module from every id")
    if not any("run" in v for v in graph.values()):
        bad.append("identity.role_graph gives no module the `run` role, so the "
                   "run recipe would be a digest over an empty module list")
    pinned = _pinned_modules(man)
    # THE LOAD-BEARING DIRECTION. A pin the graph omits is dropped from both
    # ids by `_by_role`, so omitting pins is how a manifest makes its own ids
    # weaker without saying anything false.
    orphan_pins = sorted(pinned - set(graph))
    if orphan_pins:
        bad.append(f"identity.role_graph omits pinned modules {orphan_pins} -- "
                   f"a pin with no role is filtered out of every id")
    invented = sorted(set(graph) - pinned)
    if invented:
        bad.append(f"identity.role_graph names {invented}, which this bundle "
                   f"pins nowhere -- the graph describes code the archive does "
                   f"not hold")
    unseeded = sorted(set(seeds.values()) - pinned)
    if unseeded:
        bad.append(f"identity.analysis_seeds names {unseeded}, which this "
                   f"bundle pins nowhere")
    unpinned_reach = sorted({m for v in reach.values() for m in v} - pinned)
    if unpinned_reach:
        bad.append(f"identity.analysis_reach names {unpinned_reach}, which this "
                   f"bundle pins nowhere")
    return bad + _identity_slice_violations(man, graph, reach)


def _identity_slice_violations(man: dict, graph: dict, reach: dict) -> list:
    """The SLICES the ids actually digest, not the declarations that produce them.

    Three rounds of this check validated declarations and left the slices open,
    which is the same mistake three times. `_by_role` and `_pins_for` both
    filter `producer_modules` -- and a module can be pinned as a tracked BUILD
    INPUT instead, so a graph that gives the `run` role only to
    `make_fortran_overlay` and `g33_fortran_bindings` satisfies "somebody is in
    the run role" and leaves the run slice EMPTY. Measured: run-slice 0 with a
    clean validate, which is the same end state as the forgery the previous
    round closed, reached through a different door.

    So the constraint is stated over the slice: what survives the filter must be
    non-empty, and an analysis's slice must contain its own analyzer -- a reach
    entry naming other pinned modules is non-empty, all-pinned, and still does
    not cover the bytes that produced the analysis (Codex stop-time review).
    """
    prod = {e["path"].rsplit("/", 1)[-1][:-3]
            for e in man.get("producer_modules") or []
            if isinstance(e, dict) and isinstance(e.get("path"), str)
            and e["path"].endswith(".py")}
    bad = []
    if not (prod & {m for m, r in graph.items() if "run" in r}):
        bad.append(
            "identity.role_graph gives the `run` role to no module that is "
            "pinned in producer_modules, so the run recipe digests an empty "
            "list -- a module pinned only as a build input never reaches it")
    for a in man.get("analyses") or []:
        if not isinstance(a, dict) or a.get("analysis") == "arm_stream":
            continue
        name, analyzer = a.get("analysis"), a.get("analyzer")
        if name not in reach:
            continue                      # absence is reported by _identity_covers
        slice_ = prod & set(reach[name])
        if not slice_:
            bad.append(f"identity.analysis_reach[{name!r}] names no module "
                       f"pinned in producer_modules, so that analysis id "
                       f"digests an empty list")
            continue
        if isinstance(analyzer, str) and analyzer.endswith(".py"):
            own = analyzer.rsplit("/", 1)[-1][:-3]
            if own in prod and own not in slice_:
                bad.append(f"identity.analysis_reach[{name!r}] does not contain "
                           f"{own!r}, the analyzer this entry names -- the id "
                           f"would not cover the bytes that produced it")
    return sorted(set(bad))


def _identity_covers(man: dict) -> list:
    """Analyses the bundle carries that its recorded reach map does not."""
    reach = ((man.get("identity") or {}).get("analysis_reach") or {})
    carried = {a.get("analysis") for a in (man.get("analyses") or [])
               if isinstance(a, dict)} - {"arm_stream"}
    return sorted(carried - set(reach))


class BlobUnavailable(Exception):
    """A pinned blob is not in this object database, so the recorded graph
    cannot be checked against the code it claims to describe."""


def _imports_from(blob: bytes, universe: set) -> set:
    """The pinned modules `blob` DEPENDS ON. Same AST rule the producer uses on
    the working tree -- a name in a comment or a docstring is not an import,
    and a lazy `_an("...")` dispatch IS a dependency edge, or making an import
    lazy would silently drop it from the recorded graph while the code still
    runs it."""
    names = set()
    for n in ast.walk(ast.parse(blob)):
        if isinstance(n, ast.Import):
            names |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            names.add(n.module.split(".")[0])
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                and n.func.id == "_an":
            names |= {a.value for a in n.args
                      if isinstance(a, ast.Constant) and isinstance(a.value, str)}
    return names & universe


def pinned_blobs(man: dict) -> dict:
    """module -> its PINNED source bytes.

    Not the working tree. The whole point of recording the graph is that it
    must not depend on the checkout reading it, so checking it against the
    checkout would defeat the recording -- while checking it against the blobs
    the manifest itself pins uses nothing the archive does not carry.
    """
    out = {}
    for path, pin in resolved_pins(man).items():
        if not path.endswith(".py") or not isinstance(pin["blob_sha"], str):
            continue
        mod = path.rsplit("/", 1)[-1][:-3]
        r = subprocess.run(["git", "cat-file", "blob", pin["blob_sha"]],
                           cwd=REPO, capture_output=True)
        if r.returncode != 0:
            raise BlobUnavailable(f"{mod} pins blob {pin['blob_sha'][:12]}, "
                                  f"not in this object database")
        # The blob must BE the content the pin claims ran. `_pin_path` checks
        # this at production; checking it here too makes the graph read bytes
        # the id answers for, from an arbitrary manifest (owner review §5).
        if isinstance(pin["content_sha256"], str) and \
                hashlib.sha256(r.stdout).hexdigest() != pin["content_sha256"]:
            raise BlobUnavailable(
                f"{mod}: blob {pin['blob_sha'][:12]} does not hash to the "
                f"pinned content_sha256 -- the pin names two different files")
        out[mod] = r.stdout
    return out


def pinned_imports(man: dict, blobs: dict | None = None) -> dict:
    """module -> the pinned modules it imports, read from the pinned blobs."""
    blobs = pinned_blobs(man) if blobs is None else blobs
    out = {}
    for mod, src in blobs.items():
        try:
            out[mod] = _imports_from(src, set(blobs))
        except SyntaxError as e:
            raise BlobUnavailable(f"{mod}: pinned blob does not parse: {e}")
    return out


#: The registries whose entries ARE the producer's dispatch set. A module that
#: declares both is the dispatcher, which is how the cut's SOURCE is derived
#: rather than named: naming `g33_refine_experiment` here would be a second
#: place to keep in step with the producer.
_DISPATCH_REGISTRIES = ("ANALYSES", "MULTI_RUN")


#: How the producer records the analyzer of every analysis it writes. Its
#: LITERAL arguments name the modules it dispatches to outside the registries --
#: `metric_trajectory` is written by `_driver_analyses` directly and is in
#: neither one.
_ANALYZER_PIN = "_analyzer_pin"


def _dispatch_from_blobs(blobs: dict) -> tuple:
    """(dispatcher, {analysis: seed module}, dispatch set) from the pinned code.

    The cut was DECLARED, and the declaration was answerable to nothing for a
    key that was neither in the registries nor published -- so an invented key
    could name any module the dispatcher imports and widen the excused edges.
    Measured: a bogus key naming `g33_identity` passed both checks and took the
    run slice from 9 pins to 8 (Codex stop-time review).

    So the SET is derived here and the manifest no longer contributes to it.
    Two sources, and together they are exactly the eleven modules the producer
    dispatches to: the registry values, and the literal `_analyzer_pin`
    arguments -- which is how the producer names the analyzer of an analysis it
    writes outside a registry.
    """
    found = {}
    for mod, src in blobs.items():
        try:
            tree = ast.parse(src)
        except SyntaxError as e:
            raise BlobUnavailable(f"{mod}: pinned blob does not parse: {e}")
        names, reg, lits = set(), {}, set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                    and n.func.id == _ANALYZER_PIN:
                lits |= {a.value for a in n.args
                         if isinstance(a, ast.Constant) and isinstance(a.value, str)}
            if not isinstance(n, ast.Assign):
                continue
            for t in n.targets:
                if isinstance(t, ast.Name) and t.id in _DISPATCH_REGISTRIES:
                    names.add(t.id)
                    if isinstance(n.value, ast.Dict):
                        for k, v in zip(n.value.keys, n.value.values):
                            if isinstance(k, ast.Constant) and \
                                    isinstance(v, ast.Tuple) and v.elts and \
                                    isinstance(v.elts[0], ast.Constant):
                                reg[k.value] = v.elts[0].value
        if set(_DISPATCH_REGISTRIES) <= names:
            found[mod] = (reg, lits)
    if len(found) != 1:
        raise BlobUnavailable(
            f"{len(found)} pinned modules declare "
            f"{' and '.join(_DISPATCH_REGISTRIES)}; the dispatch cut has "
            f"exactly one source or it cannot be derived")
    mod, (reg, lits) = next(iter(found.items()))
    if not reg:
        raise BlobUnavailable(
            f"{mod} declares the registries and none of their entries parse -- "
            f"the shape changed, and an empty cut would excuse nothing while "
            f"looking like it excused the right things")
    return mod, reg, set(reg.values()) | lits


def _blob_closure(edges: dict, seed: str) -> set:
    seen, todo = set(), [seed]
    while todo:
        m = todo.pop()
        if m in seen:
            continue
        seen.add(m)
        todo += list(edges.get(m, set()) - seen)
    return seen


def graph_violations(man: dict) -> list:
    """The recorded graph against the CODE IT CLAIMS TO DESCRIBE.

    Everything before this checked the graph against the manifest's other
    declarations, and a declaration cannot say whether a slice omits a genuine
    dependency. Measured: `dual_ledger`'s reach truncated from five modules to
    one validated clean, after which changes to four of its five dependencies
    could not move its id; the run role narrowed from eleven modules to one did
    the same to the recipe (Codex stop-time review).

    Two properties, both computed from the pinned blobs and both exact on the
    real bundles:

      a reach entry EQUALS the import closure of the analyzer its own entry
      names -- no seeds, no registries, nothing but the manifest;

      a role is CLOSED under imports, except where a module imports an analyzer
      this bundle names. That exception is the producer's dispatch cut, and it
      is what makes `g33_refine_experiment` a run module that imports analysis
      ones. Deriving it from `analyses` rather than from a registry keeps the
      check a function of the document.
    """
    ident = man.get("identity") or {}
    graph, reach = ident.get("role_graph"), ident.get("analysis_reach")
    if not isinstance(graph, dict) or not isinstance(reach, dict):
        return []                       # shape is the schema's business
    conflicts = pin_conflicts(man)
    if conflicts:
        return conflicts                # the table the graph reads is not one
    seeds = ident.get("analysis_seeds")
    if not isinstance(seeds, dict) or not seeds:
        return ["identity.analysis_seeds must record each analysis's seed "
                "module -- it is the producer's dispatch cut, and without it "
                "the role closure cannot be checked"]
    blobs = pinned_blobs(man)
    edges = pinned_imports(man, blobs)
    dispatcher, registry, dispatch = _dispatch_from_blobs(blobs)
    bad = []
    # THE CUT, DERIVED. It was the recorded seeds, and a seed for an analysis
    # this bundle did not publish was unconstrained -- so one could be repointed
    # to widen the set of edges the closure check excuses. The registries in the
    # pinned dispatcher say what the producer actually dispatches to
    # (Codex stop-time review).
    # THE KEY SET, exactly. A key that is neither in the pinned registries nor
    # published by this bundle was answerable to nothing: it could name any
    # module the dispatcher imports, which widens the cut, and the module it
    # names can then be dropped from the run role. Measured: a bogus key naming
    # `g33_identity` passed the schema AND the graph check clean and took the
    # run slice from 9 pins to 8 -- removing the module that computes the
    # identity from the id (Codex stop-time review).
    #
    # Registry keys stay even when this bundle publishes none of them: the
    # dispatcher imports those modules whatever one bundle produced, so the cut
    # needs them. What goes is the freedom to invent a key.
    published = {a["analysis"] for a in man.get("analyses") or []
                 if isinstance(a, dict) and a.get("analyzer")
                 and isinstance(a.get("analysis"), str)}
    want_keys = set(registry) | published
    if set(seeds) != want_keys:
        bad.append(
            f"identity.analysis_seeds keys {sorted(set(seeds) ^ want_keys)} "
            f"differ from the pinned {dispatcher} registries plus what this "
            f"bundle published -- an invented key names any module the "
            f"dispatcher imports and widens the cut to cover it")
    for name, seed in sorted(seeds.items()):
        if name in registry and seed != registry[name]:
            bad.append(f"identity.analysis_seeds[{name!r}] is {seed!r} and the "
                       f"pinned {dispatcher} registry names {registry[name]!r}")
        elif name not in registry and seed not in edges.get(dispatcher, set()):
            bad.append(f"identity.analysis_seeds[{name!r}] is {seed!r}, which "
                       f"is not in the pinned registries and is not imported "
                       f"by {dispatcher} -- a seed the producer does not "
                       f"dispatch to widens the cut for nothing")
    for a in man.get("analyses") or []:
        if not isinstance(a, dict) or not a.get("analyzer"):
            continue
        name, own = a.get("analysis"), Path(str(a["analyzer"])).stem
        if name in seeds and seeds[name] != own:
            bad.append(f"identity.analysis_seeds[{name!r}] is {seeds[name]!r} "
                       f"and the published entry names {own!r}")
    for name, seed in sorted(seeds.items()):
        if name not in reach or seed not in edges:
            continue
        want = _blob_closure(edges, seed)
        got = set(reach[name])
        if got != want:
            bad.append(
                f"identity.analysis_reach[{name!r}] is {sorted(got)}, and the "
                f"import closure of {seed!r} over the PINNED blobs is "
                f"{sorted(want)} -- a slice that omits a genuine dependency "
                f"gives an id those bytes cannot move")
    for role in ("run", "analysis"):
        holders = {m for m, r in graph.items() if role in r}
        for m in sorted(holders):
            # The cut is SCOPED to the dispatcher. Excusing dispatch edges from
            # every module let any module import an analyzer and escape the
            # closure requirement -- 11 modules import something in that set,
            # and the producer cuts out of exactly one (Codex stop-time review).
            excused = dispatch if m == dispatcher else set()
            leak = sorted(edges.get(m, set()) - holders - excused)
            if leak:
                bad.append(
                    f"identity.role_graph gives {m!r} the {role!r} role and "
                    f"not {leak}, which it imports -- a role that is not closed "
                    f"under imports leaves those bytes out of the id")
    return sorted(set(bad))



def validate(man: dict) -> list:
    """Everything wrong with this manifest, as a list of sentences.

    Empty means valid. Truthiness was the whole check before: `[{}]` counted as
    a pin block, so a v2 bundle could carry two empty dicts, be reported
    `analyzer-unpinned` -- a PASSING state kept for legacy bundles -- and check
    out clean. `instrumented` was not required, so deleting the key deleted the
    `analyses` requirement with it: the same "lower the contract by omission"
    defect the schema bump was meant to close.
    """
    if not isinstance(man, dict):
        return [f"top level is {type(man).__name__}, not an object"]
    bad = []
    if man.get("artifact_type") != "refinement_experiment":
        bad.append(f"artifact_type {man.get('artifact_type')!r} is not "
                   f"'refinement_experiment'")
    schema = man.get("schema")
    if schema not in KNOWN_SCHEMAS:
        return bad + [f"unknown schema {schema!r}"]
    if not at_least(schema, "refinement_experiment_v2"):
        return bad                       # v1 predates every field below
    if man.get("decision_eligible") is not False:
        bad.append("decision_eligible must be False: a refinement experiment is "
                   "never decision evidence")
    if not isinstance(man.get("instrumented"), bool):
        bad.append("instrumented must be present and boolean -- deleting it "
                   "deletes the `analyses` requirement with it")
    if man.get("arm") not in _ARMS:
        bad.append(f"arm {man.get('arm')!r} is not one of {_ARMS}")
    if man.get("precision") not in _PRECISIONS:
        bad.append(f"precision {man.get('precision')!r} is not one of "
                   f"{_PRECISIONS}")
    if not isinstance(man.get("build_provenance"), dict) or \
            not man["build_provenance"]:
        bad.append("build_provenance must be a non-empty object")
    elif at_least(schema, "refinement_experiment_v6"):
        # A CLOSED provenance contract (owner review §4). "Non-empty object"
        # let an arbitrary v5 manifest reduce a build's whole record --
        # compiler, every compiled source, the module, the overlay actually
        # fed to the compiler -- to one executable digest, while the real
        # producer wrote all of it. What the producer records is what the
        # document must carry.
        bp = man["build_provenance"]
        for key in ("compiler_version", "compiler_sha256", "executable_sha256",
                    "module_path", "module_sha256", "fixture_sha256",
                    "build_script_sha256", "sources", "compile_commands"):
            if bp.get(key) in (None, "", [], {}):
                bad.append(f"build_provenance.{key} is required from v6: a "
                           f"build record missing it cannot answer for what "
                           f"was compiled")
        for key in ("executable_sha256", "module_sha256", "fixture_sha256",
                    "build_script_sha256", "compiler_sha256"):
            if key in bp and not _hexlen(bp.get(key), 64):
                bad.append(f"build_provenance.{key} is not a 64-hex digest")
        if not isinstance(bp.get("sources"), list) or not bp.get("sources"):
            bad.append("build_provenance.sources must be a non-empty list of "
                       "the files this build compiled")
        else:
            for i, src in enumerate(bp["sources"]):
                if not (isinstance(src, dict) and isinstance(src.get("path"),
                                                             str)
                        and _hexlen(src.get("sha256"), 64)):
                    bad.append(f"build_provenance.sources[{i}] needs `path` "
                               f"and a 64-hex `sha256`")
        # The INSTRUMENTED build compiles a generated overlay, not the
        # pinned module, so that file is what the executable was actually
        # made from -- and it must be recorded and published, not assumed
        # to preserve the module's constants (owner review §4.3).
        if man.get("instrumented") is True:
            if not _hexlen(bp.get("compiled_module_sha256"), 64):
                bad.append("build_provenance.compiled_module_sha256 is "
                           "required for an instrumented build: the compiler "
                           "was fed the generated overlay, not the module")
            arts = {a.get("file"): a.get("sha256")
                    for a in (man.get("build_artifacts") or [])
                    if isinstance(a, dict)}
            if "module_mp_ovl.F" not in arts:
                bad.append("build_artifacts must publish module_mp_ovl.F: the "
                           "bytes the compiler read are evidence, not a "
                           "temporary")
            elif arts["module_mp_ovl.F"] != bp.get("compiled_module_sha256"):
                bad.append("the published module_mp_ovl.F is not the "
                           "compiled_module_sha256 the build recorded")

    members = man.get("members")
    if not isinstance(members, list) or not members:
        bad.append("members must be a non-empty list")
    else:
        for i, m in enumerate(members):
            if not isinstance(m, dict) or not isinstance(m.get("file"), str) \
                    or not _hexlen(m.get("output_sha256"), 64):
                bad.append(f"members[{i}] needs `file` and a 64-hex "
                           f"`output_sha256`")
        # Member metadata against the manifest's OWN top level (owner review
        # §5): the f64 rows record the precision/fixture the STREAM declared,
        # the top level records what the bundle claims to be, and two records
        # of one fact never compared are one record and one decoration. Only
        # checked where the row carries the field -- reference members
        # legitimately record less.
        fxstem = Path(str(man.get("fixture_path", ""))).stem
        for i, m in enumerate(members):
            if not isinstance(m, dict):
                continue
            if (m.get("precision") is not None
                    and m["precision"] != man.get("precision")):
                bad.append(
                    f"members[{i}] ran at {m['precision']} but the bundle "
                    f"claims precision {man.get('precision')!r}")
            if m.get("source_precision") not in (None, "f32"):
                bad.append(
                    f"members[{i}] source_precision "
                    f"{m['source_precision']!r} -- the reference this archive "
                    f"instruments is f32, always")
            if (m.get("fixture") is not None and fxstem
                    and m["fixture"] != fxstem):
                bad.append(
                    f"members[{i}] ran fixture {m['fixture']!r} but the "
                    f"bundle pins {fxstem!r}")
        algos = {m.get("algorithm") for m in members
                 if isinstance(m, dict)} - {None}
        if len(algos) > 1:
            bad.append(f"members ran different algorithms {sorted(algos)} -- "
                       f"one bundle, one experiment")
        if at_least(schema, "refinement_experiment_v4"):
            bad += _expected_run_violations(man, members)

    arts = man.get("build_artifacts")
    if not isinstance(arts, list) or not arts:
        bad.append("build_artifacts must be a non-empty list: the driver binary "
                   "and its provenance ARE published in the bundle")
    else:
        for i, a in enumerate(arts):
            if not isinstance(a, dict) or not isinstance(a.get("file"), str) \
                    or not _hexlen(a.get("sha256"), 64):
                bad.append(f"build_artifacts[{i}] needs `file` and a 64-hex "
                           f"`sha256`")
        if not any(isinstance(a, dict) and a.get("file") == "g33_refine_driver"
                   for a in arts):
            bad.append("build_artifacts must include g33_refine_driver -- the "
                       "binary that produced these numbers")
        else:
            # The manifest states the executable digest TWICE, in
            # build_artifacts and inside build_provenance, and nothing compared
            # them. Two statements about the same binary that are never checked
            # against each other are one statement and one decoration
            # (owner §8.4).
            got = {a.get("file"): a.get("sha256") for a in arts}
            want = (man.get("build_provenance") or {}).get("executable_sha256")
            if want and got.get("g33_refine_driver") != want:
                bad.append(
                    f"build_artifacts records g33_refine_driver as "
                    f"{str(got.get('g33_refine_driver'))[:12]} but "
                    f"build_provenance says {str(want)[:12]} -- the bundle "
                    f"names two different binaries")
    # An `--nflux` bundle must carry the instrumented analyses, not merely a
    # non-empty `analyses`: one arm_stream satisfied that while carrying none
    # of them (owner §8.3).
    if man.get("instrumented") is True:
        kinds = {a.get("analysis") for a in (man.get("analyses") or [])
                 if isinstance(a, dict)}
        absent = [k for k in REQUIRED_WHEN_INSTRUMENTED if k not in kinds]
        if absent:
            bad.append(f"instrumented bundle is missing the analyses that make "
                       f"it instrumented: {absent}")
    for key in ("member_parsers", "producer_modules", "tracked_build_inputs"):
        block = man.get(key)
        if not isinstance(block, list) or not block:
            bad.append(f"{key} must be a non-empty list")
            continue
        for i, e in enumerate(block):
            if not isinstance(e, dict):
                bad.append(f"{key}[{i}] is {type(e).__name__}, not an object")
            elif not (isinstance(e.get("path"), str)
                      and _hexlen(e.get("content_sha256"), 64)
                      and _hexlen(e.get("commit"), 40)
                      and _hexlen(e.get("blob_sha"), 40)):
                bad.append(f"{key}[{i}] is not a complete pin: it needs `path`, "
                           f"a 64-hex `content_sha256`, and 40-hex `commit` and "
                           f"`blob_sha`")

    # A repeated row in a SET-valued block is refused, not de-duplicated
    # (owner review §10): canonical sorting made ORDER irrelevant to the ids,
    # but [p1, p1, p2] still hashed differently from [p1, p2] while recording
    # the same facts, and no block gives multiplicity a meaning. The
    # cross-block pin table already refuses same-path DIVERGENT duplicates;
    # this closes the identical ones, and the per-block ones.
    def _dupes(rows, key):
        seen, out = set(), []
        for r in rows or []:
            if isinstance(r, dict) and (k := key(r)) is not None:
                if k in seen:
                    out.append(k)
                seen.add(k)
        return out
    for key in ("member_parsers", "producer_modules", "tracked_build_inputs"):
        for d in _dupes(man.get(key), lambda e: e.get("path")):
            bad.append(f"{key} pins {d!r} twice -- a set-valued block gives "
                       f"multiplicity no meaning")
    for d in _dupes(man.get("members"), lambda e: e.get("file")):
        bad.append(f"members records {d!r} twice")
    for d in _dupes(man.get("build_artifacts"), lambda e: e.get("file")):
        bad.append(f"build_artifacts records {d!r} twice")
    for d in _dupes(man.get("analyses"), lambda e: e.get("file")):
        bad.append(f"analyses records {d!r} twice")
    for i, a in enumerate(man.get("analyses") or []):
        if isinstance(a, dict):
            for d in _dupes(a.get("inputs"), lambda e: e.get("file")):
                bad.append(f"analyses[{i}].inputs records {d!r} twice")

    # The LAYERED IDENTITY block (owner priority 8). Required from v3, because
    # without it the ids are a function of the manifest AND of whichever
    # checkout computes them -- which is the coupling the block exists to
    # remove. It was ADDED to the producer and required by nothing, so a
    # manifest could omit it and still validate: the same "lower the contract
    # by omission" defect the v2 bump was for, reproduced one field later.
    if at_least(schema, "refinement_experiment_v3"):
        conflicts = pin_conflicts(man)
        bad += conflicts
        # The identity checks read the pin table, so on a CONFLICTED table
        # they cannot be evaluated -- `validate` is contracted to RETURN
        # violations, and letting the resolver's refusal escape as an
        # exception made the validator crash on exactly the input it exists
        # to describe (measured writing this).
        if not conflicts:
            bad += _identity_violations(man)
        uncovered = _identity_covers(man)
        if uncovered:
            bad.append(f"identity.analysis_reach omits {uncovered}, which this "
                       f"bundle carries -- those analyses' ids would fall back "
                       f"to recomputing from the reader's import graph")
    # An analysis carried at a precision it is not DEFINED at (owner priority 6).
    # The other direction is REQUIRED_WHEN_INSTRUMENTED above; this one is what
    # a manifest cannot talk its way out of, because the precision it is checked
    # against is the precision it declares about itself.
    prec = man.get("precision")
    if prec:
        wrong = sorted({a.get("analysis") for a in (man.get("analyses") or [])
                        if isinstance(a, dict)
                        and a.get("analysis") in ANALYSIS_PRECISIONS
                        and not applicable(a["analysis"], prec)})
        if wrong:
            bad.append(
                f"precision={prec} bundle carries {wrong}, which are defined "
                f"only at {sorted({p for a in wrong for p in ANALYSIS_PRECISIONS[a]})}"
                f" -- an analysis nobody can read is not evidence")
    # arm and precision are not independent: an f64 arm at f32 precision, or the
    # reverse, describes a run that cannot exist.
    if man.get("arm") == "f64" and man.get("precision") != "f64":
        bad.append("arm=f64 requires precision=f64")
    if man.get("arm") in ("reference", "probe") and man.get("precision") != "f32":
        bad.append(f"arm={man.get('arm')} requires precision=f32")

    analyses = man.get("analyses")
    if man.get("instrumented") is True and not analyses:
        bad.append("instrumented=true requires a non-empty `analyses`")
    nsplits = {m.get("nsplit") for m in (members if isinstance(members, list) else [])
               if isinstance(m, dict)}
    bad += _analysis_violations(analyses or [], nsplits, schema)

    # Every published file must live INSIDE the bundle. The producer generates
    # safe basenames, but this validator claims to judge an arbitrary v2
    # manifest, so a `../outside.txt` must not be one it accepts.
    seen = set()
    for label, block in (("members", members), ("analyses", analyses),
                        ("build_artifacts", arts)):
        for i, e in enumerate(block if isinstance(block, list) else []):
            f = e.get("file") if isinstance(e, dict) else None
            if not isinstance(f, str):
                continue
            if f != Path(f).name or f in ("", ".", ".."):
                bad.append(f"{label}[{i}].file {f!r} is not a plain basename")
            elif f in seen:
                bad.append(f"{label}[{i}].file {f!r} is declared twice")
            else:
                seen.add(f)
    return bad


#: `analyses[]` holds two different artifacts. A derived table is only as good
#: as the analyzer that produced it; a raw arm stream is only as good as the
#: command that produced it. Requiring `{file, sha256}` of both let a derived
#: JSON ship with NO analyzer, which the checker then reported as
#: `analyzer-unpinned` -- a passing state kept for legacy bundles (owner P0-4).
#: The density profiles an `arm_stream` entry may declare. A DIFFERENT
#: namespace from the manifest-level `arm` (reference|probe|f64): that one says
#: which precision arm the bundle is, this one says which density control the
#: raw stream was run under.
_RHO_ARMS = ("as-is", "uniform", "inverted", "x2", "offset+", "offset-")

#: The driver's second argument. It error-stops on anything else, so a `ran`
#: block naming something else describes a run that could not have happened.
_CARRY_MODES = ("carry", "rezero")

#: The driver reads NSPLIT into a Fortran default INTEGER, so the read fails
#: above int32 and it error-stops. MEASURED against the real binary:
#:
#:   2147483647  accepted
#:   2147483648  ERROR STOP NSPLIT must be a positive integer
#:
#: "Positive integer" alone therefore admits identities the driver rejects
#: (Codex). Python ints are unbounded; the run this describes is not.
_MAX_NSPLIT = 2 ** 31 - 1

#: The derived analyses a v2 bundle may carry. Declared here rather than
#: imported, because the producer imports THIS module; a test asserts the two
#: agree, so drift is a failure rather than a silently widened union.
#: Without it any `analysis` string that was not "arm_stream" was accepted as a
#: derived analysis, so a typo shipped as a new kind (owner §8.2).
DERIVED_ANALYSES = ("matched_closure", "cap_interface", "extension_protocol",
                    "dual_ledger", "defect_magnitude", "internal_cap_enthalpy",
                    "metric_trajectory", "substep_schedule",
                    "water_enthalpy_basis")

#: Analyses that run the DRIVER over several configurations rather than
#: reading one member stream. They analyse the bundle's own binary, so the
#: bundle is where they belong -- but they have no single member to key on,
#: which is why the derived variant's `nsplit` cannot describe them and a third
#: tag is needed. `g33_ncmin_locality` is (driver, fixture) and runs the driver
#: once per decomposition; the derived contract is (stream, basis) per member.
MULTI_RUN_ANALYSES = ("ncmin_locality", "qr_process_ledger")

#: What an `--nflux` bundle must actually contain. `instrumented: true` with a
#: single arm_stream satisfied "analyses is non-empty" while carrying none of
#: the instrumented analyses (owner §8.3).
#: Every analysis an `--nflux` bundle must carry. FLAT, and the archive is
#: brought up to it rather than exempted.
#:
#: Making it conditional on the bundle's own `producer_modules` looked like it
#: spared four immutable archived bundles, but a manifest that omits a module
#: pin then omits the requirement with it -- the synthetic manifest pins the
#: placeholder "p", so the rule required NOTHING there and the existing
#: instrumented-analyses regression went green while asserting nothing (Codex).
#: A contract a manifest can switch off by leaving something out is not a
#: contract, which is the same lesson as every other check here.
REQUIRED_WHEN_INSTRUMENTED = ("matched_closure", "cap_interface",
                              "extension_protocol", "dual_ledger",
                              "defect_magnitude", "internal_cap_enthalpy",
                              "substep_schedule", "water_enthalpy_basis")

#: analysis -> the PRECISIONS at which it is defined (owner priority 6).
#:
#: An analysis is not automatically valid on every stream the producer can hand
#: it, and until now nothing said so anywhere. `qr_process_ledger` REPLAYS the
#: reference update in raw f32 words -- it reads each operand's f32 bits,
#: accumulates in np.float32 in the source's own order under the positivity
#: clamp, and closes against the stored f32 result. At f64 those stage records
#: are f64 (D6), its `_want_f32` refuses them, and the producer dies mid-bundle.
#: That is the SAFE outcome and still the wrong one: "not defined here" and
#: "crashed here" are different facts and the bundle recorded neither.
#:
#: `ncmin_locality` and `metric_trajectory` are f32-only for a plainer reason --
#: both read the bundle's G33R member, and an f64 build emits no G33R at all.
#:
#: The eight per-member analyses read the G33N/G33F extension records, whose
#: width the stream's own PROTOCOL header carries, so they are defined at both
#: and were measured running at both.
#:
#: DECLARED, and checked in the direction a manifest cannot fake: an entry that
#: is not defined at the run's own declared precision is REFUSED, so a bundle
#: cannot carry a table nobody can read.
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
    """Whether `analysis` is DEFINED on a run at `precision`.

    Refuses a name it does not know rather than defaulting to True: a new
    analysis would otherwise be declared valid everywhere by the act of not
    being listed, which is the fail-open shape every other check here closes.
    """
    if analysis not in ANALYSIS_PRECISIONS:
        raise KeyError(
            f"{analysis!r} has no declared precision applicability; add it to "
            f"ANALYSIS_PRECISIONS rather than letting it default to valid")
    return precision in ANALYSIS_PRECISIONS[analysis]


_DERIVED_FIELDS = ("analysis", "nsplit", "analyzer", "analyzer_sha256",
                   "analyzer_commit", "analyzer_blob_sha")
_ARM_FIELDS = ("analysis", "nsplit", "arm", "runtime_argv")


#: The typed run identity, as VALUES rather than as string positions.
#:
#: ONE spelling, shared with the multi-run block below. They would otherwise be
#: two `ran` blocks under one name with different field sets, and the first
#: draft of this one said `mode` where that one says `carry` -- two words for
#: the driver's one argument, in the same manifest.
_RAN_CORE = ("nsplit", "carry", "width", "rho")

#: argv position -> the `ran` field it must agree with. `runtime_argv` stays
#: beside `ran` as the literal command line: a diagnostic, and the thing the
#: typed block is checked against.
_ARGV_TO_RAN = ((0, "nsplit"), (1, "carry"), (2, "width"), (3, "rho"))


def _expected_run_violations(man: dict, members: list) -> list:
    """The bundle's declared experiment, and every member's geometry against
    it (owner review §4, §6).

    Two records of one fact again, at the document level: `expected_run`
    states the fixture's parameters and the requested decomposition, the
    member rows state what each run stepped -- and until now the second was
    copied out of the streams and compared to nothing. The geometry is
    RECOMPUTED here from the fixture's horizon by the driver's own rule, so
    a member row can no longer carry a step nobody could have asked for.

    Not a re-read of the streams: that is the evidence chain's job, against
    the bytes. This is the DOCUMENT answering for itself.
    """
    import g33_refine_experiment as xp                  # cycle closes at call
    EXPECTED_RUN_SCHEMA = xp.EXPECTED_RUN_SCHEMA
    bad = []
    if man.get("algorithm") not in _ALGOS:
        bad.append(f"algorithm {man.get('algorithm')!r} is not one of {_ALGOS}")
    else:
        for i, m in enumerate(members):
            if isinstance(m, dict) and m.get("algorithm") not in (
                    None, man["algorithm"]):
                bad.append(f"members[{i}] ran {m['algorithm']!r} but the "
                           f"bundle declares algorithm {man['algorithm']!r}")
    exp = man.get("expected_run")
    if not isinstance(exp, dict):
        return bad + ["expected_run must be an object: without it the "
                      "manifest records what each member stepped and never "
                      "what the experiment asked for"]
    # A CLOSED schema (owner review §5). Every field was "compare if
    # present", so deleting one deleted its check: a v4 manifest could drop
    # algorithm, precision and rho_profile and still validate, and `levels`
    # was never read at all. The key set is exact -- a missing field is a
    # contract not met, an extra one is a contract nobody wrote.
    v5 = at_least(man.get("schema"), "refinement_experiment_v5")
    if v5:
        substantiable = bool(man.get("instrumented")) or man.get("arm") in (
            "probe", "f64")
        want_keys = {"schema", "fixture_id", "fixture_sha256", "dt_bits",
                     "window_seconds", "columns", "levels", "algorithm",
                     "precision", "source_precision", "mode", "nsplits",
                     "rho_profile"} | ({"tile_sizes"} if substantiable
                                       else set())
        if set(exp) != want_keys:
            bad.append(
                f"expected_run is not the {EXPECTED_RUN_SCHEMA} key set: "
                f"missing {sorted(want_keys - set(exp))}, unexpected "
                f"{sorted(set(exp) - want_keys)}")
        if exp.get("schema") != EXPECTED_RUN_SCHEMA:
            bad.append(f"expected_run.schema {exp.get('schema')!r} is not "
                       f"{EXPECTED_RUN_SCHEMA!r}")
        if exp.get("fixture_sha256") != man.get("fixture_sha256"):
            bad.append("expected_run.fixture_sha256 is not the manifest's "
                       "own fixture digest")
        # The WORD is canonical: 300.000001 decodes to the same f32 as
        # 300.0, so a document compared only on the decimal can name a
        # horizon the fixture does not hold.
        word = exp.get("dt_bits")
        if not (isinstance(word, str) and re.fullmatch(r"[0-9A-F]{8}", word)):
            bad.append(f"expected_run.dt_bits {word!r} is not an 8-hex "
                       f"f32 word")
        else:
            decoded = struct.unpack(">f", bytes.fromhex(word))[0]
            got = exp.get("window_seconds")
            # EXACT, not "rounds to the same f32": 300.000001 rounds to
            # 300.0 and would derive identical geometry while naming a
            # horizon no fixture holds. The decimal is a DECODE of the word,
            # so it is the decode or it is wrong (owner review §5).
            try:
                as_float = (float(got)
                            if isinstance(got, (int, float))
                            and not isinstance(got, bool) else None)
            except (OverflowError, ValueError):     # an unbounded Python int
                as_float = None
            if as_float is None or as_float != decoded:
                bad.append(
                    f"expected_run.window_seconds {got!r} is not the decode "
                    f"of the declared DT_BITS word {word} ({decoded})")
        if exp.get("source_precision") != "f32":
            bad.append(f"expected_run.source_precision "
                       f"{exp.get('source_precision')!r} -- the reference "
                       f"this archive instruments is f32, always")
        if exp.get("mode") not in _CARRY_MODES:
            bad.append(f"expected_run.mode {exp.get('mode')!r} is not one of "
                       f"{_CARRY_MODES}")
        ns = exp.get("nsplits")
        if (not isinstance(ns, list) or not ns
                or not all(isinstance(n, int) and not isinstance(n, bool)
                           and 1 <= n <= _MAX_NSPLIT for n in ns)
                or sorted(ns) != ns or len(set(ns)) != len(ns)):
            bad.append(f"expected_run.nsplits {ns!r} is not a sorted list of "
                       f"distinct steps the driver accepts")
        # ...and the four records of one invocation agree: the declared
        # steps and mode, the member rows, and (below) the geometry each
        # implies (owner review §6).
        elif isinstance(members, list):
            got_ns = sorted(m.get("nsplit") for m in members
                            if isinstance(m, dict))
            if got_ns != sorted(ns):
                bad.append(f"expected_run.nsplits {sorted(ns)} is not the "
                           f"members' {got_ns}")
        for i, m in enumerate(members if isinstance(members, list) else []):
            if isinstance(m, dict) and m.get("mode") not in (None,
                                                             exp.get("mode")):
                bad.append(f"members[{i}] ran mode {m['mode']!r}, the bundle "
                           f"declares {exp.get('mode')!r} -- one experiment, "
                           f"one auxiliary-state rule")
        # ...and the COMMAND LINES close the loop (owner review §6): the
        # recipe id hashes runtime_argv, so an argv that does not describe
        # the declared experiment puts a different request into the id than
        # the one the document states. Four records of one invocation --
        # argv, expected_run, the member rows, and (in the chain) the raw
        # headers -- and until here the first three were never tied.
        argv = man.get("runtime_argv")
        if not isinstance(argv, list) or not argv:
            bad.append("runtime_argv must be a non-empty list: it is the "
                       "recipe id's record of what was invoked")
        else:
            seen = []
            for i, a in enumerate(argv):
                if not (isinstance(a, list) and len(a) >= 2):
                    bad.append(f"runtime_argv[{i}] {a!r} is not a driver "
                               f"command line")
                    continue
                if a[1] != exp.get("mode"):
                    bad.append(f"runtime_argv[{i}] ran mode {a[1]!r}, the "
                               f"bundle declares {exp.get('mode')!r}")
                try:
                    seen.append(int(a[0]))
                except (TypeError, ValueError):
                    bad.append(f"runtime_argv[{i}] nsplit {a[0]!r} is not an "
                               f"integer")
                # The forcing argument, present or ABSENT (Codex): the
                # driver defaults it to `as-is`
                # (g33_refine_driver.f90:320,347), so a line that omits it
                # requested the unperturbed profile -- and leaving the
                # omission unbound let a bundle declare `uniform` beside an
                # invocation that never asked for one. An omitted argument
                # is a request, not a silence.
                got_rho = a[3] if len(a) >= 4 else "as-is"
                how = "" if len(a) >= 4 else " (the omitted argument is the " \
                                             "driver's default)"
                if got_rho != exp.get("rho_profile"):
                    bad.append(f"runtime_argv[{i}] ran rho_profile "
                               f"{got_rho!r}{how}, the bundle declares "
                               f"{exp.get('rho_profile')!r}")
                # ...and the TILE argument, which is the decomposition the
                # command line actually requested (Codex). It sits at
                # position 2 whenever the line carries one, and `ncmin` is
                # set by a tile's last column -- so an argv asking for a
                # tiling the bundle does not declare put a different
                # operator into the recipe id than the document states.
                declared = exp.get("tile_sizes")
                if isinstance(declared, list):
                    want = ",".join(str(t) for t in declared)
                    if len(a) >= 3:
                        if str(a[2]) != want:
                            bad.append(
                                f"runtime_argv[{i}] requested the "
                                f"decomposition {a[2]!r}, the bundle declares "
                                f"{want!r}")
                    # A command line with NO tile argument requests the
                    # driver's DEFAULT -- one tile over the whole domain
                    # (g33_refine_driver.f90:365-366) -- and that is a
                    # request like any other (Codex): leaving it unbound let
                    # a bundle declare (1,2) beside an argv that asked for
                    # the default, with nothing at the document level to
                    # notice.
                    elif declared != [exp.get("columns")]:
                        bad.append(
                            f"runtime_argv[{i}] carries no tile argument, so "
                            f"it requested the driver's default of one tile "
                            f"over {exp.get('columns')!r} columns -- the "
                            f"bundle declares {declared}")
            if seen and isinstance(ns, list) and sorted(seen) != sorted(ns):
                bad.append(f"runtime_argv invokes nsplits {sorted(seen)}, the "
                           f"bundle declares {sorted(ns)}")
    if exp.get("fixture_id") != Path(str(man.get("fixture_path", ""))).stem:
        bad.append(f"expected_run.fixture_id {exp.get('fixture_id')!r} is not "
                   f"the pinned fixture "
                   f"{Path(str(man.get('fixture_path', ''))).stem!r}")
    for key, top in (("algorithm", "algorithm"), ("precision", "precision"),
                     ("rho_profile", "rho_profile")):
        if key in exp and top in man and exp[key] != man[top]:
            bad.append(f"expected_run.{key} {exp[key]!r} disagrees with the "
                       f"manifest's {top} {man[top]!r}")
    horizon = exp.get("window_seconds")
    # `math.isfinite` takes a FLOAT, and an unbounded Python int overflows
    # on the way in -- so the guard against a nonsense horizon crashed on a
    # nonsense horizon (Codex). JSON gives ints and floats alike; both are
    # coerced here, and a value that cannot become one is the violation.
    try:
        horizon = float(horizon) if isinstance(
            horizon, (int, float)) and not isinstance(horizon, bool) else None
    except (OverflowError, ValueError):
        horizon = None
    if horizon is None or not math.isfinite(horizon) or horizon <= 0:
        return bad + [f"expected_run.window_seconds {horizon!r} is not a "
                      f"positive number"]
    tiles = exp.get("tile_sizes")
    # A decomposition may be declared exactly where this bundle carries a
    # protocol that records one: G33N under --nflux, or G33P on the probe
    # and f64 arms (Codex). A plain reference bundle has neither, so a
    # declaration there answers to nothing -- and its ABSENCE where one is
    # substantiable would leave the operator unrecorded.
    substantiable = bool(man.get("instrumented")) or man.get("arm") in (
        "probe", "f64")
    if tiles is not None and not substantiable:
        bad.append("expected_run.tile_sizes declares a decomposition no "
                   "protocol in this bundle records: an uninstrumented "
                   "reference member writes no tile vector")
    elif tiles is None and substantiable:
        bad.append("expected_run.tile_sizes is missing, and this bundle's "
                   "protocols do record the decomposition it ran")
    elif tiles is None:
        pass
    elif (not isinstance(tiles, list) or not tiles
            or not all(isinstance(t, int) and not isinstance(t, bool) and t > 0
                       for t in tiles)):
        bad.append(f"expected_run.tile_sizes {tiles!r} is not a non-empty "
                   f"list of positive column counts")
    elif isinstance(exp.get("columns"), int) and sum(tiles) != exp["columns"]:
        bad.append(f"expected_run.tile_sizes {tiles} sums to {sum(tiles)}, "
                   f"not the {exp['columns']} columns it declares")
    # The arms run the BUNDLE'S decomposition -- g33_run_matrix passes the
    # domain width as one tile -- so their typed `ran` blocks answer to the
    # declared one. Two records of one fact again (Codex): the chain already
    # ties each `ran` to its stream, and this ties it to the request, so the
    # document cannot declare one operator and publish another. The
    # multi-run inputs are deliberately NOT held here: varying the
    # decomposition is what that analysis is for, and each is checked
    # against its own recorded runtime_argv.
    if isinstance(tiles, list):
        for i, a in enumerate(man.get("analyses") or []):
            if not isinstance(a, dict) or a.get("analysis") != "arm_stream":
                continue
            ran = a.get("ran")
            got = ran.get("tile_sizes") if isinstance(ran, dict) else None
            if isinstance(got, list) and got != tiles:
                bad.append(
                    f"analyses[{i}] (arm_stream) ran the decomposition {got}, "
                    f"the bundle's expected_run declares {tiles}")
    prec = exp.get("precision", man.get("precision", "f32"))
    # The sub-cycle limit comes from the bundle's OWN record, never from the
    # tree validating it (owner review §4): a verdict that depends on the
    # checkout is not a verdict about a content-addressed artifact.
    kg = man.get("kernel_geometry")
    v5 = at_least(man.get("schema"), "refinement_experiment_v5")
    if kg is None and not v5:
        return bad                  # predates the record; nothing to derive
    if not isinstance(kg, dict):
        return bad + ["kernel_geometry must be an object: the member "
                      "geometry is derived from the kernel's sub-cycle "
                      "limit, and a bundle that does not record it can only "
                      "be checked against whatever tree reads it"]
    if kg.get("schema") not in xp.KNOWN_KERNEL_GEOMETRY_SCHEMAS:
        bad.append(f"kernel_geometry.schema {kg.get('schema')!r} is not one "
                   f"of {xp.KNOWN_KERNEL_GEOMETRY_SCHEMAS}")
    elif at_least(man.get("schema"), "refinement_experiment_v6") and \
            kg["schema"] != xp.KERNEL_GEOMETRY_SCHEMA:
        bad.append(f"kernel_geometry.schema {kg['schema']!r} is not "
                   f"{xp.KERNEL_GEOMETRY_SCHEMA!r}, which answers for the "
                   f"COMPILED bytes")
    elif v5 and kg["schema"] not in ("kdm6_subcycle_v2",
                                     xp.KERNEL_GEOMETRY_SCHEMA):
        bad.append(f"kernel_geometry.schema {kg['schema']!r} is not "
                   f"{xp.KERNEL_GEOMETRY_SCHEMA!r}, which records WHICH "
                   f"kernel the limit came from")
    limit = kg.get("dtcldcr")
    try:
        limit = float(limit) if isinstance(limit, (int, float)) and not \
            isinstance(limit, bool) else None
    except (OverflowError, ValueError):
        limit = None
    if limit is None or not math.isfinite(limit) or limit <= 0:
        return bad + [f"kernel_geometry.dtcldcr {kg.get('dtcldcr')!r} is not "
                      f"a positive finite number"]
    if kg.get("dtcldcr_storage") not in _PRECISIONS:
        bad.append(f"kernel_geometry.dtcldcr_storage "
                   f"{kg.get('dtcldcr_storage')!r} is not one of "
                   f"{_PRECISIONS}")
    else:
        w = ">d" if kg["dtcldcr_storage"] == "f64" else ">f"
        want_word = struct.pack(w, limit).hex().upper()
        if kg.get("dtcldcr_word") != want_word:
            bad.append(f"kernel_geometry.dtcldcr_word "
                       f"{kg.get('dtcldcr_word')!r} is not {want_word} -- the "
                       f"word and the value name two different limits")
    if not _hexlen(kg.get("source_sha256"), 64):
        bad.append("kernel_geometry.source_sha256 is not a 64-hex digest of "
                   "the kernel source the limit was read from")
    # The digest must be the MODULE THIS BUNDLE PINS, not merely 64 hex
    # (owner review §4): the record was length-checked and compared to the
    # checkout's source map, so an arbitrary digest -- or one naming a
    # different file than the manifest and the build provenance record --
    # passed while claiming to be the provenance of the limit.
    if at_least(man.get("schema"), "refinement_experiment_v6"):
        bp = man.get("build_provenance")
        bp = bp if isinstance(bp, dict) else {}
        for field, top in (("source_path", "module_path"),
                           ("source_sha256", "module_sha256")):
            if not man.get(top):
                bad.append(f"{top} is required from v6: the kernel geometry's "
                           f"provenance is the module this bundle pins")
            elif kg.get(field) != man.get(top):
                bad.append(f"kernel_geometry.{field} {kg.get(field)!r} is not "
                           f"the manifest's {top} {man.get(top)!r} -- the "
                           f"limit would be provenanced to another file")
            elif bp.get(top) not in (None, man[top]):
                bad.append(f"build_provenance.{top} {bp[top]!r} is not the "
                           f"manifest's {man[top]!r} -- two records of the "
                           f"module that was compiled")
        # ...and the STORAGE is the build's own real kind: `dtcldcr` is a
        # default real, so an f64 build stores it in eight bytes. 120.0 is
        # exact in both widths, so the two only diverge for a future limit
        # that is not f32-exact -- which is exactly when the loop count
        # would move silently (owner review §5).
        # The limit the EXECUTABLE enforces was read from the overlay the
        # compiler was fed, not assumed from the module it was generated
        # out of (owner review §4.3).
        if man.get("instrumented") is True:
            if kg.get("compiled_source_sha256") != bp.get(
                    "compiled_module_sha256"):
                bad.append(
                    f"kernel_geometry.compiled_source_sha256 "
                    f"{str(kg.get('compiled_source_sha256'))[:12]!r} is not "
                    f"the compiled_module_sha256 "
                    f"{str(bp.get('compiled_module_sha256'))[:12]!r} -- the "
                    f"limit was read from other bytes than the compiler did")
            if kg.get("compiled_dtcldcr_word") != kg.get("dtcldcr_word"):
                bad.append("kernel_geometry.compiled_dtcldcr_word is not the "
                           "module's own word: the generated overlay carries "
                           "a different sub-cycle limit")
        if kg.get("dtcldcr_storage") != man.get("precision"):
            bad.append(f"kernel_geometry.dtcldcr_storage "
                       f"{kg.get('dtcldcr_storage')!r} is not this build's "
                       f"real kind {man.get('precision')!r}")
    # WHICH kernel: the build compiles a different module per algorithm
    # (refine_build.sh:54-55), so a record naming the other one describes a
    # file this run never compiled (Codex).
    if kg.get("schema") != "kdm6_subcycle_v1" and \
            kg.get("algorithm") != man.get("algorithm"):
        bad.append(f"kernel_geometry.algorithm {kg.get('algorithm')!r} is not "
                   f"the bundle's {man.get('algorithm')!r} -- the limit was "
                   f"read from another kernel than the one that ran")
    want_src = xp.KERNEL_SOURCES.get(man.get("algorithm"))
    if (kg.get("schema") != "kdm6_subcycle_v1" and want_src is not None
            and kg.get("source_path") != str(want_src)):
        bad.append(f"kernel_geometry.source_path {kg.get('source_path')!r} is "
                   f"not the {man.get('algorithm')} kernel {str(want_src)!r}")
    for i, m in enumerate(members):
        if not isinstance(m, dict):
            continue
        n = m.get("nsplit")
        if not isinstance(n, int) or isinstance(n, bool) or n < 1:
            continue                      # the members block already says so
        # The arithmetic runs on numbers a malformed document supplies, so
        # its failures are VIOLATIONS, not exceptions: `validate` is
        # contracted to return them, and a checker that crashes on exactly
        # the input it exists to describe is the defect one level up
        # (Codex; the same shape as the pin resolver's escape before it).
        try:
            want_d, want_L, want_h = xp.expected_geometry(
                horizon, n, prec, limit)
        except (ArithmeticError, OverflowError, ValueError, struct.error) as e:
            bad.append(f"members[{i}]: the fixture's {horizon} s horizon over "
                       f"{n} splits is not computable at {prec}: {e}")
            continue
        for key, want in (("delt", want_d), ("dtcld", want_h)):
            got = m.get(key)
            if got is None or isinstance(got, bool) \
                    or not isinstance(got, (int, float)):
                bad.append(f"members[{i}] records {key}={got!r}, which is not "
                           f"a number this contract can check")
            elif f"{got:.6f}" != f"{want:.6f}":
                bad.append(
                    f"members[{i}] records {key}={got} at nsplit={n},"
                    f" but the fixture's {horizon} s horizon gives {want}")
        loops = m.get("loops")
        if not isinstance(loops, int) or isinstance(loops, bool):
            bad.append(f"members[{i}] records loops={loops!r}, which is not an "
                       f"integer this contract can check")
        elif loops != want_L:
            bad.append(f"members[{i}] records loops={loops}, the kernel's "
                       f"rule gives {want_L} for delt={want_d}")
    return bad


def _arm_ran_violations(i: int, a: dict, argv: list, v4: bool = True) -> list:
    """Every position of an arm's command line, against its typed identity.

    Only argv[0] and argv[3] were compared before, so the carry mode and the
    domain width were recorded and never read -- half the run identity of an
    arbitrary v2 manifest (owner priority 5). The vocabularies are the driver's
    own, the same ones the multi-run block uses: it error-stops on anything
    else, so a manifest declaring anything else names a run that could not have
    happened.
    """
    ran = a.get("ran")
    if not isinstance(ran, dict) or not all(k in ran for k in _RAN_CORE):
        return [f"analyses[{i}] (arm_stream) needs `ran` with "
                f"{', '.join(_RAN_CORE)}: the command line alone is four "
                f"strings and only two of them were ever checked"]
    bad = []
    if not isinstance(ran["nsplit"], int) or isinstance(ran["nsplit"], bool) \
            or not 1 <= ran["nsplit"] <= _MAX_NSPLIT:
        bad.append(f"analyses[{i}] (arm_stream) ran.nsplit {ran['nsplit']!r} "
                   f"is not a positive integer the driver accepts "
                   f"(1..{_MAX_NSPLIT})")
    elif ran["carry"] not in _CARRY_MODES:
        bad.append(f"analyses[{i}] (arm_stream) ran.carry {ran['carry']!r} is "
                   f"not one of {_CARRY_MODES}")
    elif ran["rho"] not in _RHO_ARMS:
        bad.append(f"analyses[{i}] (arm_stream) ran.rho {ran['rho']!r} is not "
                   f"one of {_RHO_ARMS}")
    elif not isinstance(ran["width"], int) or isinstance(ran["width"], bool) \
            or ran["width"] < 1:
        bad.append(f"analyses[{i}] (arm_stream) ran.width {ran['width']!r} is "
                   f"not a positive integer")
    # `levels` is ran-only -- the command line has no position for it -- and
    # required for the same reason `width` is: it is half the domain the
    # stream processed, and the chain compares it against the strict parse.
    lv = ran.get("levels")
    if not isinstance(lv, int) or isinstance(lv, bool) or lv < 1:
        bad.append(f"analyses[{i}] (arm_stream) ran.levels {lv!r} is not a "
                   f"positive integer")
    # ...and so is the DECOMPOSITION, for a stronger reason than either
    # (owner review §5): `ncmin` is a scalar set by a tile's last column, so
    # two arm streams differing only in their tiling ran two different
    # operators. A `ran` block that cannot say which one it ran cannot be
    # checked against the request by anything downstream.
    ts = ran.get("tile_sizes")
    if not v4:
        pass                     # published before the decomposition was typed
    elif (not isinstance(ts, list) or not ts
            or not all(isinstance(t, int) and not isinstance(t, bool) and t > 0
                       for t in ts)):
        bad.append(f"analyses[{i}] (arm_stream) ran.tile_sizes {ts!r} is not a "
                   f"non-empty list of positive column counts")
    elif sum(ts) != ran["width"]:
        bad.append(f"analyses[{i}] (arm_stream) ran.tile_sizes {ts} sums to "
                   f"{sum(ts)}, not the domain width {ran['width']}")
    elif ran.get("ntile") != len(ts):
        bad.append(f"analyses[{i}] (arm_stream) ran.ntile {ran.get('ntile')!r} "
                   f"is not the {len(ts)} tiles it lists")
    if bad:
        return bad
    for pos, field in _ARGV_TO_RAN:
        if argv[pos] != str(ran[field]):
            bad.append(f"analyses[{i}] runtime_argv[{pos}]={argv[pos]!r} "
                       f"contradicts ran.{field}={ran[field]!r}")
    # The entry's own top-level fields must agree with it too, or the block
    # would be a third statement nobody compares.
    if ran["nsplit"] != a.get("nsplit"):
        bad.append(f"analyses[{i}] ran.nsplit={ran['nsplit']} contradicts "
                   f"nsplit={a.get('nsplit')!r}")
    if ran["rho"] != a.get("arm"):
        bad.append(f"analyses[{i}] ran.rho={ran['rho']!r} contradicts "
                   f"arm={a.get('arm')!r}")
    return bad


def _analysis_violations(analyses, member_nsplits, schema=SCHEMA) -> list:
    bad = []
    for i, a in enumerate(analyses):
        if not isinstance(a, dict) or not isinstance(a.get("file"), str) \
                or not _hexlen(a.get("sha256"), 64):
            bad.append(f"analyses[{i}] needs `file` and a 64-hex `sha256`")
            continue
        kind = a.get("analysis")
        if not isinstance(kind, str):
            bad.append(f"analyses[{i}] declares no `analysis` kind")
            continue
        want = (_ARM_FIELDS if kind == "arm_stream"
                else () if kind in MULTI_RUN_ANALYSES else _DERIVED_FIELDS)
        missing = [k for k in want if not a.get(k)]
        if missing:
            bad.append(f"analyses[{i}] ({kind}) is missing {missing}")
        if kind == "arm_stream":
            if a.get("arm") not in _RHO_ARMS:
                bad.append(f"analyses[{i}] arm {a.get('arm')!r} is not one of "
                           f"{_RHO_ARMS}")
            argv = a.get("runtime_argv")
            if not isinstance(argv, list) or not all(isinstance(x, str)
                                                     for x in argv):
                bad.append(f"analyses[{i}] runtime_argv must be a list of str")
            elif len(argv) < 4:
                bad.append(f"analyses[{i}] runtime_argv {argv} is too short to "
                           f"say which run it was")
            else:
                # The argv is what RAN; the fields are what the manifest SAYS.
                # Recording both without comparing them lets an entry describe a
                # different run than the one it names (owner §8.1).
                #
                # ALL FOUR positions, against a TYPED block (owner priority 5).
                # Only argv[0] and argv[3] were compared, so the mode and the
                # domain width were recorded and never read -- half the run
                # identity of an arbitrary v2 manifest went unverified. `ran`
                # carries them as values rather than as string positions, and
                # the producer checks it against the raw stream's own header
                # before writing it.
                if at_least(schema, "refinement_experiment_v3"):
                    bad += _arm_ran_violations(
                        i, a, argv,
                        at_least(schema, "refinement_experiment_v4"))
                else:
                    # v2 compared exactly these two positions.
                    if argv[0] != str(a.get("nsplit")):
                        bad.append(f"analyses[{i}] runtime_argv nsplit "
                                   f"{argv[0]!r} contradicts nsplit "
                                   f"{a.get('nsplit')!r}")
                    if argv[3] != a.get("arm"):
                        bad.append(f"analyses[{i}] runtime_argv arm "
                                   f"{argv[3]!r} contradicts arm "
                                   f"{a.get('arm')!r}")
        elif kind in MULTI_RUN_ANALYSES:
            # Keyed on the FIXTURE and the decompositions it ran, not on a
            # member: there is no single stream this concluded from.
            if not isinstance(a.get("fixture"), str) or not a["fixture"]:
                bad.append(f"analyses[{i}] ({kind}) needs the `fixture` it ran")
            d = a.get("decompositions")
            decomps_ok = (isinstance(d, list) and bool(d) and all(
                isinstance(x, list) and x
                and all(isinstance(v, int) and not isinstance(v, bool) and v > 0
                        for v in x) for x in d))
            if not decomps_ok:
                bad.append(f"analyses[{i}] ({kind}) needs `decompositions` as a "
                           f"non-empty list of positive-int lists")
            elif len({tuple(x) for x in d}) != len(d):
                bad.append(f"analyses[{i}] ({kind}) repeats a decomposition")
            # The parameters the analysis DROVE THE BINARY AT. Without them
            # the entry reads as though it shared the bundle's nsplit/mode,
            # and it does not: this analysis chooses its own (Codex).
            ran = a.get("ran")
            if not isinstance(ran, dict) or not all(
                    k in ran for k in ("nsplit", "carry", "rho", "width",
                                       "decompositions")):
                bad.append(f"analyses[{i}] ({kind}) needs `ran` with nsplit, "
                           f"carry, rho, width and decompositions")
            # TYPED, not merely present. Checking only that the keys exist
            # accepted nsplit="twelve", nsplit=0, carry="banana" and
            # rho="purple" -- a run identity that cannot describe any run the
            # driver would accept (Codex). These are the driver's own
            # vocabularies: it error-stops on anything else.
            elif not isinstance(ran["nsplit"], int) or isinstance(
                    ran["nsplit"], bool) or not 1 <= ran["nsplit"] <= _MAX_NSPLIT:
                bad.append(f"analyses[{i}] ({kind}) ran.nsplit "
                           f"{ran['nsplit']!r} is not a positive integer the "
                           f"driver accepts (1..{_MAX_NSPLIT})")
            elif ran["carry"] not in _CARRY_MODES:
                bad.append(f"analyses[{i}] ({kind}) ran.carry "
                           f"{ran['carry']!r} is not one of {_CARRY_MODES}")
            elif ran["rho"] not in _RHO_ARMS:
                bad.append(f"analyses[{i}] ({kind}) ran.rho {ran['rho']!r} "
                           f"is not one of {_RHO_ARMS}")
            elif not isinstance(ran["width"], int) or isinstance(
                    ran["width"], bool) or ran["width"] < 1:
                bad.append(f"analyses[{i}] ({kind}) ran.width "
                           f"{ran['width']!r} is not a positive integer")
            elif ran["decompositions"] != a.get("decompositions"):
                bad.append(f"analyses[{i}] ({kind}) decompositions disagree "
                           f"with `ran` -- one of them is not what executed")
            # EXECUTABLE, not merely well-formed. The driver error-stops with
            # "tile sizes must sum to B", so a decomposition summing to
            # anything else names a run that could not have happened -- and a
            # SET of them summing to different totals cannot all describe one
            # domain (Codex).
            # GUARDED on the shape check above. Without it this reached
            # `sum(d)` on a malformed value and raised TypeError -- a validator
            # that CRASHES on bad input is worse than one that misses it, since
            # `validate()` is contracted to RETURN violations (Codex).
            elif not decomps_ok:
                pass
            elif [d for d in ran["decompositions"] if sum(d) != ran["width"]]:
                bad.append(
                    f"analyses[{i}] ({kind}) decompositions "
                    f"{[d for d in ran['decompositions'] if sum(d) != ran['width']]}"
                    f" do not sum to the domain width {ran['width']} -- the "
                    f"driver error-stops on tile sizes that do not cover B")
            for k in ("analyzer", "analyzer_sha256", "analyzer_commit",
                      "analyzer_blob_sha"):
                if not a.get(k):
                    bad.append(f"analyses[{i}] ({kind}) is missing {k}")
        else:
            if kind not in DERIVED_ANALYSES:
                bad.append(f"analyses[{i}] unknown derived analysis {kind!r} "
                           f"(known: {sorted(DERIVED_ANALYSES)})")
            if a.get("analyzer_commit") and not _hexlen(a["analyzer_commit"], 40):
                bad.append(f"analyses[{i}] analyzer_commit is not a 40-hex sha")
            if a.get("analyzer_blob_sha") and not _hexlen(a["analyzer_blob_sha"], 40):
                bad.append(f"analyses[{i}] analyzer_blob_sha is not a 40-hex sha")
            if a.get("analyzer_sha256") and not _hexlen(a["analyzer_sha256"], 64):
                bad.append(f"analyses[{i}] analyzer_sha256 is not a 64-hex sha")
        # An analysis of a member the bundle does not carry describes nothing.
        # A multi-run analysis reads no member, so it has no nsplit to check --
        # but it does have INPUTS, and those must be in the bundle.
        if kind in MULTI_RUN_ANALYSES:
            ins = a.get("inputs")
            if not isinstance(ins, list) or not ins:
                bad.append(f"analyses[{i}] is multi_run and records no "
                           f"`inputs` -- the raw streams it consumed are the "
                           f"evidence, and a derived JSON alone leaves the "
                           f"chain unable to reach them")
                continue
            seen = set()
            for k, src in enumerate(ins):
                if not isinstance(src, dict):
                    bad.append(f"analyses[{i}].inputs[{k}] is not an object")
                    continue
                f, d = src.get("file"), src.get("sha256")
                if not isinstance(f, str) or not f:
                    bad.append(f"analyses[{i}].inputs[{k}] names no file")
                elif f in seen:
                    bad.append(f"analyses[{i}].inputs lists {f!r} twice")
                else:
                    seen.add(f)
                if not _hexlen(d or "", 64):
                    bad.append(f"analyses[{i}].inputs[{k}] ({f!r}) is not "
                               f"pinned by a 64-hex sha")
                # A plain basename. The file is joined to the bundle directory,
                # so `../` walks out of it and names something the bundle never
                # published.
                if isinstance(f, str) and (
                        "/" in f or "\\" in f or f in (".", "..")):
                    bad.append(f"analyses[{i}].inputs[{k}] file {f!r} is not a "
                               f"plain basename -- it is resolved inside the "
                               f"bundle and must not leave it")
                argv = src.get("runtime_argv")
                if not isinstance(argv, list) or len(argv) != 4:
                    bad.append(f"analyses[{i}].inputs[{k}] ({f!r}) records no "
                               f"4-element runtime_argv -- which decomposition "
                               f"it is has to be readable from the entry")
                elif not all(isinstance(x, str) for x in argv):
                    # Every element, before anything reads one. `argv[2]` was
                    # `.split(",")` straight after the length check, so
                    # `[1, 2, 3, 4]` raised AttributeError out of a function
                    # whose contract is to RETURN violations -- a crash is not
                    # fail-close (owner §6).
                    bad.append(f"analyses[{i}].inputs[{k}] ({f!r}) runtime_argv "
                               f"is not all strings: {argv!r}")
                else:
                    # It must describe the run the ANALYSIS says it made.
                    # Recorded and never compared, so an entry could name a
                    # decomposition, nsplit, carry or rho the analysis never
                    # used and the bundle would still validate.
                    want = a.get("ran") if isinstance(a.get("ran"), dict) else {}
                    for pos, key, label in ((0, "nsplit", "nsplit"),
                                            (1, "carry", "carry"),
                                            (3, "rho", "rho")):
                        if key in want and argv[pos] != str(want[key]):
                            bad.append(
                                f"analyses[{i}].inputs[{k}] ({f!r}) says "
                                f"{label}={argv[pos]!r} but `ran` says "
                                f"{want[key]!r}")
                    tiles = argv[2].split(",")
                    if not tiles or not all(
                            t.isdigit() and int(t) > 0 for t in tiles):
                        bad.append(f"analyses[{i}].inputs[{k}] ({f!r}) "
                                   f"decomposition {argv[2]!r} is not a vector "
                                   f"of positive integers")
            # Every decomposition the analysis says it RAN must be among the
            # streams it kept. Otherwise `ran` describes a run the bundle
            # cannot produce.
            kept = {tuple(src["runtime_argv"][2].split(","))
                    for src in ins
                    if isinstance(src, dict)
                    and isinstance(src.get("runtime_argv"), list)
                    and len(src["runtime_argv"]) == 4
                    and all(isinstance(x, str) for x in src["runtime_argv"])}
            # Only where `decompositions` is well formed. Iterating it blind
            # crashed on [None] and on a bare int -- the same "a guard that
            # crashes is not a guard" defect the width check already had, so
            # the shape rules above report those and this stays quiet.
            decs = a.get("decompositions")
            if (isinstance(decs, list) and decs
                    and all(isinstance(d, list) and d
                            and all(isinstance(x, int) and not isinstance(x, bool)
                                    for x in d) for d in decs)):
                for dec in decs:
                    if tuple(str(x) for x in dec) not in kept:
                        bad.append(f"analyses[{i}] says it ran {dec} but kept "
                                   f"no stream for it")
        elif member_nsplits and a.get("nsplit") not in member_nsplits:
            bad.append(f"analyses[{i}] nsplit {a.get('nsplit')!r} is not among "
                       f"the members {sorted(member_nsplits)}")
    return bad
