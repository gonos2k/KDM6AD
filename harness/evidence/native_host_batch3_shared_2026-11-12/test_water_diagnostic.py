import copy
from decimal import Decimal, localcontext
import json
from pathlib import Path
import tempfile
import unittest

import water_diagnostic as water


class SameCallWaterTest(unittest.TestCase):
    def setUp(self):
        self.data = water.load_source()
        self.actual = water.calculate(self.data)

    def test_report_and_layer_arithmetic(self):
        self.assertEqual(water.verify(), self.actual)
        with localcontext() as ctx:
            ctx.prec = 600
            layers = self.actual["layers"]
            self.assertEqual(
                [x["level_zero_bottom_first"] for x in layers], list(range(39))
            )
            self.assertEqual(
                sum((Decimal(x["change_kg_m2"]) for x in layers), Decimal(0)),
                Decimal(self.actual["water_change_kg_m2"]),
            )
            self.assertEqual(
                Decimal(self.actual["water_change_kg_m2"])
                + Decimal(self.actual["precipitation_kg_m2"]),
                Decimal(self.actual["conditional_residual_kg_m2"]),
            )

    def test_source_mutations_rejected_by_hash(self):
        for kind in ("rain", "density", "vertical_order"):
            altered = copy.deepcopy(self.data)
            if kind == "rain":
                altered["increments_words_hex"]["rain"] = "00000000"
            elif kind == "density":
                altered["input_words_hex"]["rho"][0] = "3f800000"
            else:
                altered["input_words_hex"]["delz"].reverse()
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as d:
                path = Path(d) / "source.json"
                path.write_text(json.dumps(altered))
                with self.assertRaisesRegex(ValueError, "source SHA-256"):
                    water.load_source(path)

    def test_receipt_rejects_double_counted_snow_and_wrong_rain(self):
        for kind in ("snow", "wrong_rain"):
            report = copy.deepcopy(self.actual)
            with localcontext() as ctx:
                ctx.prec = 600
                residual = Decimal(report["conditional_residual_kg_m2"])
                if kind == "snow":
                    residual += water.decode(self.data["increments_words_hex"]["snow"])
                else:
                    residual -= water.decode(self.data["increments_words_hex"]["rain"])
                report["conditional_residual_kg_m2"] = str(residual)
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as d:
                path = Path(d) / "report.json"
                path.write_text(json.dumps(report))
                with self.assertRaisesRegex(ValueError, "diagnostic mismatch"):
                    water.verify(path)

    def test_density_reordering_changes_computed_ledger(self):
        data = copy.deepcopy(self.data)
        data["input_words_hex"]["rho"].reverse()
        self.assertNotEqual(
            water.calculate(data)["conditional_residual_kg_m2"],
            self.actual["conditional_residual_kg_m2"],
        )


if __name__ == "__main__":
    unittest.main()
