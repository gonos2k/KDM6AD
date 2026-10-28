from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from harness.analyze_qnc_star_qi_trace import analyze
from harness.native_qnc_advect_qi_trace_records import (
    read_qi_writer_trace,
    read_qnc_producer_trace,
)
from harness.native_qnc_star_qi_records import read_qnc_star_trace, read_star_qi_writer_trace


ROOT = Path(__file__).resolve().parents[1] / "evidence"
DATA = ROOT / "native_qnc_star_qi_2026-10-28/data"
PARENT = ROOT / "native_qnc_advect_qi_2026-10-28/data"


def _inputs():
    cases = ("control", "alpha025")
    star = {case: read_qnc_star_trace(DATA / case / "qnc_star.tsv") for case in cases}
    writer = {case: read_star_qi_writer_trace(DATA / case / "qnc_star_qi_moments.tsv")
              for case in cases}
    prior_writer = {case: read_qi_writer_trace(PARENT / case / "qi_writer_moments.tsv")
                    for case in cases}
    prior_producer = {case: read_qnc_producer_trace(PARENT / case / "qnc_producer.tsv")
                      for case in cases}
    return star, writer, prior_writer, prior_producer


def _analyze(star, writer, prior_writer, prior_producer):
    return analyze(star["control"], star["alpha025"], writer["control"], writer["alpha025"],
                   prior_writer["control"], prior_writer["alpha025"],
                   prior_producer["control"], prior_producer["alpha025"])


def test_rejects_shared_face_with_different_neighbor_word():
    star, writer, prior_writer, prior_producer = _inputs()
    changed = deepcopy(star["alpha025"])
    owner = changed["owner_call_id"]
    changed["records"][(owner, "RK3_POST", 112, 12, 70, "FX_EAST")] ^= 1
    star["alpha025"] = changed
    with pytest.raises(ValueError, match="internal shared face bits differ"):
        _analyze(star, writer, prior_writer, prior_producer)


def test_rejects_qi_donor_that_cannot_explain_boundary_result():
    star, writer, prior_writer, prior_producer = _inputs()
    original = writer["alpha025"]
    values = dict(original.values)
    values[(3, "QI_BDY_INPUT", 1, 33, 168, "DONOR_QI")] = 0
    writer["alpha025"] = replace(original, values=values)
    with pytest.raises(ValueError, match="donor/velocity/copy join differs"):
        _analyze(star, writer, prior_writer, prior_producer)


def test_counterfactual_requires_original_pre_face_scale_join():
    star, writer, prior_writer, prior_producer = _inputs()
    original = prior_producer["alpha025"]
    values = dict(original.values)
    values[(3, "RK3_PD_PRE_LIMIT", 113, 12, 70, "FX_EAST")] ^= 1
    prior_producer["alpha025"] = replace(original, values=values)
    with pytest.raises(ValueError, match="original target scale/share join differs"):
        _analyze(star, writer, prior_writer, prior_producer)
