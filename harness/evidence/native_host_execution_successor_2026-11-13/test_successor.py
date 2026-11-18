"""Synthetic-only contract tests; no KDM or external process is invoked."""

import copy
import gzip
import json
import unittest

import successor as s


def fixture():
    d = s.draft()
    inputs = {x["id"]: x for x in d["inputs"]}
    calls = []
    sequence = {}
    for spec in d["calls"]:
        row = {k: spec[k] for k in ("sequence", "input_id", "mode")}
        if spec["status"] == "PLANNED_OPTIONAL":
            row.update(status="SKIPPED", reason="synthetic optional omission")
        else:
            iw = inputs[row["input_id"]]["words"]
            out = [s.ZERO] * 468
            rain = s.ZERO
            row.update(
                status="COMPLETED",
                return_code=0,
                input_words=iw,
                input_sha256=s.packed_sha(iw),
                state_output_words=out,
                output_sha256=s.packed_sha(out),
                rain_sidecar={
                    "scope": "same_call_total_precipitation_raw",
                    "word": rain,
                    "sha256": s.sha(bytes.fromhex(rain)),
                },
            )
            sequence[(row["input_id"], row["mode"])] = row["sequence"]
        calls.append(row)
    seeds = {}
    for key, seed in s.effective_seeds().items():
        center = key.split(":")[0]
        out = [s.ZERO] * 468
        seeds[key] = {
            "words": seed,
            "sha256": s.packed_sha(seed),
            "graph_sequence": sequence[(center, "center_joint_graph")],
            "graph_input_words": inputs[center]["words"],
            "forward_words": out,
            "return_code": 0,
            "jvp_words": out,
            "jvp_sha256": s.packed_sha(out),
        }
    cot = [s.ZERO] * 468
    cot[8 * 39 + 15] = "3ff0000000000000"
    j = [s.ZERO] * 624
    vjp = {
        "id": "state:nc:15",
        "words": cot,
        "sha256": s.packed_sha(cot),
        "graph_sequence": sequence[("baseline", "center_joint_graph")],
        "forward_words": [s.ZERO] * 468,
        "return_code": 0,
        "vjp_words": j,
        "vjp_sha256": s.packed_sha(j),
    }
    records = []

    def emit(input_id, mode, group, kind, field, **kw):
        row = {
            "input_id": input_id,
            "mode": mode,
            "call_sequence": sequence[(input_id, mode)],
            "runtime_call": 1,
            "one_step_call": 1,
            "outer_loop": 0,
            "substep_family": "none",
            "substep_n": 0,
            "scope": "layer",
            "b_zero": 0,
            "k_zero": 23,
            "native_level_bottom_first": 16,
            "stage": "synthetic",
            "field": field,
            "record_kind": kind,
            "derivative_mode": "none",
            "direction_id": "none",
            "seed_sha256": "none",
            "cotangent_id": "none",
            "event_ordinal": 0,
            "measurement_group_id": group,
            **kw,
        }
        records.append(row)

    for ident in inputs:
        for group in d["measurement_group_ids"]:
            emit(
                ident,
                "capture_on_value",
                group,
                "value",
                "value_" + group,
                raw_hex=s.ZERO,
            )
        for mask in d["mask_ids"]:
            group = d["measurement_groups"][d["mask_groups"][mask]][0]
            emit(
                ident,
                "capture_on_value",
                group,
                "mask",
                "mask_" + mask,
                mask_id=mask,
                mask_value=False,
            )
    for center in ("baseline", "lower", "upper"):
        seedid = next(x for x in seeds if x.startswith(center + ":"))
        for group in d["measurement_group_ids"]:
            emit(
                center,
                "center_joint_graph",
                group,
                "live_tangent",
                "live_" + group,
                raw_hex=s.ZERO,
            )
            records[-1].update(
                derivative_mode="jvp",
                direction_id=seedid,
                seed_sha256=seeds[seedid]["sha256"],
            )
    return {
        "schema": "kdm6.native_host_successor_synthetic.v1",
        "origin": "SYNTHETIC_TEST_ONLY",
        "parent_plan_sha256": s.PARENT_SHA,
        "policy_source_commit": s.POLICY_COMMIT,
        "wall_seconds": 5,
        "calls": calls,
        "effective_jvp_seeds": seeds,
        "vjp_cotangent": vjp,
        "records": records,
    }


class SuccessorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = fixture()

    def test_draft_pins_and_blockers(self):
        d = s.draft()
        saved = json.loads(gzip.decompress((s.HERE / "draft.json.gz").read_bytes()))
        self.assertEqual(saved, d)
        self.assertEqual(
            (
                len(d["inputs"]),
                len(d["calls"]),
                len(d["measurement_group_ids"]),
                len(d["mask_ids"]),
            ),
            (45, 100, 28, 19),
        )
        self.assertEqual(d["status"], "DRAFT_BLOCKED")
        self.assertEqual(d["atomic_catalog_draft_sites"], 191)
        self.assertEqual(d["atomic_catalog_draft_sha256"], s.ATOMIC_CATALOG_DRAFT_SHA)
        self.assertTrue(all(v is None for v in d["required_build"].values()))
        with self.assertRaisesRegex(ValueError, "execution blocked"):
            s.require_execution_ready(d)

    def test_synthetic_never_authorizes(self):
        result = s.validate_synthetic(self.bundle)
        self.assertFalse(result["execution_ready"])
        self.assertEqual(result["status"], "DRAFT_BLOCKED")

    def test_rehashed_call_mismatch_and_missing(self):
        b = copy.deepcopy(self.bundle)
        b["calls"][0]["input_words"][0] = s.ZERO
        b["calls"][0]["input_sha256"] = s.packed_sha(b["calls"][0]["input_words"])
        with self.assertRaisesRegex(ValueError, "call input mismatch"):
            s.validate_synthetic(b)
        b = copy.deepcopy(self.bundle)
        b["calls"][1]["rain_sidecar"]["word"] = "3ff0000000000000"
        b["calls"][1]["rain_sidecar"]["sha256"] = s.sha(
            bytes.fromhex("3ff0000000000000")
        )
        with self.assertRaisesRegex(ValueError, "capture output/rain mismatch"):
            s.validate_synthetic(b)
        b = copy.deepcopy(self.bundle)
        b["calls"].pop()
        with self.assertRaisesRegex(ValueError, "call ledger count"):
            s.validate_synthetic(b)

    def test_seed_and_cotangent_rehashed_mutations(self):
        b = copy.deepcopy(self.bundle)
        x = next(iter(b["effective_jvp_seeds"].values()))
        x["words"][0] = "3ff0000000000000"
        x["sha256"] = s.packed_sha(x["words"])
        with self.assertRaisesRegex(ValueError, "effective JVP seed"):
            s.validate_synthetic(b)
        b = copy.deepcopy(self.bundle)
        x = b["vjp_cotangent"]
        x["words"][0] = "3ff0000000000000"
        x["sha256"] = s.packed_sha(x["words"])
        with self.assertRaisesRegex(ValueError, "VJP cotangent"):
            s.validate_synthetic(b)

    def test_identity_group_mask_and_ordinal_rejected(self):
        for mutation in (
            "missing_mask",
            "missing_group",
            "level",
            "duplicate",
            "ordinal",
        ):
            b = copy.deepcopy(self.bundle)
            if mutation == "missing_mask":
                b["records"].pop(
                    next(
                        i
                        for i, x in enumerate(b["records"])
                        if x["record_kind"] == "mask"
                    )
                )
            elif mutation == "missing_group":
                b["records"].pop(
                    next(
                        i
                        for i, x in enumerate(b["records"])
                        if x["record_kind"] == "value"
                    )
                )
            elif mutation == "level":
                b["records"][0]["native_level_bottom_first"] = 15
            elif mutation == "duplicate":
                b["records"].append(copy.deepcopy(b["records"][0]))
            else:
                b["records"][0]["event_ordinal"] = 1
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                s.validate_synthetic(b)

    def test_column_scope_and_synthetic_origin(self):
        b = copy.deepcopy(self.bundle)
        b["records"][0].update(
            scope="column", k_zero=None, native_level_bottom_first=None
        )
        self.assertFalse(s.validate_synthetic(b)["execution_ready"])
        b = copy.deepcopy(self.bundle)
        b["origin"] = "REAL"
        with self.assertRaisesRegex(ValueError, "synthetic only"):
            s.validate_synthetic(b)


if __name__ == "__main__":
    unittest.main()
