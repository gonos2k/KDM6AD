#!/usr/bin/env python3
"""What makes a run the same run, one layer at a time (owner §16-8 / D2).

A bundle has ONE address today, over everything in its manifest. That address
is correct and it is also why adding a single analysis re-produces the whole
archive and re-points every claim binding: a new derived JSON changes the
address of the raw stream it was derived from, which did not move.

So there are three questions the one address answers together:

    run_recipe_id     what was ASKED for -- the code, the fixture, the argv
    run_content_id    what CAME OUT -- the raw members, and the build behind them
    analysis_id       what one analyzer made of that content

Each is a digest over a subset of the same manifest, so nothing new is
recorded and no bundle is re-produced to compute them. They are DERIVED here
and checked; whether the archive should also store them is a separate decision
with a re-production cost attached.

Every one of them is a digest over CONTENT, and that is a second separation the
first attempt did not make:

    content pin        path, content_sha256, blob_sha -- what the bytes ARE
    provenance anchor  commit, repo_commit -- where they can be FETCHED from

A git blob id is a digest of the content, so `blob_sha` is a content pin. A
commit is not: it moves for every commit, including the analysis-only and
documentation-only ones these layers exist to be stable across. Both stay in the
manifest, because an anchor is what makes a pin recoverable and the evidence
chain resolves it; only the anchors are kept out of the ids. Without that, a
producer rebuilding the same bundle from the same bytes at a new HEAD gets a new
`run_recipe_id` -- the coupling being removed one level up, reproduced inside
the layer that removes it.

The layering only means anything if the code behind each layer can be named,
and that is where the first attempt stopped. `_CORE_MODULES` in the producer
serves two purposes at once -- it declares the modules that make a run, AND it
is how a transitive dependency gets pinned at all -- so reading it to decide
"run or analysis" answers a different question.

Measured, and it rules out the obvious fix: an import closure cannot separate
them either, because the producer DISPATCHES every analysis, so every analysis
module is reachable from it and `analysis-only` is empty. Cutting exactly the
dispatch edges gives a labelling that works -- 10 modules make a run, 10 make
an analysis -- and five carry BOTH roles. It is a graph, not a partition, and
a module in both moves both ids, which is correct: `g33_number_transport` is
imported by `g33_probe_read`, so it really does decide what a run admits, and
it really is an analysis of its own.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import g33_refine_experiment as rx  # noqa: E402
import g33_refine_manifest as rm  # noqa: E402


def analysis_seeds() -> set:
    """The modules the producer dispatches to. Read from the registries rather
    than listed again: a list that has to be kept in step with `ANALYSES` is
    the defect this file exists to describe."""
    return ({m for m, _fn in rx.ANALYSES.values()}
            | {m for m, _fn in rx.MULTI_RUN.values()}
            | {"g33_metric_trajectory"})


def _closure(seeds: set, cut_from: str = "", cut: set = frozenset()) -> set:
    """Import closure, with the option to cut the edges out of ONE module.

    The cut is what makes the two roles separable. Blocking the analysis
    modules everywhere instead would drop `g33_number_transport` from the run
    role -- and `g33_probe_read` imports it, so the run really does depend on
    it and the run recipe really does have to pin it.
    """
    seen, todo = set(), list(seeds)
    while todo:
        m = todo.pop()
        if m in seen:
            continue
        seen.add(m)
        nxt = rx._local_imports(m) - seen
        if m == cut_from:
            nxt -= cut
        todo += list(nxt)
    return seen


def run_modules() -> set:
    """Modules that decide what a RUN contains: the driver, the overlay
    generator, the build script's own programs, the manifest writer, and the
    strict parsers that decide what is admitted as a member."""
    seeds = {"g33_refine_experiment"} | rx._build_script_modules()
    return _closure(seeds, cut_from="g33_refine_experiment",
                    cut=analysis_seeds())


def analysis_modules() -> set:
    """Modules that decide what an ANALYSIS says about a run."""
    return _closure(analysis_seeds())


def roles() -> dict:
    """module -> the roles it carries. Every reachable module must have one:
    a module in neither is a module nothing in this file describes, and the
    layering would silently leave its bytes out of every id."""
    run, ana = run_modules(), analysis_modules()
    out = {}
    for m in run | ana:
        out[m] = ({"run"} if m in run else set()) | ({"analysis"} if m in ana
                                                     else set())
    return out


def unlabelled() -> set:
    """Reachable code carrying no role. Empty, or an id is incomplete."""
    return rx.reachable_modules() - set(roles())


#: The version of the layering these ids implement. Recorded in the bundle, so
#: a manifest says which derivation produced its ids rather than leaving a
#: reader to assume today's.
#:
#: v4: `run_recipe_id` hashes the CANONICAL INVOCATION rather than the
#: literal `runtime_argv`, and the ids carry their OWN schema tags rather
#: than the container's. Two spellings of one request -- an omitted tile
#: argument and its explicit default -- addressed differently, and so did
#: two orderings of independent member commands; meanwhile a container-format
#: bump moved every run id with no run byte changed (owner review §7, §8).
#:
#: v3: `run_recipe_id` carries the canonical `expected_run` and the
#: `kernel_geometry` the run was held to. Both are "what was REQUESTED",
#: which is the recipe's own question -- and until v3 the subtractive
#: content id picked them up while the recipe id did not, so changing the
#: request moved the id of the OUTPUT and not the id of the ASK
#: (owner review §6).
#:
#: v2: `run_content_id` reduces the recorded `identity` block to its schema tag.
#: Under v1 the whole block -- role graph, seeds, reach -- rode into the content
#: id, so an ANALYSIS-ONLY change that regenerated the block moved the run's
#: content id: the coupling the layers exist to remove, re-entering through the
#: block that records them. Measured on the real f64 manifest: growing one
#: reach entry moved `run_content_id` with no run byte changed. A version
#: rather than a quiet fix, because it changes what the id MEANS (owner
#: review §3).
IDENTITY_SCHEMA = "g33_layered_identity_v4"

#: The ids' OWN schema tags. They version the canonicalisation RULES, which
#: is a different question from the container's format -- and hashing the
#: container tag meant an archive-format bump re-addressed every run.
RUN_RECIPE_SCHEMA = "g33_run_recipe_v1"
RUN_CONTENT_SCHEMA = "g33_run_content_v1"
ANALYSIS_SCHEMA = "g33_analysis_v1"


def canonical_invocations(man: dict) -> list:
    """The member command lines as REQUESTS, not as spellings.

    The driver defaults an omitted tile argument to one tile over the domain
    and an omitted forcing argument to `as-is`, so `["12","rezero"]` and
    `["12","rezero","3","as-is"]` are the same invocation -- and the members
    are independent subprocesses, so the ORDER of the list is not part of
    the request either. Derived from `expected_run`, which the validator has
    already tied to the literal argv, and sorted.
    """
    # THE ARGUMENT ITSELF, not only its fields (Codex, generalized from
    # `identity_digest([])`). These are public readers, so a caller
    # reaches them with whatever it holds, and a reader that raises has
    # not answered. `rm._obj` is the same coercion the manifest module
    # applies, so there is one definition of "read this as a record".
    man = rm._obj(man)
    exp = man.get("expected_run") or {}
    tiles = exp.get("tile_sizes") or ([exp["columns"]]
                                      if isinstance(exp.get("columns"), int)
                                      else None)
    return sorted(
        ({"nsplit": n, "mode": exp.get("mode"),
          "tile_sizes": list(tiles) if tiles else None,
          "rho_profile": exp.get("rho_profile")}
         for n in (exp.get("nsplits") or [])),
        key=lambda d: (d["nsplit"], str(d["mode"]), str(d["tile_sizes"]),
                       str(d["rho_profile"])))


def identity_block(published=()) -> dict:
    """The role graph and the per-analysis reach, as CONTENT for the manifest.

    Without this an id is a function of the manifest AND of the checkout it is
    computed in. `roles()` and `analysis_reach()` read the registries and the
    import graph of whatever tree is present, so moving a module from run+
    analysis to analysis-only -- a refactor that touches no bundle byte --
    changes `_by_role`'s filter and moves a HISTORICAL manifest's
    `run_content_id`. That is the same coupling the layers exist to remove,
    one level further out, and it is the Phase B prerequisite: an id written
    into an archive must be reproducible from the archive (owner priority 8).

    Recorded rather than recomputed, because the graph is a fact about the code
    that made the bundle, and that code is already pinned beside it.
    """
    return {"schema": IDENTITY_SCHEMA,
            "role_graph": {m: sorted(r) for m, r in sorted(roles().items())},
            # The SEED of each reach entry, which is also the producer's
            # dispatch set -- the edges cut out of `g33_refine_experiment` to
            # make the two roles separable. Recorded because the cut is part of
            # the derivation: without it a checker either cannot excuse the run
            # module's imports of analysis ones, or has to excuse them from the
            # bundle's own `analyses`, which is under-derived for a bundle that
            # legitimately carries only some of them (an f64 bundle carries none
            # of the f32-only three).
            #
            # EXACTLY the pinned registries plus what this bundle published.
            # Recording every producible analysis left keys answerable to
            # nothing -- an f64 bundle recorded 11 and published 8 -- and an
            # invented key names any module the dispatcher imports, which
            # widens the cut to cover it (Codex stop-time review).
            "analysis_seeds": dict(sorted(_recorded(published).items())),
            "analysis_reach": {name: sorted(_closure({mod}))
                               for name, mod in sorted(_recorded(published).items())}}


def _recorded(published) -> dict:
    """The seeds a bundle records: the producer's registries, plus anything it
    published that the registries do not name.

    Registry entries stay even where this bundle produced none of them -- the
    dispatcher imports those modules whatever one bundle made, so the cut needs
    them. `metric_trajectory` is the other kind: dispatched by
    `_driver_analyses` rather than through a registry, so it is recorded only by
    the bundles that carry it, and there its seed is pinned to the analyzer its
    own published entry names.
    """
    reg = set(rx.ANALYSES) | set(rx.MULTI_RUN)
    keep = reg | set(published)
    return {n: m for n, m in producible().items() if n in keep}


def producible() -> dict:
    """analysis name -> the module that produces it, for EVERY analysis a
    bundle can carry.

    `metric_trajectory` is written by `_driver_analyses` directly rather than
    dispatched through a registry, so it is in neither `ANALYSES` nor
    `MULTI_RUN` -- and it is in every instrumented as-is bundle. Left out of the
    reach map, its `analysis_id` fell back to recomputing from the reader's
    import graph, which is the one thing the map exists to prevent. Checked
    against the manifest module's own vocabulary by a test, so the next
    analysis produced outside a registry fails here rather than going quiet.
    """
    out = {name: mod for name, (mod, _fn)
           in {**rx.ANALYSES, **rx.MULTI_RUN}.items()}
    out["metric_trajectory"] = "g33_metric_trajectory"
    return out


#: Schemas that MUST carry the identity block. Below this a manifest predates
#: it and the fallback is the only thing available; at or above it, falling
#: back would let a bundle opt out of the contract by omission -- which is the
#: defect the block was added to close, reproduced one level down.
_REQUIRES_IDENTITY = "refinement_experiment_v3"


def _requires_block(man: dict) -> bool:
    return rm.at_least(str(man.get("schema", "")), _REQUIRES_IDENTITY)


def _graph(man: dict) -> dict:
    """The role graph THIS manifest was produced under, or today's.

    A manifest that records one is read with it, whatever the checkout looks
    like now. One that PREDATES the block has nothing else to use, so its ids
    remain a function of the current tree -- a fact about those bundles rather
    than a property of the layering, and `identity_is_self_contained` is how a
    caller asks which it is holding.

    From v3 the block is required, and its absence RAISES rather than falling
    back. The fallback was unconditional at first, so a v3 manifest could omit
    the block and quietly get checkout-dependent ids anyway: the contract was
    opt-out-by-omission, which is exactly what the schema bump before it was
    for (Codex stop-time review).
    """
    rec = (man.get("identity") or {}).get("role_graph")
    if isinstance(rec, dict) and rec:
        return {m: set(r) for m, r in rec.items()}
    if _requires_block(man):
        raise ValueError(
            f"schema {man.get('schema')!r} requires an `identity.role_graph` "
            f"and this manifest has none -- deriving an id from the current "
            f"checkout would be the coupling the block exists to remove")
    return roles()


def identity_is_self_contained(man: dict) -> bool:
    """Whether this manifest's ids can be recomputed from the manifest alone."""
    # THE ARGUMENT ITSELF, not only its fields (Codex, generalized from
    # `identity_digest([])`). These are public readers, so a caller
    # reaches them with whatever it holds, and a reader that raises has
    # not answered. `rm._obj` is the same coercion the manifest module
    # applies, so there is one definition of "read this as a record".
    man = rm._obj(man)
    ident = man.get("identity") or {}
    return (ident.get("schema") == IDENTITY_SCHEMA
            and isinstance(ident.get("role_graph"), dict)
            and bool(ident["role_graph"])
            and isinstance(ident.get("analysis_reach"), dict))


def split_analyses(man: dict) -> tuple:
    """(derived, raw) entries of the `analyses` block.

    That block does double duty, the same way `_CORE_MODULES` does. Most
    entries are a derived JSON with an `analyzer` pinned three ways. Some are
    `arm_stream` -- a RAW stream from a perturbed run, recorded with its own
    `runtime_argv` and no analyzer at all, because no analyzer made it.

    A layering that strips `analyses` wholesale therefore drops raw content out
    of the content id, and two runs differing only in their arm streams would
    address as the same run. Split by whether an analyzer made the entry, and
    REFUSE anything that is neither: an entry nobody can classify must not
    quietly land on the side that happens to be cheaper.
    """
    # THE ARGUMENT ITSELF, not only its fields (Codex, generalized from
    # `identity_digest([])`). These are public readers, so a caller
    # reaches them with whatever it holds, and a reader that raises has
    # not answered. `rm._obj` is the same coercion the manifest module
    # applies, so there is one definition of "read this as a record".
    man = rm._obj(man)
    derived, raw, bad = [], [], []
    for a in man.get("analyses") or []:
        if not isinstance(a, dict):
            bad.append(a)
        elif a.get("analyzer"):
            derived.append(a)
        elif a.get("runtime_argv") and a.get("sha256"):
            raw.append(a)
        else:
            bad.append(a)
    if bad:
        raise ValueError(
            f"{len(bad)} analyses entry/entries are neither derived (an "
            f"`analyzer`) nor raw (a `runtime_argv` and a `sha256`): "
            f"{[str(x)[:80] for x in bad]}")
    return derived, raw


def _digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


#: Keys that say WHERE a byte can be RETRIEVED from, not WHAT it is.
#:
#: This is the second half of the separation, and without it the first half does
#: not work. Every pin block carries `commit` beside `content_sha256`, and
#: `repo_commit` sits at the top of the manifest -- so an id over the pins moves
#: whenever the CONTAINING commit moves, which is every commit, including the
#: analysis-only and documentation-only ones the layering exists to be stable
#: across. A producer that rebuilds the same bundle from the same bytes at a new
#: HEAD would have got a new run_recipe_id, which is exactly the coupling that
#: was being removed one level up.
#:
#: `blob_sha` STAYS: a git blob id is a digest of the content, so it is a
#: content pin that happens to be spelled the way git spells one. It is stable
#: across commits precisely when the bytes are.
#:
#: The anchors are not dropped from the MANIFEST -- they are what makes a pin
#: recoverable, and the evidence chain resolves them. They are dropped from the
#: IDENTITY, which is a different question about the same record.
PROVENANCE_ANCHORS = ("commit", "analyzer_commit", "repo_commit")

#: Blocks that describe the run rather than come out of it.
#:
#: `findings` is the prose a reviewer reads, digested at publish time so a later
#: revision is visible. Correcting a sentence in a finding must not re-address
#: the raw stream the finding describes.
NARRATIVE_KEYS = ("findings",)


def _canonical_lists(man: dict) -> dict:
    """The manifest with every SET-valued list in canonical order.

    JSON objects hash order-independently (`sort_keys`); lists do not, and
    four of the manifest's lists are semantically SETS -- the pins, the
    members, the build artifacts. The producer happens to write them in one
    order, but two valid manifests recording the same rows differently ordered
    would carry different ids, and Phase B stores ids (owner review §7.3). The
    ORDER-BEARING lists are left alone: `runtime_argv` is a command line, and
    an `analyses` entry's `inputs` follow its own sort.
    """
    out = dict(man)
    for key in ("member_parsers", "tracked_build_inputs", "producer_modules"):
        if isinstance(out.get(key), list):
            out[key] = sorted(out[key], key=lambda e: str(e.get("path", e)))
    if isinstance(out.get("members"), list):
        out["members"] = sorted(
            out["members"],
            key=lambda e: (e.get("nsplit", 0), str(e.get("mode", "")),
                           str(e.get("file", ""))))
    if isinstance(out.get("build_artifacts"), list):
        out["build_artifacts"] = sorted(out["build_artifacts"],
                                        key=lambda e: str(e.get("file", e)))
    # An analysis's `inputs` are a set of digested files (owner review §10.2):
    # the chain reads them per-file, nothing reads their order, and
    # `analysis_id` hashes the entry -- so the order must not move the id.
    if isinstance(out.get("analyses"), list):
        out["analyses"] = [
            {**a, "inputs": sorted(a["inputs"],
                                   key=lambda e: str(e.get("file", e)))}
            if isinstance(a, dict) and isinstance(a.get("inputs"), list)
            else a
            for a in out["analyses"]]
    return out


def content_only(x):
    """`x` with every retrieval anchor removed, at any depth.

    Recursive rather than a top-level key list: the anchors are mostly INSIDE
    the pin blocks (`producer_modules[].commit`, `analyses[].analyzer_commit`),
    which is why stripping `repo_commit` alone would have looked like a fix and
    left the same coupling one level down.
    """
    if isinstance(x, dict):
        return {k: content_only(v) for k, v in x.items()
                if k not in PROVENANCE_ANCHORS}
    if isinstance(x, list):
        return [content_only(v) for v in x]
    return x


def _by_role(man: dict, role: str) -> list:
    """The manifest's producer-module pins, filtered to one role and reduced to
    their CONTENT.

    The manifest lists all 17 as one block, so an id built from it unfiltered
    moves when any analysis module's bytes move -- which is the whole cost
    being separated here, reproduced inside the recipe.
    """
    keep = {m for m, r in _graph(man).items() if role in r}
    return content_only(
        sorted((e for e in (man.get("producer_modules") or [])
                if isinstance(e, dict)
                and Path(str(e.get("path", ""))).stem in keep),
               key=lambda e: str(e.get("path"))))


def run_recipe_id(man: dict) -> str:
    """What was asked for: run-role code, the fixture, the module under test,
    and the argv. NOT the members -- a recipe that changed when its own output
    changed could not answer "was this the same experiment".

    Every pin is reduced to its CONTENT first. `member_parsers` and
    `tracked_build_inputs` carry the same commit-beside-digest shape as the
    module pins, so passing them through raw put the containing commit into the
    recipe by the back door.
    """
    # THE ARGUMENT ITSELF, not only its fields (Codex, generalized from
    # `identity_digest([])`). These are public readers, so a caller
    # reaches them with whatever it holds, and a reader that raises has
    # not answered. `rm._obj` is the same coercion the manifest module
    # applies, so there is one definition of "read this as a record".
    man = rm._obj(man)
    man = _canonical_lists(man)
    return _digest({
        "modules": _by_role(man, "run"),
        "member_parsers": content_only(man.get("member_parsers")),
        "tracked_build_inputs": content_only(man.get("tracked_build_inputs")),
        # The canonical invocation, not the literal argv (owner review §7):
        # the argv stays in the MANIFEST as the diagnostic record of what was
        # typed, and the validator ties the two -- but the id is about the
        # request, and two spellings of one request are one request.
        "invocations": canonical_invocations(man),
        "fixture": (man.get("fixture_path"), man.get("fixture_sha256")),
        "module": (man.get("module_path"), man.get("module_sha256")),
        "arm": man.get("arm"), "precision": man.get("precision"),
        "rho_profile": man.get("rho_profile"),
        "instrumented": man.get("instrumented"),
        # The RECIPE's own schema, not the container's (owner review §8): a
        # container-format bump re-addressed every run whose bytes had not
        # moved, which is the coupling the layered identity exists to remove.
        "schema": RUN_RECIPE_SCHEMA,
        "artifact_type": man.get("artifact_type"),
        # WHAT WAS ASKED FOR (identity v3, owner review §6). The recipe is
        # the request; `expected_run` is the request stated in full and
        # `kernel_geometry` is the rule the request is interpreted under.
        # The subtractive content id picked both up automatically, so
        # without them here a changed request moved the OUTPUT's id and not
        # the ASK's -- the wrong way round for the question each answers.
        "expected_run": man.get("expected_run"),
        "kernel_geometry": man.get("kernel_geometry"),
    })


def run_content_id(man: dict) -> str:
    """The run itself: the recipe, plus the raw members and the build behind
    them. STABLE when an analysis is added, changed or removed -- which is the
    property that would let a new analysis stop re-addressing the stream.

    Built by removing the analysis layer and reusing `identity_digest`, so it
    inherits the same rules about what is diagnostic and what is payload
    rather than inventing a second answer to that question.

    Four things have to be taken out with it, and each was measured wrong
    first. `producer_modules` is ONE flat block holding run-role and
    analysis-role pins together, so an unfiltered content id moved when an
    analyzer's bytes moved -- the coupling this file exists to remove. The
    retrieval ANCHORS go too, `repo_commit` at the top and `commit` inside every
    pin, or the id moves on every commit whatever the bytes did. So do the
    `findings`, which are prose attached to the run and not output of it. And
    the RAW arm streams stay IN, because they are content: see `split_analyses`.

    What deliberately STAYS is the compiler. It is not an anchor: two builds of
    identical sources by different compilers are not the same run content, and
    an id that called them equal would be answering a question nobody asked.
    """
    # THE ARGUMENT ITSELF, not only its fields (Codex, generalized from
    # `identity_digest([])`). These are public readers, so a caller
    # reaches them with whatever it holds, and a reader that raises has
    # not answered. `rm._obj` is the same coercion the manifest module
    # applies, so there is one definition of "read this as a record".
    man = rm._obj(man)
    man = _canonical_lists(man)
    _derived, raw = split_analyses(man)
    keep = {k: v for k, v in man.items()
            if k not in ("analyses", "analyzer_sha256") + NARRATIVE_KEYS}
    keep["producer_modules"] = _by_role(man, "run")
    # The CONTENT's own schema, for the same reason as the recipe's (owner
    # review §8): the container's format version is not a fact about the
    # run's bytes, and hashing it re-addressed every run on an
    # archive-format bump. The literal argv goes with it -- the canonical
    # invocation in the recipe id is the request, and the content id
    # inherits that through the recipe.
    keep["schema"] = RUN_CONTENT_SCHEMA
    keep.pop("runtime_argv", None)
    # The identity block is reduced to its SCHEMA TAG (identity v2). The block
    # holds the role graph, the seeds and every reach entry, so hashing it
    # whole put the ANALYSIS half of the derivation into the run's content id
    # -- an analysis growing one import moved the id of a run whose bytes had
    # not (owner review §3). The run-role information the content id needs is
    # already in it: `_by_role` above filters the pins THROUGH the recorded
    # graph, so a graph that assigns run-role differently changes the pin list
    # itself. The tag stays because two manifests canonicalised under
    # different rules are not comparable ids.
    #
    # Still SUBTRACTIVE, deliberately, against the reviewed allow-list shape:
    # an enumerated projection silently DROPS any new manifest field from the
    # id until someone remembers to add it -- fail-open in the other
    # direction. Subtraction moves the id on an unclassified new field, which
    # is the fail-closed default everything else here follows; the exceptions
    # are enumerated and each carries its measurement.
    if isinstance(keep.get("identity"), dict):
        keep["identity"] = {"schema": keep["identity"].get("schema")}
    if raw:
        keep["arm_streams"] = sorted(raw, key=lambda a: str(a.get("file")))
    return rm.identity_digest(content_only(keep))


def _pins_for(man: dict, modules: set) -> list:
    """The manifest's pins for exactly these modules, reduced to their CONTENT."""
    return content_only(
        sorted((e for e in (man.get("producer_modules") or [])
                if isinstance(e, dict)
                and Path(str(e.get("path", ""))).stem in modules),
               key=lambda e: str(e.get("path"))))


def analysis_reach(man: dict, name: str) -> set:
    """The modules ONE analysis can reach -- its own closure, not the whole
    analysis role. An id over the role would move every analysis whenever any
    analysis module changed, which is the cost being separated here reproduced
    one layer down."""
    # THE ARGUMENT ITSELF, not only its fields (Codex). These two carry a
    # SECOND required argument, which is how the first sweep missed them:
    # the discovery filter asked for readers callable with `man` alone,
    # and that is a convenience of the sweep, not the shape of the
    # defect. The class is "a public function whose first argument is a
    # manifest"; the rest the caller supplies.
    man = rm._obj(man)
    rec = (man.get("identity") or {}).get("analysis_reach", {})
    if isinstance(rec, dict) and rec.get(name):
        # RECORDED: the closure as it stood when the bundle was made. Recomputing
        # it walks today's import graph, so an analyzer that grew an import
        # since would widen a historical analysis's id (owner priority 8).
        return set(rec[name])
    if _requires_block(man):
        raise ValueError(
            f"schema {man.get('schema')!r} requires an `identity.analysis_reach` "
            f"entry for {name!r} and this manifest has none -- recomputing the "
            f"closure would walk the reader's imports, not the producer's")
    derived, _raw = split_analyses(man)
    mods = {Path(str(a["analyzer"])).stem for a in derived
            if a.get("analysis") == name}
    unknown = {m for m in mods if not rx._module_file(m)}
    if unknown or not mods:
        # An id over nothing is an id that never moves. `arm_stream` reaches
        # here legitimately and is not an analysis at all -- it is raw content,
        # and `analysis_id` is the wrong question to ask about it.
        raise KeyError(f"{name!r}: no resolvable analyzer module "
                       f"({sorted(unknown) or 'none named'})")
    return _closure(mods)


def analysis_id(man: dict, name: str) -> str:
    """One analysis: the content it read, its own entry, and the code IT can
    reach.

    The entry carries `analyzer_commit` beside `analyzer_sha256`, so it is
    reduced to its content like every other pin: the analyzer's BYTES must move
    this id, and they do -- `analyzer_sha256` and `analyzer_blob_sha` are both
    still in it. The commit that happened to contain them must not.
    """
    # THE ARGUMENT ITSELF, not only its fields (Codex). These two carry a
    # SECOND required argument, which is how the first sweep missed them:
    # the discovery filter asked for readers callable with `man` alone,
    # and that is a convenience of the sweep, not the shape of the
    # defect. The class is "a public function whose first argument is a
    # manifest"; the rest the caller supplies.
    man = rm._obj(man)
    man = _canonical_lists(man)
    derived, _raw = split_analyses(man)
    entries = [a for a in derived if a.get("analysis") == name]
    if not entries:
        raise KeyError(f"no derived analysis named {name!r} in this manifest")
    return _digest({"schema": ANALYSIS_SCHEMA,
                    "run_content": run_content_id(man),
                    "entries": content_only(
                        sorted(entries, key=lambda a: str(a.get("file")))),
                    "modules": _pins_for(man, analysis_reach(man, name))})


#: Re-exported so the producer keeps one import. The CHECK lives in the
#: manifest module because it is a property of the DOCUMENT against the bytes
#: the document pins -- and the evidence chain must be able to run it without
#: importing the producer.
BlobUnavailable = rm.BlobUnavailable
graph_violations = rm.graph_violations
pinned_imports = rm.pinned_imports


def report(man: dict) -> None:
    # THE ARGUMENT ITSELF, not only its fields (Codex, generalized from
    # `identity_digest([])`). These are public readers, so a caller
    # reaches them with whatever it holds, and a reader that raises has
    # not answered. `rm._obj` is the same coercion the manifest module
    # applies, so there is one definition of "read this as a record".
    man = rm._obj(man)
    print(f"  run_recipe_id   {run_recipe_id(man)[:16]}")
    print(f"  run_content_id  {run_content_id(man)[:16]}")
    print(f"  identity_digest {rm.identity_digest(man)[:16]}  (the address today)")
    derived, raw = split_analyses(man)
    for n in sorted({a["analysis"] for a in derived}):
        print(f"    {n:28} {analysis_id(man, n)[:16]}"
              f"  reaches {len(analysis_reach(man, n))}")
    for a in sorted(raw, key=lambda a: str(a.get("file"))):
        print(f"    {a.get('analysis'):28} {'-':>16}  raw content, no analyzer")


if __name__ == "__main__":
    r = roles()
    print(f"  {len(r)} modules carry a role; "
          f"{sum(1 for v in r.values() if len(v) == 2)} carry both")
    for m in sorted(r):
        print(f"    {m:26} {'+'.join(sorted(r[m]))}")
    if unlabelled():
        raise SystemExit(f"REFUSED: unlabelled reachable modules: "
                         f"{sorted(unlabelled())}")
    for arg in sys.argv[1:]:
        print(f"\n  {arg}")
        report(json.loads(Path(arg).read_text()))
