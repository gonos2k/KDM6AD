"""Regression checks for the archived actual C++ slope producer stage graph."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import replay

HERE = Path(__file__).resolve().parent


class NativeD1SlopeCppAD(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = replay.replay()
        cls.raw = replay.parent_module().parse_json(
            (HERE / "raw/cpp_result.json").read_bytes()
        )

    def test_same_call_slope_and_cpp_baseline(self) -> None:
        self.assertEqual(self.result["parent_cpp_baseline_raw_equal"], 16)
        self.assertEqual(self.result["slope39"]["levels"], 39)
        self.assertEqual(self.result["verified_cpp"]["baseline_raw_equal"], 25)
        if not replay.parent_module().same_reference_runtime():
            print(
                "PORTABLE_SLOPE_REFERENCE_ULPS",
                json.dumps(
                    {
                        "slope39": self.result["slope39"]["max_oracle_ulp_by_field"],
                        "baseline": self.result["verified_cpp"]["baseline_ulp"],
                        "endpoints": self.result["verified_cpp"]["endpoint_ulp"],
                        "jvp_abs": self.result["verified_cpp"]["jvp_abs"],
                    },
                    sort_keys=True,
                ),
            )
        if replay.parent_module().same_reference_runtime():
            self.assertTrue(
                all(
                    x == 0
                    for x in self.result["slope39"]["max_oracle_ulp_by_field"].values()
                )
            )
            self.assertEqual(self.result["verified_cpp"]["endpoint_ulp"], 0)
        self.assertEqual(
            self.result["verified_cpp"]["qg_crossing"]["high"],
            {"entry_rhox": 900.0, "post_rhox": 900.0},
        )

    def test_new_snow_and_graupel_producer_tangents(self) -> None:
        qs = self.raw["directions"]["relative_qs16"]["jvp"]
        brs = self.raw["directions"]["relative_brs_pre16"]["jvp"]
        qg = self.raw["directions"]["relative_qg16"]["jvp"]
        self.assertGreater(qs[17], 0.0)  # snow rslope responds to QS
        self.assertLess(qs[6], 0.0)  # changed slope changes applied snow melt
        self.assertNotEqual(qs[10], 0.0)  # number store sees the new slope path
        self.assertGreater(brs[21], 0.0)  # graupel slope sees entry ProgB density
        self.assertEqual(qg[21], 0.0)  # QG and its ProgB intercept cancel locally
        self.assertEqual(
            set(self.result["verified_cpp"]["directions"]),
            set(replay.DIRECTIONS),
        )

    def test_portable_slope_bound_and_exact_graupel_field(self) -> None:
        parent = replay.parent_module()
        self.assertEqual(replay.SLOPE_PORTABLE_ULPS["rslope2_s"], 32)
        self.assertNotIn("rslope_g", replay.SLOPE_PORTABLE_ULPS)
        self.assertNotIn("rslopemu_s", replay.SLOPE_ENDPOINT_PORTABLE)
        base = self.raw["baseline"]["values"][18]
        candidate = base
        for _ in range(32):
            candidate = math.nextafter(candidate, math.inf)
        with patch.object(parent, "same_reference_runtime", return_value=False):
            self.assertEqual(
                parent.check_reference_word(
                    parent.word(base), candidate, "snow square portable", max_ulps=32
                ),
                32.0,
            )
            with self.assertRaisesRegex(ValueError, "exceeds 32"):
                parent.check_reference_word(
                    parent.word(base),
                    math.nextafter(candidate, math.inf),
                    "snow square portable",
                    max_ulps=32,
                )
            with self.assertRaisesRegex(ValueError, "raw bit mismatch"):
                parent.check_reference_word(
                    self.raw["baseline"]["raw_hex"][21],
                    math.nextafter(self.raw["baseline"]["values"][21], math.inf),
                    "exact graupel slope",
                    max_ulps=0,
                )

    def _mutated(self, transform) -> None:
        changed = copy.deepcopy(self.raw)
        transform(changed)
        raw = (
            json.dumps(changed, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()
        with self.assertRaises(ValueError):
            replay.replay(
                output_override=raw, output_sha=hashlib.sha256(raw).hexdigest()
            )

    def test_rehashed_baseline_and_joint_dot_forgery_fail(self) -> None:
        self._mutated(lambda d: d["baseline"]["raw_hex"].__setitem__(17, "0"))

        def forge_both(d):
            d["directions"]["relative_qs16"]["jvp_dot"] = 0.0
            d["directions"]["relative_qs16"]["vjp_dot"] = 0.0

        self._mutated(forge_both)

    def test_rehashed_slope_tangent_and_endpoint_fail(self) -> None:
        self._mutated(
            lambda d: d["directions"]["relative_qs16"]["jvp"].__setitem__(17, 0.0)
        )

        def forge_endpoint(d):
            d["directions"]["relative_qs16"]["finite_differences"]["0.01"]["high"][
                17
            ] = 0.0

        self._mutated(forge_endpoint)

    def test_cli(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(HERE / "replay.py")],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(
            json.loads(proc.stdout)["verified_cpp"]["baseline_raw_equal"], 25
        )


if __name__ == "__main__":
    unittest.main()
