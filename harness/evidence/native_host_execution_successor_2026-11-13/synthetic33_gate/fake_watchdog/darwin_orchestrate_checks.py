"""Darwin fake orchestration: valid pinned metadata, never a real DSO."""

import hashlib
import json
import os
from pathlib import Path
import select
import signal
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import real33_orchestrate as x
import real33_parent_supervisor as parent


def fake_manifest(root):
    package = root / "psutil"
    package.mkdir()
    source = package / "__init__.py"
    source.write_text("# synthetic test package only\n")
    inventory = {"__init__.py": hashlib.sha256(source.read_bytes()).hexdigest()}
    inventory_sha = hashlib.sha256(
        json.dumps(
            inventory, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("ascii")
    ).hexdigest()
    fake_dso = (root / "fake_dso").resolve()
    fake_dso.write_bytes(b"synthetic dso never loaded")
    manifest = {
        "dso_path": str(fake_dso),
        "dso_sha256": hashlib.sha256(fake_dso.read_bytes()).hexdigest(),
        "schema": "kdm6.synthetic33.private.v1",
        "status": "REVIEWED_PINNED",
        "census_provider": {
            "package": str(package.resolve()),
            "inventory": inventory,
            "inventory_sha256": inventory_sha,
        },
        "budgets": {
            "forwards": 33,
            "graph_primal": 9,
            "jvp": 18,
            "vjp": 9,
            "wall_seconds": 900,
            "cleanup_reserve_seconds": 28,
            "rss_bytes": 4 * 1024**3,
            "serialized_call_bytes": 128 * 1024**2,
            "serialized_total_bytes": 4 * 1024**3,
        },
    }
    path = root / "manifest.json"
    path.write_text(json.dumps(manifest, sort_keys=True))
    out = root / "out"
    out.mkdir()
    return out, path, hashlib.sha256(path.read_bytes()).hexdigest()


def fake_supervisor(original, *, attach_result):
    def run(supervisor, identity, life, release, ready, receipt, scenario, **kwargs):
        nonce = kwargs.pop("run_nonce")
        digest = kwargs.pop("manifest_sha")
        kwargs.pop("manifest_path")
        # This seam exercises only the original fake worker. The real native
        # helper must never be initialized by these test-only scenarios.
        if kwargs.pop("use_native_census_helper") is not True:
            raise AssertionError("expected pinned native provider request")
        kwargs.pop("native_census_package")
        kwargs.pop("native_census_manifest")
        kwargs.pop("real_capability")
        kwargs.pop("execution_deadline")
        kwargs.pop("total_deadline")
        x.watchdog.group_rss_kib = lambda pid: 1024
        kwargs["fake_ready_timeout"] = 15
        result = original(
            supervisor,
            identity,
            life,
            release,
            ready,
            receipt,
            "fixture33_exec_mock",
            **kwargs,
        )
        if attach_result:
            result.update(
                run_nonce=nonce, manifest_sha256=digest, watchdog_pid=os.getpid()
            )
            Path(receipt + ".result").write_text(json.dumps(result))
        return result

    return run


class TestOrchestrate(unittest.TestCase):
    def test_disabled_before_preflight_or_fork(self):
        with (
            patch.object(
                x.freeze33,
                "validate_frozen",
                side_effect=AssertionError("preflight should not run"),
            ),
            patch.object(
                x.os, "fork", side_effect=AssertionError("fork should not run")
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "disabled"):
                x.run("/missing", "/missing", "0" * 64)

    def test_enabled_collision_fails_before_release(self):
        with (
            tempfile.TemporaryDirectory() as d,
            patch.object(x, "REAL33_RELEASE_ENABLED", True),
            patch.object(x.os, "fork", side_effect=AssertionError("must not fork")),
        ):
            Path(d, "stale").write_text("stale")
            with self.assertRaisesRegex(RuntimeError, "empty"):
                x.run(d, "/unused", "0" * 64)

    def test_enabled_fake_actual_worker_reaches_witness_gate(self):
        original = x.watchdog.supervise
        with tempfile.TemporaryDirectory() as d:
            out, manifest, digest = fake_manifest(Path(d).resolve())
            with (
                patch.object(x, "REAL33_RELEASE_ENABLED", True),
                patch.object(x.freeze33, "validate_frozen"),
                patch.object(
                    x.watchdog,
                    "supervise",
                    side_effect=fake_supervisor(original, attach_result=True),
                ),
                patch.object(
                    x.witness33, "validate_pinned", return_value={"status": "FAKE_ONLY"}
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "armed/final identity mismatch"):
                    x.run(out, manifest, digest)
            rows = (out / "calls.jsonl").read_text().splitlines()
            self.assertEqual(len(rows), 66)
            self.assertFalse((out / "witness.json").exists())

    def test_signal_at_readiness_prevents_release(self):
        owner = os.getpid()
        original_supervise = x.watchdog.supervise
        original_select = x.select.select

        def readiness_signal(*args, **kwargs):
            value = original_select(*args, **kwargs)
            if os.getpid() == owner and value[0]:
                os.kill(owner, x.signal.SIGTERM)
            return value

        with tempfile.TemporaryDirectory() as d:
            out, manifest, digest = fake_manifest(Path(d).resolve())
            with (
                patch.object(x, "REAL33_RELEASE_ENABLED", True),
                patch.object(x.freeze33, "validate_frozen"),
                patch.object(
                    x.watchdog,
                    "supervise",
                    side_effect=fake_supervisor(
                        original_supervise, attach_result=False
                    ),
                ),
                patch.object(x.select, "select", side_effect=readiness_signal),
            ):
                with self.assertRaisesRegex(RuntimeError, "before worker release"):
                    x.run(out, manifest, digest)
            self.assertFalse((out / "calls.jsonl").exists())
            self.assertFalse((out / "witness.json").exists())

    def test_signal_between_readiness_and_release_is_not_forwarded(self):
        owner = os.getpid()
        original_supervise = x.watchdog.supervise
        original_start = x.watchdog.process_start
        calls = [0]

        def signal_in_boundary(pid):
            result = original_start(pid)
            if os.getpid() == owner and pid != owner:
                calls[0] += 1
                if calls[0] == 2:
                    os.kill(owner, x.signal.SIGTERM)
            return result

        with tempfile.TemporaryDirectory() as d:
            out, manifest, digest = fake_manifest(Path(d).resolve())
            with (
                patch.object(x, "REAL33_RELEASE_ENABLED", True),
                patch.object(x.freeze33, "validate_frozen"),
                patch.object(
                    x.watchdog,
                    "supervise",
                    side_effect=fake_supervisor(
                        original_supervise, attach_result=False
                    ),
                ),
                patch.object(
                    x.watchdog, "process_start", side_effect=signal_in_boundary
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "before worker release"):
                    x.run(out, manifest, digest)
            self.assertEqual(calls[0], 2)
            self.assertFalse((out / "calls.jsonl").exists())
            self.assertFalse((out / "witness.json").exists())

    def test_supervise_exception_is_nonzero_and_durable(self):
        with tempfile.TemporaryDirectory() as d:
            out, manifest, digest = fake_manifest(Path(d).resolve())
            with (
                patch.object(x, "REAL33_RELEASE_ENABLED", True),
                patch.object(x.freeze33, "validate_frozen"),
                patch.object(
                    x.watchdog,
                    "supervise",
                    side_effect=RuntimeError("injected supervisor failure"),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "not armed"):
                    x.run(out, manifest, digest)
            failure = json.loads((out / "watchdog_failure.json").read_text())
            self.assertEqual(failure["status"], "INCOMPLETE")
            self.assertIn("injected supervisor failure", failure["error"])
            self.assertFalse((out / "witness.json").exists())

    def test_watchdog_loss_after_release_denies_witness_with_live_worker(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            out, manifest, _ = fake_manifest(root)
            registry = root / "registry"
            registry.mkdir()
            config = json.loads(manifest.read_text())
            config["attempt_registry_root"] = str(registry)
            config["budgets"]["wall_seconds"] = 34
            manifest.write_text(json.dumps(config, sort_keys=True))
            digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
            observer, child_endpoint = socket.socketpair()
            with observer, child_endpoint:
                observer.settimeout(2)

                def lose_watchdog(_supervisor, _identity, _life, release, ready,
                                  _receipt, _scenario, **_kwargs):
                    observer.close()
                    os.write(ready, b"R")
                    if not select.select([release], [], [], 4)[0] or os.read(release, 1) != b"G":
                        raise RuntimeError("test watchdog did not receive release")
                    if os.fork() == 0:
                        try:
                            signal.signal(signal.SIGALRM, signal.SIG_DFL)
                            signal.alarm(10)  # fixture self-terminates even if the test fails
                            os.setsid()
                            child_endpoint.settimeout(8)
                            if child_endpoint.recv(1) == b"?":
                                child_endpoint.sendall(b"W")
                        finally:
                            os._exit(0)
                    os.kill(os.getpid(), signal.SIGKILL)

                with (
                    patch.object(parent, "REAL_PARENT_ENABLED", True),
                    patch.object(x, "REAL33_RELEASE_ENABLED", True),
                    patch.object(x.freeze33, "validate_frozen"),
                    patch.object(x.watchdog, "supervise", side_effect=lose_watchdog),
                ):
                    result = parent.run(out, manifest, digest)
                child_endpoint.close()
                self.assertEqual(result["status"], "UNWITNESSED")
                self.assertEqual(result["reason"], "child nonzero exit or cancellation")
                self.assertEqual(result["cleanup"], "UNVERIFIED")
                # The worker answers only after parent.run has denied completion.
                observer.sendall(b"?")
                self.assertEqual(observer.recv(1), b"W")
                self.assertEqual(observer.recv(1), b"")
                self.assertFalse((out / "completion_candidate.json").exists())
                self.assertFalse((out / "parent_witness.json").exists())


if __name__ == "__main__":
    unittest.main()
