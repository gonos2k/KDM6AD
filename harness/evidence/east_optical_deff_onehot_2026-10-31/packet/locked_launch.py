#!/usr/bin/env python3
"""Review-pinned launcher; verify-only never invokes RTTOV."""
import argparse, subprocess, sys
from pathlib import Path
R=Path(__file__).resolve().parent
RUNNER='339450c95f1ad1815e6ff295b2f256a752c43cf756423f3d5e92bbbca10527e8'
MANIFEST='2f190b1a660b50a14585b8a554b14cc4c4136b96aba0860334609e14de3cc0ba'
p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True);g.add_argument('--verify-only',action='store_true');g.add_argument('--execute',action='store_true');a=p.parse_args()
subprocess.run([sys.executable,str(R/'runner.py'),'--verify-only' if a.verify_only else '--execute','--expected-runner',RUNNER,'--expected-manifest',MANIFEST],check=True)
