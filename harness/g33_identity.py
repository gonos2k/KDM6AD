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


def _by_role(man: dict, role: str) -> list:
    """The manifest's producer-module pins, filtered to one role.

    The manifest lists all 17 as one block, so an id built from it unfiltered
    moves when any analysis module's bytes move -- which is the whole cost
    being separated here, reproduced inside the recipe.
    """
    keep = {m for m, r in roles().items() if role in r}
    return sorted((e for e in (man.get("producer_modules") or [])
                   if isinstance(e, dict)
                   and Path(str(e.get("path", ""))).stem in keep),
                  key=lambda e: str(e.get("path")))


def run_recipe_id(man: dict) -> str:
    """What was asked for: run-role code, the fixture, the module under test,
    and the argv. NOT the members -- a recipe that changed when its own output
    changed could not answer "was this the same experiment"."""
    return _digest({
        "modules": _by_role(man, "run"),
        "member_parsers": man.get("member_parsers"),
        "tracked_build_inputs": man.get("tracked_build_inputs"),
        "runtime_argv": man.get("runtime_argv"),
        "fixture": (man.get("fixture_path"), man.get("fixture_sha256")),
        "module": (man.get("module_path"), man.get("module_sha256")),
        "arm": man.get("arm"), "precision": man.get("precision"),
        "rho_profile": man.get("rho_profile"),
        "instrumented": man.get("instrumented"),
        "schema": man.get("schema"), "artifact_type": man.get("artifact_type"),
    })


def run_content_id(man: dict) -> str:
    """The run itself: the recipe, plus the raw members and the build behind
    them. STABLE when an analysis is added, changed or removed -- which is the
    property that would let a new analysis stop re-addressing the stream.

    Built by removing the analysis layer and reusing `identity_digest`, so it
    inherits the same rules about what is diagnostic and what is payload
    rather than inventing a second answer to that question.

    Two things have to be taken out with it, and both were measured wrong
    first. `producer_modules` is ONE flat block holding run-role and
    analysis-role pins together, so an unfiltered content id moved when an
    analyzer's bytes moved -- the coupling this file exists to remove. And the
    RAW arm streams stay IN, because they are content: see `split_analyses`.
    """
    _derived, raw = split_analyses(man)
    keep = {k: v for k, v in man.items()
            if k not in ("analyses", "analyzer_sha256")}
    keep["producer_modules"] = _by_role(man, "run")
    if raw:
        keep["arm_streams"] = sorted(raw, key=lambda a: str(a.get("file")))
    return rm.identity_digest(keep)


def _pins_for(man: dict, modules: set) -> list:
    """The manifest's pins for exactly these modules."""
    return sorted((e for e in (man.get("producer_modules") or [])
                   if isinstance(e, dict)
                   and Path(str(e.get("path", ""))).stem in modules),
                  key=lambda e: str(e.get("path")))


def analysis_reach(man: dict, name: str) -> set:
    """The modules ONE analysis can reach -- its own closure, not the whole
    analysis role. An id over the role would move every analysis whenever any
    analysis module changed, which is the cost being separated here reproduced
    one layer down."""
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
    reach."""
    derived, _raw = split_analyses(man)
    entries = [a for a in derived if a.get("analysis") == name]
    if not entries:
        raise KeyError(f"no derived analysis named {name!r} in this manifest")
    return _digest({"run_content": run_content_id(man),
                    "entries": sorted(entries, key=lambda a: str(a.get("file"))),
                    "modules": _pins_for(man, analysis_reach(man, name))})


def report(man: dict) -> None:
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
