import importlib
import struct
import unittest

p = importlib.import_module("harness.evidence.native_c5_limiter_call_2026-11-01.replay")
s = importlib.import_module("harness.evidence.native_c5_limiter_call_2026-11-01.capture_schema")


class DerivativeSmoke(unittest.TestCase):
    def test_nonzero_directions(self):
        rows = {}

        def setv(stage, field, value):
            dtype = (
                "f32"
                if stage == "abi_ingress" or field == "fconst.pi_f32"
                else "bool"
                if field
                in ("icenuc.ifsat", "depsub.ifsat", "depsub.ice_complete_sublim")
                else "f64"
            )
            b = (
                int(bool(value))
                if dtype == "bool"
                else int.from_bytes(
                    struct.pack("<f" if dtype == "f32" else "<d", value), "little"
                )
            )
            rows[(stage, field)] = {"dtype": dtype, "raw_hex": format(b, "x")}

        for st, fields in s.STAGES.items():
            for f in fields:
                setv(st, f, 0.0)
        for st, field, val in [
            ("c5_in", "state.qi", 0.0001),
            ("c5_in", "state.ni", 1000.0),
            ("c5_in", "state.t", 250.0),
            ("c5_in", "forcing.dend", 1.0),
            ("c5_in", "pre.supcol", 10.0),
            ("c5_in", "dtcld", 1.0),
            ("c5_in", "params.deni", 500.0),
            ("c5_in", "params.di125", 0.000125),
            ("c5_in", "params.t_split", 255.66),
            ("c5_in", "fconst.pi_f32", 3.1415927410125732),
            ("limiter_in", "working.qi", 0.0001),
            ("limiter_in", "working.ni", 1000.0),
            ("limiter_in", "pre2.supcol", 10.0),
            ("limiter_in", "dtcld", 1.0),
            ("limiter_in", "ncmin", 0.01),
        ]:
            setv(st, field, val)
        a = {}
        y = p.replay(rows, check=False, audit=a)
        for n, v in a["c5_outputs"].items():
            setv("c5_out", "agg." + n, v)
            setv("limiter_in", "cold_out." + n, v)
        for n, v in a["limited_outputs"].items():
            if ("limited", "scaled.cold." + n) in rows:
                setv("limited", "scaled.cold." + n, v)
        for n, v in zip(("qi", "ni"), y):
            setv("state_out", "new_state." + n, float(v))
        r = p.derivative_diagnostics(rows)
        self.assertEqual(r["status"], "pass", r.get("reason"))
        self.assertEqual(len(r["directions"]), 2)


if __name__ == "__main__":
    unittest.main()
