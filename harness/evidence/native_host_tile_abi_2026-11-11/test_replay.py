import copy
import json
from unittest import mock
import os
import shutil
from pathlib import Path
import tempfile
import unittest

import replay


class PrivateTileTest(unittest.TestCase):
    def test_wrong_capture_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'invalid.bin'
            path.write_bytes(b'not a tile')
            with self.assertRaisesRegex(ValueError, 'capture SHA-256'):
                replay.read_tile(path)

    @unittest.skipUnless(os.environ.get('PRIVATE_TILE_PATH') and os.environ.get('PRIVATE_DSO_PATH'),
                         'PRIVATE_TILE_PATH and PRIVATE_DSO_PATH required for private full-tile replay')
    def test_private_full_tile(self):
        counts = replay.replay_private(os.environ['PRIVATE_TILE_PATH'], os.environ['PRIVATE_DSO_PATH'], replay.load_records()[1])
        self.assertEqual(set(counts), set(replay.OUTPUTS))
        self.assertFalse(any(counts.values()))


class PublicReceiptTest(unittest.TestCase):
    def setUp(self):
        self.records = replay.load_records()

    def test_corrupted_asset_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'packet'
            shutil.copytree(replay.ROOT, root)
            (root / 'producer' / 'proxy.c').write_text('corrupt')
            with self.assertRaisesRegex(ValueError, 'asset SHA-256 mismatch'):
                replay.load_records(root)

    def test_rehashed_metadata_tampering_rejected(self):
        for relative, mutate in (
            ('raw/selected_column.json', lambda d: d['output_words_hex']['th'].__setitem__(0, '4393def2')),
            ('raw/host_tile_amendment.json', lambda d: d['loaded_libraries']['paired_on'].__setitem__('separate_lsof_snapshot', 'captured')),
            ('raw/host_tile_amendment.json', lambda d: d['files']['installed_dso'].__setitem__('path', 'private://wrong.dylib')),
            ('raw/host_tile_amendment.json', lambda d: d['capture_off_on']['timestamps'].__setitem__(1, '2025-07-19_00:00:40')),
        ):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as d:
                root = Path(d) / 'packet'
                shutil.copytree(replay.ROOT, root)
                asset = root / relative
                data = json.loads(asset.read_text())
                mutate(data)
                asset.write_text(json.dumps(data, indent=2) + '\n')
                manifest_path = root / 'manifest.json'
                manifest = json.loads(manifest_path.read_text())
                manifest['files'][relative] = replay.sha256(asset)
                manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
                with mock.patch.object(replay, 'MANIFEST_SHA', replay.sha256(manifest_path)):
                    with self.assertRaisesRegex(ValueError, 'independent.*SHA-256'):
                        replay.load_records(root)

    def test_nonfinite_word_rejected(self):
        records = copy.deepcopy(self.records)
        records[1]['output_words_hex']['th'][0] = '7f800000'
        with self.assertRaisesRegex(ValueError, 'non-finite'):
            replay.validate_public_receipts(*records)

    def test_public_receipts(self):
        self.assertTrue(replay.validate_public_receipts(*self.records))

    def test_saved_public_summary_contract(self):
        actual = replay.public_summary(self.records)
        saved = json.loads((replay.ROOT / 'results.json').read_text())
        self.assertEqual(actual, saved)
        self.assertEqual(actual['scientific_status'], 'INCONCLUSIVE')
        self.assertEqual(actual['physical_unit_status'], 'INCONCLUSIVE')

    def test_public_metadata_does_not_expose_local_workspace_paths(self):
        for name in ('host_tile_receipt.json', 'host_tile_amendment.json',
                     'producer_source_hashes.json'):
            with self.subTest(name=name):
                raw = (replay.ROOT / 'raw' / name).read_text()
                self.assertNotRegex(raw, r'/Users/[^/]+/')

    def test_mapping_and_counts_rejected(self):
        records = copy.deepcopy(self.records)
        records[0]['tile']['runtime_b_zero'] += 1
        with self.assertRaisesRegex(ValueError, 'runtime index'):
            replay.validate_public_receipts(*records)
        records = copy.deepcopy(self.records)
        records[2]['bit_mismatch_counts']['qv'] = 1
        with self.assertRaisesRegex(ValueError, 'mismatch counts'):
            replay.validate_public_receipts(*records)

    def test_malformed_words_and_paired_output_rejected(self):
        records = copy.deepcopy(self.records)
        records[1]['input_words_hex']['qv'][0] = 'xyz'
        with self.assertRaisesRegex(ValueError, 'invalid raw word'):
            replay.validate_public_receipts(*records)
        records = copy.deepcopy(self.records)
        records[4]['fcst_1']['output'] = records[4]['fcst_1']['output'].replace('frame index 1', 'frame index 0')
        records[0]['capture_off_on']['details'] = records[4]
        with self.assertRaisesRegex(ValueError, 'paired comparison output'):
            replay.validate_public_receipts(*records)


if __name__ == '__main__':
    unittest.main()
