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
