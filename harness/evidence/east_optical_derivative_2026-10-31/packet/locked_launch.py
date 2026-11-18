#!/usr/bin/env python3
"""Review gate for an isolated RTTOV directional experiment."""
import argparse, json, subprocess, sys
from pathlib import Path
import preflight as pf
ROOT=Path(__file__).resolve().parent
RUNNER='20bcd57f001d2a63fbb4d70a9b64029622de50576d2dd7174baac5f4972099ca'
MANIFEST='3287e676da020da12b5de78fd5b7cb8c4348b275d6ca25677587c313943b6585'
def main():
 p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True);g.add_argument('--verify-only',action='store_true');g.add_argument('--execute',action='store_true');a=p.parse_args()
 if pf.sha(ROOT/'runner.py')!=RUNNER or pf.sha(ROOT/'prepared/pins.json')!=MANIFEST:raise ValueError('review pin changed')
 import runner
 pins=json.loads((ROOT/'prepared/pins.json').read_text());runner.verify_sources(pins)
 for key,expected in pins['cases'].items():
  case=ROOT/'prepared'/key
  if runner.inputs(case)!=expected:raise ValueError('prepared input changed '+key)
  runner.check_case(case,key.endswith('_K'))
 if a.verify_only:
  print(json.dumps({'status':'LOCKED_VERIFIED','runner_sha256':RUNNER,'manifest_sha256':MANIFEST,'RTTOV_calls':0}));return
 subprocess.run([sys.executable,str(ROOT/'runner.py'),'--execute','--expected-runner',RUNNER,'--expected-manifest',MANIFEST],check=True)
if __name__=='__main__':main()
