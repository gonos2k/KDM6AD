import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

if __package__:
    from . import ci_build as ci
    from . import validate_build_artifact as validator
else:
    import ci_build as ci
    import validate_build_artifact as validator


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.build = self.root / 'build'
        self.build.mkdir()
        self.output = self.root / 'artifact'
        self.env = {'system': 'Linux', 'architecture': 'x86_64', 'python_abi': 'cpython-312',
                    'torch': '2.8.0+cpu', 'compiler_version': 'fake compiler', 'cmake_version': 'fake cmake'}
        commands = [
            {'file': '/source/src/runtime.cpp', 'arguments': ['c++', '-DNDEBUG', '-ffp-contract=off', '-DKDM6_BATCH5_RESEARCH_CAPTURE']},
            {'file': '/source/tests/test_x.cpp', 'arguments': ['c++', '-DNDEBUG', '-UNDEBUG', '-ffp-contract=off', 'CMakeFiles/test_x.dir/x.o']},
        ]
        (self.build / 'compile_commands.json').write_text(json.dumps(commands))
        (self.build / 'ctest-results.xml').write_text('<testsuite>' + ''.join(f'<testcase name="{x}"/>' for x in sorted(ci.RUN_TESTS)) + '</testsuite>')
        (self.build / 'libkdm6_c.so.2.0.0').write_bytes(b'fake-dso')
        (self.build / 'test_batch6_synthetic_capture_parity').write_bytes(b'fake-executable')
        pin = ci.replay.ASSETS['a7_ledger_snapshot.json']
        assets = {'a7_ledger_snapshot.json': pin, 'a7_ledger.patch': ci.replay.ASSETS['a7_ledger.patch']}
        receipt = {'status': 'passed', 'source_asset_sha256': assets, 'unrun_tests': dict(ci.UNRUN_TESTS),
                   'builds': {'ON': {'exports': sorted(ci.BASE | ci.RESEARCH), 'passed_ctests': sorted(ci.RUN_TESTS),
                                      'junit_counts': {'tests': 4, 'failures': 0, 'errors': 0, 'skipped': 0},
                                      'test_sources_with_assertions': ['test_x.cpp']}}}
        ci.preserve_artifacts(self.build, self.output, receipt, self.env)
        self.expected = {**self.env, 'snapshot_sha256': pin, 'source_assets_sha256': assets,
                         'required_compile_flags': ['-ffp-contract=off'], 'exports': sorted(ci.BASE | ci.RESEARCH),
                         'binary_sha256': {name: hashlib.sha256((self.output / name).read_bytes()).hexdigest()
                                           for name in ('libkdm6_c.so.2.0.0', 'test_batch6_synthetic_capture_parity')}}

    def validate(self):
        return validator.validate(self.output, self.expected)

    def rehash(self, name):
        path = self.output / 'manifest.json'
        manifest = json.loads(path.read_text())
        data = (self.output / name).read_bytes()
        manifest['files'][name] = {'sha256': hashlib.sha256(data).hexdigest(), 'size_bytes': len(data)}
        path.write_text(json.dumps(manifest))

    def test_valid_bundle_is_not_authorization(self):
        result = self.validate()
        self.assertEqual(result['status'], 'VERIFIED_BUILD_ASSET_ONLY')
        self.assertEqual(result['eligibility'], 'NOT_ELIGIBLE')
        self.assertEqual(result['parity_status'], 'CONTAINMENT_PENDING')

    def test_binary_mutation_symlink_and_unexpected_file_rejected(self):
        path = self.output / 'test_batch6_synthetic_capture_parity'
        path.write_bytes(b'changed')
        with self.assertRaises(ValueError):
            self.validate()
        self.rehash(path.name)
        with self.assertRaisesRegex(ValueError, 'independent binary pins'):
            self.validate()
        path.unlink()
        path.symlink_to(self.build / 'test_batch6_synthetic_capture_parity')
        with self.assertRaises(ValueError):
            self.validate()
        path.unlink()
        path.write_bytes(b'fake-executable')
        (self.output / 'extra').write_text('x')
        with self.assertRaises(ValueError):
            self.validate()

    def test_changed_expectations_rejected(self):
        for key in ('system', 'architecture', 'python_abi', 'torch', 'compiler_version', 'cmake_version', 'snapshot_sha256'):
            with self.subTest(key=key):
                previous = self.expected[key]
                self.expected[key] = 'changed'
                with self.assertRaises(ValueError):
                    self.validate()
                self.expected[key] = previous

    def test_rehashed_junit_skip_and_flag_change_rejected(self):
        junit = self.output / 'ctest-results.xml'
        junit.write_text('<testsuite>' + ''.join(f'<testcase name="{x}"><skipped/></testcase>' for x in sorted(ci.RUN_TESTS)) + '</testsuite>')
        self.rehash(junit.name)
        with self.assertRaises(ValueError):
            self.validate()
        junit.write_text('<testsuite>' + ''.join(f'<testcase name="{x}"/>' for x in sorted(ci.RUN_TESTS)) + '</testsuite>')
        self.rehash(junit.name)
        commands = self.output / 'compile_commands.json'
        db = json.loads(commands.read_text())
        db[0]['arguments'].remove('-ffp-contract=off')
        commands.write_text(json.dumps(db))
        self.rehash(commands.name)
        with self.assertRaises(ValueError):
            self.validate()

    def test_rehashed_receipt_cannot_change_unrun_or_exports(self):
        receipt = self.output / 'ci_receipt.json'
        for change in ('unrun', 'exports'):
            original = json.loads(receipt.read_text())
            modified = copy.deepcopy(original)
            if change == 'unrun':
                modified['unrun_tests'] = {}
            else:
                modified['builds']['ON']['exports'].append('leak')
            receipt.write_text(json.dumps(modified))
            self.rehash(receipt.name)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.validate()
            receipt.write_text(json.dumps(original))
            self.rehash(receipt.name)

    def test_per_file_and_total_size_bounds(self):
        with patch.dict(ci.FILE_LIMITS, {'libkdm6_c.so.2.0.0': 1}):
            with self.assertRaisesRegex(ValueError, 'file size bound'):
                self.validate()
        with patch.object(ci, 'MAX_ARTIFACT_BYTES', 1):
            with self.assertRaises(ValueError):
                self.validate()

    def test_no_binary_execution(self):
        with patch('subprocess.run', side_effect=AssertionError('unexpected execution')):
            self.validate()


if __name__ == '__main__':
    unittest.main()
