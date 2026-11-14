import json
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

    def test_research_build_includes_shared_library(self):
        receipt = {'commands': [], 'builds': {}}
        commands = []
        def fake_run(cmd, receipt):
            commands.append(cmd)
            if '--show-only=json-v1' in cmd:
                return json.dumps({'tests': [{'name': x} for x in
                    (ci.TARGET_TESTS if str(cmd[2]).endswith('/on') else ci.OFF_TESTS)]})
            return ''
        with patch.object(ci, 'run', side_effect=fake_run), patch.object(ci, 'check_flags', return_value=['test_x.cpp']), patch.object(ci, 'exports', return_value=[]), patch.object(ci, 'check_junit', return_value={'tests': 1, 'failures': 0, 'errors': 0, 'skipped': 0}):
            ci.build_all(Path('/fake/source'), Path('/fake/build'), '/fake/torch', receipt)
        on_build = next(cmd for cmd in commands if cmd[:2] == ['cmake', '--build'] and str(cmd[2]).endswith('/on'))
        self.assertIn('kdm6_c', on_build[on_build.index('--target') + 1:])
        self.assertTrue({'test_' + name for name in ci.TARGET_TESTS} <= set(on_build))

    def test_build_stops_on_missing_research_ctest(self):
        receipt = {'commands': [], 'builds': {}}
        def fake_run(cmd, receipt):
            if '--show-only=json-v1' in cmd:
                return json.dumps({'tests': [{'name': name} for name in ci.OFF_TESTS]})
            return ''
        with patch.object(ci, 'run', side_effect=fake_run), patch.object(ci, 'check_flags', return_value=['test_x.cpp']), patch.object(ci, 'exports', return_value=[]), patch.object(ci, 'check_junit', return_value={'tests': 1, 'failures': 0, 'errors': 0, 'skipped': 0}):
            with self.assertRaisesRegex(ValueError, 'missing research CTests'):
                ci.build_all(Path('/fake/source'), Path('/fake/build'), '/fake/torch', receipt)
        self.assertEqual(receipt['builds']['OFF']['passed_ctests'], sorted(ci.OFF_TESTS))
        self.assertNotIn('passed_ctests', receipt['builds']['ON'])


if __name__ == '__main__':
    unittest.main()
