#!/usr/bin/env python3
"""PR3 symbol-surface gate (docs/PR3_VISIBILITY_DESIGN.md §7).

Assert a built libkdm6_c exports EXACTLY the 9 C ABI functions and leaks zero
internal (kdm6::/libtorch/std) symbols. `nm` gives the same `addr TYPE name`
output on both platforms, so one parser covers both:

    macOS : nm -gU              (external, defined)
    Linux : nm -D --defined-only (dynamic, defined)

We collect EVERY defined external symbol regardless of nm type — not just code
(`T`/`W`) but data / RTTI / vtable (`D`/`B`/`R`/`V`/`S`) too — so an accidental
non-function export would also be caught, not silently filtered out. The only
things skipped are absolute (`A`/`a`) entries, i.e. the Linux `--version-script`
node (`KDM6_2`), which is not a real export. Per-platform quirks normalized: the
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


def exported_symbols(lib):
    """Every defined external symbol in `lib` (any type), normalized.

    Collecting all types — not just code (`T`/`W`) — means a leaked data / RTTI /
    vtable symbol is caught too. Only absolute (`A`/`a`) entries are skipped: the
    Linux `--version-script` node (`KDM6_2`) is absolute and is not an export.
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
            continue                          # undefined / version-node rows (no address)
        kind, name = parts[1], parts[2]
        if kind in ("A", "a"):                # absolute (Linux version node), not an export
            continue
        name = name.split("@", 1)[0]          # drop Linux @@KDM6_2 version suffix
        if strip_underscore and name.startswith("_"):
            name = name[1:]                   # drop the macOS leading underscore
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
