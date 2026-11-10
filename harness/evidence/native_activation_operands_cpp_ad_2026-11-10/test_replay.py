"""Parent-pin smoke tests for the native activation operand child packet."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import math
from pathlib import Path
import struct
import unittest
from unittest import mock


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("native_activation_operands_replay", HERE / "replay.py")
if spec is None or spec.loader is None:
    raise RuntimeError("activation operand replay loader")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def make_exact_tie_row() -> dict:
    nc, nccn, dt, fraction = 1.5e8, 1.0e8, 20.0, 1.0
    preclamp = -nc + ((nccn + nc) * fraction)
    raw_rate = max(preclamp, 0.0) / dt
    cap = max(nccn, 0.0) / dt

    def word(value: float) -> str:
        return format(struct.unpack(">Q", struct.pack(">d", value))[0], "016x")

    return {
        "sw_percent": 0.48, "sw_positive": True,
        "activated_fraction": fraction, "nc_input": nc, "nccn_input": nccn, "dtcld": dt,
        "ncact_raw": raw_rate, "ncact_rate_cap": cap,
        "ncact_raw_minus_cap": raw_rate - cap, "ncact_cap_active": False,
        "ncact_cap_tie": True, "ncact": raw_rate,
        "operand_values": {
            "sw_ratio": 1.0, "sw_ratio_word": word(1.0),
            "safe_pow_clamped_base_diagnostic": 1.0,
            "safe_pow_clamped_base_diagnostic_word": word(1.0),
            "activation_fraction_one": 1.0, "activation_fraction_pow": 1.0,
            "activation_fraction_pow_word": word(1.0), "activation_fraction_min_output": 1.0,
            "activation_fraction_pow_lt_one": False,
            "activation_fraction_pow_eq_one": True,
            "activation_fraction_pow_gt_one": False,
            "ncact_preclamp_fma": preclamp, "ncact_clamped_numerator": preclamp,
            "ncact_nccn_rate_cap": cap, "ncact_nccn_rate_cap_word": word(cap),
            "ncact_min_output": raw_rate,
            "ncact_raw_lt_nccn_rate_cap": False,
            "ncact_raw_eq_nccn_rate_cap": True,
            "ncact_raw_gt_nccn_rate_cap": False,
        },
    }


def operand_packet() -> dict:
    return json.loads((HERE / "raw/activation_boundary.json").read_text())


def rehashed_override(change) -> tuple[bytes, str]:
    data = operand_packet()
    change(data)
    raw = (json.dumps(data, sort_keys=True, allow_nan=True) + "\n").encode()
    return raw, hashlib.sha256(raw).hexdigest()


def rehashed_default_cpp_override(change) -> tuple[bytes, str]:
    data = json.loads((HERE / "raw/cpp_result.json").read_text())
    change(data)
    raw = (json.dumps(data, sort_keys=True, allow_nan=True) + "\n").encode()
    return raw, hashlib.sha256(raw).hexdigest()


def shifted_ulps(value: float, offset: int) -> float:
    target = math.inf if offset >= 0 else -math.inf
    for _ in range(abs(offset)):
        value = math.nextafter(value, target)
    return value


def captured_pow_by_base() -> dict[str, float]:
    captured: dict[str, float] = {}
    for _, row, _ in module._actual_operand_call_rows(operand_packet()):
        op = row["operand_values"]
        key = module.f64_word(op["safe_pow_clamped_base_diagnostic"])
        value = float(op["activation_fraction_pow"])
        if key in captured and module.f64_word(captured[key]) != module.f64_word(value):
            raise ValueError("original repeated safe_pow values disagree")
        captured[key] = value
    return captured


class PowOffsetMath:
    """Place the independent pow result at a chosen ULP offset from C++ capture."""

    def __init__(self, offset: int, captured: dict[str, float]) -> None:
        self.offset = offset
        self.captured = captured

    def __getattr__(self, name: str):
        return getattr(math, name)

    def pow(self, base: float, exponent: float) -> float:
        if exponent == module.ACTK:
            key = module.f64_word(base)
            if key in self.captured:
                return shifted_ulps(self.captured[key], self.offset)
        return math.pow(base, exponent)


class ParentPinTests(unittest.TestCase):
    def test_source_order_links_replay_independent_exact_ties(self) -> None:
        result = module.verify_operand_observation(make_exact_tie_row(), "synthetic tie")
        self.assertEqual(result["pow_operand_class"], "equal_one")
        self.assertEqual(result["ncact_rate_cap_class"], "tie")

    def test_pow_mutation_is_rejected_even_if_min_output_stays_one(self) -> None:
        row = make_exact_tie_row()
        values = row["operand_values"]
        values["activation_fraction_pow"] = math.nextafter(1.0, math.inf)
        values["activation_fraction_pow_word"] = module.f64_word(values["activation_fraction_pow"])
        values["activation_fraction_pow_eq_one"] = False
        values["activation_fraction_pow_gt_one"] = True
        with self.assertRaisesRegex(ValueError, "exact safe_pow\(1, ACTK\)"):
            module.verify_operand_observation(row, "pow mutation")

    def test_rate_cap_operand_mutation_is_rejected(self) -> None:
        row = make_exact_tie_row()
        values = row["operand_values"]
        values["ncact_nccn_rate_cap"] = math.nextafter(
            values["ncact_nccn_rate_cap"], math.inf)
        values["ncact_nccn_rate_cap_word"] = module.f64_word(
            values["ncact_nccn_rate_cap"])
        with self.assertRaisesRegex(ValueError, "source order: ncact_nccn_rate_cap"):
            module.verify_operand_observation(row, "rate cap mutation")

    def test_parent_replay_is_pinned_and_fully_verified(self) -> None:
        parent_module, summary = module.verified_parent()
        self.assertEqual(module.sha((module.PARENT / "replay.py").read_bytes()),
                         module.PARENT_REPLAY_SHA256)
        self.assertEqual(summary["activation_bisection_trace_rows"], 168)
        self.assertEqual(summary["activation_interior_ad_calls"], 4)
        self.assertEqual(summary["activation_one_sided_fd_calls"], 16)
        self.assertEqual(summary["activation_call_counts"]["total_full_call_forwards"], 190)
        parent_tree = {"schema": "parent", "baseline": {
            "input_word": "3ff", "d1_branch": {}, "value": 1.25, "raw": ["3ff4"]}}
        child_tree = {"schema": module.OPERAND_BOUNDARY_SCHEMA,
                      "parent_schema": "kdm6.native_d1_activation_boundary.v1", "baseline": {
            "input_word": "3ff", "d1_branch": {}, "event_id": "baseline",
            "forward_call_ordinal": 1, "trace_index": -1, "value": 1.25,
            "raw": ["3ff4"], "operand_values": {"sw_ratio": 1.02}}}
        module.compare_parent_projection(parent_tree, child_tree, parent_module)
        child_tree["baseline"]["raw"][0] = "3ff5"
        with self.assertRaisesRegex(ValueError, "changes parent value"):
            module.compare_parent_projection(parent_tree, child_tree, parent_module)

    def test_full_replay_and_saved_contract(self) -> None:
        actual = module.replay()
        saved = json.loads((HERE / "results.json").read_text())
        self.assertEqual(actual, saved)
        self.assertEqual(actual["schema"], "kdm6.native_activation_operands_cpp_ad_replay.v1")
        self.assertEqual(actual["scientific_status"], "INCONCLUSIVE")
        self.assertEqual(actual["physical_unit_status"], "INCONCLUSIVE")
        self.assertEqual(actual["operand_bearing_forward_events"], 189)
        self.assertEqual(actual["forward_call_ordinal_first"], 1)
        self.assertEqual(actual["forward_call_ordinal_last"], 189)
        self.assertEqual(actual["operand_observation_objects_verified"], 197)
        self.assertEqual(actual["operand_output_gaps_verified"], 36)
        self.assertEqual(actual["operand_comparison_classifications"], {
            "pow_below_one": 104, "pow_equal_one": 0, "pow_above_one": 85,
            "ncact_raw_below_cap": 104, "ncact_tie": 85, "ncact_raw_above_cap": 0,
        })

    def test_rehashed_parent_old_field_drift_is_rejected(self) -> None:
        override = rehashed_override(lambda data: data["baseline"].update(
            final_nc16=math.nextafter(data["baseline"]["final_nc16"], math.inf)))
        with self.assertRaisesRegex(ValueError, "changes parent value"):
            module.replay(operand_override=override)

    def test_default_vjp_old_row_drift_is_rejected(self) -> None:
        def change(data: dict) -> None:
            row = data["vjp"]["final_nc16"]
            row[0] = math.nextafter(row[0], math.inf)

        with self.assertRaisesRegex(ValueError, r"default C\+\+ parent raw field: vjp"):
            module.replay(default_cpp_override=rehashed_default_cpp_override(change))

    def test_default_thermal_endpoint_drift_is_rejected(self) -> None:
        def change(data: dict) -> None:
            raw = data["thermal_directions"]["directions"]["th16_abs"][
                "finite_differences"]["0.001"]["high_final_raw"]
            raw[123] = format(int(raw[123], 16) ^ 1, "016x")

        with self.assertRaisesRegex(ValueError, "default thermal FD parent data"):
            module.replay(default_cpp_override=rehashed_default_cpp_override(change))

    def test_rehashed_pow_operand_outside_portable_bound_is_rejected(self) -> None:
        def change(data: dict) -> None:
            op = data["baseline"]["operand_values"]
            expected = module.math.pow(max(op["sw_ratio"], module.EPS), module.ACTK)
            value = shifted_ulps(expected, 17)
            op["activation_fraction_pow"] = value
            op["activation_fraction_pow_word"] = module.f64_word(value)

        with self.assertRaisesRegex(ValueError, "safe_pow within portable ULP"):
            module.replay(operand_override=rehashed_override(change))

    def test_pow_ulp_boundary_is_portable_across_allowed_libm_offsets(self) -> None:
        saved = json.loads((HERE / "results.json").read_text())
        captured = captured_pow_by_base()
        for offset in (-16, -1, 1, 16):
            with self.subTest(offset=offset), mock.patch.object(
                module, "math", PowOffsetMath(offset, captured)
            ):
                # The original C++ evidence remains valid throughout the
                # diagnostic's declared library-difference interval.
                self.assertEqual(module.replay(), saved)
                for distance in (16, 17):
                    def change(data: dict) -> None:
                        op = data["baseline"]["operand_values"]
                        expected = module.math.pow(max(op["sw_ratio"], module.EPS), module.ACTK)
                        value = shifted_ulps(expected, distance)
                        op["activation_fraction_pow"] = value
                        op["activation_fraction_pow_word"] = module.f64_word(value)

                    changed = rehashed_override(change)
                    if distance == 16:
                        module.replay(operand_override=changed)
                    else:
                        with self.assertRaisesRegex(ValueError, "safe_pow within portable ULP"):
                            module.replay(operand_override=changed)

    def test_rehashed_repeated_operand_drift_is_rejected(self) -> None:
        def change(data: dict) -> None:
            row = data["axes"]["th16"]["bisection"]["sw_percent_0p48"]["trace"][5]
            op = row["operand_values"]
            value = math.nextafter(op["activation_fraction_pow"], math.inf)
            op["activation_fraction_pow"] = value
            op["activation_fraction_pow_word"] = module.f64_word(value)

        with self.assertRaisesRegex(ValueError, "repeated-input operand values"):
            module.replay(operand_override=rehashed_override(change))

    def test_rehashed_rate_cap_operand_is_rejected(self) -> None:
        def change(data: dict) -> None:
            op = data["baseline"]["operand_values"]
            value = math.nextafter(op["ncact_nccn_rate_cap"], math.inf)
            op["ncact_nccn_rate_cap"] = value
            op["ncact_nccn_rate_cap_word"] = module.f64_word(value)

        with self.assertRaisesRegex(ValueError, "source order: ncact_nccn_rate_cap"):
            module.replay(operand_override=rehashed_override(change))

    def test_rehashed_operand_vjp_jvp_and_fd_mutations_are_rejected(self) -> None:
        mutations = (
            (lambda data: data["axes"]["th16"]["interior_points"]["fraction_below_one"][
                "jvp"].update(ncact_min_output=0.0), "ncact min JVP to legacy output"),
            (lambda data: data["axes"]["qv16"]["interior_points"]["fraction_below_one"][
                "vjp_rows"]["ncact_min_output"]["raw_hex"].__setitem__(
                    0, format(int(data["axes"]["qv16"]["interior_points"]["fraction_below_one"][
                        "vjp_rows"]["ncact_min_output"]["raw_hex"][0], 16) ^ 1, "016x")),
             "operand VJP raw word"),
            (lambda data: data["axes"]["th16"]["interior_points"]["fraction_below_one"][
                "one_sided_fd"]["step_scales"][0]["outputs"]["activation_fraction_pow"].update(
                    fd=0.0), "FD operand quotient"),
            (lambda data: data["axes"]["qv16"]["interior_points"]["fraction_eq_one"][
                "one_sided_fd"]["step_scales"][0].update(same_operand_branch=False),
             "same-operand-branch diagnostic"),
        )
        for change, message in mutations:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    module.replay(operand_override=rehashed_override(change))

    def test_rehashed_event_ordinal_and_unknown_operand_key_are_rejected(self) -> None:
        changes = (
            (lambda data: data["baseline"].update(forward_call_ordinal=2),
             "captured call ordinals preserve"),
            (lambda data: data["baseline"]["operand_values"].update(unexpected_operand=1.0),
             "operand field inventory"),
        )
        for change, message in changes:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    module.replay(operand_override=rehashed_override(change))


if __name__ == "__main__":
    unittest.main()
