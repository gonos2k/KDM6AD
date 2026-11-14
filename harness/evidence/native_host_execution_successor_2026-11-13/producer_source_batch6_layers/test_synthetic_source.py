"""A4 changes only synthetic parity test registration and its test source."""
import importlib.util
import json
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('layers_for_synthetic', HERE / 'replay.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class SyntheticSourceTests(unittest.TestCase):
    def test_source_projection_and_synthetic_test_contract(self):
        a5 = m.load_a5()
        validator = a5.parent_module()
        a3 = m.snapshot((HERE / 'a3_snapshot.json').read_bytes(), 83, validator)
        a4 = m.snapshot((HERE / 'a4_snapshot.json').read_bytes(), 84, validator)
        source_patch = (HERE / 'a4.patch').read_bytes()
        self.assertEqual(validator.validate_patch(source_patch, a3, a4),
                         {'libtorch/CMakeLists.txt', 'libtorch/tests/test_batch6_synthetic_capture_parity.cpp'})
        broken = source_patch.replace(b'new file mode 100644', b'new file mode 120000', 1)
        with self.assertRaises(ValueError):
            validator.validate_patch(broken, a3, a4)
        with m.reconstructed_tree() as (root, _):
            wrong = dict(a4)
            wrong['libtorch/CMakeLists.txt'] = '0' * 64
            with self.assertRaises(ValueError):
                m.verify_tree(root, wrong, validator)
            cmake = (root / 'CMakeLists.txt').read_text()
            block = '''    add_executable(test_batch6_synthetic_capture_parity tests/test_batch6_synthetic_capture_parity.cpp)
    target_include_directories(test_batch6_synthetic_capture_parity PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/bridge)
    target_compile_options(test_batch6_synthetic_capture_parity PRIVATE -UNDEBUG)
    target_link_libraries(test_batch6_synthetic_capture_parity PRIVATE kdm6_c)
    add_test(NAME batch6_synthetic_capture_parity COMMAND test_batch6_synthetic_capture_parity)
'''
            self.assertEqual(cmake.count(block), 1)
            self.assertEqual(m.sha(cmake.replace(block, '', 1).encode()), a3['libtorch/CMakeLists.txt'])
            for name, digest in a3.items():
                if name != 'libtorch/CMakeLists.txt':
                    self.assertEqual(m.sha((root.parent / name).read_bytes()), digest, name)
            source = (root / 'tests/test_batch6_synthetic_capture_parity.cpp').read_text()
            for token in ('quiet_NaN()', 'std::isfinite', 'capture_off_value', 'capture_on_value',
                          'aw==bw && a.rain==b.rain', 'std::memcmp', 'kdm6_step_ad_state_forcing_c',
                          'synthetic f64 value ABI; no native host or derivative claim'):
                self.assertIn(token, source)
            self.assertEqual(len(json.loads((HERE / 'a4_snapshot.json').read_bytes())), 84)


if __name__ == '__main__':
    unittest.main()
