"""Audit A7 selected/reset source nodes without asserting physical flux."""
import importlib.util
import re
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('layers_for_a7', HERE / 'replay.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def project(text):
    return re.sub(r'#ifdef KDM6_BATCH5_RESEARCH_CAPTURE // A7_BLOCK_BEGIN\n.*?#endif // A7_BLOCK_END\n', '', text, flags=re.S)


def valid_hooks(coordinator, runtime):
    expected = {('a7_main_selected', f'{species}_{kind}') for species in ('qr', 'nr', 'qs', 'qg', 'brs') for kind in ('state', 'fall')}
    expected |= {('a7_ice_selected', f'{species}_{kind}') for species in ('qi', 'ni') for kind in ('state', 'fall')}
    expected |= {(stage, field) for stage in ('a7_main_progb_reset', 'a7_presed_progb_reset') for field in ('brs_before', 'bg_selected')}
    found = re.findall(r'batch5::full\("(a7_[^"]+)", "([^"]+)",', coordinator + '\n' + runtime)
    return (len(found) == 18 and set(found) == expected and len(set(found)) == 18
            and all(f'"{sp}_state", adv_state.{sp}, true' in coordinator and f'"{sp}_fall", fall_{sp}, true' in coordinator for sp in ('qr', 'nr', 'qs', 'qg', 'brs'))
            and all(f'"{sp}_state", ice_state.{sp}, true' in coordinator and f'"{sp}_fall", fall_{sp}, true' in coordinator for sp in ('qi', 'ni')))


class LedgerSourceTest(unittest.TestCase):
    def test_layer_projection_hooks_and_corruption(self):
        validator = m.load_a5().parent_module()
        base = m.snapshot((HERE / 'a5_graph_snapshot.json').read_bytes(), 84, validator)
        target = m.snapshot((HERE / 'a7_ledger_snapshot.json').read_bytes(), 84, validator)
        patch = (HERE / 'a7_ledger.patch').read_bytes()
        self.assertEqual(validator.validate_patch(patch, base, target), {'libtorch/src/coordinator.cpp', 'libtorch/src/runtime.cpp'})
        for bad in (patch.replace(b'a/libtorch/src/runtime.cpp', b'a/libtorch/../src/runtime.cpp', 1),
                    patch.replace(b' 100644\n', b' 100755\n', 1)):
            with self.assertRaises(ValueError):
                validator.validate_patch(bad, base, target)
        with m.reconstructed_tree('a5_graph') as (root, _):
            before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            m.apply_layer(root, patch, base, target, validator)
            wrong = dict(target)
            wrong['libtorch/src/runtime.cpp'] = '0' * 64
            with self.assertRaises(ValueError):
                m.verify_tree(root, wrong, validator)
            after = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
        self.assertEqual(set(before), set(after))
        self.assertEqual({n for n in before if before[n] != after[n]}, {'src/coordinator.cpp', 'src/runtime.cpp'})
        for name in ('src/coordinator.cpp', 'src/runtime.cpp'):
            self.assertEqual(project(after[name].decode()).encode(), before[name], name)
        coordinator, runtime = after['src/coordinator.cpp'].decode(), after['src/runtime.cpp'].decode()
        self.assertTrue(valid_hooks(coordinator, runtime))
        for text, stage, field, node in (
            (coordinator, 'a7_main_progb_reset', 'brs_before', 'adv_state.brs'),
            (coordinator, 'a7_main_progb_reset', 'bg_selected', 'pre.progb.bg'),
            (runtime, 'a7_presed_progb_reset', 'brs_before', 'cur_pyc.brs'),
            (runtime, 'a7_presed_progb_reset', 'bg_selected', 'pre_sed.progb.bg'),
        ):
            self.assertIn(f'batch5::full("{stage}", "{field}", {node}, true);', text)

        self.assertFalse(valid_hooks(coordinator.replace('"qr_state"', '"fake_state"', 1), runtime))
        self.assertFalse(valid_hooks(coordinator.replace('adv_state.qr, true', 'out.state.qr, true', 1), runtime))
        sedimentation = after['src/sedimentation.cpp'].decode()
        for sp in ('qr', 'nr', 'qs', 'qg', 'brs', 'qi', 'ni'):
            for suffix in ('falk_candidate', 'state_before', 'state_after_candidate', 'out_limited_candidate', 'arrival_limited_candidate'):
                self.assertIn(f'"{sp}_{suffix}"', sedimentation)
        for sp in ('qr', 'qs', 'qg', 'qi'):
            self.assertIn(f'"fall_{sp}"', sedimentation)


if __name__ == '__main__':
    unittest.main()
