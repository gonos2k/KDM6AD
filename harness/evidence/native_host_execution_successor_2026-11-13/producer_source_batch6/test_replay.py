import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('batch6_replay', HERE / 'replay.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parent = m.parent_module()
        cls.patch = (HERE / 'rain_checkpoint.patch').read_bytes()
        cls.target = {'libtorch/' + k: v for k, v in json.loads((HERE / 'source_snapshot.json').read_bytes()).items()}
        cls.base = json.loads((m.PARENT.parent / 'source_manifest.json').read_bytes())['target_file_sha256']

    def test_reconstruction(self):
        result = m.replay()
        self.assertEqual((result['base_files'], result['changed_files'], result['reconstructed_files']), (76, 9, 77))
        self.assertEqual(result['scientific_status'], 'INCONCLUSIVE')

    def test_rehashed_patch_path_and_mode_rejected(self):
        for bad in (self.patch.replace(b'a/libtorch/CMakeLists.txt', b'a/libtorch/../CMakeLists.txt', 1),
                    self.patch.replace(b'new file mode 100644', b'new file mode 120000', 1)):
            with self.subTest():
                with self.assertRaises(ValueError):
                    m.validate_patch(self.parent, bad, self.base, self.target)

    def test_rehashed_target_content_or_inventory_rejected(self):
        for mutation in ('digest', 'missing', 'extra'):
            with self.subTest(mutation=mutation), self.parent.reconstructed_tree() as (root, _):
                target = dict(self.target)
                if mutation == 'digest': target['libtorch/CMakeLists.txt'] = '0' * 64
                elif mutation == 'missing': target.pop('libtorch/CMakeLists.txt')
                else: target['libtorch/extra'] = '0' * 64
                with self.assertRaises(ValueError): m.apply_and_validate(self.parent, root, self.patch, target)

    def test_unexpected_file_and_link_rejected(self):
        for kind in ('file', 'link'):
            with self.subTest(kind=kind), self.parent.reconstructed_tree() as (root, _):
                extra = root / 'unexpected'
                if kind == 'file': extra.write_text('unexpected')
                else: extra.symlink_to('CMakeLists.txt')
                with self.assertRaises(ValueError): m.apply_and_validate(self.parent, root, self.patch, self.target)

    def test_asset_and_parent_pins(self):
        with patch.object(m, 'PATCH_SHA', '0' * 64):
            with self.assertRaises(ValueError): m.replay()
        with patch.object(m, 'PARENT_SHA', '0' * 64):
            with self.assertRaises(ValueError): m.replay()

if __name__ == '__main__': unittest.main()
