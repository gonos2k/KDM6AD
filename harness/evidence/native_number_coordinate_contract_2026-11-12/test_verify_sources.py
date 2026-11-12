import gzip, hashlib, importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock
p=Path(__file__).with_name('verify_sources.py');spec=importlib.util.spec_from_file_location('number_review',p);v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
class SourceTests(unittest.TestCase):
    def test_historical_skips_current(self):
        original=Path.read_bytes
        def guarded(path):
            if any(path==v.ROOT/name for name in v.ARCHIVES):raise AssertionError('live source read')
            return original(path)
        with mock.patch.object(Path,'read_bytes',guarded):
            self.assertEqual(v.verify()['current_public_and_private_source'],'SKIPPED')
    def test_current_source_freshness(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'public';host=Path(d)/'host';host.mkdir()
            for name in v.ARCHIVES:
                target=root/name;target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(gzip.decompress((v.HERE/'reviewed_source'/(name+'.gz')).read_bytes()))
            fake=b'private reviewed source';(host/'source').write_bytes(fake)
            with mock.patch.object(v,'PRIVATE',{'source':hashlib.sha256(fake).hexdigest()}):
                self.assertEqual(v.verify(host,require_current_source=True,current_root=root)['current_public_and_private_source'],'MATCH')
                (root/'libtorch/src/runtime.cpp').write_bytes(b'changed')
                self.assertEqual(v.verify()['current_public_and_private_source'],'SKIPPED')
                with self.assertRaisesRegex(ValueError,'reviewed source changed'):
                    v.verify(host,require_current_source=True,current_root=root)
    def test_freshness_requires_private_root(self):
        with self.assertRaisesRegex(ValueError,'private host root required'):
            v.verify(require_current_source=True)
if __name__=='__main__':unittest.main()
