import hashlib
import importlib.util
import json
import os
from pathlib import Path
import time
import unittest
from unittest import mock

import test_execute_budget as budget_tests

b = budget_tests.b

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "synthetic_supervisor", HERE / "synthetic_supervisor.py"
)
supervisor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(supervisor)


class SupervisorTest(unittest.TestCase):
    setUp = budget_tests.BudgetTest.setUp
    tearDown = budget_tests.BudgetTest.tearDown

    def run_supervisor(self):
        with mock.patch.object(supervisor, "scheduler", b):
            return supervisor.supervise(
                self.plan,
                self.binding,
                self.commands,
                {3},
                self.root / "run",
                root=self.root,
            )

    def test_actual_normal_child_exit_creates_bound_witness(self):
        outcome = self.run_supervisor()
        self.assertEqual(outcome["status"], "WITNESSED_SYNTHETIC_UNVERIFIED")
        path = self.root / "run"
        receipt = (path / "receipt.json").read_bytes()
        candidate = (path / "completion.json").read_bytes()
        witness = json.loads((path / "supervisor_witness.json").read_text())
        self.assertEqual(
            json.loads(receipt)["status"], "SYNTHETIC_CANDIDATE_UNVERIFIED"
        )
        self.assertEqual(witness["receipt_sha256"], hashlib.sha256(receipt).hexdigest())
        self.assertEqual(
            witness["candidate_sha256"], hashlib.sha256(candidate).hexdigest()
        )
        self.assertEqual(witness["child_exit_code"], 0)
        self.assertIs(witness["child_return_confirmed"], True)
        token = witness["child_return_token"].encode("utf-8")
        self.assertEqual(
            witness["child_return_token_sha256"], hashlib.sha256(token).hexdigest()
        )
        self.assertEqual(json.loads(token)["receipt_sha256"], witness["receipt_sha256"])
        self.assertEqual(
            json.loads(token)["candidate_sha256"], witness["candidate_sha256"]
        )
        self.assertLessEqual(witness["wall_seconds"], witness["budget_seconds"])

    def test_witness_directory_fsync_failure_removes_published_file(self):
        path = self.root / "witness.json"
        original = os.fsync
        count = 0

        def fail_directory(fd):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError("synthetic directory fsync failure")
            return original(fd)

        with mock.patch.object(supervisor.os, "fsync", side_effect=fail_directory):
            with self.assertRaises(OSError):
                supervisor._write_new(path, {"test": True})
        self.assertFalse(path.exists())

    def test_nonzero_child_does_not_create_witness(self):
        self.commands[1] = self.command("fail")
        outcome = self.run_supervisor()
        self.assertEqual(outcome["status"], "UNWITNESSED")
        self.assertNotEqual(outcome["child_exit_code"], 0)
        self.assertFalse((self.root / "run/supervisor_witness.json").exists())

    def test_post_candidate_abrupt_exit_is_not_witnessed(self):
        self.reference["limits"]["wall_seconds_max"] = 1.0
        self.plan["limits"]["wall_seconds_max"] = 1.0
        original = b._write_receipt

        def interrupt_after_publish(path, receipt):
            original(path, receipt)
            if path.name == "completion.json":
                time.sleep(1.6)
                os._exit(73)

        with mock.patch.object(
            b, "_write_receipt", side_effect=interrupt_after_publish
        ):
            outcome = self.run_supervisor()
        self.assertEqual(outcome["status"], "UNWITNESSED")
        self.assertEqual(outcome["child_exit_code"], 73)
        self.assertGreater(outcome["wall_seconds"], 1.0)
        self.assertTrue((self.root / "run/completion.json").exists())
        receipt = json.loads((self.root / "run/receipt.json").read_text())
        self.assertEqual(receipt["status"], "SYNTHETIC_CANDIDATE_UNVERIFIED")
        self.assertFalse((self.root / "run/supervisor_witness.json").exists())

    def test_premature_zero_exit_within_budget_has_no_return_token(self):
        original = b._write_receipt

        def exit_before_postcheck(path, receipt):
            original(path, receipt)
            if path.name == "completion.json":
                os._exit(0)

        with mock.patch.object(b, "_write_receipt", side_effect=exit_before_postcheck):
            outcome = self.run_supervisor()
        self.assertEqual(outcome["child_exit_code"], 0)
        self.assertLess(
            outcome["wall_seconds"], self.plan["limits"]["wall_seconds_max"]
        )
        self.assertEqual(outcome["status"], "UNWITNESSED")
        self.assertTrue((self.root / "run/completion.json").exists())
        self.assertFalse((self.root / "run/supervisor_witness.json").exists())

    def test_even_zero_exit_over_full_wall_cannot_be_witnessed(self):
        self.reference["limits"]["wall_seconds_max"] = 1.0
        self.plan["limits"]["wall_seconds_max"] = 1.0
        original = b._write_receipt

        def exit_zero_after_delay(path, receipt):
            original(path, receipt)
            if path.name == "completion.json":
                time.sleep(1.6)
                os._exit(0)

        with mock.patch.object(b, "_write_receipt", side_effect=exit_zero_after_delay):
            outcome = self.run_supervisor()
        self.assertEqual(outcome["child_exit_code"], 0)
        self.assertGreater(outcome["wall_seconds"], 1.0)
        self.assertEqual(outcome["status"], "UNWITNESSED")
        self.assertFalse((self.root / "run/supervisor_witness.json").exists())


if __name__ == "__main__":
    unittest.main()
