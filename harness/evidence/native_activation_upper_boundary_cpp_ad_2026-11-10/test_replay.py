"""Focused replay checks for the activation-boundary packet."""

from __future__ import annotations

import copy
import importlib.util
import json
import math
from pathlib import Path
import unittest


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("native_activation_boundary_replay", HERE / "replay.py")
if spec is None or spec.loader is None:
    raise RuntimeError("activation-boundary replay loader")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def boundary_packet() -> dict:
    return json.loads((HERE / "raw/activation_boundary.json").read_text())


def parent_packet() -> dict:
    return json.loads((module.PARENT / "raw/cpp_result.json").read_text())


class ActivationBoundaryReplayTests(unittest.TestCase):
    def test_full_replay_and_saved_activation_contract(self) -> None:
        actual = module.replay()
        saved = json.loads((HERE / "results.json").read_text())
        self.assertEqual(actual["schema"], "kdm6.native_activation_upper_boundary_cpp_ad_replay.v1")
        for key in (
            "activation_boundary_schema", "activation_boundary_input", "activation_thresholds",
            "activation_bisection_calls_by_axis", "activation_bisection_trace_rows",
            "activation_bisection_results", "activation_adjacent_nc_decomposition",
            "activation_interior_points", "activation_interior_ad_calls",
            "activation_one_sided_fd_calls", "activation_call_counts",
            "activation_baseline_upper_fraction_observed",
        ):
            self.assertEqual(actual[key], saved[key], key)
        self.assertEqual(actual["activation_bisection_trace_rows"], 168)
        self.assertEqual(actual["activation_call_counts"]["total_full_call_forwards"], 190)
        self.assertEqual(actual["activation_interior_ad_calls"], 4)
        self.assertEqual(actual["activation_one_sided_fd_calls"], 16)
        for axis in ("th16", "qv16"):
            self.assertEqual(set(actual["activation_interior_points"][axis]),
                             {"fraction_eq_one", "fraction_below_one"})
            for side in ("fraction_eq_one", "fraction_below_one"):
                point = actual["activation_interior_points"][axis][side]
                self.assertTrue(any(error < 1e-6
                                    for error in point["final_nc_one_sided_fd_relative_errors"]))
                self.assertEqual(point["jvp"]["final_nccn16"], 0.0)

    def test_packet_and_run_receipts_are_pinned(self) -> None:
        module.fixed_manifest()
        parent_raw = (module.PARENT / "raw/cpp_result.json").read_bytes()
        boundary_raw = (HERE / "raw/activation_boundary.json").read_bytes()
        module.provenance(parent_raw, boundary_raw)

    def test_full_replay_rejects_nonfinite_interior_endpoint_override(self) -> None:
        for invalid in (math.nan, math.inf, -math.inf):
            with self.subTest(invalid=invalid):
                data = copy.deepcopy(boundary_packet())
                endpoint = data["axes"]["th16"]["interior_points"]["fraction_eq_one"][
                    "one_sided_fd"]["step_scales"][0]["endpoint"]
                endpoint["final_nc16"] = invalid
                raw = json.dumps(data, sort_keys=True, allow_nan=True).encode()
                with self.assertRaisesRegex(ValueError, "nonstandard JSON numeric constant"):
                    module.replay(activation_override=(raw, module.sha(raw)))

    def test_bisection_and_adjacent_nc_arithmetic(self) -> None:
        result = module.verify_activation_boundary(boundary_packet(), parent_packet())
        self.assertEqual(result["activation_bisection_trace_rows"], 168)
        self.assertEqual(result["activation_call_counts"]["total_full_call_forwards"], 190)
        th = result["activation_adjacent_nc_decomposition"]["th16/sw_percent_0p48"]
        qv = result["activation_adjacent_nc_decomposition"]["qv16/sw_percent_0p48"]
        self.assertAlmostEqual(th["remainder_after_activation_rate_change"], 5.140900611877441e-7)
        self.assertEqual(qv["remainder_after_activation_rate_change"], 0.0)
        self.assertEqual(th["interpretation"], "adjacent endpoint arithmetic; not causal attribution")

    def test_trace_rejects_input_word_mutation(self) -> None:
        data = copy.deepcopy(boundary_packet())
        row = data["axes"]["th16"]["bisection"]["sw_percent_0p48"]["trace"][2]
        row["input_word"] = module.word(float(row["input"]) + 1.0e-6)
        with self.assertRaisesRegex(ValueError, "trace input/word"):
            module.verify_activation_boundary(data, parent_packet())

    def test_trace_rejects_source_arithmetic_mutation(self) -> None:
        data = copy.deepcopy(boundary_packet())
        row = data["axes"]["qv16"]["bisection"]["sw_percent_0p48"]["trace"][2]
        row["ncact_raw"] += 1.0
        with self.assertRaisesRegex(ValueError, "source-order ncact raw"):
            module.verify_activation_boundary(data, parent_packet())

    def test_trace_rejects_parent_seed_drift(self) -> None:
        data = copy.deepcopy(boundary_packet())
        row = data["axes"]["th16"]["bisection"]["sw_percent_0p48"]["trace"][0]
        row["final_nc16"] = math.nextafter(float(row["final_nc16"]), math.inf)
        with self.assertRaisesRegex(ValueError, "parent final NC anchor"):
            module.verify_activation_boundary(data, parent_packet())

    def test_full_replay_requires_both_interior_axes(self) -> None:
        for axis in ("th16", "qv16"):
            with self.subTest(axis=axis):
                data = copy.deepcopy(boundary_packet())
                del data["axes"][axis]["interior_points"]
                raw = json.dumps(data, sort_keys=True).encode()
                with self.assertRaisesRegex(ValueError, "activation interior point inventory"):
                    module.replay(activation_override=(raw, module.sha(raw)))

    def test_full_replay_requires_both_sides_per_axis(self) -> None:
        data = copy.deepcopy(boundary_packet())
        del data["axes"]["qv16"]["interior_points"]["fraction_below_one"]
        raw = json.dumps(data, sort_keys=True).encode()
        with self.assertRaisesRegex(ValueError, "activation interior point inventory"):
            module.replay(activation_override=(raw, module.sha(raw)))

    def test_full_replay_binds_terminal_trace_to_bracket_observations(self) -> None:
        data = copy.deepcopy(boundary_packet())
        bracket = data["axes"]["th16"]["bisection"]["sw_percent_0p48"]
        bracket["lower"]["final_nc16"] += 1.0
        gap = bracket["output_gaps"]["final_nc16"]
        gap["lower"] = bracket["lower"]["final_nc16"]
        gap["delta"] = gap["upper"] - gap["lower"]
        gap["ulp_distance"] = module.module_ulp_distance(gap["lower"], gap["upper"])
        gap["resolution_status"] = "resolved_above_one_output_ulp"
        raw = json.dumps(data, sort_keys=True).encode()
        with self.assertRaisesRegex(ValueError, "terminal trace observations match bracket endpoints"):
            module.replay(activation_override=(raw, module.sha(raw)))

    def test_full_replay_binds_repeated_trace_seed_observations(self) -> None:
        data = copy.deepcopy(boundary_packet())
        trace = data["axes"]["th16"]["bisection"][
            "activated_fraction_ge_1_observed_value"]["trace"]
        trace[0]["final_nc16"] += 1.0
        raw = json.dumps(data, sort_keys=True).encode()
        with self.assertRaisesRegex(ValueError, "repeated-input trace observations"):
            module.replay(activation_override=(raw, module.sha(raw)))

    def test_interior_rejects_vjp_word_mutation(self) -> None:
        data = copy.deepcopy(boundary_packet())
        row = data["axes"]["qv16"]["interior_points"]["fraction_below_one"]
        words = row["vjp_rows"]["final_nc16"]["raw_hex"]
        words[0] = format(int(words[0], 16) ^ 1, "016x")
        with self.assertRaisesRegex(ValueError, "VJP raw words"):
            module.verify_activation_boundary(data, parent_packet())

    def test_interior_rejects_branch_mask_mutation(self) -> None:
        data = copy.deepcopy(boundary_packet())
        row = data["axes"]["th16"]["interior_points"]["fraction_below_one"]
        row["one_sided_fd"]["step_scales"][0]["same_activation_branch"] = False
        with self.assertRaisesRegex(ValueError, "same-activation-branch flag"):
            module.verify_activation_boundary(data, parent_packet())

    def test_interior_rejects_duplicated_fd_endpoint_under_larger_step(self) -> None:
        data = copy.deepcopy(boundary_packet())
        steps = data["axes"]["th16"]["interior_points"]["fraction_eq_one"][
            "one_sided_fd"]["step_scales"]
        duplicated = copy.deepcopy(steps[1])
        duplicated["nominal_step"] = steps[0]["nominal_step"]
        steps[0] = duplicated
        with self.assertRaisesRegex(ValueError, "FD endpoint coordinate follows nominal step"):
            module.verify_activation_boundary(data, parent_packet())

    def test_activation_call_ledger_is_checked(self) -> None:
        data = copy.deepcopy(boundary_packet())
        data["call_counts"]["total_full_call_forwards"] -= 1
        with self.assertRaisesRegex(ValueError, "total forward-call ledger"):
            module.verify_activation_boundary(data, parent_packet())


if __name__ == "__main__":
    unittest.main()
