"""Fixed evidence expectations cannot shrink with the received census."""

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from replay_native_multistep_10min import (  # noqa: E402
    EVIDENCE_NAME, replay, validate_metadata,
)


EVIDENCE = Path(__file__).resolve().parents[2] / "harness" / "evidence"


def _data():
    return json.loads((EVIDENCE / EVIDENCE_NAME).read_text())


def test_public_complete_negative_census_replays_without_science_approval():
    result = replay(EVIDENCE)
    assert result["selected_rows"] == result["consumed_rows"] == 1_948_800
    assert result["multistep_selected"] == 0
    assert not result["native_mstep_ge_2_certified"]
    assert not result["operational_transport_p1_closed"]
    assert not result["netcdf_reopened"]


def test_plan_and_record_cannot_shrink_together():
    data = _data()
    for key, value in (("outer_steps", 29), ("owned_i_1_based", [2, 232])):
        bad = copy.deepcopy(data)
        bad["run_plan"][key] = value
        bad["census"]["audit"]["selected_rows"] = 29 * 280 * 231
        with pytest.raises(ValueError, match="fixed run plan"):
            validate_metadata(bad)
    bad = copy.deepcopy(data)
    del bad["runs"]["capture"]
    with pytest.raises(ValueError, match="native run"):
        validate_metadata(bad)


def test_recorded_hash_count_or_approval_mutation_is_rejected():
    data = _data()
    mutations = (
        ("history", lambda x: x["runs"]["control"].__setitem__("history_sha256", "0" * 64)),
        ("namelist", lambda x: x["runs"]["capture"].__setitem__("effective_namelist_sha256", "0" * 64)),
        ("case", lambda x: x["run_plan"].__setitem__("input_case", "other weather")),
        ("run", lambda x: x["runs"]["capture"].__setitem__("campaign_id", "0" * 64)),
        ("archive", lambda x: x["census"].__setitem__("compressed_sha256", "0" * 64)),
        ("census", lambda x: x["census"]["audit"].__setitem__("multistep_selected", 1)),
        ("approval", lambda x: x["scope"].__setitem__("operational_transport_p1_closed", True)),
    )
    for _name, change in mutations:
        bad = copy.deepcopy(data)
        change(bad)
        with pytest.raises(ValueError):
            validate_metadata(bad)
