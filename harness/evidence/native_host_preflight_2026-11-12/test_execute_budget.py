import copy
import importlib.util
import json
import multiprocessing
import signal
import subprocess
import time
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "execute_budget", HERE / "execute_budget.py"
)
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


class BudgetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.src = self.root / "source.txt"
        self.src.write_text("source")
        self.dep = self.root / "dep"
        self.dep.write_text("dep")
        self.dso = self.root / "new.dylib"
        self.dso.write_text("fake instrumented bytes")
        self.python = Path(sys.executable).resolve()
        h = b.digest
        self.reference = {
            "schema": "kdm6.native_host_capture_preflight.v1",
            "status": "SPEC_ONLY",
            "execution_receipt": None,
            "controls": {"shape": [1, 39, 1], "threads": 1},
            "build_requirements": {
                "instrumented_dso_sha256": None,
                "installed_dso_sha256": "0" * 64,
                "source_pins": {"source.txt": h(self.src)},
            },
            "limits": {"calls_max": 3, "wall_seconds_max": 10},
            "calls": [
                {
                    "sequence": 1,
                    "input_id": "a",
                    "mode": "capture_off_value",
                    "status": "PLANNED",
                },
                {
                    "sequence": 2,
                    "input_id": "b",
                    "mode": "center_joint_graph",
                    "status": "PLANNED",
                },
                {
                    "sequence": 3,
                    "input_id": "c",
                    "mode": "installed_value_optional",
                    "status": "PLANNED_OPTIONAL",
                },
            ],
        }
        self.plan = copy.deepcopy(self.reference)
        self.plan["build_requirements"]["instrumented_dso_sha256"] = h(self.dso)

        def asset(p):
            return {"path": str(p), "sha256": h(p)}

        self.binding = {
            "dso": asset(self.dso),
            "dependencies": {"fake": asset(self.dep)},
            "sources": {"source.txt": asset(self.src)},
            "producer_files": {"python": asset(self.python)},
            "controls": self.plan["controls"],
            "compiler": {
                "identity": "SYNTHETIC_TEST_ONLY",
                "flags": ["-ffp-contract=off"],
                "test_assertions": "enabled",
            },
        }
        self.env = {
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "OMP_THREAD_LIMIT": "1",
        }

        def cmd(scenario):
            return {
                "argv": [str(self.python), "-I", "-S", str(b.STUB), scenario],
                "env": self.env,
                "artifact": "out.bin",
            }

        self.command = cmd
        self.commands = {i: cmd("success") for i in (1, 2)}
        self.patch = mock.patch.object(b, "canonical_plan", return_value=self.reference)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def run_adapter(self):
        return b.run(
            self.plan,
            self.binding,
            self.commands,
            {3},
            self.root / "run",
            synthetic_test=True,
            root=self.root,
        )

    def test_current_plan_blocked_before_launch(self):
        with mock.patch.object(
            b, "canonical_plan", side_effect=self.patch.stop() or b.canonical_plan
        ):
            p = b.canonical_plan()
            with self.assertRaisesRegex(b.BudgetError, "new instrumented DSO"):
                b.validate(p, {}, {}, set())
        self.patch.start()

    def test_canonical_plan_tampering_rejected(self):
        (self.root / "plan.json.gz").write_bytes(b"tampered")
        self.patch.stop()
        try:
            with mock.patch.object(b, "HERE", self.root):
                with self.assertRaisesRegex(b.BudgetError, "canonical plan hash"):
                    b.canonical_plan()
        finally:
            self.patch.start()

    def test_filled_spec_plan_still_cannot_launch_production(self):
        with self.assertRaisesRegex(b.BudgetError, "production execution blocked"):
            b.run(
                self.plan,
                self.binding,
                self.commands,
                {3},
                self.root / "run",
                root=self.root,
            )
        self.assertFalse((self.root / "run").exists())

    def test_success_all_calls_accounted(self):
        r = self.run_adapter()
        self.assertEqual(r["status"], "SYNTHETIC_COMPLETED_UNVERIFIED")
        self.assertEqual(
            [x["status"] for x in r["calls"]], ["completed", "completed", "skipped"]
        )
        self.assertEqual(r["calls"][2]["reason"], "explicit_optional_skip")
        self.assertEqual(
            r["calls"][0]["output_sha256"], b.digest(self.root / "run/001/out.bin")
        )
        receipt_path = self.root / "run/receipt.json"
        self.assertEqual(json.loads(receipt_path.read_text())["status"], r["status"])
        marker = json.loads((self.root / "run/completion.json").read_text())
        self.assertEqual(
            marker["schema"], "kdm6.native_host_preflight.budget_completion.v1"
        )
        self.assertEqual(marker["receipt_sha256"], b.digest(receipt_path))
        self.assertEqual(marker["plan_sha256"], r["plan_sha256"])

    def test_elapsed_covers_producer_output_write(self):
        self.commands[1] = self.command("success")
        r = self.run_adapter()
        self.assertGreaterEqual(r["calls"][0]["elapsed_seconds"], 0.15)
        self.assertEqual(r["calls"][0]["status"], "completed")

    def test_preflight_mismatch_never_launches(self):
        self.dep.write_text("modified")
        with self.assertRaisesRegex(b.BudgetError, "changed"):
            self.run_adapter()
        self.assertFalse((self.root / "run").exists())

    def test_required_failure_accounts_remaining_and_optional(self):
        self.commands[1] = self.command("fail")
        r = self.run_adapter()
        self.assertEqual(r["status"], "INCOMPLETE")
        self.assertEqual(
            [x["status"] for x in r["calls"]], ["failed", "skipped", "skipped"]
        )
        self.assertEqual(r["calls"][0]["returncode"], 7)

    def test_timeout_is_incomplete(self):
        self.reference["limits"]["wall_seconds_max"] = 0.4
        self.plan["limits"]["wall_seconds_max"] = 0.4
        self.commands[1] = self.command("sleep")
        r = self.run_adapter()
        self.assertEqual(r["status"], "INCOMPLETE")
        self.assertEqual(r["calls"][0]["status"], "failed")
        self.assertIn("timed out", r["calls"][0]["reason"])
        self.assertEqual(len(r["calls"]), 3)

    def test_timeout_kills_term_ignoring_group(self):
        self.reference["limits"]["wall_seconds_max"] = 0.8
        self.plan["limits"]["wall_seconds_max"] = 0.8
        self.commands[1] = self.command("term_ignoring_child")
        r = self.run_adapter()
        self.assertEqual(r["status"], "INCOMPLETE")
        self.assertEqual(r["calls"][0]["status"], "failed")
        self.assertIn("timed out", r["calls"][0]["reason"])

    def test_signal_interrupt_records_unstarted_calls(self):
        self.commands[1] = self.command("sleep")
        proc = multiprocessing.get_context("fork").Process(target=self.run_adapter)
        proc.start()
        try:
            deadline = time.monotonic() + 5
            while (
                time.monotonic() < deadline
                and not (self.root / "run/001/stdout.bin").exists()
            ):
                time.sleep(0.02)
            self.assertTrue((self.root / "run/001/stdout.bin").exists())
            time.sleep(0.1)
            os.kill(proc.pid, signal.SIGTERM)
            proc.join(5)
            self.assertFalse(proc.is_alive())
            r = json.loads((self.root / "run/receipt.json").read_text())
            self.assertEqual(r["status"], "INCOMPLETE")
            self.assertEqual(
                [x["status"] for x in r["calls"]], ["failed", "skipped", "skipped"]
            )
            self.assertIn(signal.SIGTERM, r["signals"])
        finally:
            if proc.is_alive():
                proc.kill()
                proc.join()

    def test_arbitrary_command_and_environment_rejected_before_launch(self):
        self.commands[1]["argv"] = [str(self.python), "-c", "print('unsafe')"]
        with self.assertRaisesRegex(b.BudgetError, "pinned synthetic stub"):
            self.run_adapter()
        self.assertFalse((self.root / "run").exists())
        self.commands[1] = self.command("success")
        self.commands[1]["env"] = dict(self.env, PYTHONPATH="/tmp")
        with self.assertRaisesRegex(b.BudgetError, "environment"):
            self.run_adapter()
        self.assertFalse((self.root / "run").exists())

    def test_tampered_stub_rejected_before_launch(self):
        stub = self.root / "stub.py"
        stub.write_bytes(b.STUB.read_bytes() + b"\n# changed\n")
        with mock.patch.object(b, "STUB", stub):
            for cmd in self.commands.values():
                cmd["argv"][3] = str(stub)
            with self.assertRaisesRegex(b.BudgetError, "stub missing or changed"):
                self.run_adapter()
        self.assertFalse((self.root / "run").exists())

    def test_double_sigterm_does_not_interrupt_cleanup(self):
        self.commands[1] = self.command("term_ignoring_child")
        marker = self.root / "cleanup_started"
        original = b._terminate

        def observed(proc, deadline):
            marker.write_text(str(proc.pid))
            return original(proc, deadline)

        with mock.patch.object(b, "_terminate", side_effect=observed):
            proc = multiprocessing.get_context("fork").Process(target=self.run_adapter)
            proc.start()
            try:
                deadline = time.monotonic() + 5
                while (
                    time.monotonic() < deadline
                    and not (self.root / "run/001/stdout.bin").exists()
                ):
                    time.sleep(0.02)
                self.assertTrue((self.root / "run/001/stdout.bin").exists())
                time.sleep(0.3)
                os.kill(proc.pid, signal.SIGTERM)
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline and not marker.exists():
                    time.sleep(0.01)
                self.assertTrue(marker.exists())
                time.sleep(0.1)
                os.kill(proc.pid, signal.SIGTERM)
                proc.join(5)
                self.assertFalse(proc.is_alive())
                r = json.loads((self.root / "run/receipt.json").read_text())
                self.assertEqual(r["status"], "INCOMPLETE")
                self.assertEqual(
                    [x["status"] for x in r["calls"]], ["failed", "skipped", "skipped"]
                )
                self.assertEqual(r["signals"].count(signal.SIGTERM), 2)
                with self.assertRaises(ProcessLookupError):
                    os.kill(int(marker.read_text()), 0)
                listing = subprocess.run(
                    ["ps", "-axo", "pgid=,stat="],
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout
                live = [
                    line
                    for line in listing.splitlines()
                    if len(line.split()) >= 2
                    and line.split()[0] == marker.read_text()
                    and not line.split()[1].startswith("Z")
                ]
                self.assertEqual(live, [])
            finally:
                if proc.is_alive():
                    proc.kill()
                    proc.join()

    def test_initial_validation_time_counts_against_budget(self):
        self.reference["limits"]["wall_seconds_max"] = 2.0
        self.plan["limits"]["wall_seconds_max"] = 2.0
        original = b.validate

        def delayed(*args, **kwargs):
            time.sleep(2.2)
            return original(*args, **kwargs)

        with mock.patch.object(b, "validate", side_effect=delayed):
            r = self.run_adapter()
        self.assertEqual(r["status"], "INCOMPLETE")
        self.assertGreaterEqual(r["elapsed_seconds"], 2.2)
        self.assertEqual(
            [x["status"] for x in r["calls"]], ["skipped", "skipped", "skipped"]
        )
        self.assertFalse((self.root / "run/001").exists())

    def test_final_receipt_delay_counts_and_is_persisted_incomplete(self):
        self.reference["limits"]["wall_seconds_max"] = 2.0
        self.plan["limits"]["wall_seconds_max"] = 2.0
        original = b._write_receipt
        count = 0

        def delayed(path, receipt):
            nonlocal count
            count += 1
            if count == 4:
                time.sleep(2.2)
            original(path, receipt)

        with mock.patch.object(b, "_write_receipt", side_effect=delayed):
            r = self.run_adapter()
        self.assertEqual(r["status"], "INCOMPLETE")
        self.assertGreaterEqual(r["elapsed_seconds"], 2.2)
        stored = json.loads((self.root / "run/receipt.json").read_text())
        self.assertEqual(stored["status"], "INCOMPLETE")
        self.assertGreaterEqual(stored["elapsed_seconds"], 2.2)
        self.assertFalse((self.root / "run/completion.json").exists())

    def test_final_receipt_failure_is_explicit_and_not_success(self):
        original = b._write_receipt
        count = 0

        def failing(path, receipt):
            nonlocal count
            count += 1
            if count == 4:
                raise OSError("synthetic fsync failure")
            original(path, receipt)

        with mock.patch.object(b, "_write_receipt", side_effect=failing):
            with self.assertRaisesRegex(
                b.FinalReceiptError, "final receipt write failed"
            ) as caught:
                self.run_adapter()
        self.assertEqual(caught.exception.receipt["status"], "INCOMPLETE")
        stored = json.loads((self.root / "run/receipt.json").read_text())
        self.assertEqual(stored["status"], "INCOMPLETE")
        self.assertIn("final receipt write failed", stored["reason"])

    def test_failed_overrun_correction_never_has_completion_marker(self):
        self.reference["limits"]["wall_seconds_max"] = 2.0
        self.plan["limits"]["wall_seconds_max"] = 2.0
        original = b._write_receipt
        count = 0

        def delayed_then_fail(path, receipt):
            nonlocal count
            count += 1
            if count == 4:
                time.sleep(2.2)
            if count == 5:
                raise OSError("correction write failed")
            original(path, receipt)

        with mock.patch.object(b, "_write_receipt", side_effect=delayed_then_fail):
            with self.assertRaises(b.FinalReceiptError):
                self.run_adapter()
        self.assertFalse((self.root / "run/completion.json").exists())
        stored = json.loads((self.root / "run/receipt.json").read_text())
        self.assertEqual(stored["status"], "INCOMPLETE")

    def test_completion_marker_write_overrun_removes_marker(self):
        self.reference["limits"]["wall_seconds_max"] = 2.0
        self.plan["limits"]["wall_seconds_max"] = 2.0
        original = b._write_receipt

        def delayed(path, receipt):
            if path.name == "completion.json":
                time.sleep(2.2)
            original(path, receipt)

        with mock.patch.object(b, "_write_receipt", side_effect=delayed):
            r = self.run_adapter()
        self.assertEqual(r["status"], "INCOMPLETE")
        self.assertIn("completion marker", r["reason"])
        self.assertFalse((self.root / "run/completion.json").exists())
        self.assertEqual(
            json.loads((self.root / "run/receipt.json").read_text())["status"],
            "INCOMPLETE",
        )

    def test_optional_skip_only_and_budget_cap(self):
        with self.assertRaisesRegex(b.BudgetError, "optional"):
            b.validate(self.plan, self.binding, self.commands, {1, 3}, root=self.root)
        self.reference["limits"]["wall_seconds_max"] = 901
        self.plan["limits"]["wall_seconds_max"] = 901
        with self.assertRaisesRegex(b.BudgetError, "budget"):
            self.run_adapter()

    def test_residual_group_never_success(self):
        self.commands[1] = self.command("residual_child")
        r = self.run_adapter()
        self.assertEqual(r["status"], "INCOMPLETE")
        self.assertEqual(r["calls"][0]["status"], "failed")
        self.assertTrue(
            "residual" in r["calls"][0]["reason"]
            or "probe denied" in r["calls"][0]["reason"]
        )


if __name__ == "__main__":
    unittest.main()
