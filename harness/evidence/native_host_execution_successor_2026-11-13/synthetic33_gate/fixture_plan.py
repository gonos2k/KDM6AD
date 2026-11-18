"""Synthetic input and finite-call contract only; does not load or call a DSO."""
import math
import struct

K = 39
CENTER = 23  # zero-based packed bottom-first
TARGET_TOP = K-1-CENTER
NATIVE_LEVEL = CENTER+1
FIELDS = ('th', 'qv', 'qc', 'qr', 'qi', 'qs', 'qg', 'nccn', 'nc', 'ni', 'nr', 'bg', 'rho', 'pii', 'p', 'delz')
H = (1e-5, 5e-6)
MODES = ('capture_off_value', 'capture_on_value', 'center_joint_graph')
CASES = ('warm', 'mixed_ice', 'vertical', 'boundary_low', 'boundary_high')

def fixture(case):
    if case not in CASES:
        raise ValueError(case)
    x = [0.0] * (16*K)
    def put(field, k, value): x[FIELDS.index(field)*K+k] = float(value)
    for k in range(K):
        for field, value in (('th', 280.), ('qv', .005), ('nccn', 1e8), ('rho', 1.), ('pii', 1.), ('p', 100000.), ('delz', 100.)):
            put(field, k, value)
        if case == 'warm':
            for f, v in (('qc', 2e-4), ('qr', 1e-4), ('nc', 1e8), ('nr', 1e5)): put(f, k, v)
        elif case == 'mixed_ice':
            for f, v in (('th', 260.), ('qv', .002), ('qi', 1e-5), ('qs', 2e-5), ('qg', 3e-5), ('ni', 1e4), ('bg', 3e-5/500.)): put(f, k, v)
        elif case == 'vertical':
            for f, v in (('th', 275. + .2*k), ('qv', .003 + .00003*k), ('qc', 1e-4 + 1e-6*k), ('qr', 2e-5 + 5e-7*k), ('nc', 5e7 + 1e6*k), ('nr', 1e5 + 1000*k)): put(f, k, v)
        else:
            for f, v in (('qc', 1e-8), ('nc', 10. - 1e-4 if case == 'boundary_low' else 10. + 1e-4)): put(f, k, v)
    return x

def direction(case):
    v = [0.0] * (16*K)
    v[FIELDS.index('nc')*K+CENTER] = 1. if case.startswith('boundary_') else 1e6
    return v

def perturb(x, v, delta):
    return [a + delta*b for a,b in zip(x,v)]

def schedule():
    calls=[]
    for case in CASES:
        for mode in MODES: calls.append((case, mode, 0.))
        for h in H:
            for sign in (-1, 1): calls.append((case, 'capture_on_value', sign*h))
    return calls

def raw_words(x):
    return b''.join(struct.pack('<d', z) for z in x)

def validate_plan():
    if len(schedule()) != 35 or len(set(schedule())) != 35: raise ValueError('invalid budget')
    for case in CASES:
        x, v = fixture(case), direction(case)
        if len(x)!=624 or len(v)!=624 or not all(math.isfinite(z) for z in x+v): raise ValueError('invalid fixture')
        if sum(z != 0 for z in v)!=1: raise ValueError('invalid direction')
        for h in H:
            if raw_words(perturb(x,v,h)) == raw_words(x) or raw_words(perturb(x,v,-h)) == raw_words(x): raise ValueError('ineffective perturbation')
