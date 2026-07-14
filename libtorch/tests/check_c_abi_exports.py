#!/usr/bin/env python3
"""PR3 symbol-surface gate (docs/PR3_VISIBILITY_DESIGN.md §7).

Assert that a built ``libkdm6_c`` exports EXACTLY the 9 C ABI functions and
leaks ZERO internal (kdm6::/libtorch/std) symbols. Cross-platform: macOS
(``nm -gU``) and Linux (``readelf --dyn-syms``), applying the toolchain-specific
normalization the design doc requires (on Linux the ``--version-script`` stamps
``kdm6_step_c@@KDM6_2``, so the suffix and the ``KDM6_2`` version-node entry must
be normalized away before comparing).

Because the exported set is compared for EXACT equality with the allowlist, any
non-listed symbol (i.e. any internal leak) makes the set differ and fails — the
exact-set check IS the zero-leak assertion.

Usage: ``check_c_abi_exports.py <path-to-libkdm6_c.{dylib,so,so.N}>``
Exit 0 iff the exported surface is exactly the 9 C ABI symbols.
"""
import platform
import re
import subprocess
import sys

# The entire public surface — must match kdm6_c_api.h and the linker allowlists
# (kdm6_c.exports / kdm6_c.map). Growing this set requires a separate approval.
ALLOW = {
    "kdm6_step_c",
    "kdm6_step_ad_c",
    "kdm6_step_v2_c",
    "kdm6_get_abi_version_c",
    "kdm6_step_v2_args_size_c",
    "kdm6_handle_vjp_c",
    "kdm6_handle_jvp_c",
    "kdm6_handle_close_c",
    "kdm6_handle_closep_c",
}


def _run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def macos_exports(lib):
    """External DEFINED symbols on macOS (``nm -gU``); strip the leading '_'."""
    syms = set()
    for line in _run(["nm", "-gU", lib]).splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        name = parts[2]
        syms.add(name[1:] if name.startswith("_") else name)
    return syms


def linux_exports(lib):
    """Externally-visible defined FUNCTIONS in ``.dynsym`` (readelf --dyn-syms).

    Per design §7: strip ``@@VER`` / ``@VER``, drop the version-node entry, and
    keep only GLOBAL/WEAK + DEFAULT-visibility + DEFINED FUNC symbols.
    """
    syms = set()
    for line in _run(["readelf", "--dyn-syms", "--wide", lib]).splitlines():
        # Num:  Value  Size  Type  Bind  Vis  Ndx  Name
        m = re.match(
            r"\s*\d+:\s+[0-9a-fA-F]+\s+\d+\s+(\w+)\s+(\w+)\s+(\w+)\s+(\S+)\s+(\S+)",
            line,
        )
        if not m:
            continue
        typ, bind, vis, ndx, name = m.groups()
        if typ != "FUNC" or bind not in ("GLOBAL", "WEAK") or vis != "DEFAULT":
            continue
        if ndx == "UND":  # undefined = imported, not an export
            continue
        name = re.split(r"@+", name)[0]  # kdm6_step_c@@KDM6_2 -> kdm6_step_c
        if name and name != "KDM6_2":    # never the version-node label itself
            syms.add(name)
    return syms


def _demangle(names):
    """Best-effort c++filt for readable failure output (never gates)."""
    if not names:
        return {}
    try:
        out = _run(["c++filt"] + list(names))
        return dict(zip(names, out.splitlines()))
    except Exception:
        return {n: n for n in names}


def main():
    if len(sys.argv) != 2:
        print("usage: check_c_abi_exports.py <lib>", file=sys.stderr)
        return 2
    lib = sys.argv[1]
    system = platform.system()
    if system == "Darwin":
        exported = macos_exports(lib)
    elif system == "Linux":
        exported = linux_exports(lib)
    else:
        print(f"unsupported platform {system!r} (PR3 targets macOS/Linux)",
              file=sys.stderr)
        return 2

    missing = ALLOW - exported
    unexpected = exported - ALLOW  # anything here is an internal leak

    print(f"[check_c_abi_exports] {lib}")
    print(f"  platform : {system}")
    print(f"  exported : {len(exported)} symbol(s)  (allowlist: {len(ALLOW)})")

    if missing:
        print("  MISSING (must be exported but absent):")
        for s in sorted(missing):
            print(f"    - {s}")
    if unexpected:
        demangled = _demangle(sorted(unexpected))
        print(f"  UNEXPECTED / leaked ({len(unexpected)}), first 25:")
        for s in sorted(unexpected)[:25]:
            print(f"    + {demangled.get(s, s)}")
        if len(unexpected) > 25:
            print(f"    ... and {len(unexpected) - 25} more")

    if not missing and not unexpected:
        print("  OK: exported set == the 9 C ABI symbols, zero internal leakage")
        return 0
    print("  FAIL: exported surface is not exactly the 9 C ABI symbols")
    return 1


if __name__ == "__main__":
    sys.exit(main())
