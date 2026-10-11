#!/usr/bin/env python3
"""Restore only the nine original Jul19 GK2A L1B bytes, without retry."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import urllib.request

PACKET = Path(__file__).resolve().parent


def main():
    plan_path = PACKET / 'RESTORE_PLAN.json'
    plan = json.loads(plan_path.read_text())
    assert len(plan['files']) == plan['maximum_files'] == 9
    target = Path(plan['raw_destination'])
    target.mkdir(parents=True, mode=0o700, exist_ok=False)
    target.chmod(0o700)
    records = []

    def restore(item):
        path = target / item['name']
        digest = hashlib.sha256()
        count = 0
        with urllib.request.urlopen(item['url'], timeout=60) as response, path.open('xb') as stream:
            path.chmod(0o600)
            assert response.status == 200
            header = dict(response.headers)
            while data := response.read(1 << 18):
                count += len(data)
                if count > plan['maximum_total_bytes'] // 9:
                    raise ValueError('per-file restoration byte budget exceeded')
                digest.update(data)
                stream.write(data)
        if digest.hexdigest() != item['expected_sha256']:
            raise ValueError(f'original SHA mismatch: {item["name"]}')
        return {**item, 'path': str(path), 'actual_sha256': digest.hexdigest(),
                'bytes': count, 'http_status': 200, 'etag': header.get('ETag'),
                'last_modified': header.get('Last-Modified')}

    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            for record in pool.map(restore, plan['files']):
                records.append(record)
        assert sum(r['bytes'] for r in records) <= plan['maximum_total_bytes']
        status = 'ALL_NINE_ORIGINAL_HASHES_RESTORED'
        error = None
    except Exception as exc:
        status, error = 'RESTORATION_FAILED_NO_RETRY', f'{type(exc).__name__}: {exc}'
    receipt = {'schema': 'pr411_original_ami_restoration_receipt_v1', 'status': status,
       'plan_sha256': hashlib.sha256(plan_path.read_bytes()).hexdigest(),
       'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
       'files': records, 'error': error, 'automatic_retry': False, 'new_dates': 0,
       'no_other_satellite_L2_or_model_data': True}
    (PACKET / 'RESTORE_RESULT.json').open('x').write(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'status': status, 'verified_files': len(records), 'error': error}))
    return 0 if error is None else 1


if __name__ == '__main__':
    os.environ['OMP_NUM_THREADS'] = '1'
    raise SystemExit(main())
