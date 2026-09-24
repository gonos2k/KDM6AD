#!/usr/bin/env python3
"""Replay measured mp237 ice stores and conditional transfer inventories."""

import json
import math
from pathlib import Path

from replay_native_number import f32

EVIDENCE = Path(__file__).parent / "evidence/conservative_native_2026-09-21.json"
FIELDS = (
    "qi",
    "ni",
    "work1",
    "workn",
    "rho",
    "dz",
    "dt",
    "mstep",
    "departure_qi",
    "departure_ni",
    "upper_departure_qi",
    "upper_departure_ni",
)


def replay(data):
    if not __debug__:
        raise RuntimeError("assertions must remain enabled")
    assert data["schema"] == "conservative-native-v1"
    for name in (
        "operational_fix_applied",
        "physical_number_basis_resolved",
        "accepted_observation_cost",
    ):
        assert data[name] is False
    provenance = data["provenance"]
    assert provenance["source_capture_stripped_exact"] is True
    for name in ("control_valid", "capture_valid"):
        assert provenance[name]["experiment_valid"] is True
        assert provenance[name]["model_completed"] is True
        assert provenance[name]["exit_code"] == 0
    proof = data["noninterference"]
    assert proof["input_hash_records_equal"] and proof["namelist_bytes_equal"]
    assert proof["history_sha256"]["control"] == proof["history_sha256"]["capture"]
    assert proof["frames"] == [
        dict(frame=i, numeric_equal=253, other_exact=1) for i in range(3)
    ]
    records = data["records"]
    assert len(records) == 156
    keyed = {}
    for r in records:
        assert set(r) == {"step", "substep", "i", "native_k", "loop", "stage", *FIELDS}
        key = (r["step"], r["native_k"], r["stage"])
        assert key not in keyed
        keyed[key] = r
        assert (r["substep"], r["loop"], r["i"], r["dt"], r["mstep"]) == (
            1,
            1,
            144,
            20.0,
            1.0,
        )
        assert all(math.isfinite(r[f]) for f in FIELDS)
        assert r["rho"] > 0 and r["dz"] > 0
        assert all(r[f] >= 0 for f in FIELDS)
    assert set(keyed) == {
        (s, k, t) for s in (1, 2) for k in range(1, 40) for t in ("before", "after")
    }
    result = []
    for step in (1, 2):
        rows = []
        upper = None
        for k in range(39, 0, -1):
            pre = keyed[step, k, "before"]
            post = keyed[step, k, "after"]
            assert all(
                pre[f] == post[f]
                for f in ("rho", "dz", "dt", "mstep", "work1", "workn")
            )
            row = {"native_k": k}
            for field in ("qi", "ni"):
                dep = post["departure_" + field]
                assert 0 <= dep <= pre[field]
                assert post["upper_departure_" + field] == (
                    0.0 if upper is None else upper["departure_" + field]
                )
                if upper is None:
                    arrival = 0.0
                elif field == "qi":
                    src = f32(upper["rho"] * upper["dz"])
                    dst = f32(pre["rho"] * pre["dz"])
                    arrival = f32(f32(upper["departure_qi"] * src) / dst)
                else:
                    arrival = f32(f32(upper["departure_ni"] * upper["dz"]) / pre["dz"])
                expected = f32(f32(pre[field] - dep) + arrival)
                assert expected == post[field], (step, k, field, expected, post[field])
                weight = pre["dz"] * (pre["rho"] if field == "qi" else 1.0)
                row[field] = dict(
                    before=pre[field],
                    after=post[field],
                    departure=dep,
                    arrival_source_order_reconstructed=arrival,
                    weight=weight,
                    storage_rounding=(post[field] - pre[field]) - (-dep + arrival),
                )
            rows.append(row)
            upper = post
        budgets = {}
        for field in ("qi", "ni"):
            terms = [r[field] for r in rows]
            departure = math.fsum(v["weight"] * v["departure"] for v in terms[:-1])
            arrival = math.fsum(
                v["weight"] * v["arrival_source_order_reconstructed"] for v in terms[1:]
            )
            delta = math.fsum(v["weight"] * (v["after"] - v["before"]) for v in terms)
            rounding = math.fsum(v["weight"] * v["storage_rounding"] for v in terms)
            bottom = terms[-1]["weight"] * terms[-1]["departure"]
            mismatch = arrival - departure
            budgets[field] = dict(
                internal_departure=departure,
                internal_arrival=arrival,
                interface_mismatch=mismatch,
                relative_interface_mismatch=mismatch / departure if departure else None,
                bottom_outflow=bottom,
                inventory_change=delta,
                storage_rounding=rounding,
                balance_residual=delta - (mismatch - bottom + rounding),
            )
        result.append(dict(step=step, rows=rows, budgets=budgets))
    return dict(
        scope="recorded_native_stores_and_source_order_reconstructed_arrival",
        cases=result,
        operational_fix_applied=False,
        physical_number_basis_resolved=False,
        accepted_observation_cost=False,
    )


if __name__ == "__main__":
    print(json.dumps(replay(json.loads(EVIDENCE.read_text())), indent=2))
