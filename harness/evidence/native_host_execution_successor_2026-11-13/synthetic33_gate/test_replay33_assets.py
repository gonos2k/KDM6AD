import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import replay33_assets as replay
import real33_worker as worker
from test_real33_worker import FakeRunner


class Replay33Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        r, w = os.pipe()
        os.write(w, b"G")
        os.close(w)
        with (
            patch.object(worker, "preflight", return_value={"dso_path": "fake"}),
            patch.object(worker, "Runner", FakeRunner),
        ):
            worker.run(r, self.path)

    def mutate(self, index, fn):
        path = self.path / f"call_{index:02}.json"
        data = json.loads(path.read_bytes())
        fn(data)
        raw = json.dumps(
            data, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("ascii")
        path.write_bytes(raw)
        journal_path = self.path / "calls.jsonl"
        rows = [json.loads(line) for line in journal_path.read_text().splitlines()]
        rows[2 * index - 1]["asset_sha256"] = hashlib.sha256(raw).hexdigest()
        rows[2 * index - 1]["bytes"] = len(raw)
        journal_path.write_text(
            "".join(
                json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
                for row in rows
            )
        )

    def test_complete_replay(self):
        result = replay.replay(self.path)
        self.assertEqual(
            (result["calls"], len(result["rows"]), result["status"]),
            (33, 18, "INCONCLUSIVE"),
        )
        self.assertTrue(
            all(
                len(row["steps"]) == 2
                and all(
                    step["recorded_branch_schedule"] == "STABLE"
                    for step in row["steps"]
                )
                for row in result["rows"]
            )
        )
        self.assertTrue(
            all(abs(row["jvp"] - row["vjp_dot"]) < 1e-14 for row in result["rows"])
        )

    def test_rehashed_gradient_and_input_mutations_fail(self):
        def gradient(data):
            selector = next(iter(data["result"]["selectors"].values()))
            selector["grad_words"][23] = "0000000000000000"

        self.mutate(3, gradient)
        with self.assertRaisesRegex(ValueError, "gradient"):
            replay.replay(self.path)

    def test_rehashed_stored_dot_mutation_fails(self):
        def dot(data):
            selector = next(iter(data["result"]["selectors"].values()))
            selector["dots"][0] += 1.0

        self.mutate(3, dot)
        with self.assertRaisesRegex(ValueError, "stored dot"):
            replay.replay(self.path)

    def test_rehashed_endpoint_primal_detects_numeric_mismatch(self):
        def endpoint(data):
            selector = next(iter(data["result"]["selectors"].values()))
            selector["primal"] += 100000000

        self.mutate(4, endpoint)
        rows = replay.replay(self.path)["rows"]
        self.assertTrue(
            any(
                step["status"] == "NUMERIC_MISMATCH"
                for row in rows
                for step in row["steps"]
            )
        )

    def test_one_good_step_one_bad_step_cannot_pass_pair(self):
        def endpoint(data):
            selector = next(iter(data["result"]["selectors"].values()))
            selector["primal"] += 100000000

        self.mutate(4, endpoint)
        rows = replay.replay(self.path)["rows"]
        mixed = [
            row
            for row in rows
            if {step["status"] for step in row["steps"]}
            == {"LOCAL_NUMERIC_CONSISTENT", "NUMERIC_MISMATCH"}
        ]
        self.assertTrue(mixed)
        self.assertTrue(all(row["pair_status"] == "NUMERIC_MISMATCH" for row in mixed))

    def test_rehashed_malformed_condition_rejected(self):
        self.mutate(
            2, lambda data: data["result"]["conditions"][0].__setitem__("raw", 2)
        )
        with self.assertRaises(ValueError):
            replay.replay(self.path)

    def test_rehashed_selector_identity_rejected(self):
        def identity(data):
            entry = next(iter(data["result"]["selectors"].values()))
            entry["identity"]["k_zero"] = 999

        self.mutate(3, identity)
        with self.assertRaises(ValueError):
            replay.replay(self.path)

    def test_rehashed_abi_status_rejected(self):
        def status(data):
            entry = next(iter(data["result"]["selectors"].values()))
            entry["abi_jvp_statuses"][0] = 7

        self.mutate(3, status)
        with self.assertRaises(ValueError):
            replay.replay(self.path)

    def test_duality_mismatch_precedes_branch_crossing(self):
        def jvp(data):
            entry = next(iter(data["result"]["selectors"].values()))
            entry["jvps"][0] += 1.0

        def cross(data):
            data["result"]["conditions"][0]["raw"] = 0

        self.mutate(3, jvp)
        self.mutate(4, cross)
        rows = replay.replay(self.path)["rows"]
        bad = [
            row
            for row in rows
            if row["duality"] == "MISMATCH"
            and any(
                step["recorded_branch_schedule"] == "CROSS" for step in row["steps"]
            )
        ]
        self.assertTrue(bad)
        self.assertTrue(all(row["pair_status"] == "NUMERIC_MISMATCH" for row in bad))

    def test_valid_missing_selector_and_crossing_remain_inconclusive(self):
        names = list(
            json.loads((self.path / "call_02.json").read_text())["result"]["selectors"]
        )
        name = names[0]

        def missing(data):
            data["result"]["selectors"][name] = {
                "status": "INCONCLUSIVE",
                "reason": "missing or ambiguous full selector",
            }
            if data["slot"]["mode"] == "center_joint_graph":
                data["result"]["query_counts"] = {"graph_primal": 2, "jvp": 4, "vjp": 2}

        self.mutate(2, missing)
        self.mutate(3, missing)
        self.mutate(
            4, lambda data: data["result"]["conditions"][0].__setitem__("raw", 0)
        )
        result = replay.replay(self.path)
        rows = [
            row
            for row in result["rows"]
            if row["fixture"] == "baseline" and row["selector"] == name
        ]
        self.assertEqual(
            (result["calls"], result["status"], len(rows)), (33, "INCONCLUSIVE", 2)
        )
        self.assertTrue(
            all(
                row["selector_status"] == "INCONCLUSIVE"
                and row["jvp"] is None
                and row["vjp_dot"] is None
                for row in rows
            )
        )
        self.assertTrue(
            any(
                step["recorded_branch_schedule"] == "CROSS"
                for row in rows
                for step in row["steps"]
            )
        )
        self.assertTrue(
            all(row["pair_status"] != "LOCAL_NUMERIC_CONSISTENT" for row in rows)
        )

    def test_missing_endpoint_and_unconnected_direction(self):
        name = next(
            iter(
                json.loads((self.path / "call_03.json").read_text())["result"][
                    "selectors"
                ]
            )
        )

        def disconnected(data):
            entry = data["result"]["selectors"][name]
            entry["mask"] = 1
            entry["grad_words"][8 * 39 + 23] = "0000000000000000"
            entry["jvps"][0] = entry["dots"][0] = 0.0
            entry["direction_connectivity"][0] = "UNCONNECTED"

        self.mutate(3, disconnected)

        def missing(data):
            data["result"]["selectors"][name] = {
                "status": "INCONCLUSIVE",
                "reason": "selector identity mismatch",
            }

        self.mutate(6, missing)
        rows = [
            row
            for row in replay.replay(self.path)["rows"]
            if row["fixture"] == "baseline" and row["selector"] == name
        ]
        nc = next(row for row in rows if row["direction"] == "nc")
        self.assertEqual(
            (nc["connectivity"], nc["pair_status"], nc["selector_status"]),
            ("UNCONNECTED", "UNRESOLVED", "INCONCLUSIVE"),
        )
        self.assertIsNone(nc["steps"][1]["fd"])

    def test_rehashed_boolean_sequence_rejected(self):
        path = self.path / "call_01.json"
        data = json.loads(path.read_bytes())
        data["slot"]["seq"] = True
        raw = json.dumps(
            data, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("ascii")
        path.write_bytes(raw)
        journal = self.path / "calls.jsonl"
        rows = [json.loads(line) for line in journal.read_text().splitlines()]
        rows[0]["seq"] = True
        rows[1]["seq"] = True
        rows[1]["asset_sha256"] = hashlib.sha256(raw).hexdigest()
        rows[1]["bytes"] = len(raw)
        journal.write_text(
            "".join(
                json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
                for row in rows
            )
        )
        with self.assertRaisesRegex(ValueError, "started slot"):
            replay.replay(self.path)

    def test_exact_slot_types_and_float_bits(self):
        expected = {"seq": 1, "offset": 0.0, "direction": None, "input_sha256": "abc"}
        self.assertTrue(replay.exact_fields(expected.copy(), expected))
        for mutation in (
            {"seq": True},
            {"offset": 0},
            {"offset": -0.0},
            {"direction": []},
            {"input_sha256": ["abc"]},
        ):
            with self.subTest(mutation=mutation):
                self.assertFalse(
                    replay.exact_fields({**expected, **mutation}, expected)
                )

    def test_rehashed_input_mutation_fails(self):
        def input_word(data):
            raw = bytearray.fromhex(data["input_words"])
            raw[0] ^= 1
            data["input_words"] = raw.hex()

        self.mutate(4, input_word)
        with self.assertRaisesRegex(ValueError, "input words"):
            replay.replay(self.path)

    def test_rehashed_condition_crossing_is_reported(self):
        def crossing(data):
            data["result"]["conditions"][0]["raw"] = 0

        self.mutate(4, crossing)
        rows = replay.replay(self.path)["rows"]
        self.assertTrue(
            any(
                step["recorded_branch_schedule"] == "CROSS"
                for row in rows
                for step in row["steps"]
            )
        )


if __name__ == "__main__":
    unittest.main()
