import json
import hashlib
import io
import subprocess
import tempfile
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

if __package__:
    from . import ci_build as ci
else:  # direct discovery with -s producer_source_batch6
    import ci_build as ci


class DriverTests(unittest.TestCase):
    def test_failed_command_is_recorded(self):
        receipt = {'commands': []}
        with patch.object(ci.subprocess, 'run', return_value=subprocess.CompletedProcess(['fake'], 2, 'out', 'bad')):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError, 'command failed'):
                    ci.run(['fake'], receipt)
        self.assertEqual(receipt['commands'][0]['returncode'], 2)
        self.assertEqual(receipt['commands'][0]['stderr'], 'bad')

    def test_missing_tool_is_recorded(self):
        receipt = {'commands': []}
        with patch.object(ci.subprocess, 'run', side_effect=FileNotFoundError('missing fake tool')):
            with self.assertRaisesRegex(RuntimeError, 'could not complete'):
                ci.run(['fake'], receipt)
        self.assertIn('missing fake tool', receipt['commands'][0]['error'])

    def test_flags_require_assertions_and_strict_fp(self):
        with tempfile.TemporaryDirectory() as temp:
            build = Path(temp)
            db = build / 'compile_commands.json'
            def write(flags):
                db.write_text(json.dumps([{'file': '/src/tests/test_x.cpp', 'arguments': ['c++', 'CMakeFiles/test_x.dir/a.o', *flags]}]))
            write(['-DNDEBUG', '-UNDEBUG', '-ffp-contract=off'])
            self.assertEqual(ci.check_flags(build), ['test_x.cpp'])
            write(['-UNDEBUG', '-DNDEBUG', '-ffp-contract=off'])
            with self.assertRaisesRegex(ValueError, 'assertions disabled'):
                ci.check_flags(build)
            write(['-UNDEBUG', '-ffp-contract=fast'])
            with self.assertRaisesRegex(ValueError, 'floating-point'):
                ci.check_flags(build)

    def test_export_mismatch_fails(self):
        with patch.object(ci.platform, 'system', return_value='Linux'), patch.object(ci, 'run', return_value='000 T unexpected@@KDM6_2\n'):
            with self.assertRaisesRegex(ValueError, 'export mismatch'):
                ci.exports(Path('/fake'), {'expected'}, {'commands': []})

    def test_missing_asset_writes_failed_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            receipt_path = Path(temp) / 'receipt.json'
            with patch.object(ci.replay, 'HERE', Path(temp)), patch.object(sys, 'argv', ['ci_build.py', '--receipt', str(receipt_path)]):
                with redirect_stderr(io.StringIO()):
                    self.assertEqual(ci.main(), 1)
            receipt = json.loads(receipt_path.read_text())
            self.assertEqual(receipt['status'], 'failed')
            self.assertIn('FileNotFoundError', receipt['error'])

    def test_junit_requires_exact_successful_inventory(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'results.xml'
            path.write_text('<testsuite><testcase name="a"/><testcase name="b"/></testsuite>')
            self.assertEqual(ci.check_junit(path, {'a', 'b'})['tests'], 2)
            path.write_text('<testsuite><testcase name="a"><skipped/></testcase></testsuite>')
            with self.assertRaisesRegex(ValueError, 'unsuccessful'):
                ci.check_junit(path, {'a'})
            with self.assertRaisesRegex(ValueError, 'inventory mismatch'):
                ci.check_junit(path, {'a', 'b'})

    def test_preserve_regular_artifacts_and_reject_mutations(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build = root / 'build'
            build.mkdir()
            source = root / 'source'
            source.mkdir()
            snapshot = source / 'a7_ledger_snapshot.json'
            snapshot.write_bytes(b'snapshot')
            for name in ('libkdm6_c.so.2.0.0', 'test_batch6_synthetic_capture_parity', 'compile_commands.json', 'ctest-results.xml'):
                (build / name).write_bytes(name.encode())
            receipt = {'status': 'passed', 'source_asset_sha256': {'a7_ledger_snapshot.json': hashlib.sha256(b'snapshot').hexdigest()},
                       'unrun_tests': dict(ci.UNRUN_TESTS), 'builds': {'ON': {'exports': ['example'], 'passed_ctests': sorted(ci.RUN_TESTS)}}}
            with patch.object(ci.replay, 'HERE', source), patch.dict(ci.replay.ASSETS, {'a7_ledger_snapshot.json': hashlib.sha256(b'snapshot').hexdigest()}):
                with patch.dict(ci.FILE_LIMITS, {'libkdm6_c.so.2.0.0': 1}):
                    with self.assertRaisesRegex(ValueError, 'artifact file size bound'):
                        ci.preserve_artifacts(build, root / 'oversized', receipt, {'system': 'Linux'})
                    self.assertFalse((root / 'oversized').exists())
                dest = root / 'out'
                manifest = ci.preserve_artifacts(build, dest, receipt, {'system': 'Linux', 'architecture': 'fake'})
                self.assertEqual(manifest['parity_status'], 'CONTAINMENT_PENDING')
                self.assertEqual((dest / 'test_batch6_synthetic_capture_parity').read_bytes(), b'test_batch6_synthetic_capture_parity')
                for name, meta in manifest['files'].items():
                    self.assertEqual(hashlib.sha256((dest / name).read_bytes()).hexdigest(), meta['sha256'])
                with self.assertRaisesRegex(ValueError, 'unsafe artifact destination'):
                    ci.preserve_artifacts(build, root / 'other' / '..' / 'escape', receipt, {'system': 'Linux'})
                with self.assertRaisesRegex(ValueError, 'already exists'):
                    ci.preserve_artifacts(build, dest, receipt, {'system': 'Linux'})
                executable = build / 'test_batch6_synthetic_capture_parity'
                executable.unlink()
                with self.assertRaisesRegex(ValueError, 'missing or unsafe'):
                    ci.preserve_artifacts(build, root / 'missing', receipt, {'system': 'Linux'})
                outside = root / 'outside'
                outside.write_bytes(b'fake')
                executable.symlink_to(outside)
                with self.assertRaisesRegex(ValueError, 'missing or unsafe'):
                    ci.preserve_artifacts(build, root / 'link', receipt, {'system': 'Linux'})
                executable.unlink()
                executable.write_bytes(b'fake')
                snapshot.write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError, 'snapshot changed'):
                    ci.preserve_artifacts(build, root / 'changed', receipt, {'system': 'Linux'})

    def test_research_build_includes_shared_library(self):
        receipt = {'commands': [], 'builds': {}}
        commands = []
        def fake_run(cmd, receipt):
            commands.append(cmd)
            if '--show-only=json-v1' in cmd:
                return json.dumps({'tests': [{'name': x} for x in
                    (ci.OFF_TESTS | ci.TARGET_TESTS if str(cmd[2]).endswith('/on') else ci.OFF_TESTS)]})
            return ''
        with patch.object(ci, 'run', side_effect=fake_run), patch.object(ci, 'check_flags', return_value=['test_x.cpp']), patch.object(ci, 'exports', return_value=[]), patch.object(ci, 'check_junit', return_value={'tests': 1, 'failures': 0, 'errors': 0, 'skipped': 0}):
            ci.build_all(Path('/fake/source'), Path('/fake/build'), '/fake/torch', receipt)
        on_build = next(cmd for cmd in commands if cmd[:2] == ['cmake', '--build'] and str(cmd[2]).endswith('/on'))
        self.assertIn('kdm6_c', on_build[on_build.index('--target') + 1:])
        self.assertTrue({'test_' + name for name in ci.TARGET_TESTS} <= set(on_build))
        on_ctest = next(cmd for cmd in commands if cmd[0] == 'ctest' and str(cmd[2]).endswith('/on') and '--output-junit' in cmd)
        self.assertEqual(on_ctest[on_ctest.index('-R') + 1], '^(' + '|'.join(sorted(ci.RUN_TESTS)) + ')$')
        self.assertEqual(receipt['builds']['ON']['passed_ctests'], sorted(ci.RUN_TESTS))
        self.assertEqual(receipt['unrun_tests'], {'batch6_synthetic_capture_parity': 'CONTAINMENT_PENDING'})
        self.assertNotIn('batch6_synthetic_capture_parity', receipt['builds']['ON']['passed_ctests'])
        self.assertEqual(len(ci.RUN_TESTS), 4)
        self.assertEqual(ci.TARGET_TESTS, ci.RUN_TESTS | set(ci.UNRUN_TESTS))

    def test_build_stops_on_missing_research_ctest(self):
        receipt = {'commands': [], 'builds': {}}
        def fake_run(cmd, receipt):
            if '--show-only=json-v1' in cmd:
                return json.dumps({'tests': [{'name': name} for name in ci.OFF_TESTS]})
            return ''
        with patch.object(ci, 'run', side_effect=fake_run), patch.object(ci, 'check_flags', return_value=['test_x.cpp']), patch.object(ci, 'exports', return_value=[]), patch.object(ci, 'check_junit', return_value={'tests': 1, 'failures': 0, 'errors': 0, 'skipped': 0}):
            with self.assertRaisesRegex(ValueError, 'invalid research CTest inventory'):
                ci.build_all(Path('/fake/source'), Path('/fake/build'), '/fake/torch', receipt)
        self.assertEqual(receipt['builds']['OFF']['passed_ctests'], sorted(ci.OFF_TESTS))
        self.assertNotIn('passed_ctests', receipt['builds']['ON'])


if __name__ == '__main__':
    unittest.main()
