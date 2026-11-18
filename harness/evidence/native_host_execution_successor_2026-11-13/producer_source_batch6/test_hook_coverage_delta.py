import json
import unittest
from pathlib import Path
from unittest.mock import patch
try:
    from . import hook_coverage_delta as audit
except ImportError:
    import hook_coverage_delta as audit

class DeltaTests(unittest.TestCase):
    def test_saved_delta(self):
        result=audit.run()
        self.assertEqual(result,json.loads((Path(__file__).parent/'hook_coverage_delta.json').read_text()))
        self.assertEqual((result['new_hook_calls'],result['new_mapped_atoms'],result['remaining_unmapped_atoms']),(35,18,66))
    def test_mapping_mutations_fail_closed(self):
        for bad in ({**audit.MAP,'made.up':('a5_heat','xlf','xlf')},
                    {**audit.MAP,'phase_change_heat.site.03':('a5_heat','xlf','wrong_tensor')}):
            with self.subTest(), patch.object(audit,'MAP',bad):
                with self.assertRaises(ValueError): audit.run()
    def test_parent_pin(self):
        with patch.object(audit,'SUMMARY_SHA','0'*64):
            with self.assertRaises(ValueError): audit.run()

if __name__=='__main__': unittest.main()
