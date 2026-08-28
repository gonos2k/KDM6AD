#!/usr/bin/env python3
"""Two things public CI can do without the private data, and one of them would
have caught a live NameError.

`FINDING_ci_dark_surface_v1` measured that six harness modules have no
CI-visible test and said the skips are not fixable in this CI as configured.
That is true of the FORTRAN INTEGRATION. It is not true of the Python contract:
`where_the_number_is()` shipped referencing two names that exist only in a
different function, so it raised `NameError` on any state with a non-empty
number population, and nothing anywhere noticed. A synthetic-array smoke test
and a scope-aware name check both catch it, and neither needs a byte of the
reference tree.
"""
import ast
import builtins
import sys
import types
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_number_basis as nb           # noqa: E402

BUILT = set(dir(builtins)) | {"__file__", "__name__", "__doc__", "__spec__",
                              "__package__", "__loader__", "__builtins__"}


# ── a name that is not bound in any enclosing scope ──────────────────────────

def _bound_here(node):
    out = set()
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        a = node.args
        for x in a.args + a.posonlyargs + a.kwonlyargs:
            out.add(x.arg)
        if a.vararg:
            out.add(a.vararg.arg)
        if a.kwarg:
            out.add(a.kwarg.arg)
    stack = list(ast.iter_child_nodes(node))
    while stack:
        n = stack.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(n.name)
            continue                                    # a scope of its own
        if isinstance(n, ast.Lambda):
            continue
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            out.add(n.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for al in n.names:
                out.add((al.asname or al.name).split(".")[0])
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            out |= set(n.names)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            out.add(n.name)
        stack.extend(ast.iter_child_nodes(n))
    return out


def _loads_here(node):
    out, stack = [], list(ast.iter_child_nodes(node))
    while stack:
        n = stack.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                          ast.ClassDef, ast.Lambda)):
            continue
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            out.append((n.id, n.lineno))
        stack.extend(ast.iter_child_nodes(n))
    return out


def _undefined(path):
    hits = []

    def walk(node, enclosing):
        here = _bound_here(node) | enclosing
        for name, ln in _loads_here(node):
            if name not in here and name not in BUILT:
                hits.append((ln, getattr(node, "name", "<module>"), name))
        # DIRECT children only, then descend through non-scope nodes. Walking
        # every descendant from here would hand a nested function the OUTER
        # scope instead of its own enclosing one, and call every closed-over
        # name undefined.
        def descend(n, scope):
            for child in ast.iter_child_nodes(n):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                      ast.ClassDef)):
                    walk(child, scope)
                else:
                    descend(child, scope)

        descend(node, here)

    walk(ast.parse(Path(path).read_text()), set())
    return sorted(set(hits))


def test_this_checker_is_narrower_than_ruff_and_says_so(tmp_path):
    """What this check does NOT cover, measured rather than assumed.

    It caught the `NameError` that shipped, and it misses three things `ruff
    F821` catches -- a name only a lambda body reads, a method reading a CLASS
    attribute as if it were enclosing scope, and a comprehension target used
    after the comprehension. All three were probed and all three came back
    clean here, which is why `ruff --select F821` is now a CI step and this
    stays as the regression test for the one case it was written for.
    """
    probes = {
        "lambda": "f = lambda: missing_in_lambda\n",
        "class_scope": "class A:\n    x = 1\n    def f(self):\n        return x\n",
        "comprehension": "def g(xs):\n    ys = [q for q in xs]\n    return q\n",
    }
    missed = []
    for name, src in probes.items():
        tmp = tmp_path / f"_gap_{name}.py"
        tmp.write_text(src)
        try:
            if not _undefined(tmp):
                missed.append(name)
        finally:
            tmp.unlink(missing_ok=True)
    assert sorted(missed) == ["class_scope", "comprehension", "lambda"], (
        f"the gaps moved: {missed}. If this checker got wider, say so; if it "
        f"got narrower, that is a regression.")


def test_the_local_checker_finds_plain_scope_undefined_names():
    """`where_the_number_is` referenced `keep` and `finite`, which are bound in
    `report()`. A non-unique string replacement put one function's census into
    another, and the only way to reach it was to run the function on real data
    -- which CI cannot do, and which nothing else did either."""
    bad = []
    # EVERY module, which the two globs this started with were not. They
    # covered 54 of the 65 files in harness/ and the docstring said "every
    # harness module" -- a claim wider than the code, which is the shape of
    # mistake this file exists to catch. The eleven that were missed scan
    # clean, so nothing was hidden; the wording was still wrong.
    for p in sorted(list(ROOT.glob("*.py"))
                    + list((ROOT / "g33_fortran").glob("*.py"))
                    + list((ROOT / "g33_overlay").glob("*.py"))):
        for ln, fn, name in _undefined(p):
            bad.append(f"{p.name}:{ln} {fn}(): {name!r}")
    assert not bad, "undefined name(s):\n  " + "\n  ".join(bad)


def test_the_name_check_actually_fires(tmp_path):
    """A check that never fails is not a check."""
    src = "def f(a):\n    return a + b\n"
    tmp = tmp_path / "_undef_probe.py"
    tmp.write_text(src)
    try:
        assert _undefined(tmp) == [(2, "f", "b")]
    finally:
        tmp.unlink(missing_ok=True)


def test_the_name_check_does_not_fire_on_a_closure(tmp_path):
    """The naive version called every closed-over name undefined."""
    src = ("def outer():\n"
           "    x = 1\n"
           "    def inner():\n"
           "        return x\n"
           "    return inner()\n")
    tmp = tmp_path / "_closure_probe.py"
    tmp.write_text(src)
    try:
        assert _undefined(tmp) == []
    finally:
        tmp.unlink(missing_ok=True)


# ── the function itself, on synthetic arrays ─────────────────────────────────

class _Var:
    def __init__(self, a):
        self._a = np.asarray(a)
        self.shape = self._a.shape

    def __getitem__(self, k):
        return self._a[k]


class _Ds:
    def __init__(self, spec):
        self.variables = dict(spec)

    def __getitem__(self, k):
        return self.variables[k]


def _fake_state(monkeypatch, number, legacy_dry, armn_dry, mass):
    """Drive the function without netCDF4 or a forecast file."""
    ds = _Ds({"QNRAIN": _Var(np.asarray(number)[None, ...])})
    fake = types.SimpleNamespace(Dataset=lambda _path: ds)
    monkeypatch.setitem(sys.modules, "netCDF4", fake)
    monkeypatch.setattr(nb, "profile", lambda *a, **k: {
        "dry_layer_mass_upper": np.asarray(mass),
        "legacy_moist": np.asarray(legacy_dry),
        "legacy_dry": np.asarray(legacy_dry),
        "armn_dry": np.asarray(armn_dry),
    })


def test_it_runs_at_all_on_a_populated_column(monkeypatch):
    """It did not: `NameError: name 'keep' is not defined`, on every state whose
    number population is non-empty."""
    K = 5
    _fake_state(monkeypatch,
                number=np.full((K, 1, 1), 2.0),
                legacy_dry=np.full((K - 1, 1, 1), 0.10),
                armn_dry=np.full((K - 1, 1, 1), 0.02),
                mass=np.full((K - 1, 1, 1), 3.0))
    out = nb.where_the_number_is(Path("synthetic"))
    assert out["armn_residual_fraction"]["median"] == pytest.approx(0.2)
    assert out["armn_residual_fraction"]["valid_interfaces"] == 4


def test_an_empty_number_population_returns_early(monkeypatch):
    K = 5
    _fake_state(monkeypatch,
                number=np.zeros((K, 1, 1)),
                legacy_dry=np.full((K - 1, 1, 1), 0.10),
                armn_dry=np.full((K - 1, 1, 1), 0.02),
                mass=np.full((K - 1, 1, 1), 3.0))
    assert nb.where_the_number_is(Path("synthetic")).get("empty") is True


def test_a_nonfinite_interface_is_excluded_and_counted(monkeypatch):
    """The census must be over the population it describes -- which is the
    defect that produced the NameError in the first place."""
    K = 5
    legacy = np.full((K - 1, 1, 1), 0.10)
    legacy[0] = np.nan
    _fake_state(monkeypatch,
                number=np.full((K, 1, 1), 2.0),
                legacy_dry=legacy,
                armn_dry=np.full((K - 1, 1, 1), 0.02),
                mass=np.full((K - 1, 1, 1), 3.0))
    out = nb.where_the_number_is(Path("synthetic"))
    r = out["armn_residual_fraction"]
    assert r["population_interfaces"] == 4
    assert r["valid_interfaces"] == 3
    assert r["nonfinite_excluded"] == 1
    assert np.isfinite(r["median"])


def test_every_population_reports_what_it_dropped(monkeypatch):
    K = 4
    armn = np.full((K - 1, 1, 1), 0.02)
    armn[1] = np.inf
    _fake_state(monkeypatch,
                number=np.full((K, 1, 1), 2.0),
                legacy_dry=np.full((K - 1, 1, 1), 0.10),
                armn_dry=armn,
                mass=np.full((K - 1, 1, 1), 3.0))
    out = nb.where_the_number_is(Path("synthetic"))
    assert out["nonfinite_interfaces"] == 1
    for name, pop in out["populations"].items():
        assert pop["population_interfaces"] >= pop["valid_interfaces"], name
        assert pop["nonfinite_excluded"] == 1, name


def test_an_upper_populated_front_is_not_thrown_away_as_empty(monkeypatch):
    """`upper_populated` exists because an interface whose UPPER cell carries
    number and whose lower cell is empty is transport-active -- sedimentation
    moves number downward. Returning `empty` on `occupied_pair` alone discarded
    exactly those, which is the front the second population was added to see."""
    K = 5
    n = np.zeros((K, 1, 1))
    n[3:] = 2.0                        # loaded above, empty below: a front
    _fake_state(monkeypatch, number=n,
                legacy_dry=np.full((K - 1, 1, 1), 0.10),
                armn_dry=np.full((K - 1, 1, 1), 0.02),
                mass=np.full((K - 1, 1, 1), 3.0))
    out = nb.where_the_number_is(Path("synthetic"))
    assert out.get("empty") is not True, "the front was discarded as empty"
    assert out["populations"]["upper_populated"]["valid_interfaces"] > 0
    assert out["populations"]["occupied_pair"]["valid_interfaces"] >= 0


def test_a_genuinely_empty_field_still_returns_empty(monkeypatch):
    """Widening the early return must not remove it."""
    K = 5
    _fake_state(monkeypatch, number=np.zeros((K, 1, 1)),
                legacy_dry=np.full((K - 1, 1, 1), 0.10),
                armn_dry=np.full((K - 1, 1, 1), 0.02),
                mass=np.full((K - 1, 1, 1), 3.0))
    assert nb.where_the_number_is(Path("synthetic")).get("empty") is True


def test_a_nonfinite_number_cell_is_counted_not_silently_dropped(monkeypatch):
    """`n > 0` is False at a NaN, so a broken number cell used to leave every
    population without appearing in any census (owner review 6.2)."""
    K = 5
    n = np.full((K, 1, 1), 2.0)
    n[2] = np.nan
    _fake_state(monkeypatch, number=n,
                legacy_dry=np.full((K - 1, 1, 1), 0.10),
                armn_dry=np.full((K - 1, 1, 1), 0.02),
                mass=np.full((K - 1, 1, 1), 3.0))
    out = nb.where_the_number_is(Path("synthetic"))
    assert out["nonfinite_number_interfaces"] == 2      # k=2 bounds two interfaces
    assert out["nonfinite_interfaces"] >= 2


def test_negative_number_cells_are_reported(monkeypatch):
    """The real ten-minute forecast carries 97 negative QNRAIN cells. A number
    concentration below zero is not a measurement; it should be visible."""
    K = 4
    n = np.full((K, 1, 1), 2.0)
    n[1] = -1.0
    _fake_state(monkeypatch, number=n,
                legacy_dry=np.full((K - 1, 1, 1), 0.10),
                armn_dry=np.full((K - 1, 1, 1), 0.02),
                mass=np.full((K - 1, 1, 1), 3.0))
    assert nb.where_the_number_is(Path("synthetic"))["negative_number_cells"] == 1


def test_a_zero_legacy_denominator_leaves_the_ratio(monkeypatch):
    """Flooring it at 1e-300 turned an interface with no legacy defect into an
    enormous finite ratio and put it in the median (owner review 6.3)."""
    K = 4
    legacy = np.full((K - 1, 1, 1), 0.10)
    legacy[0] = 0.0
    _fake_state(monkeypatch, number=np.full((K, 1, 1), 2.0),
                legacy_dry=legacy, armn_dry=np.full((K - 1, 1, 1), 0.02),
                mass=np.full((K - 1, 1, 1), 3.0))
    out = nb.where_the_number_is(Path("synthetic"))
    pop = out["populations"]["occupied_pair"]
    assert pop["zero_legacy_denominator"] == 1
    assert pop["ratio_interfaces"] == pop["valid_interfaces"] - 1
    assert pop["median"] == pytest.approx(0.2)     # not 2e+298


# ── ruff is the authority, so the contract is on RUFF, not on my checker ─────

RUFF_PROBES = [
    ("lambda body", "f = lambda: missing_in_lambda\n", "F821"),
    ("class scope", "class A:\n    x = 1\n    def f(self):\n        return x\n", "F821"),
    ("comprehension target", "def g(xs):\n    ys = [q for q in xs]\n    return q\n", "F821"),
    ("read before assignment", "def h():\n    y = x\n    x = 1\n    return y\n", "F821"),
    ("undefined export", '__all__ = ["nope"]\n', "F822"),
]


@pytest.mark.parametrize("what, source, code",
                         RUFF_PROBES, ids=[p[0] for p in RUFF_PROBES])
def test_ruff_catches_the_name_failures_ci_relies_on(tmp_path, what, source, code):
    """The CI step's contract, pinned against ruff ITSELF.

    The other tests here pin what the hand-written checker MISSES. That is not
    the same contract: ruff runs before pytest, over the repository only, so
    these probes never reach it and nothing would notice if the rule selection
    narrowed, the command lost a flag, or ruff stopped being installed.

    This runs ruff exactly as the workflow does. Skipped where ruff is absent,
    which is how a developer machine without it reads -- not as a pass.
    """
    import subprocess
    probe = tmp_path / "probe.py"
    probe.write_text(source, encoding="utf-8")
    try:
        r = subprocess.run(
            [sys.executable, "-m", "ruff", "--isolated", "check",
             "--select", "F821,F822,F823", "--no-cache", str(probe)],
            text=True, capture_output=True, check=False)
    except OSError:                                     # pragma: no cover
        pytest.skip("ruff is not installed here")
    if "No module named ruff" in (r.stderr or ""):
        pytest.skip("ruff is not installed here")
    out = r.stdout + r.stderr
    assert r.returncode == 1, f"ruff accepted {what}:\n{out}"
    assert code in out, f"ruff reported something other than {code} for {what}:\n{out}"


def test_the_harness_is_clean_under_the_selection_ci_uses(tmp_path):
    """And the same command, on the real tree, the way CI runs it."""
    import subprocess
    try:
        r = subprocess.run(
            [sys.executable, "-m", "ruff", "--isolated", "check",
             "--select", "F821,F822,F823", "--no-cache",
             "--no-respect-gitignore", str(ROOT)],
            text=True, capture_output=True, check=False)
    except OSError:                                     # pragma: no cover
        pytest.skip("ruff is not installed here")
    if "No module named ruff" in (r.stderr or ""):
        pytest.skip("ruff is not installed here")
    assert r.returncode == 0, (r.stdout + r.stderr)


def test_an_empty_ratio_population_is_a_verdict_not_an_IndexError(monkeypatch):
    """`valid.any()` was asked and `ratio.any()` was not. A column whose every
    valid interface has `legacy_dry == 0` reached `np.median` on an empty array
    and raised `IndexError: cannot do a non-empty take from an empty axes`
    (owner review 9). The two populations are different sizes and only one of
    them can carry a median."""
    K = 4
    _fake_state(monkeypatch, number=np.full((K, 1, 1), 2.0),
                legacy_dry=np.zeros((K - 1, 1, 1)),
                armn_dry=np.full((K - 1, 1, 1), 0.02),
                mass=np.full((K - 1, 1, 1), 3.0))
    out = nb.where_the_number_is(Path("synthetic"))
    for name, pop in out["populations"].items():
        assert pop["ratio_interfaces"] == 0, name
        assert pop.get("empty_ratio") is True, name
        assert "median" not in pop, f"{name} reported a median over nothing"
    r = out["armn_residual_fraction"]
    assert r["ratio_interfaces"] == 0 and r.get("empty_ratio") is True
    assert "median" not in r


def test_a_partly_zero_denominator_still_reports_over_what_is_left(monkeypatch):
    """The guard must not swallow a population that has SOME usable ratios."""
    K = 4
    legacy = np.full((K - 1, 1, 1), 0.10)
    legacy[0] = 0.0
    _fake_state(monkeypatch, number=np.full((K, 1, 1), 2.0),
                legacy_dry=legacy, armn_dry=np.full((K - 1, 1, 1), 0.02),
                mass=np.full((K - 1, 1, 1), 3.0))
    pop = nb.where_the_number_is(Path("synthetic"))["populations"]["occupied_pair"]
    assert pop["zero_legacy_denominator"] == 1
    assert pop["ratio_interfaces"] == pop["valid_interfaces"] - 1
    assert pop["median"] == pytest.approx(0.2)
    assert "empty_ratio" not in pop
