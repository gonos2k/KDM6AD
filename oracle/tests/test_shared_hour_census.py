"""The test-only census cache must not hide changed inputs or shared mutation."""

import hashlib
from pathlib import Path
import sys

import pytest

from conftest import make_census_provider

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from streaming_ice_census import CensusPlan


def test_provider_checks_identity_and_returns_independent_deep_copies(tmp_path):
    archive = tmp_path / "archive.xz"
    archive.write_bytes(b"known input")
    sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    plan = CensusPlan((1,), (2, 3), (4, 5), 0)
    calls = []

    def replay(path, supplied_plan):
        calls.append((path, supplied_plan))
        return {"file_sha256": sha, "audit": {"mstep_histogram": {1: 2}}}

    provider = make_census_provider(archive, plan, sha, replay)
    first = provider(archive, plan)
    first["audit"]["mstep_histogram"][1] = 99
    assert provider(archive, plan)["audit"]["mstep_histogram"] == {1: 2}
    assert len(calls) == 1
    with pytest.raises(ValueError, match="source or plan"):
        provider(archive, CensusPlan((2,), (2, 3), (4, 5), 0))
    other = tmp_path / "other.xz"
    other.write_bytes(archive.read_bytes())
    with pytest.raises(ValueError, match="source or plan"):
        provider(other, plan)
    archive.write_bytes(b"changed input")
    with pytest.raises(ValueError, match="source hash"):
        provider(archive, plan)


def test_provider_rejects_source_change_during_first_replay(tmp_path):
    archive = tmp_path / "archive.xz"
    archive.write_bytes(b"original")
    sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    plan = CensusPlan((1,), (1, 1), (1, 1))

    def replay(path, _plan):
        path.write_bytes(b"changed")
        return {"file_sha256": sha}

    provider = make_census_provider(archive, plan, sha, replay)
    with pytest.raises(ValueError, match="during replay"):
        provider(archive, plan)
