"""Source projection and diagnostic-role checks for the A-3 layer."""
import importlib.util
import json
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('layers_for_diagnostics', HERE / 'replay.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def project_helper(text):
    start = '// Raw declared C++ double; effective tensor-comparison conversion is separate.\n'
    end = '} // A2_DIAG_HELPER_END\n'
    include = '#include <cstring> // A2_DIAG_INCLUDE\n'
    if text.count(start) != 1 or text.count(end) != 1 or text.count(include) != 1:
        raise ValueError('diagnostic helper markers')
    before, tail = text.split(start, 1)
    _, after = tail.split(end, 1)
    return (before + '}\n' + after).replace(include, '')


class DiagnosticSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        a5 = m.load_a5()
        validator = a5.parent_module()
        base = m.snapshot((a5.HERE / 'source_snapshot.json').read_bytes(), 77, validator)
        v2 = m.snapshot((HERE / 'v2_snapshot.json').read_bytes(), 82, validator)
        a2 = m.snapshot((HERE / 'a2_snapshot.json').read_bytes(), 83, validator)
        a3 = m.snapshot((HERE / 'a3_snapshot.json').read_bytes(), 83, validator)
        with a5.reconstructed_tree() as (root, _):
            m.apply_layer(root, (HERE / 'v2.patch').read_bytes(), base, v2, validator)
            m.apply_layer(root, (HERE / 'a2.patch').read_bytes(), v2, a2, validator)
            cls.before = {name: (root / name).read_bytes() for name in json.loads((HERE / 'a2_snapshot.json').read_bytes())}
            m.apply_layer(root, (HERE / 'a3.patch').read_bytes(), a2, a3, validator)
            cls.after = {str(path.relative_to(root)): path.read_bytes() for path in root.rglob('*') if path.is_file()}

    def test_helper_exact_projection_and_mutations(self):
        name = 'include/kdm6/batch6_a2_named_hooks.h'
        source = self.after[name].decode()
        expected = self.before[name].decode()
        self.assertEqual(project_helper(source), expected)
        for old, new in (('scope==Scope::LAYER?39:1', 'scope==Scope::LAYER?38:1'),
                         ('ordinals[key]=ord+1;', 'ordinals[key]=ord+2;'),
                         ('if (!batch5::enabled()) return;', 'if (batch5::enabled()) return;')):
            self.assertIn(old, source)
            self.assertNotEqual(project_helper(source.replace(old, new, 1)), expected)

    def test_projection_and_roles(self):
        for name, count in (('src/runtime.cpp', 14), ('src/thermo.cpp', 11), ('src/coordinator.cpp', 20)):
            text = self.after[name].decode()
            projection = ''.join(line for line in text.splitlines(keepends=True) if '// A2_DIAG' not in line)
            self.assertEqual(projection.encode(), self.before[name], name)
            self.assertEqual(text.count('// A2_DIAG\n'), count)
            for line in text.splitlines():
                if '// A2_DIAG' in line:
                    for forbidden in ('absent(', '.item(', '.detach(', 'no_grad'):
                        self.assertNotIn(forbidden, line)
                    if 'record(' in line:
                        self.assertTrue('Role::OPERAND' in line or 'Role::DIAGNOSTIC_COMPARISON' in line)
                        self.assertNotIn('Role::CONSUMED_BOOL_TENSOR', line)

    def test_scalar_wire_and_other_files(self):
        helper = self.after['include/kdm6/batch6_a2_named_hooks.h'].decode()
        for token in ('std::memcpy(&bits,&value,sizeof(bits))', 'Dtype::F64', 'Scope::LAYER',
                      'c.epoch', 'c.one_step_call', 'c.outer_loop', 'c.family', 'c.substep_n'):
            self.assertIn(token, helper)
        changed = {'src/runtime.cpp', 'src/thermo.cpp', 'src/coordinator.cpp', 'include/kdm6/batch6_a2_named_hooks.h'}
        self.assertEqual(set(self.before), set(self.after))
        for name, content in self.before.items():
            if name not in changed:
                self.assertEqual(self.after[name], content, name)


if __name__ == '__main__':
    unittest.main()
