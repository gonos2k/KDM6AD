"""Python ↔ C++ 심볼 parity check.

Walks `kdm6_torch/kdm6/*.py` for Python `*_torch` functions and
`kdm6_libtorch/include/kdm6/*.h` for C++ `*_torch` declarations. Reports
functions that exist in Python but lack a C++ counterpart (codex review #13
권고). Catches the "function entirely missing" bug class that LLM review
silently misses.

Per-function known divergences (e.g., orchestration not yet ported) live in
the EXPECTED_MISSING allowlist below. CI can fail on any new entry.

Usage:
    python parity/symbol_parity.py            # report-only
    python parity/symbol_parity.py --strict   # exit 1 on unexpected gaps
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import NamedTuple


_THIS = Path(__file__).resolve().parent
_PROJ = _THIS.parent
_PY_PKG = _PROJ / "kdm6_torch" / "kdm6"
_CPP_INC = _PROJ / "kdm6_libtorch" / "include" / "kdm6"


# Functions known to be Python-only and intentionally not in C++.
# Each entry is `module.function` (Python module name + function basename).
# Move entries OUT of this set when ported; CI will then enforce parity.
EXPECTED_MISSING = {
    # 모든 F1/F2 phase orchestration C++ 포팅 완료 (Tasks #80-96).
    # 현재 allowlist는 비어 있음 — 새 Python 함수가 추가되면 즉시 unexpected gap으로 발견됨.

    # cloud_dsd helpers — Task #91에서 모두 C++ 포팅 완료. allowlist에 더 이상 없음.

    # Note: thermo.compute_* / coordinator.{state_update,warm_phase,reclassify_*,
    # apply_*} 등은 C++에 동명(또는 _torch 제거 형) 함수가 존재해 자동으로 매치됨.
    # _has_cpp_counterpart()가 suffix 제거 매칭까지 처리.
}


_PY_TORCH_DEF = re.compile(r"^def\s+([a-zA-Z_][a-zA-Z0-9_]*_torch)\s*\(", re.MULTILINE)

# review14#1 fix: tighter C++ matcher — match only declaration-shaped lines.
# A C++ declaration looks roughly like:
#     `[const] [namespace::]Type [&|*] name(` after de-commenting.
# We accept either:
#   (a) bare identifier `name(` at start of a non-comment line (e.g., a function
#       declaration that wraps onto its own line), OR
#   (b) `Type [&|*] name(` (where Type can be `torch::Tensor`, `void`, primitive,
#       `Foo::Bar`, etc.).
# Inline call sites and comments don't match (a) because they're indented + not
# at line start; (b) because there's no preceding type-token.
_CPP_LINE_COMMENT = re.compile(r"//[^\n]*")
_CPP_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
# Identifier at line start, OR identifier preceded by a type-token chain ending
# in space, &, or *.
_CPP_DECL = re.compile(
    r"""
    (?:
      ^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\(   # case (a): bare function name at line start
      |
      (?:[a-zA-Z_][a-zA-Z0-9_:]*[\s&*]+)+ # one or more type-tokens (with separators)
        ([a-zA-Z_][a-zA-Z0-9_]*)\s*\(     # case (b): name following a type chain
    )
    """,
    re.MULTILINE | re.VERBOSE,
)


class FoundFn(NamedTuple):
    module: str
    func: str

    @property
    def qualified(self) -> str:
        return f"{self.module}.{self.func}"


def _scan_python() -> set[FoundFn]:
    found: set[FoundFn] = set()
    for path in sorted(_PY_PKG.glob("*.py")):
        if path.name.startswith("_") or path.name == "__init__.py":
            continue
        module = path.stem
        text = path.read_text()
        for m in _PY_TORCH_DEF.finditer(text):
            found.add(FoundFn(module=module, func=m.group(1)))
    return found


def _scan_cpp() -> set[str]:
    """Return set of C++ function names declared in headers.

    review14#1: Strip comments first, then match only declaration-shaped lines
    (bare `name(` at line start, or `Type [&*] name(` form). This rejects:
      - // comments mentioning a function name
      - /* block comments */
      - inline call sites within other declarations
    Catches actual exported declarations.
    """
    names: set[str] = set()
    for path in sorted(_CPP_INC.glob("*.h")):
        text = path.read_text()
        # Strip block then line comments. (Block first so we don't strip "//" inside /* */.)
        text = _CPP_BLOCK_COMMENT.sub("", text)
        text = _CPP_LINE_COMMENT.sub("", text)
        for m in _CPP_DECL.finditer(text):
            # Either group (case (a) or (b)) is captured; the other is None.
            name = m.group(1) or m.group(2)
            if name:
                names.add(name)
    return names


def _has_cpp_counterpart(py_name: str, cpp_names: set[str]) -> bool:
    """Match Python `name_torch` against C++ `name_torch` *or* `name`."""
    if py_name in cpp_names:
        return True
    if py_name.endswith("_torch") and py_name[:-len("_torch")] in cpp_names:
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 if any Python *_torch function lacks a C++ counterpart "
             "outside the EXPECTED_MISSING allowlist.",
    )
    args = parser.parse_args()

    py = _scan_python()
    cpp = _scan_cpp()

    py_only_names = {f for f in py if not _has_cpp_counterpart(f.func, cpp)}
    unexpected = sorted(
        (f for f in py_only_names if f.qualified not in EXPECTED_MISSING),
        key=lambda f: f.qualified,
    )
    expected_present = sorted(
        (f for f in py_only_names if f.qualified in EXPECTED_MISSING),
        key=lambda f: f.qualified,
    )

    print(f"# Python *_torch functions: {len(py)}")
    print(f"# C++  *_torch declarations: {len(cpp)}")
    print(f"# Python with C++ counterpart: {len(py) - len(py_only_names)}")
    print(f"# Python-only (allowed):     {len(expected_present)}")
    print(f"# Python-only (UNEXPECTED):  {len(unexpected)}")
    print()

    if expected_present:
        print("Allowed Python-only (in EXPECTED_MISSING):")
        for f in expected_present:
            print(f"  - {f.qualified}")
        print()

    if unexpected:
        print("UNEXPECTED Python-only — likely a missing C++ port:")
        for f in unexpected:
            print(f"  ! {f.qualified}")
        print()
        if args.strict:
            print("FAIL: unexpected gaps. Either port the function or add to EXPECTED_MISSING.")
            return 1

    print("OK." if not unexpected else "WARN: unexpected gaps (re-run with --strict to enforce).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
