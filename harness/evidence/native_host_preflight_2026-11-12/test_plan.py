import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import plan


class PreflightTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = plan.construct()
        cls.base = cls.result["inputs"][0]["words"]

    def test_pinned_saved_plan_and_field_inventory(self):
        self.assertEqual(plan.verify(), self.result)
        inventory = plan.field_inventory()
        self.assertEqual(
            inventory["parent_counts"],
            {"stages": 51, "stage_field_pairs": 505, "rows": 19656},
        )
        self.assertEqual(
            set(inventory["groups"]),
            {
                "nc_zero",
                "pii_chain",
                "rate_cap_tie",
                "sedimentation",
                "named_process",
                "same_call_water",
                "heat_bg",
            },
        )
        self.assertTrue(
            all(
                x["required_record_kinds"] == ["value", "live_tangent", "mask"]
                for x in inventory["groups"].values()
            )
        )

    def test_exact_stencil_and_call_budget(self):
        p = self.result
        self.assertEqual(p["status"], "SPEC_ONLY")
        self.assertIsNone(p["execution_receipt"])
        self.assertEqual(len(p["inputs"]), 45)
        self.assertEqual(len({tuple(x["words"]) for x in p["inputs"]}), 45)
        self.assertTrue(all(len(x["words"]) == 624 for x in p["inputs"]))
        counts = {
            k: sum(x["direction"] == k for x in p["inputs"])
            for k in ("center", "nc", "pii", "th", "qv")
        }
        self.assertEqual(counts, {"center": 3, "nc": 18, "pii": 12, "th": 6, "qv": 6})
        modes = {
            k: sum(c["mode"] == k for c in p["calls"])
            for k in (
                "capture_off_value",
                "capture_on_value",
                "center_joint_graph",
                "installed_value_optional",
            )
        }
        self.assertEqual(
            modes,
            {
                "capture_off_value": 45,
                "capture_on_value": 45,
                "center_joint_graph": 3,
                "installed_value_optional": 7,
            },
        )
        self.assertEqual(len(p["calls"]), p["limits"]["calls_max"])
        self.assertEqual(p["limits"]["wall_seconds_max"], 900)
        for center in ("lower", "upper"):
            self.assertEqual(
                {
                    (x["h"], x["multiple"])
                    for x in p["inputs"]
                    if x["center"] == center and x["direction"] == "pii"
                },
                {(h, m) for h in (1e-4, 1e-5, 1e-6) for m in (-1, 1)},
            )
        self.assertTrue(
            all(
                x["archived_output_status"] == "not established by input match"
                for x in p["inputs"]
            )
        )

    def test_capture_identity_preserves_repeated_substeps_and_events(self):
        inventory = plan.field_inventory()
        self.assertIn("substep", inventory["record_identity"])
        self.assertIn("event_ordinal", inventory["record_identity"])
        self.assertIn("never overwrite", inventory["duplicate_policy"])
        record = {
            "input_id": "lower",
            "mode": "capture_on_value",
            "runtime_call": 1,
            "one_step_call": 1,
            "substep": 0,
            "b_zero": 0,
            "k_zero": 23,
            "native_level_bottom_first": 16,
            "stage": "fd_satadj_inner",
            "field": "ncact_raw",
            "record_kind": "value",
            "derivative_mode": "none",
            "direction_id": "none",
            "seed_sha256": "none",
            "cotangent_id": "none",
            "event_ordinal": 0,
        }
        second_substep = dict(record, substep=1)
        repeated_event = dict(record, event_ordinal=1)
        self.assertEqual(
            plan.validate_record_identity(
                [record, second_substep, repeated_event], inventory, self.result
            ),
            3,
        )
        with self.assertRaisesRegex(ValueError, "duplicate capture"):
            plan.validate_record_identity(
                [record, dict(record)], inventory, self.result
            )
        with self.assertRaisesRegex(ValueError, "ordinals must be contiguous"):
            plan.validate_record_identity(
                [record, dict(record, event_ordinal=2)], inventory, self.result
            )
        with self.assertRaisesRegex(ValueError, "vertical mapping"):
            plan.validate_record_identity(
                [dict(record, native_level_bottom_first=15)], inventory, self.result
            )

    def test_capture_identity_binds_plan_mode_and_derivative_seed(self):
        inventory = plan.field_inventory()
        value = {
            "input_id": "lower",
            "mode": "capture_on_value",
            "runtime_call": 1,
            "one_step_call": 1,
            "substep": 0,
            "b_zero": 0,
            "k_zero": 23,
            "native_level_bottom_first": 16,
            "stage": "fd_satadj_inner",
            "field": "ncact_raw",
            "record_kind": "value",
            "derivative_mode": "none",
            "direction_id": "none",
            "seed_sha256": "none",
            "cotangent_id": "none",
            "event_ordinal": 0,
        }
        graph_th = dict(
            value,
            mode="center_joint_graph",
            record_kind="live_tangent",
            derivative_mode="jvp",
            direction_id="th",
            seed_sha256="a" * 64,
        )
        graph_pii = dict(graph_th, direction_id="pii", seed_sha256="b" * 64)
        graph_vjp = dict(
            graph_th,
            derivative_mode="vjp",
            direction_id="none",
            cotangent_id="nc16_unit",
            seed_sha256="c" * 64,
        )
        self.assertEqual(
            plan.validate_record_identity(
                [graph_th, graph_pii, graph_vjp], inventory, self.result
            ),
            3,
        )
        with self.assertRaisesRegex(ValueError, "unplanned capture input"):
            plan.validate_record_identity(
                [dict(value, input_id="not-in-plan")], inventory, self.result
            )
        with self.assertRaisesRegex(ValueError, "mode/kind"):
            plan.validate_record_identity(
                [dict(graph_th, mode="capture_on_value")], inventory, self.result
            )
        endpoint_id = next(
            x["id"] for x in self.result["inputs"] if x["direction"] == "nc"
        )
        with self.assertRaisesRegex(ValueError, "mode/kind"):
            plan.validate_record_identity(
                [dict(graph_th, input_id=endpoint_id)], inventory, self.result
            )
        with self.assertRaisesRegex(ValueError, "seed identity"):
            plan.validate_record_identity(
                [dict(graph_th, seed_sha256="bad")], inventory, self.result
            )
        with self.assertRaisesRegex(ValueError, "JVP direction"):
            plan.validate_record_identity(
                [dict(graph_th, direction_id="missing")], inventory, self.result
            )
        with self.assertRaisesRegex(ValueError, "VJP cotangent"):
            plan.validate_record_identity(
                [dict(graph_vjp, cotangent_id="none")], inventory, self.result
            )

    def test_undeclared_negative_zero_and_invalid_words_rejected(self):
        for args in [
            ("baseline", "nc", 1e-4, -1),
            ("baseline", "nc", 1e-4, 0),
            ("baseline", "pii", 1e-5, 1),
            ("lower", "qv", 1e-4, 1),
            ("upper", "th", 1e-5, 0),
        ]:
            with (
                self.subTest(args=args),
                self.assertRaisesRegex(ValueError, "undeclared"),
            ):
                plan.calculate_input(self.base, *args)
        bad = list(self.base)
        bad[8 * 39 + 15] = plan.to64(-1e8)
        with self.assertRaisesRegex(ValueError, "negative NC"):
            plan.calculate_input(bad, "baseline", "nc", 1e-6, 1)
        bad = list(self.base)
        bad[0] = plan.to64(float("nan"))
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            plan.calculate_input(bad, "baseline", "center", 0, 0)

    def test_execution_stays_blocked(self):
        with self.assertRaisesRegex(ValueError, "missing new instrumented DSO"):
            plan.execution_preflight(self.result)
        changed = copy.deepcopy(self.result)
        changed["build_requirements"]["instrumented_dso_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "outside this source-only"):
            plan.execution_preflight(changed)

    def test_source_hash_and_saved_manifest_tampering(self):
        pins = dict(plan.SOURCE_PINS)
        pins[next(iter(pins))] = "0" * 64
        with (
            mock.patch.object(plan, "SOURCE_PINS", pins),
            self.assertRaisesRegex(ValueError, "source SHA-256"),
        ):
            plan.construct()
        bad = copy.deepcopy(self.result)
        bad["calls"].pop()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "plan.json.gz").write_bytes(gzip.compress(json.dumps(bad).encode()))
            with (
                mock.patch.object(plan, "HERE", root),
                self.assertRaisesRegex(ValueError, "saved plan mismatch"),
            ):
                plan.verify()


if __name__ == "__main__":
    unittest.main()
