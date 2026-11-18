import ctypes as C
import unittest

import condition_abi_v2_reader as reader


class Function:
    def __init__(self, fn):
        self.fn = fn

    def __call__(self, *args):
        return self.fn(*args)


class Fake:
    def __init__(self):
        self.rows = [self.row(1), self.row(5)]
        self.fail = None
        self.bits = 0
        self.calls = []
        for suffix, method in [
            ("count", self.count),
            ("meta", self.meta),
            ("raw", self.raw),
            ("verify_absences", self.verify),
        ]:
            setattr(self, "kdm6_batch5_condition_v2_" + suffix + "_c", Function(method))

    @staticmethod
    def row(role):
        m = reader.Meta()
        m.abi_version = 2
        m.struct_size = C.sizeof(m)
        for k, v in dict(
            input_id=b"x",
            mode=b"capture_on_value",
            family=b"main",
            stage=b"s",
            field=b"f",
            source_hook=b"h",
        ).items():
            setattr(m, k, v)
        m.context_epoch = 1
        m.runtime_call = 2
        m.one_step_call = 1
        m.outer_loop = 1
        m.substep_n = 1
        m.B = 1
        m.K = 39
        m.b_zero = 0
        m.k_zero = 0
        m.native_level_bottom_first = 39
        m.scope = 1
        m.role = role
        m.dtype = 1 if role == 1 else 5
        m.reason = 0 if role == 1 else 1
        m.causal_index = reader.NO_CAUSE if role == 1 else 0
        return m

    def count(self, h, t, out):
        self.calls.append(("count", h, t))
        if self.fail != "count_no_write":
            C.cast(out, C.POINTER(C.c_uint64))[0] = len(self.rows)
        return int(self.fail == "count")

    def meta(self, h, t, i, out, size):
        self.calls.append(("meta", i))
        if self.fail == "meta":
            return -1
        if self.fail != "meta_no_write":
            C.memmove(out, C.byref(self.rows[i]), size)
        return 0

    def raw(self, h, t, i, out):
        self.calls.append(("raw", i))
        if self.fail != "raw_no_write":
            C.cast(out, C.POINTER(C.c_uint64))[0] = self.bits
        return int(self.fail == "raw")

    def verify(self, h, t, out):
        self.calls.append(("verify", h, t))
        if self.fail != "verify_no_write":
            C.cast(out, C.POINTER(C.c_uint64))[0] = (
                0 if self.fail == "verify_count" else 1
            )
        return int(self.fail == "verify")


class ReaderTests(unittest.TestCase):
    def run_value(self, lib, **kw):
        return reader.read_records(
            lib, input_id="x", mode="capture_on_value", runtime_call=2, **kw
        )

    def test_order_and_original_cause(self):
        lib = Fake()
        result = self.run_value(lib)
        self.assertEqual(result["status"], "SPEC_ONLY_BLOCKED")
        self.assertEqual(result["records"][1]["causal_index"], 0)
        self.assertEqual(
            [c[0] for c in lib.calls],
            [
                "count",
                "count",
                "meta",
                "meta",
                "raw",
                "raw",
                "meta",
                "meta",
                "verify",
                "verify",
            ],
        )

    def test_fail_closed(self):
        for failure in (
            "count",
            "meta",
            "raw",
            "verify",
            "verify_count",
            "count_no_write",
            "meta_no_write",
            "raw_no_write",
            "verify_no_write",
        ):
            with self.subTest(failure=failure):
                lib = Fake()
                lib.fail = failure
                with self.assertRaises(RuntimeError):
                    self.run_value(lib)
        lib = Fake()
        lib.rows[1].causal_index = 1
        with self.assertRaises(RuntimeError):
            self.run_value(lib)
        lib = Fake()
        lib.rows[0].struct_size = 0
        with self.assertRaises(RuntimeError):
            self.run_value(lib)
        with self.assertRaises(RuntimeError):
            self.run_value(Fake(), max_records=1)

    def test_typed_words_and_nonfinite(self):
        for dtype, bits, expected in (
            (2, 0x3F800000, "3f800000"),
            (3, 0x3FF0000000000000, "3ff0000000000000"),
            (4, 0xFFFFFFFFFFFFFFFF, "ffffffffffffffff"),
        ):
            lib = Fake()
            lib.rows = [lib.row(4)]
            lib.rows[0].scope = 3
            lib.rows[0].B = lib.rows[0].K = lib.rows[0].b_zero = lib.rows[
                0
            ].k_zero = lib.rows[0].native_level_bottom_first = -1
            lib.rows[0].dtype = dtype
            lib.rows[0].reason = 0
            lib.rows[0].causal_index = reader.NO_CAUSE
            lib.bits = bits
            lib.fail = "verify_count"
            self.assertEqual(self.run_value(lib)["records"][0]["raw_hex"], expected)
        lib = Fake()
        lib.rows = [lib.row(3)]
        lib.rows[0].dtype = 3
        lib.rows[0].reason = 0
        lib.rows[0].causal_index = reader.NO_CAUSE
        lib.bits = 0x7FF8000000000000
        with self.assertRaises(RuntimeError):
            self.run_value(lib)

    def test_raw_no_write_all_dtypes(self):
        for dtype in (1, 2, 3, 4):
            lib = Fake()
            lib.rows = [lib.row(4)]
            m = lib.rows[0]
            m.scope = 3
            m.B = m.K = m.b_zero = m.k_zero = m.native_level_bottom_first = -1
            m.dtype = dtype
            m.reason = 0
            m.causal_index = reader.NO_CAUSE
            lib.fail = "raw_no_write"
            with self.assertRaisesRegex(RuntimeError, "not fully written"):
                self.run_value(lib)

    def test_identity_ordinals_and_role_scope(self):
        for ordinal in (0, 2):
            lib = Fake()
            lib.rows = [lib.row(1), lib.row(1)]
            lib.rows[1].event_ordinal = ordinal
            with self.assertRaisesRegex(RuntimeError, "ordinal"):
                self.run_value(lib)
        lib = Fake()
        lib.rows = [lib.row(1), lib.row(1)]
        lib.rows[1].event_ordinal = 1
        lib.fail = "verify_count"
        self.assertEqual(len(self.run_value(lib)["records"]), 2)
        lib = Fake()
        lib.rows = [lib.row(4)]
        lib.rows[0].dtype = 3
        lib.rows[0].reason = 0
        lib.rows[0].causal_index = reader.NO_CAUSE
        with self.assertRaisesRegex(RuntimeError, "role scope"):
            self.run_value(lib)
        for role in (1, 2, 3, 5):
            lib = Fake()
            lib.rows = [lib.row(role)]
            lib.rows[0].scope = 3
            lib.rows[0].B = lib.rows[0].K = lib.rows[0].b_zero = lib.rows[
                0
            ].k_zero = lib.rows[0].native_level_bottom_first = -1
            with self.assertRaisesRegex(RuntimeError, "role scope"):
                self.run_value(lib)

    def test_graph_only_metadata(self):
        lib = Fake()
        for row in lib.rows:
            row.mode = b"center_joint_graph"
        result = reader.read_records(
            lib,
            input_id="x",
            mode="center_joint_graph",
            runtime_call=2,
            handle=12,
            token=7,
        )
        self.assertTrue(result["graph_metadata_only"])
        self.assertEqual(
            [c[0] for c in lib.calls],
            ["count", "count", "meta", "meta", "meta", "meta"],
        )
        with self.assertRaises(ValueError):
            reader.read_records(
                lib, input_id="x", mode="center_joint_graph", runtime_call=2
            )


if __name__ == "__main__":
    unittest.main()
