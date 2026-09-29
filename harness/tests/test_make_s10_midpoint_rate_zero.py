from __future__ import annotations

from pathlib import Path
from collections import Counter
import hashlib
import json
import math
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import make_s10_midpoint_rate_zero as hybrid  # noqa: E402


def test_four_rate_guards_restore_midpoint_source_when_disabled():
    base = (
        hybrid.USE_ANCHOR + hybrid.DECL_ANCHOR
        + hybrid.QG_MASS_SNAPSHOTS[0] + hybrid.SITES[0][2]
        + hybrid.QG_MASS_SNAPSHOTS[1] + hybrid.SITES[1][2]
        + hybrid.SITES[2][2] + hybrid.SITES[3][2]
        + hybrid.QG_MASS_SNAPSHOTS[2] + hybrid.WARM_BRS_STORE
    )
    generated = hybrid.inject_hybrid(base)
    assert hybrid.strip_hybrid(generated) == base
    assert generated.count("S10_HYBRID_BEGIN:") == 10
    assert generated.count("S10HYFAIL") == 8
    assert "qrs(i,k,3).eq.0." not in generated
    for consumer_id, rate, original, zero in hybrid.SITES:
        start = generated.index(f"! S10_HYBRID_BEGIN:{consumer_id}")
        end = generated.index(f"! S10_HYBRID_END:{consumer_id}", start)
        block = generated[start:end]
        zero_arm, nonzero_arm = block.split("            else\n", 1)
        assert zero_arm.index(f"ieee_is_finite({rate})") < zero_arm.index(f"if ({rate}.eq.0.)")
        assert f"if ({rate}.eq.0.)" in zero_arm
        assert zero in zero_arm
        assert "/rhox(i,k)" not in zero_arm
        assert original in nonzero_arm
        checks = [nonzero_arm.index(value) for value in (
            "capture_rhox_assigned(i,k)",
            "ieee_is_finite(rhox(i,k))",
            "rhox(i,k).gt.0.",
            "if (.not.s10_hybrid_density_valid)",
            original,
        )]
        assert checks == sorted(checks)
        assert f"transfer({rate},0_s10_hybrid_word_kind)" in nonzero_arm
        assert "S10HYACT" in block or consumer_id in {2915, 2916}
    assert generated.count("'S10HYACT'") == 4


def test_selected_native_success_rows_replay():
    path = (Path(__file__).resolve().parents[1] / "evidence" /
            "S10_midpoint_rate_zero_run2" / "S10HYACT_selected_rows.txt")
    receipt = json.loads((path.parent / "receipt.json").read_text())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == (
        receipt["success_action_ledger"]["raw_selected_rows_sha256"])
    counts = Counter()
    selected_pair = 0
    keys = set()
    for line in path.read_text().splitlines():
        fields = line.split()
        assert fields[0] == "S10HYACT" and len(fields) == 19
        step, lat, site, loop, substep, i, k, consumer, action, assigned = (
            map(int, fields[1:11]))
        assert step == 1 and (lat == 73 and i in (113, 115) or
                              lat == 2 and i == 142 and k == 17)
        key = (step, lat, site, loop, substep, i, k, consumer)
        assert key not in keys
        keys.add(key)
        assert (site, loop, substep) == (
            (3, 1, 1) if consumer == 1418 else (5, 1, 0))
        words = fields[11:]
        assert all(len(word) == 8 for word in words)
        values = [struct.unpack(">f", bytes.fromhex(word))[0] for word in words]
        assert all(map(math.isfinite, values))
        qg_before, qg_after, rate, rho, term, brs_before, brs_after, dt = values
        assert dt == 20.0 and all(map(math.isfinite,
                                     (qg_before, qg_after, brs_before, brs_after)))
        if action == 0:
            assert assigned == 1 and rate != 0.0 and rho > 0.0
            assert struct.pack(">f", rate / rho).hex().upper() == words[4]
        else:
            assert action == 1 and rate == term == 0.0
        counts[consumer, action] += 1
        if lat == 2:
            assert (site, consumer, action, assigned) == (5, 2824, 1, 1)
            selected_pair += 1
    assert counts == {(1418, 0): 24, (2824, 1): 47,
                      (2915, 1): 32, (2916, 1): 32}
    assert selected_pair == 1
