import copy
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parents[1] / 'evidence/oracle_runner_worker_probe_2026-11-12'
spec = importlib.util.spec_from_file_location('oracle_worker_probe_receipt', HERE / 'verify.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class WorkerProbeReceiptTest(unittest.TestCase):
    def test_saved_nonpass_record(self):
        result = probe.verify()
        self.assertEqual(result['speedup_status'], 'INCONCLUSIVE')
        self.assertEqual(result['one_worker']['passed'], 25)

    def test_false_two_worker_completion_rejected(self):
        import gzip
        import json
        receipt = json.loads((HERE / 'raw/receipt.json').read_bytes())
        one = json.loads((HERE / 'raw/workers_1.json').read_bytes())
        logs = {name: gzip.decompress((HERE / 'raw' / name).read_bytes())
                for name in ('workers_1.log.gz', 'workers_2.log.gz')}
        altered = copy.deepcopy(receipt)
        altered['two_worker']['status'] = 'complete'
        with self.assertRaisesRegex(ValueError, 'two-worker nonpass scope'):
            probe.check_record(altered, one, logs)


if __name__ == '__main__':
    unittest.main()
