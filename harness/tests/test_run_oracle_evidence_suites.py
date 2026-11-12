import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('evidence_runner', ROOT / 'harness/run_oracle_evidence_suites.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class EvidenceRunnerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'harness/evidence').mkdir(parents=True)
        self.report = self.root / 'result.json'

    def suite(self, name, code):
        path = self.root / 'harness/evidence' / name
        path.mkdir()
        (path / 'test_case.py').write_text(code)
        return 'harness/evidence/' + name

    def registry(self, suites, count=None):
        path = self.root / 'registry.json'
        path.write_text(json.dumps({'schema':'kdm6.oracle_evidence_suites.v1', 'expected_count':len(suites) if count is None else count, 'suites':suites, 'excluded_test_directories':{}, 'allowed_skips':{}}))
        return path

    def test_real_registry_has_original_49_unique_suites(self):
        suites = runner.read_registry()
        self.assertGreaterEqual(len(suites), 50)
        self.assertEqual(len(set(suites)), len(suites))

    def test_registry_rejects_missing_duplicate_escape_and_count(self):
        good = self.suite('good', 'import unittest\n')
        for values, count in [([good, good], None), ([good, 'harness/evidence/nope'], None), (['harness/evidence/../good'], None), ([good], 2), ([], None)]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                runner.read_registry(self.registry(values, count), self.root)

    def test_unclassified_directory_requires_explicit_exclusion(self):
        active = self.suite('active', 'import unittest\n')
        other = self.suite('other', 'import unittest\n')
        path = self.registry([active])
        with self.assertRaisesRegex(ValueError, 'unclassified'):
            runner.read_registry(path, self.root)
        data = json.loads(path.read_text())
        data['excluded_test_directories'] = {other: 'Historical test outside this gate.'}
        path.write_text(json.dumps(data))
        self.assertEqual(runner.read_registry(path, self.root), [active])
        data['excluded_test_directories'][active] = 'overlap'
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'overlap'):
            runner.read_registry(path, self.root)
        data['excluded_test_directories'] = {other: ''}
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'invalid excluded'):
            runner.read_registry(path, self.root)

    def test_duplicate_json_key_rejected(self):
        path = self.root / 'registry.json'
        path.write_text('{"schema":"x", "schema":"y"}')
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
            runner.read_registry(path, self.root)

    def test_success_and_optimization_propagates_to_grandchild(self):
        code = '''import os, subprocess, sys, unittest
class T(unittest.TestCase):
 def test_mode(self):
  self.assertEqual(sys.flags.optimize, int(os.getenv('EXPECT_OPT', '0')))
  self.assertEqual(subprocess.check_output([sys.executable, '-c', 'import sys; print(sys.flags.optimize)']).decode().strip(), os.getenv('EXPECT_OPT', '0'))
'''
        suites = [self.suite('a', code), self.suite('b', code)]
        for mode in ('normal','optimized'):
            with mock.patch.dict(os.environ, {'EXPECT_OPT': '1' if mode == 'optimized' else '0', 'PYTHONOPTIMIZE':'1'}):
                self.assertTrue(runner.run(suites, mode, self.report, root=self.root))
            result = json.loads(self.report.read_text())
            self.assertEqual([r['suite'] for r in result['suites']], suites)
            self.assertTrue(result['success'])

    def test_failure_zero_test_signal_timeout_and_incomplete(self):
        cases = [('fail', 'import unittest\nclass T(unittest.TestCase):\n def test_x(self): self.fail()\n', 'fail'),
                 ('zero', 'import unittest\n', 'fail'),
                 ('signal', 'import os,signal\nos.kill(os.getpid(), signal.SIGTERM)\n', 'fail'),
                 ('slow', 'import time\ntime.sleep(2)\n', 'timeout')]
        for name, code, status in cases:
            suite = self.suite(name, code)
            with self.subTest(name=name):
                self.assertFalse(runner.run([suite], 'normal', self.report, root=self.root, timeout=.5 if name == 'slow' else 10))
                result = json.loads(self.report.read_text())
                self.assertEqual(result['suites'][0]['status'], status)
                self.assertFalse(result['success'])

    def test_skip_accounting_and_inconsistent_report(self):
        suite = self.suite('skip', "import unittest\nclass T(unittest.TestCase):\n @unittest.skip('because')\n def test_skip(self): pass\n def test_pass(self): pass\n")
        self.assertFalse(runner.run([suite], 'normal', self.report, root=self.root))
        allow = {suite: {'test_case.T.test_skip': 'because'}}
        self.assertTrue(runner.run([suite], 'normal', self.report, root=self.root, allowed_skips=allow))
        result = json.loads(self.report.read_text())['suites'][0]
        self.assertEqual((result['tests'], result['skipped']), (2, 1))
        self.assertEqual(len(result['skip_reasons']), 1)
        self.assertIn('because', result['skip_reasons'][0])
        fake = self.root / 'fake_python'
        fake.write_text("#!/bin/sh\necho \"test_a ... skipped 'x'\"\necho 'Ran 2 tests in 0.1s'\necho 'OK (skipped=2)'\n")
        fake.chmod(0o755)
        self.assertFalse(runner.run([suite], 'normal', self.report, root=self.root, python=str(fake)))

    def test_schedule_is_longest_first_stable_and_hints_validated(self):
        self.assertEqual(runner.schedule(['a', 'b', 'c', 'd'], {'a':1, 'b':3, 'c':3}), [(1,'b'),(2,'c'),(0,'a'),(3,'d')])
        suite = self.suite('timed', 'import unittest\n')
        path = self.registry([suite])
        data = json.loads(path.read_text())
        for bad in (-1, float('nan'), True):
            data['timing_hints_seconds'] = {'normal': {suite: bad}}
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError): runner.read_registry(path, self.root)

    def test_skip_wrong_reason_and_missing_approved(self):
        suite = self.suite('skip_extra', "import unittest\nclass T(unittest.TestCase):\n @unittest.skip('actual')\n def test_skip(self): pass\n")
        with self.subTest('wrong reason'):
            self.assertFalse(runner.run([suite], 'normal', self.report, root=self.root, allowed_skips={suite: {'test_case.T.test_skip':'other'}}))
        passing = self.suite('no_skip', "import unittest\nclass T(unittest.TestCase):\n def test_ok(self): pass\n")
        self.assertTrue(runner.run([passing], 'normal', self.report, root=self.root, allowed_skips={passing: {'test_case.T.missing': 'allowed'}}))

    def test_provenance_required_for_ci_but_not_synthetic_root(self):
        with mock.patch.dict(os.environ, {'GITHUB_ACTIONS':'true'}, clear=True):
            details = runner.provenance(self.root, self.root / 'no-registry', 'normal', 2, 300)
            self.assertIsNone(details['head_commit'])
            with self.assertRaisesRegex(ValueError, 'CI provenance'):
                runner.provenance(runner.ROOT, runner.REGISTRY, 'normal', 2, 300)
        with mock.patch.dict(os.environ, {'GITHUB_ACTIONS':'true', 'GITHUB_RUN_ID':'12', 'GITHUB_RUN_ATTEMPT':'2', 'GITHUB_SHA':'0'*40}, clear=True):
            with self.assertRaisesRegex(ValueError, 'CI provenance'):
                runner.provenance(runner.ROOT, runner.REGISTRY, 'normal', 2, 300)
        details = runner.provenance(runner.ROOT, runner.REGISTRY, 'normal', 2, 300)
        with mock.patch.dict(os.environ, {'GITHUB_ACTIONS':'true', 'GITHUB_RUN_ID':'12', 'GITHUB_RUN_ATTEMPT':'2', 'GITHUB_SHA':details['head_commit']}, clear=True):
            ci = runner.provenance(runner.ROOT, runner.REGISTRY, 'normal', 2, 300)
            self.assertEqual((ci['github_run_id'], ci['github_run_attempt']), ('12','2'))
        self.assertRegex(details['head_commit'], r'^[0-9a-f]{40}$')
        self.assertRegex(details['head_tree'], r'^[0-9a-f]{40}$')
        self.assertRegex(details['registry_sha256'], r'^[0-9a-f]{64}$')
        self.assertEqual((details['workers'], details['timeout_seconds']), (2, 300))
        with self.assertRaisesRegex(ValueError, 'registry changed'):
            runner.run(['dummy'], 'normal', self.report, root=self.root, expected_registry_sha='0'*64)

    def test_timeout_kills_term_ignoring_grandchild_after_parent_exits(self):
        pidfile = self.root / 'grandchild_pid'
        fake = self.root / 'fake_python'
        fake.write_text("#!/usr/bin/env python3\nimport subprocess,sys,time\nc=subprocess.Popen([sys.executable,'-c','import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(60)'])\nopen(" + repr(str(pidfile)) + ", 'w').write(str(c.pid))\ntime.sleep(60)\n")
        fake.chmod(0o755)
        # Allow enough startup time on a contended CI host for the child to
        # publish its PID before exercising the timeout cleanup path.
        self.assertFalse(runner.run(['dummy'], 'normal', self.report, root=self.root, python=str(fake), timeout=3))
        pid = int(pidfile.read_text())
        def alive():
            try: os.kill(pid, 0)
            except ProcessLookupError: return False
            proc = subprocess.run(['ps', '-o', 'stat=', '-p', str(pid)], capture_output=True, text=True)
            return proc.returncode == 0 and not proc.stdout.strip().startswith('Z')
        try:
            deadline = time.monotonic() + 2
            while alive() and time.monotonic() < deadline: time.sleep(.05)
            self.assertFalse(alive(), 'grandchild survived process group cleanup')
        finally:
            if alive(): os.kill(pid, signal.SIGKILL)

    def test_completed_parent_with_grandchild_fails_closed(self):
        pidfile = self.root / 'leaked_pid'
        fake = self.root / 'fake_leak'
        fake.write_text("#!/usr/bin/env python3\nimport subprocess,sys\nc=subprocess.Popen([sys.executable,'-c','import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(60)'])\nopen(" + repr(str(pidfile)) + ", 'w').write(str(c.pid))\nprint('Ran 1 test in 0.001s\\nOK')\n")
        fake.chmod(0o755)
        self.assertFalse(runner.run(['dummy'], 'normal', self.report, root=self.root, python=str(fake), timeout=5))
        self.assertEqual(json.loads(self.report.read_text())['suites'][0]['status'], 'fail')
        pid = int(pidfile.read_text())
        proc = subprocess.run(['ps', '-o', 'stat=', '-p', str(pid)], capture_output=True, text=True)
        if proc.returncode == 0 and not proc.stdout.strip().startswith('Z'):
            os.kill(pid, signal.SIGKILL)
            self.fail('grandchild remained live')

    def test_eperm_timeout_and_interruption_still_write_failure_report(self):
        suite = self.suite('eperm', 'import time\ntime.sleep(60)\n')
        def denied(_pid, _sig):
            raise PermissionError(1, 'operation not permitted')
        with mock.patch.object(runner.os, 'killpg', side_effect=denied):
            self.assertFalse(runner.run([suite], 'normal', self.report, root=self.root, timeout=.4))
        record = json.loads(self.report.read_text())
        self.assertFalse(record['success'])
        self.assertEqual(record['suites'][0]['status'], 'timeout')
        self.assertIn('operation not permitted', record['suites'][0]['cleanup_error'])
        self.assertTrue(record['suites'][0]['leaked_or_unverified_group'])
        original_sleep = runner.time.sleep
        calls = iter([True])
        def interrupt_once(delay):
            if next(calls, False): raise KeyboardInterrupt
            original_sleep(delay)
        with mock.patch.object(runner.os, 'killpg', side_effect=denied), mock.patch.object(runner.time, 'sleep', side_effect=interrupt_once):
            self.assertFalse(runner.run([suite], 'normal', self.report, root=self.root))
        record = json.loads(self.report.read_text())
        self.assertFalse(record['success'])
        self.assertEqual(record['suites'][0]['status'], 'cancelled')
        self.assertIn('operation not permitted', record['suites'][0]['cleanup_error'])
        self.assertTrue(record['suites'][0]['leaked_or_unverified_group'])

    def test_unexpected_finally_cleanup_exception_still_reports(self):
        suite = self.suite('cleanup_broken', 'import time\ntime.sleep(60)\n')
        original_sleep = runner.time.sleep
        calls = iter([True])
        def interrupt_once(delay):
            if next(calls, False): raise KeyboardInterrupt
            original_sleep(delay)
        original_killpg = runner.os.killpg
        def cleanup_raises(pid, _sig):
            try: original_killpg(pid, signal.SIGKILL)
            except ProcessLookupError: pass
            raise RuntimeError('synthetic cleanup failure')
        with mock.patch.object(runner.os, 'killpg', side_effect=cleanup_raises), mock.patch.object(runner.time, 'sleep', side_effect=interrupt_once):
            self.assertFalse(runner.run([suite], 'normal', self.report, root=self.root))
        record = json.loads(self.report.read_text())
        self.assertFalse(record['success'])
        self.assertIn('synthetic cleanup failure', record['suites'][0]['cleanup_error'])

    def test_spawn_failure(self):
        suite = self.suite('x', 'import unittest\n')
        self.assertFalse(runner.run([suite], 'normal', self.report, root=self.root, python='/missing/python'))
        self.assertEqual(json.loads(self.report.read_text())['suites'][0]['status'], 'spawn_error')

    def test_interruption_cancels_and_marks_pending(self):
        suites = [self.suite(str(i), 'import time\ntime.sleep(5)\n') for i in range(3)]
        original_sleep = runner.time.sleep
        calls = iter([True])
        def interrupt_once(delay):
            if next(calls, False): raise KeyboardInterrupt
            original_sleep(delay)
        with mock.patch.object(runner.time, 'sleep', side_effect=interrupt_once):
            self.assertFalse(runner.run(suites, 'normal', self.report, root=self.root))
        result = json.loads(self.report.read_text())
        self.assertEqual([x['status'] for x in result['suites']], ['cancelled', 'cancelled', 'not_run'])

    def test_repeated_interrupt_during_cleanup_still_reports_failure(self):
        suite = self.suite('interrupt_twice', 'import time\ntime.sleep(5)\n')
        with mock.patch.object(runner.time, 'sleep', side_effect=KeyboardInterrupt):
            self.assertFalse(runner.run([suite], 'normal', self.report, root=self.root, workers=1))
        result = json.loads(self.report.read_text())
        self.assertFalse(result['success'])
        self.assertEqual(result['suites'][0]['status'], 'cancelled')
        self.assertFalse(result['success'])


if __name__ == '__main__': unittest.main()
