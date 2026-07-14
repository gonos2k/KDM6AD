#!/usr/bin/env python3
"""PR3 symbol-surface gate (docs/PR3_VISIBILITY_DESIGN.md §7).

Assert a built libkdm6_c exports EXACTLY the 9 C ABI functions and leaks zero
internal (kdm6::/libtorch/std) symbols. `nm` gives the same `addr TYPE name`
output on both platforms, so one parser covers both:

    macOS : nm -gU              (external, defined)
    Linux : nm -D --defined-only (dynamic, defined)

We collect EVERY defined external symbol regardless of nm type — not just code
(`T`/`W`) but data / RTTI / vtable (`D`/`B`/`R`/`V`/`S`) and even a global
absolute (`A`) — so an accidental non-function export is caught, not silently
filtered out. The ONLY exclusion is the Linux `--version-script` node
(`KDM6_2`), removed BY NAME (not by skipping the whole absolute class, which
would also hide a genuine absolute leak). Per-platform quirks normalized: the
macOS leading underscore (`_kdm6_step_c`) and the Linux version suffix
(`kdm6_step_c@@KDM6_2`). Comparing the exported set for exact equality with the 9
IS the zero-leak check: any leaked symbol makes the set differ.

Usage: check_c_abi_exports.py <libkdm6_c.{dylib,so,so.N}>   (exit 0 iff == the 9)
"""
import platform
import subprocess
import sys

# The entire public surface — must match kdm6_c_api.h and the linker allowlists
# (kdm6_c.exports / kdm6_c.map). Growing this set requires a separate approval.
ALLOW = {
    "kdm6_step_c", "kdm6_step_ad_c", "kdm6_step_v2_c",
    "kdm6_get_abi_version_c", "kdm6_step_v2_args_size_c",
    "kdm6_handle_vjp_c", "kdm6_handle_jvp_c",
    "kdm6_handle_close_c", "kdm6_handle_closep_c",
}

# The Linux --version-script node (kdm6_c.map). When nm surfaces it, it is a
# verdef label, not a real export, so it is excluded BY NAME — never by skipping
# the whole absolute class, which would also hide a genuine absolute leak.
VERSION_NODE = "KDM6_2"


def exported_symbols(lib):
    """Every defined external symbol in `lib` (any type), normalized.

    All types are collected — code (`T`/`W`), data / RTTI / vtable
    (`D`/`B`/`R`/`V`/`S`), and a global absolute (`A`) — so any leak is caught.
    The sole exclusion is the version-script node `KDM6_2`, removed by name.
    """
    system = platform.system()
    if system == "Darwin":
        cmd, strip_underscore = ["nm", "-gU", lib], True
    elif system == "Linux":
        cmd, strip_underscore = ["nm", "-D", "--defined-only", lib], False
    else:
        sys.exit(f"unsupported platform {system!r} (PR3 targets macOS/Linux)")

    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    names = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue                          # undefined / verdef rows (no address)
        name = parts[2]
        name = name.split("@", 1)[0]          # drop Linux @@KDM6_2 version suffix
        if strip_underscore and name.startswith("_"):
            name = name[1:]                   # drop the macOS leading underscore
        if name == VERSION_NODE:              # verdef label, not a real export
            continue
        names.add(name)
    return names


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: check_c_abi_exports.py <lib>")
    lib = sys.argv[1]
    exported = exported_symbols(lib)
    missing = sorted(ALLOW - exported)
    leaked = sorted(exported - ALLOW)

    print(f"[check_c_abi_exports] {lib}: {len(exported)} exported (want {len(ALLOW)})")
    for s in missing:
        print(f"  MISSING  {s}")
    for s in leaked:
        print(f"  LEAKED   {s}")
    if missing or leaked:
        sys.exit("FAIL: exported surface is not exactly the 9 C ABI functions")
    print("OK: exported set == the 9 C ABI symbols, zero internal leakage")


if __name__ == "__main__":
    main()
