"""Fail-closed Darwin process-group sampling; not an OS memory limit.

All calls may block in the kernel or psutil. Run this provider in a separately
supervised helper with an external deadline; its local deadline is not a hard
execution bound. A complete group cannot be inferred between samples.
"""

import ctypes
import hashlib
import importlib
import sys
import os
import time
from pathlib import Path

RSS_POLICY = "SAMPLED_STOP_THRESHOLD"
PSUTIL_VERSION = "5.9.4"
PSUTIL_SHA256 = {
    "__init__.py": "dd432804c19d3e01bf961a678e7bc119279ec82a5ca0540e7d3e4bbe0b12bb99",
    "_psutil_osx.abi3.so": "f9d2715fb1de8c0218bacec13269ee6eb5d7bb7a9c694474000e1ab001943096",
    "_psutil_posix.abi3.so": "5f0f4fcfb5277cdb1daec18bd4053efc62eeb6258eca5b70d81e2f2e657ad1e0",
}


class CensusError(RuntimeError):
    pass


def require(ok, message):
    if not ok:
        raise CensusError(message)


def read_group(
    list_pids, pgid, deadline, *, clock=time.monotonic, initial=32, maximum=4096
):
    """list_pids(pgid, capacity) -> (returned byte count, sequence of PIDs)."""
    require(type(pgid) is int and pgid > 0, "invalid group")
    require(
        type(initial) is int and type(maximum) is int and 0 < initial <= maximum,
        "capacity",
    )
    size = initial
    while True:
        require(clock() < deadline, "census deadline")
        nbytes, pids = list_pids(pgid, size)
        require(clock() < deadline, "census deadline")
        require(
            type(nbytes) is int and nbytes >= 0 and nbytes % 4 == 0,
            "invalid byte count",
        )
        require(
            nbytes <= size * 4 and len(pids) == nbytes // 4, "malformed census size"
        )
        if nbytes == size * 4:
            require(size < maximum, "census full or truncated")
            size = min(maximum, size * 2)
            continue
        require(all(type(p) is int and p > 0 for p in pids), "invalid PID")
        require(len(pids) == len(set(pids)), "duplicate PID")
        require(pgid in pids, "reserved leader missing")
        return tuple(sorted(pids))


def sample_group(provider, request, deadline, *, clock=time.monotonic):
    """Sibling-helper census. Parent must bracket this with its own WNOWAIT checks.

    request carries leader_pid, leader_start, leader_state and request_id. The
    helper echoes these fields; it cannot authenticate parent-held reservation.
    The parent must reject a changed/missing response or reservation state.
    """
    leader = request["leader_pid"]
    leader_start = request["leader_start"]
    state = request["leader_state"]
    request_id = request["request_id"]
    require(type(leader) is int and leader > 0, "leader PID")
    require(leader_start is not None, "missing leader start identity")
    require(state in ("alive", "exited_reserved"), "leader state")
    require(isinstance(request_id, str) and bool(request_id), "request identity")
    first = read_group(provider.list_group, leader, deadline, clock=clock)
    observed = {}
    for pid in first:
        if pid == leader and state == "exited_reserved":
            continue
        require(clock() < deadline, "census deadline")
        start, pgid, rss = provider.inspect(pid)
        require(
            start is not None and type(pgid) is int and pgid == leader, "identity/group"
        )
        require(type(rss) is int and rss >= 0, "RSS")
        if pid == leader:
            require(start == leader_start, "leader start identity")
        observed[pid] = (start, pgid, rss)
    second = read_group(provider.list_group, leader, deadline, clock=clock)
    require(first == second, "group membership churn")
    for pid, (start, pgid, _) in observed.items():
        require(clock() < deadline, "census deadline")
        later_start, later_pgid, later_rss = provider.inspect(pid)
        require((later_start, later_pgid) == (start, pgid), "PID identity churn")
        require(type(later_rss) is int and later_rss >= 0, "RSS")
        observed[pid] = (start, pgid, max(observed[pid][2], later_rss))
    require(clock() < deadline, "census deadline")
    return {
        "request": dict(request),
        "policy": RSS_POLICY,
        "members": first,
        "rss_bytes": sum(x[2] for x in observed.values()),
        "scope": "sampled group RSS; parent reservation must bracket helper",
    }


def parent_reservation(leader, leader_start, inspect):
    """Run only in the direct parent; WNOWAIT retains the child PID reservation."""
    require(
        type(leader) is int and leader > 0 and leader_start is not None,
        "leader identity",
    )
    libc = ctypes.CDLL(None, use_errno=True)
    libc.waitid.argtypes = (ctypes.c_int, ctypes.c_uint, ctypes.c_void_p, ctypes.c_int)
    libc.waitid.restype = ctypes.c_int
    buf = ctypes.create_string_buffer(512)
    ctypes.set_errno(0)
    if libc.waitid(os.P_PID, leader, buf, os.WEXITED | os.WNOWAIT | os.WNOHANG):
        raise CensusError("parent waitid failed: errno " + str(ctypes.get_errno()))
    observed_pid = ctypes.c_int.from_buffer(buf, 12).value
    require(observed_pid in (0, leader), "unexpected waitid child")
    if observed_pid == leader:
        return "exited_reserved"
    start, group, _ = inspect(leader)
    require(start == leader_start and group == leader, "live leader identity")
    return "alive"


def verify_package(package, expected_manifest):
    """Hash the caller-pinned full .py/.so inventory before importing psutil."""
    require(
        isinstance(package, Path)
        and package.is_absolute()
        and package == package.resolve(),
        "resolved package path",
    )
    require(package.is_dir() and package.name == "psutil", "package directory")
    require(
        isinstance(expected_manifest, dict) and bool(expected_manifest),
        "missing pinned package inventory",
    )
    found = {}

    def scan_error(error):
        raise CensusError("psutil tree traversal failed") from error

    for directory, dirs, files in os.walk(
        package, topdown=True, followlinks=False, onerror=scan_error
    ):
        for name in dirs + files:
            path = Path(directory) / name
            require(not path.is_symlink(), "symlink in psutil tree")
            require(
                name != "__pycache__" and path.suffix != ".pyc",
                "cached bytecode in psutil tree",
            )
        for name in files:
            path = Path(directory) / name
            if path.suffix not in (".py", ".so"):
                continue
            require(path.is_file(), "nonregular psutil file")
            found[path.relative_to(package).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    require(found == expected_manifest, "psutil package inventory/hash")
    for filename, expected in PSUTIL_SHA256.items():
        require(found.get(filename) == expected, "psutil pinned asset: " + filename)
    return found


class DarwinProvider:
    """Native provider. Construct only in the isolated, externally bounded helper."""

    def __init__(self, package, expected_manifest):
        verify_package(package, expected_manifest)
        require(
            not any(k == "psutil" or k.startswith("psutil.") for k in sys.modules),
            "psutil already imported",
        )
        sys.path.insert(0, str(package.parent))
        old_dont_write = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        try:
            psutil = importlib.import_module("psutil")
        finally:
            sys.dont_write_bytecode = old_dont_write
            sys.path.pop(0)
        require(psutil.__version__ == PSUTIL_VERSION, "unsupported psutil version")
        require(
            Path(psutil.__file__).resolve() == package / "__init__.py",
            "imported psutil path",
        )
        for name, module in tuple(sys.modules.items()):
            if name != "psutil" and not name.startswith("psutil."):
                continue
            path = Path(getattr(module, "__file__", "")).resolve()
            require(
                path.is_file() and package in path.parents,
                "imported psutil module path",
            )
            rel = path.relative_to(package).as_posix()
            require(
                rel in expected_manifest
                and hashlib.sha256(path.read_bytes()).hexdigest()
                == expected_manifest[rel],
                "imported psutil module hash",
            )
        verify_package(package, expected_manifest)
        self.psutil = psutil
        self.lib = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        self.lib.proc_listpids.argtypes = (
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_int,
        )
        self.lib.proc_listpids.restype = ctypes.c_int

    def list_group(self, pgid, capacity):
        buf = (ctypes.c_int * capacity)()
        ctypes.set_errno(0)
        nbytes = self.lib.proc_listpids(
            2, pgid, buf, ctypes.sizeof(buf)
        )  # PROC_PGRP_ONLY
        if nbytes <= 0:
            raise CensusError(
                "proc_listpids failed or returned empty: errno "
                + str(ctypes.get_errno())
            )
        return nbytes, list(buf[: min(capacity, max(0, nbytes // 4))])

    def inspect(self, pid):
        p = self.psutil.Process(pid)
        require(p.status() != self.psutil.STATUS_ZOMBIE, "unaccounted zombie member")
        start = p.create_time()
        group = os.getpgid(pid)
        rss = p.memory_info().rss
        require(p.status() != self.psutil.STATUS_ZOMBIE, "member became zombie")
        # psutil 5.9.4 caches Process.create_time() on each Process object.
        # A second call on p would only repeat that cached value even if the
        # PID had been reused during memory_info(). A fresh Process performs a
        # new OS start-time lookup; group identity alone cannot detect reuse.
        later_start = self.psutil.Process(pid).create_time()
        require(later_start == start and os.getpgid(pid) == group, "inspect race")
        return start, group, rss
