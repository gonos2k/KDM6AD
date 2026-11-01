"""Synthetic smoke checks; native acceptance requires an authenticated capture."""

import importlib
import struct
import unittest

replay = importlib.import_module(
    "harness.evidence.native_c5_limiter_call_2026-11-01.replay").replay


class ReplaySmoke(unittest.TestCase):
    def test_zero_case_and_mutation(self):
        stages = importlib.import_module(
            "harness.evidence.native_c5_limiter_call_2026-11-01.capture_schema").STAGES

        rows = {}
        for stage, fields in stages.items():
            for field in fields:
                v = 0.0
                if field in ("dtcld", "forcing.dend", "params.deni", "params.di125"):
                    v = 1.0
                if field == "fconst.pi_f32":
                    v = 3.1415927410125732
                dtype = (
                    "f32"
                    if stage == "abi_ingress" or field == "fconst.pi_f32"
                    else "bool"
                    if field
                    in ("icenuc.ifsat", "depsub.ifsat", "depsub.ice_complete_sublim")
                    else "f64"
                )
                raw = (
                    int(bool(v))
                    if dtype == "bool"
                    else int.from_bytes(
                        struct.pack("<f" if dtype == "f32" else "<d", v), "little"
                    )
                )
                rows[(stage, field)] = {"dtype": dtype, "raw_hex": format(raw, "x")}
        result = replay(rows)
        self.assertEqual(result.tolist(), [0.0, 0.0])
        rows[("c5_out", "agg.psaut")]["raw_hex"] = format(
            int.from_bytes(struct.pack("<d", 1.0), "little"), "x"
        )
        with self.assertRaises(ValueError):
            replay(rows)


if __name__ == "__main__":
    unittest.main()
