import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('layers', HERE / 'replay.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class LayerTests(unittest.TestCase):
    def test_complete_reconstruction(self):
        result = m.replay()
        self.assertEqual([result[x]['reconstructed_files'] for x in ('a5', 'v2', 'a2', 'a3', 'a4', 'a5_graph', 'a7_ledger')], [77, 82, 83, 83, 84, 84, 84])
        self.assertEqual(result['scientific_status'], 'INCONCLUSIVE')

    def test_asset_and_base_pins(self):
        for name in m.ASSETS:
            with self.subTest(name=name), patch.dict(m.ASSETS, {name: '0' * 64}):
                with self.assertRaisesRegex(ValueError, 'asset SHA'):
                    with m.reconstructed_tree():
                        pass
        with patch.object(m, 'A5_SHA', '0' * 64), self.assertRaisesRegex(ValueError, 'A5 replay SHA'):
            m.load_a5()

    def test_duplicate_and_invalid_inventory(self):
        validator = m.load_a5().parent_module()
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            m.snapshot(b'{"x":"a", "x":"b"}', 1, validator)
        with self.assertRaises(ValueError):
            m.snapshot(json.dumps({'../x': '0' * 64}).encode(), 1, validator)

    def test_corrupt_patch_and_inventory_rejected(self):
        a5 = m.load_a5()
        validator = a5.parent_module()
        base = m.snapshot((a5.HERE / 'source_snapshot.json').read_bytes(), 77, validator)
        target = m.snapshot((HERE / 'v2_snapshot.json').read_bytes(), 82, validator)
        source_patch = (HERE / 'v2.patch').read_bytes()
        mutations = [source_patch.replace(b'a/libtorch/CMakeLists.txt', b'a/libtorch/../CMakeLists.txt', 1),
                     source_patch.replace(b'new file mode 100644', b'new file mode 120000', 1)]
        for bad in mutations:
            with self.subTest(kind=bad[:40]):
                with self.assertRaises(ValueError):
                    validator.validate_patch(bad, base, target)
        with a5.reconstructed_tree() as (root, _):
            corrupt = dict(target)
            corrupt['libtorch/CMakeLists.txt'] = '0' * 64
            with self.assertRaises(ValueError):
                m.apply_layer(root, source_patch, base, corrupt, validator)

    def test_a2_patch_and_inventory_rejected(self):
        a5 = m.load_a5()
        validator = a5.parent_module()
        base = m.snapshot((a5.HERE / 'source_snapshot.json').read_bytes(), 77, validator)
        v2 = m.snapshot((HERE / 'v2_snapshot.json').read_bytes(), 82, validator)
        a2 = m.snapshot((HERE / 'a2_snapshot.json').read_bytes(), 83, validator)
        source_patch = (HERE / 'a2.patch').read_bytes()
        with self.assertRaises(ValueError):
            validator.validate_patch(source_patch.replace(b'new file mode 100644', b'new file mode 120000', 1), v2, a2)
        with a5.reconstructed_tree() as (root, _):
            m.apply_layer(root, (HERE / 'v2.patch').read_bytes(), base, v2, validator)
            wrong = dict(a2)
            wrong['libtorch/src/progb.cpp'] = '0' * 64
            with self.assertRaises(ValueError):
                m.apply_layer(root, source_patch, v2, wrong, validator)

    def test_a3_corrupt_patch_and_inventory_rejected(self):
        a5 = m.load_a5()
        validator = a5.parent_module()
        base = m.snapshot((a5.HERE / 'source_snapshot.json').read_bytes(), 77, validator)
        v2 = m.snapshot((HERE / 'v2_snapshot.json').read_bytes(), 82, validator)
        a2 = m.snapshot((HERE / 'a2_snapshot.json').read_bytes(), 83, validator)
        a3 = m.snapshot((HERE / 'a3_snapshot.json').read_bytes(), 83, validator)
        source_patch = (HERE / 'a3.patch').read_bytes()
        with self.assertRaises(ValueError):
            validator.validate_patch(source_patch.replace(b'a/libtorch/src/runtime.cpp', b'a/libtorch/../src/runtime.cpp', 1), a2, a3)
        with a5.reconstructed_tree() as (root, _):
            m.apply_layer(root, (HERE / 'v2.patch').read_bytes(), base, v2, validator)
            m.apply_layer(root, (HERE / 'a2.patch').read_bytes(), v2, a2, validator)
            wrong = dict(a3)
            wrong['libtorch/src/runtime.cpp'] = '0' * 64
            with self.assertRaises(ValueError):
                m.apply_layer(root, source_patch, a2, wrong, validator)

    def test_extra_file_and_symlink_rejected(self):
        a5 = m.load_a5()
        validator = a5.parent_module()
        base = m.snapshot((a5.HERE / 'source_snapshot.json').read_bytes(), 77, validator)
        for kind in ('file', 'link'):
            with self.subTest(kind=kind), a5.reconstructed_tree() as (root, _):
                extra = root / 'unexpected'
                if kind == 'file':
                    extra.write_text('x')
                else:
                    extra.symlink_to('CMakeLists.txt')
                with self.assertRaises(ValueError):
                    m.verify_tree(root, base, validator)


if __name__ == '__main__':
    unittest.main()
