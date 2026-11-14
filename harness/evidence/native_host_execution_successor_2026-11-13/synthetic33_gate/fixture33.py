"""Predeclared synthetic B1K39 plan. No DSO/model execution."""
import hashlib
from fixture_plan import K,CENTER,FIELDS,fixture,perturb,raw_words
CASES=('baseline','warm_vertical','ice_vertical')
H=(1e-5,5e-6)
DIRECTIONS=('nc','th')

def center(case):
    if case=='baseline':
        x=fixture('warm')
        for k in range(K):x[FIELDS.index('qr')*K+k]=0.;x[FIELDS.index('nr')*K+k]=0.
    elif case=='warm_vertical':x=fixture('vertical')
    elif case=='ice_vertical':
        x=fixture('mixed_ice')
        for k in range(K):
            x[FIELDS.index('th')*K+k]=255.+.2*k
            x[FIELDS.index('qi')*K+k]*=1.+k/100.
            x[FIELDS.index('qs')*K+k]*=1.+k/100.
            x[FIELDS.index('qg')*K+k]*=1.+k/100.
            x[FIELDS.index('bg')*K+k]*=1.+k/100.
            x[FIELDS.index('qc')*K+k]=1e-4
            x[FIELDS.index('nc')*K+k]=1e8
    else:raise ValueError('unknown synthetic fixture')
    return x

def direction(name):
    if name not in DIRECTIONS:raise ValueError('unknown direction')
    d=[0.]*624
    d[FIELDS.index(name)*K+CENTER]=1e6 if name=='nc' else 1.
    return d

def plan():
    rows=[]
    for case in CASES:
        x=center(case)
        specs=[('capture_off_value',None,0.),('capture_on_value',None,0.),('center_joint_graph',None,0.)]
        for ident in DIRECTIONS:
            for h in H:
                for sign in (-1,1):specs.append(('capture_on_value',ident,sign*h))
        for mode,ident,offset in specs:
            xx=x if ident is None else perturb(x,direction(ident),offset)
            rows.append({'seq':len(rows)+1,'fixture':case,'mode':mode,'direction':ident,'offset':offset,'input_sha256':hashlib.sha256(raw_words(xx)).hexdigest(),'state':'UNSTARTED'})
    return rows

def validate():
    import math
    rows=plan()
    if len(rows)!=33 or len({(r['fixture'],r['mode'],r['direction'],r['offset']) for r in rows})!=33:raise ValueError('invalid slot identity')
    for case in CASES:
        x=center(case)
        if len(x)!=624 or not all(math.isfinite(v) for v in x):raise ValueError('nonfinite synthetic input')
        for field in ('qv','qc','qr','qi','qs','qg','nccn','nc','ni','nr','bg'):
            if any(x[FIELDS.index(field)*K+k]<0 for k in range(K)):raise ValueError('negative synthetic field')
        for field in ('rho','pii','p','delz'):
            if any(x[FIELDS.index(field)*K+k]<=0 for k in range(K)):raise ValueError('invalid synthetic forcing')
        for name in DIRECTIONS:
            vec=direction(name);idx=FIELDS.index(name)*K+CENTER
            if sum(v!=0 for v in vec)!=1 or vec[idx]==0:raise ValueError('invalid direction')
            for h in H:
                lo=perturb(x,vec,-h);hi=perturb(x,vec,h)
                if not lo[idx]<x[idx]<hi[idx] or any(lo[i]!=x[i] or hi[i]!=x[i] for i in range(624) if i!=idx):raise ValueError('unrepresented perturbation')
                if name=='nc' and lo[idx]<0:raise ValueError('inadmissible NC endpoint')
    return rows
