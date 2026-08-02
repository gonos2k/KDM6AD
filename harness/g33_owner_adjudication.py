#!/usr/bin/env python3
"""A place for the owner's scientific judgment that cannot forge the tool's (§13).

The automatic verdict stays INCONCLUSIVE; this is a separate layer, not a looser
verdict. Three properties, each a way it could otherwise become the tool's own:

  * the gate never writes one — an adjudication is human-authored, in its own file
  * it cannot write `verdict` — no parameter, no code path
  * it is BOUND to the artifact it judges — the one that matters, since an unbound
    one would keep applying after a regeneration that moved the result

Contains NO adjudication content: the classification in the review is a
recommendation, not an issued verdict.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

#: What an adjudication must carry. Absent or extra keys are both rejected: a
#: missing scope line is a judgment with an unstated domain, and an unexpected key
#: is a field whose meaning nothing here defines.
REQUIRED_FIELDS = (
    "status",                              # closed | open
    "classification",                      # the mechanism, in the owner's words
    "conservative_only_seed",              # bool: did the variant create a seed
    "exact_multisubcycle_cross_tree_parity",   # bool: is exact parity claimed
    "reference_parity_domain",             # where parity IS claimed
    "thermo_policy_selection",             # open | <policy>
    "meteorological_materiality",          # unmeasured | <measurement>
)

#: Fields of the artifact the adjudication is pinned to. Changing any of them
#: means a human reviewed a different result.
BINDING_FIELDS = (
    "verifier_semantics_sha256",
    "fortran_legacy_manifest_sha256",
    "fortran_conservative_manifest_sha256",
    "cpp_root_manifest_sha256",
    "fixture_manifest_sha256",
)


def artifact_digest(artifact: dict) -> str:
    """Digest of the result WITHOUT any attached adjudication — including it would
    make the binding circular and nothing could ever match."""
    body = {k: v for k, v in artifact.items() if k != "owner_adjudication"}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


def binding_for(artifact: dict) -> dict:
    prov = artifact.get("provenance", {})
    b = {k: prov.get(k) for k in BINDING_FIELDS}
    b["artifact_sha256"] = artifact_digest(artifact)
    b["verdict"] = artifact.get("verdict")
    return b


def problems(adjudication: dict, artifact: dict) -> tuple:
    """Every reason this adjudication does not apply. A tuple, not a bool: "the
    fixture was regenerated" and "someone edited it" need different responses."""
    out = []
    body = adjudication.get("owner_adjudication")
    if not isinstance(body, dict):
        return ("no `owner_adjudication` object",)

    missing = [f for f in REQUIRED_FIELDS if f not in body]
    if missing:
        out.append(f"missing required field(s): {', '.join(missing)}")
    extra = [f for f in body if f not in REQUIRED_FIELDS and f != "bound_to"]
    if extra:
        out.append(f"unrecognised field(s): {', '.join(sorted(extra))}")

    bound = body.get("bound_to")
    if not isinstance(bound, dict):
        out.append("no `bound_to` block: an unbound adjudication would keep "
                   "applying after a regeneration that moved the result")
        return tuple(out)

    want = binding_for(artifact)
    for k, w in want.items():
        got = bound.get(k)
        if got != w:
            out.append(f"bound_to.{k} is {got!r}, artifact has {w!r}")
    return tuple(out)


def attach(artifact: dict, adjudication: dict) -> dict:
    """A copy of `artifact` carrying the adjudication, or raise. `verdict` is copied
    through untouched — no parameter changes it and no branch writes it."""
    bad = problems(adjudication, artifact)
    if bad:
        raise ValueError("adjudication does not apply to this artifact:\n  - "
                         + "\n  - ".join(bad))
    out = dict(artifact)
    out["owner_adjudication"] = dict(adjudication["owner_adjudication"])
    return out


def load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text())


def template(artifact: dict) -> dict:
    """A skeleton bound to `artifact`, every judgment None — a plausible default
    would put the tool's words in the owner's file."""
    return {"owner_adjudication": {**{f: None for f in REQUIRED_FIELDS},
                                   "bound_to": binding_for(artifact)}}


def _main(argv) -> int:
    """Print a bound template, or validate one against an artifact. A generator
    rather than a committed file, which would go stale on the next regeneration."""
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("artifact", type=Path)
    ap.add_argument("--check", type=Path, default=None,
                    help="validate this adjudication against the artifact")
    a = ap.parse_args(argv)
    art = load(a.artifact)
    if a.check is None:
        print(json.dumps(template(art), indent=2))
        return 0
    bad = problems(load(a.check), art)
    if bad:
        print("DOES NOT APPLY to this artifact:")
        for p in bad:
            print("  -", p)
        return 1
    print(f"applies to {a.artifact} (verdict {art.get('verdict')}, unchanged)")
    return 0


if __name__ == "__main__":
    import sys as _sys
    raise SystemExit(_main(_sys.argv[1:]))
