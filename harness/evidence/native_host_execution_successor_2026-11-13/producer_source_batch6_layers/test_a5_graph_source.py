"""A5 shared hooks preserve the exact A4 macro-OFF source projection."""
import importlib.util
import re
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('layers_for_a5_graph', HERE / 'replay.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class A5GraphSourceTest(unittest.TestCase):
    def test_projection_hook_sites_and_integrity(self):
        validator = m.load_a5().parent_module()
        a4 = m.snapshot((HERE / 'a4_snapshot.json').read_bytes(), 84, validator)
        target = m.snapshot((HERE / 'a5_graph_snapshot.json').read_bytes(), 84, validator)
        patch = (HERE / 'a5_graph.patch').read_bytes()
        self.assertEqual(validator.validate_patch(patch, a4, target), {
            'libtorch/include/kdm6/batch6_a2_named_hooks.h', 'libtorch/src/coordinator.cpp', 'libtorch/src/runtime.cpp'})
        with self.assertRaises(ValueError):
            validator.validate_patch(patch.replace(b'a/libtorch/src/runtime.cpp', b'a/libtorch/../src/runtime.cpp', 1), a4, target)
        with self.assertRaises(ValueError):
            validator.validate_patch(patch.replace(b' 100644\n', b' 100755\n', 1), a4, target)
        with m.reconstructed_tree('a4') as (root, _):
            before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            m.apply_layer(root, patch, a4, target, validator)
            wrong = dict(target)
            wrong['libtorch/src/runtime.cpp'] = '0' * 64
            with self.assertRaises(ValueError):
                m.verify_tree(root, wrong, validator)
            after = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
        self.assertEqual(set(before), set(after))
        changed = {name for name in before if before[name] != after[name]}
        self.assertEqual(changed, {'include/kdm6/batch6_a2_named_hooks.h', 'src/coordinator.cpp', 'src/runtime.cpp'})
        coordinator = after['src/coordinator.cpp'].decode()
        runtime = after['src/runtime.cpp'].decode()
        helper = after['include/kdm6/batch6_a2_named_hooks.h'].decode()
        added_hooks = re.findall(r'^\+.*?"(src/(?:coordinator|runtime)\.cpp:[^"]+)"', patch.decode(), re.M)
        self.assertEqual(set(added_hooks), {
            'src/coordinator.cpp:nc_snap1.ncmin_present', 'src/coordinator.cpp:nc_snap2.ncmin_present',
            'src/coordinator.cpp:a5_phase_mask.gate', 'src/coordinator.cpp:a5_phase_mask.supcol',
            'src/coordinator.cpp:a5_heat_mask.gate', 'src/coordinator.cpp:a5_heat_mask.supcol',
            'src/coordinator.cpp:cleanup_mask.qmin', 'src/coordinator.cpp:lambda.control.q_thresh',
            'src/coordinator.cpp:lambda.control.n_thresh', 'src/coordinator.cpp:lambda.control.lamda_min',
            'src/coordinator.cpp:lambda.control.lamda_max', 'src/coordinator.cpp:dsd_inner.ncmax',
            'src/runtime.cpp:schedule.mstepmax_main', 'src/runtime.cpp:schedule.mstepmax_ice',
        })
        self.assertEqual(len(added_hooks), 14)
        self.assertEqual(coordinator.count('// A5_CONTROL'), 8)
        self.assertEqual(runtime.count('batch5::a2_named::scalar_integral('), 2)
        blocks = re.findall(r'#ifdef KDM6_BATCH5_RESEARCH_CAPTURE // A5_REPLACE_BEGIN\n(.*?)#else // A5_ORIGINAL\n(.*?)#endif // A5_REPLACE_END\n', coordinator, re.S)
        self.assertEqual(len(blocks), 2)
        self.assertEqual(sum(part.count('batch5::a2_named::record(') for part, _ in blocks), 4)
        for instrumented, _ in blocks:
            self.assertIn('Role::CONSUMED_BOOL_TENSOR', instrumented)
            self.assertIn('Role::OPERAND', instrumented)
        original = re.sub(r'#ifdef KDM6_BATCH5_RESEARCH_CAPTURE // A5_REPLACE_BEGIN\n.*?#else // A5_ORIGINAL\n(.*?)#endif // A5_REPLACE_END\n', r'\1', coordinator, flags=re.S)
        original = ''.join(line for line in original.splitlines(keepends=True) if '// A5_CONTROL' not in line)
        self.assertEqual(original.encode(), before['src/coordinator.cpp'])
        original = re.sub(r'#ifdef KDM6_BATCH5_RESEARCH_CAPTURE // A5_BLOCK_BEGIN\n.*?#endif // A5_BLOCK_END\n', '', runtime, flags=re.S)
        self.assertEqual(original.encode(), before['src/runtime.cpp'])
        original = re.sub(r'// A5_SCALAR_HELPER_BEGIN\n.*?// A5_SCALAR_HELPER_END\n', '', helper, flags=re.S)
        self.assertEqual(original.encode(), before['include/kdm6/batch6_a2_named_hooks.h'])
        for text in (helper, coordinator, runtime):
            for line in text.splitlines():
                if 'batch5::a2_named::scalar_integral(' in line or '// A5_CONTROL' in line:
                    self.assertNotIn('.item(', line)
                    self.assertNotIn('.detach(', line)


if __name__ == '__main__':
    unittest.main()
