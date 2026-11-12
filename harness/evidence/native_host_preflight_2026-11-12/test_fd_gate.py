import copy
import importlib.util
import math
import unittest
from pathlib import Path

p = Path(__file__).with_name("fd_gate.py")
s = importlib.util.spec_from_file_location("fd_gate", p)
m = importlib.util.module_from_spec(s)
s.loader.exec_module(m)


def obs(value):
    out = [m.word(0.0)] * 468
    out[0] = m.word(value)
    return {
        "output_words": out,
        "reference_output_words": out.copy(),
        "masks": {"gate": True},
        "schedule": {"loops": m.word(1.0)},
    }


def example(stencil="central", signal_ulps=16, jvp_factor=1.0, component=1.0):
    center = [m.word(0.0)] * 624
    center[0] = m.word(1.0)
    direction = [m.word(0.0)] * 624
    direction[0] = m.word(component)
    base = 1.0
    low = base
    high = base + signal_ulps * math.ulp(base)
    plan = {
        "schema": "kdm6.output_fd_gate_plan.v1",
        "attestation": "caller_attests_registered_before_capture",
        "protocol_id": "synthetic-new-test",
        "output_index": 0,
        "center_input_words": center,
        "nominal_direction_words": direction,
        "steps": [],
    }
    samples = []
    for i, h in enumerate((0.125, 0.25)):
        lo = center.copy()
        hi = center.copy()
        lo[0] = m.word(1.0 - h * component if stencil == "central" else 1.0)
        hi[0] = m.word(1.0 + h * component)
        den = 2 * h if stencil == "central" else h
        actual = (m.val(hi[0]) - m.val(lo[0])) / den
        seed = [m.word(0.0)] * 624
        seed[0] = m.word(actual)
        step = {
            "id": str(i),
            "h_word": m.word(h),
            "stencil": stencil,
            "lower_input_words": lo,
            "upper_input_words": hi,
        }
        sample = {
            "id": str(i),
            "jvp_evaluation_input_words": center,
            "jvp_direction_words": seed,
            "jvp_output_words": [m.word((high - low) / den * jvp_factor)]
            + [m.word(0.0)] * 467,
            "jvp_forward_output_words": obs(1.0)["output_words"],
            "jvp_rc": 0,
            "lower": obs(low),
            "upper": obs(high),
        }
        if stencil == "forward":
            plus2 = center.copy()
            plus2[0] = m.word(1.0 + 2 * h * component)
            step["plus2_input_words"] = plus2
            sample["plus2"] = obs(high)
        plan["steps"].append(step)
        samples.append(sample)
    return {
        "schema": m.SCHEMA,
        "intent": "prospective_pre_capture_plan",
        "data_origin": "new_prospective_acquisition",
        "plan": plan,
        "plan_sha256": m.plan_sha(plan),
        "center": obs(1.0),
        "samples": samples,
    }


class GateTests(unittest.TestCase):
    def test_16_ulp_and_two_distinct_steps(self):
        d = example(signal_ulps=16)
        self.assertEqual(
            m.evaluate(d, allow_synthetic=True)["tag"], "LOCAL_NUMERIC_CONSISTENT"
        )
        d = example(signal_ulps=15)
        self.assertEqual(m.evaluate(d, allow_synthetic=True)["tag"], "UNRESOLVED")
        d = example(signal_ulps=16)
        d["plan"]["steps"][1]["h_word"] = d["plan"]["steps"][0]["h_word"]
        d["plan_sha256"] = m.plan_sha(d["plan"])
        with self.assertRaisesRegex(ValueError, "distinct h"):
            m.evaluate(d, allow_synthetic=True)

    def test_relative_and_rounding_tags(self):
        self.assertEqual(
            m.evaluate(example(jvp_factor=0.99), allow_synthetic=True)["tag"],
            "ROUNDING_LIMITED",
        )
        self.assertEqual(
            m.evaluate(example(jvp_factor=2.0), allow_synthetic=True)["tag"],
            "NUMERIC_MISMATCH",
        )

    def test_crossing_degenerate_and_zero_jvp(self):
        d = example()
        d["samples"][0]["upper"]["masks"]["gate"] = False
        self.assertEqual(m.evaluate(d, allow_synthetic=True)["tag"], "BRANCH_CROSSING")
        d = example(component=math.ulp(0.0))
        self.assertEqual(
            m.evaluate(d, allow_synthetic=True)["tag"], "DIRECTION_DEGENERATE"
        )
        d = example(jvp_factor=0.0)
        self.assertEqual(m.evaluate(d, allow_synthetic=True)["tag"], "UNRESOLVED")

    def test_input_seed_and_parity_fail_closed(self):
        d = example()
        d["samples"][0]["jvp_direction_words"][0] = m.word(2.0)
        with self.assertRaisesRegex(ValueError, "JVP direction"):
            m.evaluate(d, allow_synthetic=True)
        d = example()
        d["samples"][0]["upper"]["reference_output_words"][0] = m.word(2.0)
        with self.assertRaisesRegex(ValueError, "output parity"):
            m.evaluate(d, allow_synthetic=True)
        d = example()
        d["plan"]["steps"][0]["upper_input_words"][0] = m.word(9.0)
        d["plan_sha256"] = m.plan_sha(d["plan"])
        with self.assertRaisesRegex(ValueError, "planned perturbation"):
            m.evaluate(d, allow_synthetic=True)

    def test_fail_closed_mixed_tags_and_zero_jvp_signal(self):
        d = example(jvp_factor=2.0)
        d["samples"][1]["jvp_output_words"][0] = m.word(0.0)
        result = m.evaluate(d, allow_synthetic=True)
        self.assertEqual(result["tag"], "NUMERIC_MISMATCH")
        self.assertTrue(result["steps"][1]["zero_jvp_resolved_signal"])
        self.assertEqual(
            result["gate_eligibility"],
            "NOT_ELIGIBLE: numeric classification is schema-only until independent execution receipts are verified",
        )

    def test_canonical_synthetic_data_never_certified(self):
        plan = m.canonical_plan(
            m.PACKET.read_bytes(), m.PACKET_GZ_SHA, "lower", "nc", 0
        )
        center = plan["center_input_words"]
        center_output = obs(0.0)
        samples = []
        for step in plan["steps"]:
            h = m.val(step["h_word"])
            lo = step["lower_input_words"]
            hi = step["upper_input_words"]
            actual = [(m.val(b) - m.val(a)) / h for a, b in zip(lo, hi)]
            jvp = [m.word(0.0)] * 468
            jvp[0] = m.word(actual[8 * 39 + 15])
            samples.append(
                {
                    "id": step["id"],
                    "jvp_evaluation_input_words": center,
                    "jvp_direction_words": [m.word(x) for x in actual],
                    "jvp_output_words": jvp,
                    "jvp_forward_output_words": center_output["output_words"],
                    "jvp_rc": 0,
                    "lower": obs(0.0),
                    "upper": obs(m.val(hi[8 * 39 + 15])),
                    "plus2": obs(m.val(step["plus2_input_words"][8 * 39 + 15])),
                }
            )
        data = {
            "schema": m.SCHEMA,
            "intent": "prospective_pre_capture_plan",
            "data_origin": "new_prospective_acquisition",
            "center_name": "lower",
            "direction": "nc",
            "packet_plan_sha256": m.PACKET_GZ_SHA,
            "plan": plan,
            "plan_sha256": m.plan_sha(plan),
            "center": center_output,
            "samples": samples,
        }
        result = m.evaluate(data)
        self.assertEqual(result["tag"], "LOCAL_NUMERIC_CONSISTENT")
        self.assertEqual(result["provenance_status"], "UNVERIFIED_EXECUTION_RECEIPTS")
        self.assertTrue(result["gate_eligibility"].startswith("NOT_ELIGIBLE"))

    def test_relative_threshold_boundary(self):
        self.assertEqual(
            m.evaluate(example(jvp_factor=1.0000009), allow_synthetic=True)["tag"],
            "LOCAL_NUMERIC_CONSISTENT",
        )
        self.assertEqual(
            m.evaluate(example(jvp_factor=1.0000011), allow_synthetic=True)["tag"],
            "ROUNDING_LIMITED",
        )

    def test_single_h_unresolved(self):
        d = example()
        d["plan"]["steps"] = d["plan"]["steps"][:1]
        d["samples"] = d["samples"][:1]
        d["plan_sha256"] = m.plan_sha(d["plan"])
        self.assertEqual(m.evaluate(d, allow_synthetic=True)["tag"], "UNRESOLVED")

    def test_canonical_plan_and_rehashed_tamper(self):
        canonical = m.canonical_plan(
            m.PACKET.read_bytes(), m.PACKET_GZ_SHA, "lower", "nc", 0
        )
        self.assertEqual(len(canonical["steps"]), 3)
        d = example()
        d["center_name"] = "lower"
        d["direction"] = "nc"
        d["packet_plan_sha256"] = m.PACKET_GZ_SHA
        d["plan"] = copy.deepcopy(canonical)
        d["plan"]["center_input_words"][0] = m.word(0.0)
        d["plan_sha256"] = m.plan_sha(d["plan"])
        with self.assertRaisesRegex(ValueError, "pinned canonical packet"):
            m.evaluate(d)

    def test_forward_segment_observation(self):
        d = example(stencil="forward")
        out = m.evaluate(d, allow_synthetic=True)
        self.assertEqual(out["tag"], "LOCAL_NUMERIC_CONSISTENT")
        self.assertTrue(out["steps"][0]["forward_segments"]["plus_equals_plus2"])
        self.assertNotEqual(
            out["steps"][0]["forward_segments"]["center_to_plus_delta"], 0.0
        )
        self.assertEqual(
            out["steps"][0]["forward_segments"]["plus_to_plus2_delta"], 0.0
        )

    def test_historical_and_nonfinite_rejected(self):
        d = example()
        d["data_origin"] = "retrospective_586"
        with self.assertRaisesRegex(ValueError, "prospective input"):
            m.evaluate(d, allow_synthetic=True)
        d = example()
        d["samples"][0]["jvp_output_words"][0] = "7ff8000000000000"
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            m.evaluate(d, allow_synthetic=True)
        d = example()
        d["plan_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "plan SHA"):
            m.evaluate(d, allow_synthetic=True)


if __name__ == "__main__":
    unittest.main()
