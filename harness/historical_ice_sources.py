"""Read immutable source bytes used by the 2026-10-23 ice factorial campaign.

Historical replay uses these exact source words. This module does not claim
the current C++ sources still accept the old instrumentation anchors.
"""

import hashlib
from pathlib import Path
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


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked_factorial_root():
    """Return source tree only if every archived byte matches the old pins."""
    for name, expected in HISTORICAL_TU_SHA256.items():
        if digest(LIBTORCH / "src" / name) != expected:
            raise ValueError("historical source digest " + name)
    if digest(LIBTORCH / "CMakeLists.txt") != CMAKE_SHA256:
        raise ValueError("historical source digest CMakeLists.txt")
    return LIBTORCH


def checked_actual_qr_coordinator():
    path = ROOT / "actual_qr/coordinator.cpp"
    if digest(path) != ACTUAL_QR_COORDINATOR_SHA256:
        raise ValueError("historical actual-QR coordinator digest")
    return path


def historical_manifest_source(relative, expected):
    """Resolve only known historical source pins; leave other paths unchanged."""
    if relative.startswith("libtorch/src/"):
        name = Path(relative).name
        if HISTORICAL_TU_SHA256.get(name) == expected:
            return checked_factorial_root() / "src" / name
    if (relative == "oracle/kdm6/sedimentation.py" and
            expected == ORACLE_SEDIMENTATION_SHA256):
        path = ROOT / "oracle/kdm6/sedimentation.py"
        if digest(path) != expected:
            raise ValueError("historical oracle sedimentation digest")
        return path
    if relative.startswith("harness/tests/") and len(expected) == 64:
        path = ROOT / "test_sources" / expected / relative
        if path.is_file():
            if digest(path) != expected:
                raise ValueError("historical test source digest " + relative)
            return path
    return REPO / relative
