#!/usr/bin/env python3
"""PR1-B2 fresh-process contract: the shipped dylib must NOT inject
KMP_DUPLICATE_LIB_OK. In a fresh process, loading the library leaves an UNSET
value unset and preserves an explicit FALSE/TRUE. Also asserts the 9 C ABI
symbols resolve and the ABI version is 2.

usage: check_kmp_duplicate_env.py <path-to libkdm6_c .dylib/.so>
"""
import ctypes
import os
import subprocess
import sys

LIB = os.path.abspath(sys.argv[1])

# Read the *effective* env via libc getenv (not Python's cached os.environ), after
# the dylib's constructor has run, in a fresh child process per state.
_PROBE = r"""
import ctypes, sys
libc = ctypes.CDLL(None)
libc.getenv.argtypes = [ctypes.c_char_p]; libc.getenv.restype = ctypes.c_char_p
ctypes.CDLL(sys.argv[1])
v = libc.getenv(b"KMP_DUPLICATE_LIB_OK")
sys.stdout.write("" if v is None else "SET:" + v.decode())
"""

NINE = [
    "kdm6_step_c", "kdm6_step_ad_c", "kdm6_step_v2_c", "kdm6_get_abi_version_c",
    "kdm6_step_v2_args_size_c", "kdm6_handle_vjp_c", "kdm6_handle_jvp_c",
    "kdm6_handle_close_c", "kdm6_handle_closep_c",
]


def after_load(parent_value):
    env = dict(os.environ)
    env.pop("KMP_DUPLICATE_LIB_OK", None)
    if parent_value is not None:
        env["KMP_DUPLICATE_LIB_OK"] = parent_value
    out = subprocess.run([sys.executable, "-c", _PROBE, LIB],
                         env=env, capture_output=True, text=True, check=True).stdout.strip()
    return None if out == "" else out[len("SET:"):]


def main():
    failures = []
    # 1. fresh-process env contract: UNSET stays unset; FALSE/TRUE preserved.
    for name, parent, expect in [("UNSET", None, None), ("FALSE", "FALSE", "FALSE"), ("TRUE", "TRUE", "TRUE")]:
        got = after_load(parent)
        ok = got == expect
        print(f"  {name}: parent={parent!r} after_load={got!r} expect={expect!r} {'OK' if ok else 'FAIL'}")
        if not ok:
            failures.append(name)
    # 2. the 9 C ABI symbols resolve, ABI version == 2.
    lib = ctypes.CDLL(LIB)
    for s in NINE:
        try:
            getattr(lib, s)
        except AttributeError:
            print(f"  symbol {s}: MISSING")
            failures.append(f"symbol:{s}")
    lib.kdm6_get_abi_version_c.restype = ctypes.c_int
    ver = lib.kdm6_get_abi_version_c()
    print(f"  abi_version={ver} (want 2) {'OK' if ver == 2 else 'FAIL'}")
    if ver != 2:
        failures.append("abi_version")

    if failures:
        print("FAIL:", ", ".join(failures))
        return 1
    print("OK: fresh-process KMP env contract + 9 symbols + abi==2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
