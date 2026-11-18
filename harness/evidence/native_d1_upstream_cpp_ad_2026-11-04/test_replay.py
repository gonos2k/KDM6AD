"""Same-call native entry work2/ProgB-to-D1 C++ AD regression."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "native_d1_upstream_replay", HERE / "replay.py"
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("native upstream replay import failed")
replay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replay)


def changed(stage: str, field: str, k: int, raw_hex: str) -> bytes:
    lines = (HERE / replay.CAPTURE).read_text().splitlines()
    found = 0
    for i, line in enumerate(lines):
        cells = line.split(",")
        if len(cells) == 11 and (cells[4], cells[7], cells[8]) == (
            str(k),
            stage,
            field,
        ):
            cells[-1] = raw_hex
            lines[i] = ",".join(cells)
            found += 1
    if found != 1:
        raise AssertionError("mutation target is not unique")
    return ("\n".join(lines) + "\n").encode()


class NativeD1UpstreamCppAD(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = replay.replay()
        cls.cpp = replay.parse_json((HERE / "raw/cpp_result.json").read_bytes())

    def test_same_call_entry_capture_and_cpp_baseline(self) -> None:
        result = self.result
        self.assertEqual(result["native_rows"], 9516)
        self.assertEqual(result["parent_rows_raw_bit_equal"], 8892)
        self.assertEqual(
            result["upstream_baseline"]["levels_thermo_progb_reference_checked"], 39
        )
        if not replay.same_reference_runtime():
            print(
                "PORTABLE_UPSTREAM_REFERENCE_ULPS",
                json.dumps(
                    {
                        "producer": result["upstream_baseline"][
                            "max_reference_ulp_by_field"
                        ],
                        "baseline": result["verified_cpp"][
                            "max_cpp_python_baseline_ulps"
                        ],
                        "endpoints": result["verified_cpp"][
                            "max_cpp_python_endpoint_ulps"
                        ],
                        "jvp_abs": result["verified_cpp"][
                            "max_abs_cpp_python_jvp_error"
                        ],
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
        self.assertIn(16, result["upstream_baseline"]["active_rhox_native_levels"])
        self.assertEqual(
            result["verified_cpp"]["cpp_baseline_raw_bit_equal_outputs"], 16
        )
        native = result["upstream_baseline"]["native16"]
        self.assertEqual(native["work2"], 200.29441022254784)
        self.assertEqual(native["precg2"], 24.35783384950257)
        self.assertEqual(native["rhox"], 899.9209324078313)
        self.assertEqual(
            result["source_and_runs"]["native_endpoint_sha256"],
            "225d2cabe8a466304c06ba1a04638b84c8456b8477326b6852c9217360440070",
        )

    def test_upstream_producer_jvp_and_branch_local_fd(self) -> None:
        verified = self.result["verified_cpp"]
        self.assertEqual(set(verified["directions"]), set(replay.DIRECTIONS))
        self.assertLess(verified["max_abs_cpp_python_jvp_error"], 1e-10)
        self.assertLess(verified["max_normalized_cpp_fd_jvp_error"], 3e-5)
        order = self.cpp["output_order"]
        pressure = dict(zip(order, self.cpp["directions"]["relative_p16"]["jvp"]))
        self.assertAlmostEqual(pressure["work2"], 66.76479673103562, delta=1e-10)
        self.assertLess(pressure["ps"], 0)
        self.assertEqual(pressure["entry_precg2"], 0)
        temp = dict(zip(order, self.cpp["directions"]["absolute_t16"]["jvp"]))
        self.assertAlmostEqual(temp["work2"], -0.5376620814389188, delta=1e-10)
        qg = dict(zip(order, self.cpp["directions"]["relative_qg16"]["jvp"]))
        brs = dict(zip(order, self.cpp["directions"]["relative_brs_pre16"]["jvp"]))
        self.assertGreater(qg["entry_precg2"], 5)
        self.assertLess(brs["entry_precg2"], -5)
        self.assertGreater(qg["entry_rhox"], 899)
        self.assertLess(brs["entry_rhox"], -899)

    def test_entry_and_postmelt_upper_cap_crossing_is_separate(self) -> None:
        cross = self.cpp["qg_cross_cap"]
        self.assertEqual(cross["high"][2], 900.0)
        self.assertEqual(cross["high"][11], 900.0)
        self.assertLess(cross["low"][2], 900.0)
        self.assertLess(cross["low"][11], 900.0)
        critical = self.result["verified_cpp"][
            "qg_entry_upper_cap_critical_relative_step"
        ]
        self.assertGreater(critical, 1e-5)
        self.assertLess(critical, 1e-4)
        self.assertAlmostEqual(critical, 8.786059899409143e-5, delta=1e-12)

    def test_rehashed_native_input_and_producer_mutations_fail(self) -> None:
        for stage, field, raw in (
            (replay.ENTRY, "brs", "0"),
            (replay.PRODUCER, "work2", "0"),
            (replay.PRODUCER, "precg2", "0"),
        ):
            with self.subTest(stage=stage, field=field):
                bad = changed(stage, field, replay.TARGET, raw)
                with self.assertRaises(ValueError):
                    replay.replay(
                        capture_override=bad,
                        capture_sha=hashlib.sha256(bad).hexdigest(),
                    )
        old = changed("d1_postmelt_progb", "rhox", replay.TARGET, "0")
        with self.assertRaisesRegex(ValueError, "parent 8892 rows"):
            replay.replay(
                capture_override=old, capture_sha=hashlib.sha256(old).hexdigest()
            )

    def test_portable_ulp_limits_keep_exact_handoffs(self) -> None:
        base = self.result["upstream_baseline"]["native16"]["work2"]
        self.assertIn("entry_precg2", replay.ENDPOINT_PORTABLE_ULPS)
        self.assertNotIn("entry_rhox", replay.ENDPOINT_PORTABLE_ULPS)
        candidate = base
        with patch.object(replay, "same_reference_runtime", return_value=False):
            for _ in range(4):
                candidate = math.nextafter(candidate, math.inf)
            self.assertEqual(
                replay.check_reference_word(
                    replay.word(base), candidate, "work2 portable", max_ulps=4
                ),
                4.0,
            )
            too_far = math.nextafter(candidate, math.inf)
            with self.assertRaisesRegex(ValueError, "exceeds 4"):
                replay.check_reference_word(
                    replay.word(base), too_far, "work2 portable", max_ulps=4
                )
            endpoint_ulp = base
            for _ in range(replay.ENDPOINT_PORTABLE_MAX_ULPS):
                endpoint_ulp = math.nextafter(endpoint_ulp, math.inf)
            self.assertEqual(
                replay.check_reference_word(
                    replay.word(base),
                    endpoint_ulp,
                    "dependent endpoint",
                    max_ulps=replay.ENDPOINT_PORTABLE_MAX_ULPS,
                ),
                float(replay.ENDPOINT_PORTABLE_MAX_ULPS),
            )
            with self.assertRaisesRegex(ValueError, "exceeds 4"):
                replay.check_reference_word(
                    replay.word(base),
                    math.nextafter(endpoint_ulp, math.inf),
                    "dependent endpoint",
                    max_ulps=replay.ENDPOINT_PORTABLE_MAX_ULPS,
                )
            with self.assertRaisesRegex(ValueError, "raw bit mismatch"):
                replay.check_reference_word(
                    replay.word(base),
                    math.nextafter(base, math.inf),
                    "unaffected producer",
                    max_ulps=0,
                )
            one_ulp = replay.word(math.nextafter(base, math.inf))
            bad = changed(replay.PRODUCER, "work2", replay.TARGET, one_ulp)
            with self.assertRaisesRegex(ValueError, "upstream-to-D1 consumed input"):
                replay.replay(
                    capture_override=bad, capture_sha=hashlib.sha256(bad).hexdigest()
                )
        with patch.object(replay, "same_reference_runtime", return_value=True):
            with self.assertRaisesRegex(ValueError, "raw bit mismatch"):
                replay.check_reference_word(
                    replay.word(base),
                    math.nextafter(base, math.inf),
                    "same runtime",
                    max_ulps=4,
                )

    def test_rehashed_cpp_jvp_dots_and_endpoint_mutations_fail(self) -> None:
        def altered(mutate):
            data = json.loads((HERE / "raw/cpp_result.json").read_text())
            mutate(data)
            raw = (json.dumps(data, sort_keys=True) + "\n").encode()
            return raw, hashlib.sha256(raw).hexdigest()

        def forge_qv_cancellation(data):
            section = data["directions"]["relative_qv16"]
            section["jvp"][11] += 1e-13
            dot = math.fsum(w * j for w, j in zip(replay.WEIGHTS, section["jvp"]))
            section["jvp_dot"] = dot
            section["vjp_dot"] = dot

        qv_bad, qv_digest = altered(forge_qv_cancellation)
        with self.assertRaisesRegex(ValueError, "independent Python producer JVP"):
            replay.replay(cpp_output_override=qv_bad, cpp_output_sha=qv_digest)

        cases = (
            lambda d: d["directions"]["relative_p16"]["jvp"].__setitem__(0, 0.0),
            lambda d: d["directions"]["relative_qg16"].update(jvp_dot=0.0, vjp_dot=0.0),
            lambda d: d["directions"]["relative_qg16"].__setitem__(
                "vjp_dot", d["directions"]["relative_qg16"]["vjp_dot"] + 1e-7
            ),
            lambda d: d["directions"]["relative_qg16"]["finite_differences"]["1e-05"][
                "high"
            ].__setitem__(2, 900.0),
            lambda d: d["qg_cross_cap"]["high"].__setitem__(11, 899.0),
        )
        for mutate in cases:
            with self.subTest(mutate=mutate):
                bad, digest = altered(mutate)
                with self.assertRaises(ValueError):
                    replay.replay(cpp_output_override=bad, cpp_output_sha=digest)

    def test_pressure_postmelt_roundoff_components_are_bounded_not_resolved(
        self,
    ) -> None:
        data = json.loads((HERE / "raw/cpp_result.json").read_text())
        section = data["directions"]["relative_p16"]
        for i in (11, 13, 14):  # postmelt rhox, avtg, bvtg
            section["jvp"][i] = 0.0
        dot = math.fsum(w * j for w, j in zip(replay.WEIGHTS, section["jvp"]))
        section["jvp_dot"] = dot
        section["vjp_dot"] = dot
        raw = (json.dumps(data, sort_keys=True) + "\n").encode()
        result = replay.replay(
            cpp_output_override=raw, cpp_output_sha=hashlib.sha256(raw).hexdigest()
        )
        self.assertEqual(
            result["verified_cpp"]["cpp_baseline_raw_bit_equal_outputs"], 16
        )

    def test_rehashed_identity_or_order_mutation_fails(self) -> None:
        raw = (HERE / replay.CAPTURE).read_text()
        bad = raw.replace(
            ",27945,23,32248,39,d1_upstream_entry,qg,",
            ",27945,23,32712,39,d1_upstream_entry,qg,",
            1,
        ).encode()
        self.assertNotEqual(bad, raw.encode())
        with self.assertRaisesRegex(ValueError, "upstream call/tile identity"):
            replay.replay(
                capture_override=bad, capture_sha=hashlib.sha256(bad).hexdigest()
            )
        lines = raw.splitlines()
        first = next(
            i for i, line in enumerate(lines) if ",d1_upstream_entry,qg," in line
        )
        lines[first], lines[first + 1] = lines[first + 1], lines[first]
        reordered = ("\n".join(lines) + "\n").encode()
        with self.assertRaisesRegex(ValueError, "upstream row order"):
            replay.replay(
                capture_override=reordered,
                capture_sha=hashlib.sha256(reordered).hexdigest(),
            )

    def test_cli(self) -> None:
        done = subprocess.run(
            [sys.executable, str(HERE / "replay.py")],
            cwd=HERE.parents[2],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("NATIVE_D1_UPSTREAM_CPP_AD_REPLAY_PASSED", done.stdout)


if __name__ == "__main__":
    unittest.main()
