import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
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
        path.write_text(json.dumps({'schema':'kdm6.oracle_evidence_suites.v1', 'expected_count':len(suites) if count is None else count, 'suites':suites, 'excluded_test_directories':{}}))
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
        self.assertTrue(runner.run([suite], 'normal', self.report, root=self.root))
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
        self.assertFalse(result['success'])


if __name__ == '__main__': unittest.main()
