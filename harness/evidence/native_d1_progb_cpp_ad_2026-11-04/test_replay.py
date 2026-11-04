"""Archived actual C++/libtorch D1-to-ProgB local AD regression."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "native_d1_progb_cpp_replay", HERE / "replay.py"
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("C++ AD replay import failed")
replay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replay)


class NativeD1ProgBCppAD(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = replay.replay()
        cls.native = replay.parse_json((HERE / "raw/cpp_result.json").read_bytes())
        cls.parent = replay.parent_module()
        cls.fields, cls.state_parent, cls.producer = replay.parent_fields(cls.parent)

    def test_actual_cpp_source_archive_and_raw_baseline(self) -> None:
        result = self.result
        self.assertEqual(result["verified"]["baseline_raw_bit_equal_outputs"], 10)
        self.assertEqual(result["source_and_build"]["torch_version"], "2.13.0")
        self.assertEqual(
            result["source_and_build"]["input_capture_sha256"],
            "98bfe8ca7deb80590d4c739421fa9f6d90b17da0e7b2e05bec02c05e7685bc16",
        )
        self.assertEqual(
            result["source_and_build"]["parent_native_archive_sha256"],
            "93575a832a92c786ac7ecfb75154daa42ebdca84a6a400cd2871fa2a406bb8ae",
        )
        self.assertEqual(self.native["baseline"]["values"][5], 899.9209324078314)
        self.assertEqual(
            self.native["baseline"]["values"][6], self.native["baseline"]["values"][3]
        )

    def test_cpp_graph_jvp_vjp_and_branch_local_differences(self) -> None:
        checked = self.result["verified"]
        self.assertEqual(set(checked["directions"]), set(replay.DIRECTIONS))
        self.assertLess(checked["max_normalized_fd_jvp_error"], 1e-6)
        output = self.native["output_order"]
        qg = dict(zip(output, self.native["directions"]["relative_qg16"]["jvp"]))
        self.assertGreater(qg["rhox"], 1100)
        self.assertAlmostEqual(qg["brs_reclamped"], 0, delta=1e-20)
        rhox = dict(zip(output, self.native["directions"]["relative_rhox16"]["jvp"]))
        self.assertLess(rhox["rhox"], -260)
        self.assertGreater(rhox["brs_reclamped"], 1e-8)

    def test_cpp_cap_crossing_is_separate_from_local_fd(self) -> None:
        checked = self.result["verified"]
        self.assertAlmostEqual(
            checked["qg_upper_cap_critical_relative_step"],
            6.798259282050436e-5,
            delta=1e-12,
        )
        self.assertLess(checked["qg_crossing_lower_raw_ratio"], 900)
        self.assertGreater(checked["qg_crossing_upper_raw_ratio"], 900)
        self.assertEqual(checked["qg_crossing_upper_selected_rhox"], 900)
        high = self.native["qg_cross_cap"]["high"]
        low = self.native["qg_cross_cap"]["low"]
        local = self.native["directions"]["relative_qg16"]["jvp"]
        qg_input = self.native["directions"]["relative_qg16"]["seed"]
        gap = (qg_input * 1.0001 - qg_input * 0.9999) / qg_input
        self.assertGreater(abs((high[5] - low[5]) / gap - local[5]), 100)

    def test_rehashed_output_mutations_fail_arithmetic(self) -> None:
        def altered(mutate):
            data = json.loads((HERE / "raw/cpp_result.json").read_text())
            mutate(data)
            raw = (json.dumps(data, sort_keys=True) + "\n").encode()
            return raw, hashlib.sha256(raw).hexdigest()

        bad, digest = altered(lambda d: d["baseline"]["raw_hex"].__setitem__(5, "0"))
        with self.assertRaisesRegex(ValueError, r"C\+\+ baseline"):
            replay.replay(output_override=bad, output_sha=digest)

        qv_bad, qv_digest = altered(
            lambda d: d["directions"]["relative_qv16"]["jvp"].__setitem__(
                5, d["directions"]["relative_qv16"]["jvp"][5] + 5e-13
            )
        )
        with self.assertRaisesRegex(ValueError, "independent analytic JVP"):
            replay.replay(output_override=qv_bad, output_sha=qv_digest)

        both_dots_bad, both_dots_digest = altered(
            lambda d: d["directions"]["relative_qg16"].update(jvp_dot=0.0, vjp_dot=0.0)
        )
        with self.assertRaisesRegex(
            ValueError, r"saved C\+\+ JVP dot versus verified JVP vector"
        ):
            replay.replay(output_override=both_dots_bad, output_sha=both_dots_digest)

        vjp_only_bad, vjp_only_digest = altered(
            lambda d: d["directions"]["relative_qg16"].__setitem__(
                "vjp_dot", d["directions"]["relative_qg16"]["vjp_dot"] + 1e-7
            )
        )
        with self.assertRaisesRegex(
            ValueError, r"saved C\+\+ VJP dot versus verified JVP vector"
        ):
            replay.replay(output_override=vjp_only_bad, output_sha=vjp_only_digest)

        cases = (
            lambda d: d["directions"]["relative_qg16"]["jvp"].__setitem__(5, 0.0),
            lambda d: d["directions"]["relative_qg16"]["finite_differences"]["1e-05"][
                "high"
            ].__setitem__(5, 900.0),
            lambda d: d["qg_cross_cap"]["high"].__setitem__(5, 899.0),
        )
        for mutate in cases:
            with self.subTest(mutate=mutate):
                bad, _ = altered(mutate)
                with self.assertRaises(ValueError):
                    replay.verify_output(
                        bad, self.fields, self.state_parent, self.producer, self.parent
                    )

    def test_duplicate_or_nonfinite_json_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            replay.parse_json(b'{"a":1,"a":2}')
        with self.assertRaisesRegex(ValueError, "nonfinite JSON"):
            replay.parse_json(b'{"a":NaN}')

    def test_cli(self) -> None:
        done = subprocess.run(
            [sys.executable, str(HERE / "replay.py")],
            cwd=HERE.parents[2],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("NATIVE_D1_PROGB_CPP_AD_REPLAY_PASSED", done.stdout)


if __name__ == "__main__":
    unittest.main()
