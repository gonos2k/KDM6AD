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


def test_no_harness_module_loads_a_name_nothing_binds():
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


def test_the_name_check_actually_fires():
    """A check that never fails is not a check."""
    src = "def f(a):\n    return a + b\n"
    tmp = ROOT / "tests" / "_undef_probe.py"
    tmp.write_text(src)
    try:
        assert _undefined(tmp) == [(2, "f", "b")]
    finally:
        tmp.unlink(missing_ok=True)


def test_the_name_check_does_not_fire_on_a_closure():
    """The naive version called every closed-over name undefined."""
    src = ("def outer():\n"
           "    x = 1\n"
           "    def inner():\n"
           "        return x\n"
           "    return inner()\n")
    tmp = ROOT / "tests" / "_closure_probe.py"
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
