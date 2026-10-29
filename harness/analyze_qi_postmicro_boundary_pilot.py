"""Check saved west-boundary pilot samples, not the full affected boundary.

Four trace inputs are required: control and alpha025, each pilot off/on.
Optionally compare the pilot-on samples against their inherited donor traces
and verify the pinned private solve source. This tool never runs the host.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import struct
from pathlib import Path

OVERLAY_SHA256 = '222ca46f5ac57a0cbc40fafecae92539c0fd7ea4f7fe8a0c61b57b918ff0727c'
PARENT_SOLVE_SHA256 = '73d4ac972e3576d151b4a04ee8a263da0e3a9d19734ba6e75a1d83c1a055a451'
HEADER = ['# KDM6AD_QI_POST_BDY_V1', '# VAL step stage i k j field raw_word_hex']
WORD = re.compile(r'[0-9A-F]{8}\Z')
STAGES = ('BEFORE', 'AFTER')
FIELDS = ('QI', 'NI', 'RU_M')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def f32(word: str) -> float:
    return struct.unpack('>f', bytes.fromhex(word))[0]


def read_trace(path: Path, pilot: int) -> dict:
    lines = path.read_text(encoding='ascii').splitlines()
    if lines[:2] != HEADER or len(lines) < 3 or lines[2].split() != ['GATES', '3', str(pilot), '1', '1']:
        raise ValueError('trace header or pilot/paired gates differ')
    values, branches = {}, {}
    for line in lines[3:]:
        parts = line.split()
        if len(parts) == 8 and parts[0] == 'VAL':
            _, step, stage, i, k, j, field, word = parts
            if step != '3' or stage not in STAGES or i not in ('1','2') or k not in ('30','31','32','33') or j != '168' or field not in FIELDS or not WORD.fullmatch(word):
                raise ValueError('invalid trace value record')
            if not math.isfinite(f32(word)):
                raise ValueError('nonfinite sampled value')
            key = (stage, int(i), int(k), field)
            if key in values: raise ValueError('duplicate trace value')
            values[key] = word
        elif len(parts) == 7 and parts[0] == 'BRANCH':
            _, step, stage, k, j, name, branch = parts
            if step != '3' or stage not in STAGES or k not in ('30','31','32','33') or j != '168' or name != 'WEST_OUTFLOW_U_LT_ZERO' or branch not in ('0','1'):
                raise ValueError('invalid branch record')
            key = (stage, int(k))
            if key in branches: raise ValueError('duplicate branch')
            branches[key] = int(branch)
        else:
            raise ValueError('unexpected trace record')
    expected = {(stage,i,k,field) for stage in STAGES for i in (1,2) for k in range(30,34) for field in FIELDS}
    if set(values) != expected or set(branches) != {(stage,k) for stage in STAGES for k in range(30,34)}:
        raise ValueError('incomplete trace inventory')
    for stage in STAGES:
        for k in range(30,34):
            if branches[(stage,k)] != int(f32(values[(stage,1,k,'RU_M')]) < 0.0):
                raise ValueError('branch differs from strict west velocity sign')
    for k in range(30,34):
        if branches[('BEFORE',k)] != branches[('AFTER',k)]: raise ValueError('branch changed')
        for i in (1,2):
            if values[('BEFORE',i,k,'RU_M')] != values[('AFTER',i,k,'RU_M')]:
                raise ValueError('velocity changed')
            for field in ('QI','NI'):
                before, after = values[('BEFORE',i,k,field)], values[('AFTER',i,k,field)]
                if pilot == 0 or i == 2:
                    expected_word = before
                else:
                    expected_word = values[('BEFORE',2,k,field)] if branches[('BEFORE',k)] else '00000000'
                if after != expected_word:
                    raise ValueError('sampled boundary map or donor noninterference differs')
    return {'values': values, 'branches': branches}


def analyze(paths: dict, donors: dict | None = None, parent_source: Path | None = None) -> dict:
    overlay = Path(__file__).with_name('native_qi_postmicro_boundary_pilot_overlay.py')
    if sha(overlay) != OVERLAY_SHA256: raise ValueError('pilot overlay source pin differs')
    if parent_source is not None and sha(parent_source) != PARENT_SOLVE_SHA256:
        raise ValueError('parent solve source pin differs')
    inputs = {}
    for case in ('control','alpha025'):
        for mode,pilot in (('off',0),('on',1)):
            key=(case,mode)
            inputs[key]=read_trace(paths[key],pilot)
        off,on=inputs[(case,'off')],inputs[(case,'on')]
        for key,word in off['values'].items():
            if key[0]=='BEFORE' and on['values'][key] != word:
                raise ValueError('pilot on/off pre-intervention samples differ')
        if any(off['branches'][('BEFORE',k)] != on['branches'][('BEFORE',k)] for k in range(30,34)):
            raise ValueError('pilot on/off input branch differs')
    compared = []
    if donors:
        from harness.analyze_qi_donor_transient import read_trace as read_donor
        for case,path in donors.items():
            if case not in ('control','alpha025'): raise ValueError('unexpected donor case')
            donor=read_donor(path)
            values=inputs[(case,'on')]['values']
            for i in (1,2):
                for field in ('QI','NI'):
                    if donor[(0,'POST_FINISH',i,field)] != values[('AFTER',i,33,field)]:
                        raise ValueError('pilot AFTER and inherited donor POST_FINISH differ')
            compared.append(case)
    a=inputs[('alpha025','on')]['values']
    before,after=a[('BEFORE',1,33,'QI')],a[('AFTER',1,33,'QI')]
    if (before,after) != ('00000002','00000000'):
        raise ValueError('alpha025 k33 sampled QI witness differs')
    return {'schema':'kdm6.qi_postmicro_boundary_sample_analysis.v1',
            'input_sha256': {f'{case}_{mode}':sha(path) for (case,mode),path in paths.items()},
            'donor_sha256': {case:sha(path) for case,path in (donors or {}).items()},
            'overlay_sha256': OVERLAY_SHA256, 'parent_solve_expected_sha256': PARENT_SOLVE_SHA256,
            'parent_solve_verified': parent_source is not None, 'donor_compared':sorted(compared),
            'alpha025_k33_target_qi': {'before':before,'after':after,'f32_subnormal_units_before':2},
            'scope':'sampled west target and donor at j=168, k=30..33 only; no full-boundary or budget claim'}


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('control-off','control-on','alpha025-off','alpha025-on'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--control-donor',type=Path)
    p.add_argument('--alpha025-donor',type=Path)
    p.add_argument('--parent-solve-source',type=Path)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    paths={(case,mode):getattr(a,case+'_'+mode) for case in ('control','alpha025') for mode in ('off','on')}
    donors={case:path for case,path in (('control',a.control_donor),('alpha025',a.alpha025_donor)) if path is not None}
    result=analyze(paths,donors,a.parent_solve_source)
    if a.output.exists() or a.output.is_symlink() or a.output.parent.is_symlink():
        raise FileExistsError('output must be fresh')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x',encoding='utf-8') as f: json.dump(result,f,sort_keys=True,indent=2); f.write('\n')
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=='__main__': raise SystemExit(main())
