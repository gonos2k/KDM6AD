#!/usr/bin/env python3
"""Check whether live source bytes still match the number-coordinate review."""
import gzip
import hashlib
import json
import os
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
PUBLIC={'libtorch/src/runtime.cpp':'ae40dac52a3768fb2381fda90213cca1736a04a864cb49fe7590b2f7afc109f8','libtorch/src/coordinator.cpp':'2a9d9df17dd9bab8d8288bd2d2c6e57ebd7dc65b15d688c06c523cd825b0c932','libtorch/bridge/kdm6_c_api.cpp':'8c3f4a96dc7078eea8b19806d70c0ec6477debbc2cead04eec32403c26efe049','libtorch/bridge/kdm6_c_api.h':'de9ca99da4a77af741a875fd4c69de39c68525dbcd781e900144585bb1fd9481','harness/evidence/native_host_column_f32_2026-11-11/raw/selected_full.json':'e3117d277a073042bbae648b87e7dd6661d14b600fc8245f6aeabc19fe715eae'}
PRIVATE={'Registry/Registry.EM_COMMON':'6741720cba12ad7ee1c172339bd8def5973b22f4e88ab9cd152f3ba3df456e37','phys/module_microphysics_driver.F':'94db84c45b7422b62e04967cb3cd1362311abdb02fa3d374d881799c0bce7e84','phys/module_mp_kdm6ad.F':'c56499524c73bec4e5092e7aecfde244d072f9572733708226c7f6d743cc9e67','phys/module_mp_kdm6.F':'fc0a72d33a5e61803fea56eb9118018039c6da8b5775813032b4861a2bd66eb5'}

ARCHIVES={'libtorch/src/runtime.cpp':'ce4e69f1173bfa830f8fddfd1c719865edf6e45394f68279e5da5cdf2b4150e3','libtorch/src/coordinator.cpp':'fbe94e1876f6bb3efd9d89e9d31bd347c040c4c2c9f470378249db6ffb1d476d','libtorch/bridge/kdm6_c_api.cpp':'ea69be031bf9175894e3d636407ab22bb3174894c18b2b750f742fd8b3c142b8','libtorch/bridge/kdm6_c_api.h':'3cbfb0c2772ebd012a7d8f6b3e9372b65f843ed410b29c8447cfa0e0782d0cb9'}
SELECTED='harness/evidence/native_host_column_f32_2026-11-11/raw/selected_full.json'

def check(root, pins):
    for name,digest in pins.items():
        raw=(root/name).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=digest: raise ValueError('reviewed source changed: '+name)

def verify(private_root=None, *, require_current_source=False, current_root=ROOT):
    for name,digest in ARCHIVES.items():
        raw=(HERE/'reviewed_source'/(name+'.gz')).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=digest or hashlib.sha256(gzip.decompress(raw)).hexdigest()!=PUBLIC[name]:
            raise ValueError('reviewed archive changed: '+name)
    check(ROOT,{SELECTED:PUBLIC[SELECTED]})
    selected=json.loads((ROOT/SELECTED).read_bytes())
    if selected['column_native']!=[203,149] or [selected['input_words_hex'][k][15] for k in ('nccn','nc','ni','nr')]!=['4c0bfc3a','00000000','00000000','00000000']:
        raise ValueError('selected coordinate mapping')
    if require_current_source:
        if private_root is None: raise ValueError('private host root required for current-source check')
        check(Path(current_root),{k:PUBLIC[k] for k in ARCHIVES})
        check(Path(private_root),PRIVATE)
    return {'reviewed_public_archives':'MATCH','selected_input':'MATCH',
            'current_public_and_private_source':'MATCH' if require_current_source else 'SKIPPED',
            'scientific_status':'INCONCLUSIVE','physical_unit_status':'INCONCLUSIVE'}

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--require-current-source',action='store_true');args=parser.parse_args()
    print(json.dumps(verify(os.environ.get('KDM6AD_PRIVATE_HOST_ROOT'),require_current_source=args.require_current_source),indent=2,sort_keys=True))
