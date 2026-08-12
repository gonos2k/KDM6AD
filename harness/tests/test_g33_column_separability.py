#!/usr/bin/env python3
"""Column-local physics must be block-separable — LOCAL ONLY (needs gfortran).

Microphysics is column-local: each column's tendencies depend on that column's state and
forcing. That makes the operator block-separable,

    M(X_1, ..., X_B) = (M_1(X_1), ..., M_B(X_B))

and therefore equivariant under any column permutation P:

    M(P X) = P M(X)

This is not a style preference. It is what makes a result independent of column ordering,
tile decomposition and MPI partitioning — a model that fails it can give different
answers for the same atmosphere depending on how the domain was split.

`ncmin` in the pinned Fortran reference is a candidate violation
(harness/evidence/FINDING_ncmin_scalar_vs_percell.md): it is declared
`real :: ncmin` — a SCALAR — assigned inside a per-column loop, so after the loop it
holds only column `ite`'s value, and it is then read at 18 per-(k,i) sites. Every
column is gated on the LAST column's threshold.

If that reading is right, permuting the columns changes which threshold every column
gets, so equivariance fails. If it is wrong, this test says so. Either way it is a
measurement rather than an argument from reading the source.

The test needs a fixture where the mechanism can act at all: mixed surface types AND
different ncmin values. `boundary_mapping_v1` is the only one — both arithmetic fixtures
are all-land with ncmin_land == ncmin_sea, which is why nothing has ever seen this.
"""
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "harness" / "g33_fortran"))
import g33_fixture_v1 as gfx          # noqa: E402
import g33_fortran_dump as fd         # noqa: E402

BUILD = ROOT / "harness" / "g33_fortran" / "fortran_build.sh"
REF = ROOT / "host" / "KIM-meso_v1.0" / "phys" / "module_mp_kdm6.F"
GEN = ROOT / "harness" / "g33_fixture_v1.py"

pytestmark = pytest.mark.skipif(
    shutil.which("gfortran") is None or not REF.is_file(),
    reason="Fortran leg is local-only (needs gfortran + the gitignored host reference)",
)

FIXTURE = "boundary_mapping_v1"
#: The permutation applied to the columns. It must MOVE THE SEA COLUMN TO `ite`,
#: because the scalar `ncmin` keeps whatever the LAST column's surface type selected.
#: (1, 0, 2) swaps columns 1 and 2 and leaves the land column at the end, so the scalar
#: is unchanged and the test passes without exercising anything — which is what it did
#: on the first run, because the precondition below asserted the opposite of what it
#: needed.
#:
#: The fixture's nc is 4.0e7..5.04e7, between ncmin_sea 2.5e7 and ncmin_land 1e8, so
#: `nci <= ncmin` genuinely flips with the selection.
PERM = (0, 2, 1)          # 0-based: bring the SEA column (index 1) to the last slot


def _f32(word: str) -> float:
    return struct.unpack(">f", bytes.fromhex(word))[0]


def _permuted_manifest(authority: dict, perm) -> dict:
    """The same atmosphere with its columns reordered. Every per-column quantity moves
    together — fields, xland — so the SET of columns is unchanged."""
    B, K = authority["B"], authority["K"]
    out = json.loads(json.dumps(authority))       # deep copy
    for name, words in authority["fields"].items():
        out["fields"][name] = [words[perm[c] * K + k]
                               for c in range(B) for k in range(K)]
    out["xland"] = [authority["xland"][perm[c]] for c in range(B)]
    return out


def _run(manifest: dict, tmp: Path, tag: str) -> dict:
    """Render the manifest, build, run at the kernel boundary, parse."""
    # The renderer prints its outputs relative to ROOT, so they have to live inside the
    # repo; and the build selects a generated module by NAME from its own directory, so
    # the .f90 has to sit beside the others anyway.
    mpath = tmp / f"{tag}.json"
    mpath.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    staged = ROOT / "harness" / "g33_fortran" / f"g33_fixture_permtest_{tag}.f90"
    staged_h = ROOT / "harness" / "g33_overlay" / f"g33_fixture_permtest_{tag}.h"
    try:
        r = subprocess.run([sys.executable, str(GEN), "--write", "--manifest", str(mpath),
                            "--cpp-out", str(staged_h), "--fortran-out", str(staged)],
                           capture_output=True, text=True, cwd=ROOT)
        assert r.returncode == 0, f"render failed:\n{r.stdout}\n{r.stderr}"
        out = tmp / f"build_{tag}"
        b = subprocess.run(["bash", str(BUILD), str(out), "--algo=legacy", "--dump",
                            f"--fixture=g33_fixture_permtest_{tag}"],
                           capture_output=True, text=True, cwd=ROOT)
        assert b.returncode == 0, f"build failed:\n{b.stdout}\n{b.stderr}"
        env = {**os.environ, "G33_ENTRY": "kernel"}
        p = subprocess.run([str(out / "g33_fortran_driver")], capture_output=True,
                           text=True, env=env)
        assert p.returncode == 0, f"driver crashed:\n{p.stderr}"
    finally:
        staged.unlink(missing_ok=True)
        staged_h.unlink(missing_ok=True)
    return fd.parse_fortran_run(p.stdout, "legacy", manifest["K"], manifest["B"],
                                allow_negative_input=True)


def test_the_fixture_can_actually_expose_the_mechanism():
    """Both escape conditions must be broken, or the test proves nothing."""
    _, a = gfx.load_fixture(FIXTURE)
    lands = [_f32(x) for x in a["xland"]]
    sea = [x >= 1.5 for x in lands]
    assert any(sea) and not all(sea), f"xland={lands} is not mixed"
    assert (a["common_parameters"]["ncmin_land"]
            != a["common_parameters"]["ncmin_sea"])
    # THE PERMUTATION MUST CHANGE THE SURFACE TYPE AT `ite`, or the scalar ncmin is
    # unchanged and the equivariance test cannot fail however wrong the code is. My
    # first version asserted `==` here — the opposite — and the test passed vacuously.
    assert sea[PERM[-1]] != sea[-1], (
        f"permutation {PERM} leaves ite's surface type at {sea[-1]}, so the scalar "
        f"ncmin selection does not move and nothing is exercised")
    # and the gate must be able to flip under the two thresholds
    nc = [_f32(x) for x in a["fields"]["nc"]]
    lo = _f32(a["common_parameters"]["ncmin_sea"])
    hi = _f32(a["common_parameters"]["ncmin_land"])
    assert min(nc) > min(lo, hi) and max(nc) < max(lo, hi), (
        f"nc {min(nc):.3g}..{max(nc):.3g} does not straddle the thresholds "
        f"{lo:.3g}/{hi:.3g}, so `nci <= ncmin` gives the same answer either way")


@pytest.mark.xfail(strict=True, reason=(
    "MEASURED FAILURE, not a harness bug: 46 of 144 final-state cells change when the "
    "columns are reordered, so the pinned Fortran operator is not column-local. The "
    "`ncmin` scalar is the mechanism (see FINDING_ncmin_scalar_vs_percell.md). strict=True "
    "on purpose — if this ever starts passing, the behaviour changed and this test must "
    "be promoted from xfail to a requirement. Which implementation is correct — "
    "reference-faithful scalar, or per-column — is an owner decision, and production "
    "physics is frozen."))
def test_column_permutation_equivariance():
    """M(P X) == P M(X), on the final state.

    The same atmosphere with its columns in a different order must give the same answer,
    reordered. A model that fails this can give different results depending on how the
    domain was split across tiles or ranks.
    """
    _, authority = gfx.load_fixture(FIXTURE)
    B, K = authority["B"], authority["K"]
    with tempfile.TemporaryDirectory(prefix="g33-perm.") as td:
        tmp = Path(td)
        base = _run(authority, tmp, "base")
        perm = _run(_permuted_manifest(authority, PERM), tmp, "perm")

    # STATE key is (field, col, k) with col 1-based; undo the permutation on the
    # permuted run and require bit equality with the base run.
    def unpermute(state):
        return {(f, PERM.index(c - 1) + 1, k): b for (f, c, k), b in state.items()}

    got, want = unpermute(perm.state), base.state
    assert set(got) == set(want)
    bad = sorted(k for k in want if got[k] != want[k])
    assert not bad, (
        f"{len(bad)} of {len(want)} final-state cells are not permutation-equivariant, "
        f"e.g. {bad[:6]} — the operator is not column-local. See "
        f"harness/evidence/FINDING_ncmin_scalar_vs_percell.md")


# ── tile-decomposition invariance (owner review §6 acceptance gate) ──────────
#
# Column permutation is one of the four gates §6 asks for. This is the second:
# splitting the SAME columns across separate kdm62D calls, the way a tile or MPI
# decomposition does. It is driver-side only -- `its:ite` is a call argument -- so
# it needs no production change, and it exercises the mechanism from a completely
# different direction than permuting the input.

REFINE_BUILD = ROOT / "harness" / "g33_fortran" / "refine_build.sh"


def _compositions(n):
    """Every contiguous partition of `n` columns — (3,), (1,2), (2,1), (1,1,1)."""
    if n == 0:
        yield ()
        return
    for first in range(1, n + 1):
        for rest in _compositions(n - first):
            yield (first,) + rest


def _tiled(tmp: Path, tiles) -> dict:
    """Final state after the fixture's step, columns split as `tiles`."""
    out = tmp / "build"
    if not out.exists():
        b = subprocess.run(["bash", str(REFINE_BUILD), str(out),
                            "--fixture=g33_fixture_boundary_mapping_v1",
                            "--algo=legacy"], capture_output=True, text=True, cwd=ROOT)
        assert b.returncode == 0, f"build failed:\n{b.stdout}\n{b.stderr}"
    p = subprocess.run([str(out / "g33_refine_driver"), "1", "rezero",
                        ",".join(str(t) for t in tiles)],
                       capture_output=True, text=True)
    assert p.returncode == 0, f"driver crashed:\n{p.stderr}"
    return {tuple(ln.split()[2:5]): ln.split()[5]
            for ln in p.stdout.splitlines() if ln.startswith("G33R STATE")}


def test_the_partitions_include_one_that_can_expose_the_mechanism():
    """Without this the gate is vacuous however wrong the code is: the scalar
    `ncmin` keeps the LAST column's threshold, so a partition whose tiles all end on
    the same surface type as the whole domain gives identical gating. (1,2) is such
    a partition and is EXPECTED to agree -- testing only that would pass while the
    operator was arbitrarily non-local."""
    _, a = gfx.load_fixture(FIXTURE)
    sea = [_f32(x) >= 1.5 for x in a["xland"]]
    whole = sea[-1]

    def ends(tiles):
        i, out = 0, []
        for w in tiles:
            i += w
            out.append(sea[i - 1])
        return out

    parts = list(_compositions(a["B"]))
    assert any(t != whole for p in parts for t in ends(p)), (
        "no partition puts a different surface type at a tile end")
    assert any(all(t == whole for t in ends(p)) for p in parts if len(p) > 1), (
        "expected at least one multi-tile partition that agrees trivially")


@pytest.mark.xfail(strict=True, reason=(
    "MEASURED FAILURE, not a harness bug. Over ALL four contiguous partitions of the "
    "3-column domain, two change the final state: (1,1,1) moves 16 of 144 cells and "
    "(2,1) moves 31, up to 21% of the state, decided purely by where the tile "
    "boundary falls. The `ncmin` scalar keeps the last column's threshold, so a tile "
    "ending on the sea column gates ALL of its columns on ncmin_sea. An MPI rank "
    "boundary IS a tile boundary, so this is the rank-count dependence too. "
    "strict=True: if it starts passing the behaviour changed and it must be promoted "
    "to a requirement. Production physics is frozen; the corrected variant is an "
    "owner decision."))
def test_tile_decomposition_invariance():
    """M(X) must not depend on how the columns are split across kernel calls.

    Exhaustive over the compositions of the domain, not just even splits: the even
    split misses (2,1), which is the worst case here.
    """
    _, authority = gfx.load_fixture(FIXTURE)
    with tempfile.TemporaryDirectory(prefix="g33-tile.") as td:
        tmp = Path(td)
        whole = _tiled(tmp, (authority["B"],))
        moved = {p: _tiled(tmp, p) for p in _compositions(authority["B"])
                 if len(p) > 1}
    bad = {p: sorted(k for k in whole if whole[k] != r[k]) for p, r in moved.items()}
    offenders = {p: v for p, v in bad.items() if v}
    assert not offenders, (
        "the final state depends on the tiling: "
        + "; ".join(f"{p} moves {len(v)}/{len(whole)} cells in columns "
                    f"{sorted({k[1] for k in v})}" for p, v in offenders.items()))

