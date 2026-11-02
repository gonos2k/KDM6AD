"""Read immutable source bytes used by the 2026-10-23 ice factorial campaign.

Historical replay uses these exact source words. This module does not claim
the current C++ sources still accept the old instrumentation anchors.
"""

import hashlib
from pathlib import Path
import re
from types import MappingProxyType


REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "harness/evidence/historical_ice_factorial_sources_2026-10-23"
LIBTORCH = ROOT / "libtorch"
# Fixed historical campaign receipt values. Never import mutable generator
# source pins here: a later generator rebase must not rewrite old execution.
HISTORICAL_TU_SHA256 = MappingProxyType({
    "runtime.cpp": "4a56110c91b7495aea0542531eb809a048bb7994747cea2be826f9a2f6e26f7a",
    "coordinator.cpp": "9253e1741cb8926f98fc088c56579a015472ea43b7ef0b365ef2c42bd2660152",
    "sedimentation.cpp": "1fd41e6dff2f99cf80cf9f318245cb50cb2d107d2f9053f8c65802f6b4037c2a",
    "sedimentation_conservative.cpp": "53b13bc505b0e46327942b3b4070a541ce04f23f7a37d3b0bf60d731f8659694",
})
ACTUAL_QR_COORDINATOR_SHA256 = (
    "373e77cc9f81bd77603c6993a53cd8dfd5e9b3b401da6e102d90bc16028f280e"
)
CMAKE_SHA256 = "829b78bb0e872aadde362e3c9b65391a9d0f229fe4a459be6da798a49aae7d90"
ORACLE_SEDIMENTATION_SHA256 = (
    "0e2b866f1a71937fbc2cf9ff382ced8bd0e439c732992b494b2ea2251f806f89"
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_HISTORICAL_CPP_PATHS = MappingProxyType({
    f"libtorch/src/{name}": (name, digest)
    for name, digest in HISTORICAL_TU_SHA256.items()
})


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _regular_within(path, root):
    """Reject aliases and symlinks before hashing a retained source file."""
    path, root = Path(path), Path(root)
    lexical_root = root.absolute()
    trusted = REPO if lexical_root.is_relative_to(REPO) else Path(lexical_root.anchor)
    try:
        parts = path.relative_to(root).parts
        resolved = path.resolve(strict=True)
        allowed = root.resolve(strict=True)
        root_parts = lexical_root.relative_to(trusted).parts
    except (ValueError, OSError) as exc:
        raise ValueError("unresolved historical source path " + str(path)) from exc
    cursor = trusted
    for part in root_parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError("historical source root contains symlink " + str(root))
    cursor = root
    if root.is_symlink() or not resolved.is_relative_to(allowed):
        raise ValueError("historical source path escapes root " + str(path))
    for part in parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError("historical source path contains symlink " + str(path))
    if not path.is_file():
        raise ValueError("unresolved historical source path " + str(path))
    return path


def checked_factorial_root():
    """Return source tree only if every archived byte matches the old pins."""
    for name, expected in HISTORICAL_TU_SHA256.items():
        if digest(_regular_within(LIBTORCH / "src" / name, LIBTORCH)) != expected:
            raise ValueError("historical source digest " + name)
    if digest(_regular_within(LIBTORCH / "CMakeLists.txt", LIBTORCH)) != CMAKE_SHA256:
        raise ValueError("historical source digest CMakeLists.txt")
    return LIBTORCH


def checked_actual_qr_coordinator():
    path = _regular_within(ROOT / "actual_qr/coordinator.cpp", ROOT / "actual_qr")
    if digest(path) != ACTUAL_QR_COORDINATOR_SHA256:
        raise ValueError("historical actual-QR coordinator digest")
    return path


def historical_manifest_source(relative, expected):
    """Resolve only exact historical path+digest pairs; fail on path aliases."""
    if (type(relative) is not str or not relative or "\\" in relative or
            any(part in ("", ".", "..") for part in relative.split("/")) or
            type(expected) is not str or _SHA256.fullmatch(expected) is None):
        raise ValueError("invalid historical source path or SHA-256")
    cpp = _HISTORICAL_CPP_PATHS.get(relative)
    if cpp is not None:
        name, historical_digest = cpp
        if historical_digest == expected:
            return checked_factorial_root() / "src" / name
    if expected in HISTORICAL_TU_SHA256.values():
        raise ValueError("historical C++ source path mismatch " + relative)
    if expected == CMAKE_SHA256:
        if relative != "libtorch/CMakeLists.txt":
            raise ValueError("historical CMake source path mismatch " + relative)
        return checked_factorial_root() / "CMakeLists.txt"
    if expected == ACTUAL_QR_COORDINATOR_SHA256:
        if relative != "libtorch/src/coordinator.cpp":
            raise ValueError("historical actual-QR source path mismatch " + relative)
        return checked_actual_qr_coordinator()
    if expected == ORACLE_SEDIMENTATION_SHA256 and relative != "oracle/kdm6/sedimentation.py":
        raise ValueError("historical oracle source path mismatch " + relative)
    if (relative == "oracle/kdm6/sedimentation.py" and
            expected == ORACLE_SEDIMENTATION_SHA256):
        path = ROOT / "oracle/kdm6/sedimentation.py"
        if digest(_regular_within(path, ROOT / "oracle")) != expected:
            raise ValueError("historical oracle sedimentation digest")
        return path
    archive = ROOT / "test_sources" / expected
    if archive.is_dir():
        if not relative.startswith("harness/tests/"):
            raise ValueError("historical test source path mismatch " + relative)
        path = archive / relative
        if not path.is_file():
            raise ValueError("historical test source path mismatch " + relative)
        if digest(_regular_within(path, ROOT / "test_sources")) != expected:
            raise ValueError("historical test source digest " + relative)
        return path
    return _regular_within(REPO / relative, REPO)
