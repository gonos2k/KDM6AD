"""Verify named hooks against the reconstructed, pinned v2 source."""
import importlib.util
import json
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('layers_for_hooks', HERE / 'replay.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
FILES = {'src/coordinator.cpp': 27, 'src/progb.cpp': 6, 'src/satadj.cpp': 6}


class NamedHookSourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        a5 = m.load_a5()
        validator = a5.parent_module()
        base = m.snapshot((a5.HERE / 'source_snapshot.json').read_bytes(), 77, validator)
        v2_raw = (HERE / 'v2_snapshot.json').read_bytes()
        if m.sha(v2_raw) != m.ASSETS['v2_snapshot.json']:
            raise ValueError('v2 snapshot SHA')
        v2 = m.snapshot(v2_raw, 82, validator)
        a2 = m.snapshot((HERE / 'a2_snapshot.json').read_bytes(), 83, validator)
        cls.ctx = a5.reconstructed_tree()
        root, _ = cls.ctx.__enter__()
        try:
            m.apply_layer(root, (HERE / 'v2.patch').read_bytes(), base, v2, validator)
            cls.before = {name: (root / name).read_bytes() for name in json.loads(v2_raw)}
            m.apply_layer(root, (HERE / 'a2.patch').read_bytes(), v2, a2, validator)
            cls.after = {str(path.relative_to(root)): path.read_bytes()
                         for path in root.rglob('*') if path.is_file()}
        finally:
            cls.ctx.__exit__(None, None, None)

    def test_original_projection_and_scope(self):
        for name, count in FILES.items():
            text = self.after[name].decode()
            projection = ''.join(line for line in text.splitlines(keepends=True)
                                 if '// A2_HOOK' not in line and '// A2_INCLUDE' not in line)
            self.assertEqual(projection.encode(), self.before[name], name)
            self.assertEqual(text.count('// A2_HOOK'), count)
            lines = text.splitlines()
            for i, line in enumerate(lines):
                if '// A2_HOOK' in line:
                    self.assertGreater(i, 0)
                    self.assertIn('batch5::', lines[i - 1])
                    self.assertIn('batch5::a2_named::record(', line)
                    self.assertNotIn('NOT_EVALUATED', line)
                    self.assertNotIn('DIAGNOSTIC_COMPARISON', line)
                    self.assertTrue('Role::OPERAND' in line or 'Role::CONSUMED_BOOL_TENSOR' in line)

    def test_helper_lifetime_and_identity(self):
        helper = self.after['include/kdm6/batch6_a2_named_hooks.h'].decode()
        for token in ('thread_local', 'c.epoch', 'c.one_step_call', 'c.outer_loop', 'c.family',
                      'c.substep_n', 'int(scope)', 'source_hook', 'int(role)', 'if(epoch!=c.epoch)',
                      'tensor(stage,field,source_hook,role,scope,t,k,top_first,ord)'):
            self.assertIn(token, helper)
        for token in ('.item(', '.detach(', 'no_grad', 'absent('):
            self.assertNotIn(token, helper)

    def test_untouched_remaining_files(self):
        for name, content in self.before.items():
            if name not in FILES:
                self.assertEqual(self.after[name], content, name)
        self.assertEqual(set(self.after) - set(self.before), {'include/kdm6/batch6_a2_named_hooks.h'})


if __name__ == '__main__':
    unittest.main()
