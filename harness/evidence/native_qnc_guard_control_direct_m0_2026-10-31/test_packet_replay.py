"""Negative checks on copies of the finalized packet; no model calls."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('qnc_verifier', HERE / 'verify_export.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


class PacketChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        with tarfile.open(HERE / 'chunk_artifacts.tar.gz', 'r:gz') as tar:
            for m in tar:
                if not m.isfile() or m.name.startswith('/') or '..' in Path(m.name).parts:
                    raise ValueError('unsafe member')
                dest = self.root / m.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(m) as src, dest.open('xb') as out:
                    shutil.copyfileobj(src, out)

    def tearDown(self):
        self.tmp.cleanup()

    def test_complete(self):
        self.assertEqual(v.verify(self.root)['control_cost'], 11.007967186042567)

    def test_missing_tail(self):
        shutil.rmtree(self.root / 'chunks/chunk_128')
        with self.assertRaisesRegex(ValueError, 'chunk set'):
            v.verify(self.root)

    def test_failure_receipt(self):
        (self.root / 'chunks/chunk_128/failure.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'failure'):
            v.verify(self.root)

    def test_corrupt_capture(self):
        (self.root / 'chunks/chunk_128/result.npz').write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'capture hash'):
            v.verify(self.root)

    def test_forged_receipt(self):
        path = self.root / 'chunks/chunk_128/result.json'
        receipt = json.loads(path.read_text())
        receipt['direct_calls'] = 0
        path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError, 'result mismatch'):
            v.verify(self.root)

    def test_swapped_source_indices(self):
        path = self.root / 'chunks/chunk_000/result.json'
        receipt = json.loads(path.read_text())
        indices = receipt['rttov_receipt']['source_flat_indices']
        indices[0], indices[1] = indices[1], indices[0]
        path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError, 'source index identity'):
            v.verify(self.root)

    def test_invalid_driver_flag(self):
        path = self.root / 'chunks/chunk_000/result.json'
        receipt = json.loads(path.read_text())
        receipt['rttov_receipt']['driver_flags']['case_do_k'] = True
        path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError, 'case driver flags'):
            v.verify(self.root)

    def test_mutated_verifier_source(self):
        spec = importlib.util.spec_from_file_location('qnc_official', HERE / 'packet_replay.py')
        official = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(official)
        shutil.copyfile(HERE / 'chunk_artifacts.tar.gz', self.root / 'chunk_artifacts.tar.gz')
        (self.root / 'verify_export.py').write_text('modified')
        (self.root / 'executed_sources').mkdir()
        shutil.copyfile(HERE / 'executed_sources/verify_control_direct.py.txt', self.root / 'executed_sources/verify_control_direct.py.txt')
        shutil.copyfile(HERE / 'executed_sources/verify_export_executed.py.txt', self.root / 'executed_sources/verify_export_executed.py.txt')
        official.HERE = self.root
        with self.assertRaisesRegex(ValueError, 'source hash mismatch'):
            official.main()

    def test_forged_summary(self):
        path = self.root / 'summary.json'
        summary = json.loads(path.read_text())
        summary['cost'] = 0.0
        path.write_text(json.dumps(summary))
        with self.assertRaisesRegex(ValueError, 'summary arithmetic'):
            v.verify(self.root)


if __name__ == '__main__':
    unittest.main()
