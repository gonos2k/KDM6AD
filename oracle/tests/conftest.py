"""Test-only fixtures for expensive, immutable public evidence replays."""

import copy
import hashlib
from pathlib import Path
import sys

import pytest

HARNESS = Path(__file__).resolve().parents[2] / "harness"
HOUR_ARCHIVE = HARNESS / "evidence/native_ice_census_1hour_rank0_2026-09-25.txt.xz"
HOUR_SHA256 = "f7a4d6666f69b8f217eb5e6c4307f4441dabb46ad9d86e00a0985f432b33c4ad"


def _hash_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def make_census_provider(path, plan, digest, replay):
    """Cache one identified source/plan; return isolated copies to consumers."""
    expected = path.resolve(strict=True)
    cache = None

    def get(requested, requested_plan):
        nonlocal cache
        requested = Path(requested)
        if requested.resolve(strict=True) != expected or requested_plan != plan:
            raise ValueError("shared census source or plan mismatch")
        if _hash_file(requested) != digest:
            raise ValueError("shared census source hash mismatch")
        if cache is None:
            computed = replay(requested, requested_plan)
            if computed["file_sha256"] != digest or _hash_file(requested) != digest:
                raise ValueError("shared census source changed during replay")
            cache = copy.deepcopy(computed)
        return copy.deepcopy(cache)

    return get


@pytest.fixture(scope="session")
def shared_hour_census():
    if str(HARNESS) not in sys.path:
        sys.path.insert(0, str(HARNESS))
    from streaming_ice_census import CensusPlan, replay_file

    plan = CensusPlan(tuple(range(1, 181)), (2, 233), (2, 281), 0)
    return make_census_provider(HOUR_ARCHIVE, plan, HOUR_SHA256, replay_file)
