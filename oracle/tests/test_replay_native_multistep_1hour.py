"""The complete one-hour archive remains a bounded negative native result."""

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from replay_native_multistep_1hour import (  # noqa: E402
    ADDENDUM_NAME, EVIDENCE_NAME, PLAN_NAME, replay, validate_metadata,
)


EVIDENCE = Path(__file__).resolve().parents[2] / "harness" / "evidence"


def _data():
    return json.loads((EVIDENCE / EVIDENCE_NAME).read_text())


def test_complete_one_hour_public_archive_replays_without_multistep_approval():
    result = replay(EVIDENCE)
    assert result["selected_rows"] == result["consumed_rows"] == 11_692_800
    assert result["multistep_selected"] == 0
    assert result["control_capture_history_recorded_equal"]
    assert not result["native_mstep_ge_2_certified"]
    assert not result["operational_transport_p1_closed"]
    assert not result["netcdf_reopened"]


def test_hour_plan_run_hash_and_acceptance_cannot_change_with_record():
    data = _data()
    mutations = (
        lambda x: x["run_plan"].__setitem__("outer_steps", 179),
        lambda x: x["run_plan"].__setitem__("plan_sha256", "0" * 64),
        lambda x: x["runs"]["capture"].__setitem__("effective_namelist_sha256", "0" * 64),
        lambda x: x["runs"]["control"].__setitem__("history_sha256", "0" * 64),
        lambda x: x["census"]["audit"].__setitem__("multistep_selected", 1),
        lambda x: x["terminal_ice_snapshot"].__setitem__("qice_and_qnice_positive_cells", 0),
        lambda x: x["scope"].__setitem__("operational_transport_p1_closed", True),
    )
    for change in mutations:
        bad = copy.deepcopy(data)
        change(bad)
        with pytest.raises(ValueError):
            validate_metadata(bad)


def test_published_pre_run_plan_and_later_control_addendum_are_pinned(tmp_path):
    (tmp_path / EVIDENCE_NAME).write_bytes((EVIDENCE / EVIDENCE_NAME).read_bytes())
    (tmp_path / PLAN_NAME).write_bytes((EVIDENCE / PLAN_NAME).read_bytes() + b" ")
    (tmp_path / ADDENDUM_NAME).write_bytes((EVIDENCE / ADDENDUM_NAME).read_bytes())
    with pytest.raises(ValueError, match="published plan/addendum"):
        replay(tmp_path)
