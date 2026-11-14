"""Fake assets test source pin completeness; no library is loaded."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import fixture33
import real33_contract as real


class SourcePins(unittest.TestCase):
    def test_all_execution_sources_pinned_and_content_checked(self):
        source = Path(real.__file__).resolve().parent
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            for name in real.EXECUTION_SOURCE_FILES:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source / name, target)
            spec = importlib.util.spec_from_file_location('temporary_contract', root / 'real33_contract.py')
            contract = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(contract)
            assets = {str(root / name): contract.sha(root / name) for name in contract.EXECUTION_SOURCE_FILES}
            dso = root / 'fake_dso'
            interpreter = root / 'fake_python'
            dso.write_bytes(b'fake dso')
            interpreter.write_bytes(b'fake python')
            assets[str(dso)] = contract.sha(dso)
            assets[str(interpreter)] = contract.sha(interpreter)
            manifest = {'schema':'kdm6.synthetic33.private.v1','status':'REVIEWED_PINNED','slots':fixture33.validate(),'assets':assets,'dso_path':str(dso),'dso_sha256':assets[str(dso)],'interpreter':str(interpreter),'approved_loaded_images':{str(dso):assets[str(dso)]},'required_loaded_images':[str(dso)]}
            path = root / 'manifest.json'
            def validate(m):
                path.write_text(json.dumps(m, sort_keys=True))
                with patch.dict(os.environ, {'RESEARCH_PRIVATE_MANIFEST':str(path), 'RESEARCH_MANIFEST_SHA256':contract.sha(path)}):
                    return contract.preflight()
            self.assertEqual(validate(manifest)['status'], 'SPEC_ONLY_UNVERIFIED_RUNTIME_LOADER')
            for name in contract.EXECUTION_SOURCE_FILES:
                with self.subTest(missing=name):
                    incomplete = dict(manifest, assets=dict(assets))
                    del incomplete['assets'][str(root / name)]
                    with self.assertRaises(ValueError):
                        validate(incomplete)
            for name in ('selector_manifest_spec_v1.py','census_helper.py','darwin_census_provider.py','fake_watchdog/watchdog.py'):
                with self.subTest(changed=name):
                    target = root / name
                    original = target.read_bytes()
                    target.write_bytes(original + b'\n# tampered\n')
                    with self.assertRaisesRegex(ValueError, 'asset pin mismatch'):
                        validate(manifest)
                    target.write_bytes(original)


if __name__ == '__main__':
    unittest.main()
