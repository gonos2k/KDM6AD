"""Synthetic-only review of real-mode orchestration wiring; no forks or DSO."""

import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import real33_orchestrate as orchestrator


class PlumbingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.package = self.root / "package"
        self.package.mkdir()
        inventory = {"__init__.py": "a" * 64}
        digest = hashlib.sha256(
            json.dumps(
                inventory, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("ascii")
        ).hexdigest()
        self.issuer = patch.object(orchestrator.watchdog, "issue_real_capability", return_value=object())
        self.issued = self.issuer.start()
        self.addCleanup(self.issuer.stop)
        self.manifest = {
            "dso_sha256": "c" * 64,
            "schema": "kdm6.synthetic33.private.v1",
            "status": "REVIEWED_PINNED",
            "census_provider": {
                "package": str(self.package),
                "inventory": inventory,
                "inventory_sha256": digest,
            },
            "budgets": {
                "forwards": 33,
                "graph_primal": 9,
                "jvp": 18,
                "vjp": 9,
                "wall_seconds": 900,
                "rss_bytes": 4 * 1024**3,
                "serialized_call_bytes": 128 * 1024**2,
                "serialized_total_bytes": 4 * 1024**3,
            },
        }
        self.path = self.root / "manifest.json"
        self.write_manifest()

    def write_manifest(self):
        self.path.write_text(json.dumps(self.manifest))
        self.digest = hashlib.sha256(self.path.read_bytes()).hexdigest()

    def test_missing_dso_digest_fails_as_value_error(self):
        del self.manifest['dso_sha256'];self.write_manifest()
        with patch.object(orchestrator.freeze33,'validate_frozen'):
            with self.assertRaisesRegex(ValueError,'DSO SHA256'):
                orchestrator.reviewed_configuration(self.path,self.digest)

    def test_reviewed_config_binds_exact_manifest_and_policy(self):
        with patch.object(orchestrator.freeze33, "validate_frozen") as freeze:
            result = orchestrator.reviewed_configuration(self.path, self.digest)
        self.assertEqual(result["package"], self.package)
        self.assertEqual(
            result["inventory"], self.manifest["census_provider"]["inventory"]
        )
        self.assertEqual(result["policy"], self.manifest["budgets"])
        freeze.assert_called_once_with(self.path, self.digest)
        for mutation in ("stale_sha", "inventory", "policy", "package"):
            original = json.loads(json.dumps(self.manifest))
            if mutation == "inventory":
                self.manifest["census_provider"]["inventory"]["__init__.py"] = "b" * 64
            elif mutation == "policy":
                self.manifest["budgets"]["rss_bytes"] = 8 * 1024**3
            elif mutation == "package":
                self.manifest["census_provider"]["package"] = str(self.root / "missing")
            self.write_manifest()
            pin = "0" * 64 if mutation == "stale_sha" else self.digest
            with (
                self.subTest(mutation=mutation),
                patch.object(orchestrator.freeze33, "validate_frozen"),
                self.assertRaises((ValueError, OSError)),
            ):
                orchestrator.reviewed_configuration(self.path, pin)
            self.manifest = original
            self.write_manifest()

    def test_call_policy_uses_selector_derived_budget(self):
        totals = {"graph_primal": 12, "jvp": 24, "vjp": 12}
        self.manifest["budgets"].update(totals)
        self.write_manifest()
        with (
            patch.object(orchestrator.freeze33, "validate_frozen"),
            patch.object(
                orchestrator.selectors, "query_budget", return_value={"total": totals}
            ) as query,
        ):
            result = orchestrator.reviewed_configuration(self.path, self.digest)
        query.assert_called_once_with(orchestrator.fixture33.plan())
        self.assertEqual(result["policy"]["jvp"], 24)
        self.manifest["budgets"]["jvp"] = 18
        self.write_manifest()
        with (
            patch.object(orchestrator.freeze33, "validate_frozen"),
            patch.object(
                orchestrator.selectors, "query_budget", return_value={"total": totals}
            ),
            self.assertRaisesRegex(ValueError, "call/query policy"),
        ):
            orchestrator.reviewed_configuration(self.path, self.digest)

    def test_disabled_before_any_preflight_or_fork(self):
        with (
            patch.object(
                orchestrator.freeze33,
                "validate_frozen",
                side_effect=AssertionError("preflight"),
            ),
            patch.object(orchestrator.os, "fork", side_effect=AssertionError("fork")),
        ):
            with self.assertRaisesRegex(RuntimeError, "disabled"):
                orchestrator.run("/missing", "/missing", "0" * 64)

    def test_fork_failure_closes_all_pipes_and_restores_handlers(self):
        out = self.root / "out"
        out.mkdir()
        closed = []
        original_close = os.close

        def close(fd):
            closed.append(fd)
            return original_close(fd)

        with (
            patch.object(orchestrator, "REAL33_RELEASE_ENABLED", True),
            patch.object(orchestrator.freeze33, "validate_frozen"),
            patch.object(orchestrator.watchdog, "process_start", return_value=(1, 2)),
            patch.object(
                orchestrator.os, "fork", side_effect=OSError("fake fork failure")
            ),
            patch.object(orchestrator.os, "close", side_effect=close),
        ):
            with self.assertRaisesRegex(OSError, "fake fork failure"):
                orchestrator.run(out, self.path, self.digest)
        self.assertGreaterEqual(len(closed), 7)  # nonce plus all six pipe ends
        self.assertFalse((out / "armed.json").exists())

    def test_delayed_postcheck_cannot_reach_publication(self):
        with (
            patch.object(orchestrator, "_CANCELLED", []),
            patch.object(orchestrator.witness33, "sha", return_value="a"*64),
            patch.object(orchestrator.time, "monotonic", side_effect=[5.0, 11.0]),
            patch.object(
                orchestrator.witness33,
                "validate_pinned",
                return_value={"status": "fake"},
            ) as validate,
        ):
            with self.assertRaisesRegex(RuntimeError, "expired during postcheck"):
                orchestrator.validate_before_publication(
                    "out", {}, 0.0, 10.0, "manifest", "pin", "trace"
                )
        self.assertEqual(validate.call_args.args[2], 5.0)

    def test_offline_replay_binds_assets_and_rejects_mutation(self):
        out=self.root/'snapshot';out.mkdir()
        for name in ['calls.jsonl','worker_result.json','worker_dyld.stderr']+[f'call_{i:02}.json' for i in range(1,34)]:
            (out/name).write_bytes(name.encode())
        trace=out/'worker_dyld.stderr'
        def replay(_):return {'status':'INCONCLUSIVE','calls':33,'rows':[]}
        with patch.object(orchestrator.witness33,'validate_pinned',return_value={'status':'EXECUTION_COMPLETED_ASSETS_ONLY'}),patch.object(orchestrator.replay33_assets,'replay',side_effect=replay):
            result=orchestrator.validate_before_publication(out,{},0,float('inf'),'manifest','pin',trace)
            self.assertEqual(len(result['asset_sha256']),36)
        def mutate(_):
            (out/'call_01.json').write_bytes(b'tampered')
            return replay(None)
        with patch.object(orchestrator.witness33,'validate_pinned',return_value={}),patch.object(orchestrator.replay33_assets,'replay',side_effect=mutate):
            with self.assertRaisesRegex(RuntimeError,'asset changed'):orchestrator.validate_before_publication(out,{},0,float('inf'),'manifest','pin',trace)

    def test_preflight_failure_leaves_only_non_evidence_nonce(self):
        out = self.root / "failed-preflight"
        out.mkdir()
        with (
            patch.object(orchestrator, "REAL33_RELEASE_ENABLED", True),
            patch.object(
                orchestrator,
                "reviewed_configuration",
                side_effect=ValueError("invalid pins"),
            ),
            patch.object(
                orchestrator.os, "fork", side_effect=AssertionError("must not fork")
            ),
        ):
            with self.assertRaisesRegex(ValueError, "invalid pins"):
                orchestrator.run(out, self.path, self.digest)
        self.assertTrue((out / "run_nonce").is_file())
        self.assertFalse((out / "armed.json").exists())
        self.assertFalse((out / "witness.json").exists())

    def test_preflight_deadline_blocks_before_fork(self):
        out = self.root / "deadline"
        out.mkdir()
        with (
            patch.object(orchestrator, "REAL33_RELEASE_ENABLED", True),
            patch.object(orchestrator.freeze33, "validate_frozen"),
            patch.object(orchestrator.time, "monotonic", side_effect=[0, 901]),
            patch.object(
                orchestrator.os, "fork", side_effect=AssertionError("must not fork")
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "preflight wall"):
                orchestrator.run(out, self.path, self.digest)
        self.assertFalse((out / "witness.json").exists())

    def test_child_forwards_reviewed_native_provider_without_real_fork(self):
        out = self.root / "child"
        out.mkdir()
        pipes = []
        original_pipe = os.pipe
        original_close = os.close

        def pipe():
            ends = original_pipe()
            pipes.extend(ends)
            return ends

        try:
            with (
                patch.object(orchestrator, "REAL33_RELEASE_ENABLED", True),
                patch.object(orchestrator.freeze33, "validate_frozen"),
                patch.object(
                    orchestrator.watchdog, "process_start", return_value=(1, 2)
                ),
                patch.object(orchestrator.os, "pipe", side_effect=pipe),
                patch.object(orchestrator.os, "fork", return_value=0),
                patch.object(orchestrator.os, "_exit", side_effect=SystemExit),
                patch.object(orchestrator.watchdog, "supervise") as supervise,
            ):
                with self.assertRaises(SystemExit):
                    orchestrator.run(out, self.path, self.digest)
            kwargs = supervise.call_args.kwargs
            self.assertIs(kwargs["use_native_census_helper"], True)
            self.assertEqual(kwargs["native_census_package"], self.package)
            self.assertEqual(
                kwargs["native_census_manifest"],
                self.manifest["census_provider"]["inventory"],
            )
            self.assertIs(kwargs["real_capability"], self.issued.return_value)
            self.assertEqual(kwargs["max_rss_kib"], 4 * 1024**2)
            self.assertEqual(kwargs["manifest_sha"], self.digest)
            self.assertLessEqual(kwargs["timeout"], 900)
        finally:
            for fd in pipes:
                try:
                    original_close(fd)
                except OSError:
                    pass

    def test_changed_preflight_blocks_g_release(self):
        out = self.root / "out"
        out.mkdir()
        config = {
            "package": self.package,
            "inventory": {"__init__.py": "a" * 64},
            "inventory_sha256": "b" * 64,
            "policy": self.manifest["budgets"],
            "dso_sha256": self.manifest["dso_sha256"],
        }
        writes = []
        original_write = os.write

        def write(fd, data):
            writes.append(data)
            return original_write(fd, data)

        selections = iter([([1], [], []), ([], [], [])])
        with (
            patch.object(orchestrator, "REAL33_RELEASE_ENABLED", True),
            patch.object(
                orchestrator,
                "reviewed_configuration",
                side_effect=[config, ValueError("changed pin")],
            ),
            patch.object(orchestrator.watchdog, "process_start", return_value=(1, 2)),
            patch.object(orchestrator.os, "fork", return_value=999999),
            patch.object(orchestrator.os, "waitpid", side_effect=ChildProcessError),
            patch.object(
                orchestrator.select, "select", side_effect=lambda *a: next(selections)
            ),
            patch.object(orchestrator.os, "read", return_value=b"R"),
            patch.object(orchestrator.os, "write", side_effect=write),
        ):
            with self.assertRaisesRegex(ValueError, "changed pin"):
                orchestrator.run(out, self.path, self.digest)
        self.assertNotIn(b"G", writes)
        self.assertFalse((out / "witness.json").exists())


if __name__ == "__main__":
    unittest.main()
