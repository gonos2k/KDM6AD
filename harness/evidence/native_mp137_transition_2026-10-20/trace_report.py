"""Reproduce this campaign's selected-column trace metrics from private traces.

Run from the repository root. This profile is specific to the archived arm64
GFortran object/disassembly; it is a value diagnostic, never a derivative gate.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path

import numpy as np

from harness.native_finish_replay import replay_arm64_theta_m_finish
from harness.native_trace_records import TRACE_FIELDS, validate_window_trace


def bits(value):
    return int(np.asarray([value], np.float32).view(np.uint32)[0])


def fraction(value):
    return Fraction.from_float(float(value))


def replay_report(rows):
    mismatches, links, limiter, cross = [], [], [], []
    for key, pre in rows.items():
        if pre.kind != 'FINISH_PRE':
            continue
        tail = key[1:]
        post = rows[('FINISH_POST', *tail)]
        ip, op = rows[('MP_INPUT', *tail)], rows[('MP_OUTPUT', *tail)]
        expected = replay_arm64_theta_m_finish(dict(zip(pre.fields, pre.values)))
        for field, value in expected.items():
            actual = pre.value(field) if field in pre.fields else post.value(field)
            if bits(actual) != bits(value):
                mismatches.append({'key': key, 'field': field,
                                   'actual_bits': f'{bits(actual):08X}',
                                   'replayed_bits': f'{bits(value):08X}'})
        for name, a, b in (
            ('TH_IN', ip.value('TH'), pre.value('H_PRE')),
            ('Q_IN', ip.value('Q'), pre.value('QV_PRE')),
            ('TH_OUT', op.value('TH'), pre.value('TH_PLUS')),
            ('Q_OUT', op.value('Q'), pre.value('QV_PLUS')),
        ):
            if bits(a) != bits(b):
                links.append({'key': key, 'field': name})
        dth = fraction(pre.value('TH_PLUS')) - fraction(pre.value('H_PRE'))
        dq = fraction(pre.value('QV_PLUS')) - fraction(pre.value('QV_PRE'))
        alpha, applied = fraction(pre.value('ALPHA')), fraction(pre.value('MP_CLIPPED'))
        limiter.append(float((applied - dth) * (1 + alpha * fraction(pre.value('QV_PLUS')))))
        cross.append(float(alpha * dth * dq))
    return {'level_step_samples': len(limiter), 'arithmetic_mismatches': mismatches,
            'packing_to_finish_mismatches': links,
            'limiter_term_max_abs_K': max(map(abs, limiter)),
            'ideal_cross_term_max_abs_K': max(map(abs, cross))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'probe', 'reference', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--i', type=int, required=True)
    parser.add_argument('--j', type=int, required=True)
    parser.add_argument('--levels', type=int, required=True)
    parser.add_argument('--steps', type=int, nargs='+', required=True)
    parser.add_argument('--dt', type=float, required=True)
    args = parser.parse_args()
    rows, hashes = {}, {}
    for name in ('baseline', 'probe', 'reference'):
        path = getattr(args, name)
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        rows[name] = validate_window_trace(path, steps=tuple(args.steps), i=args.i,
                                          j=args.j, levels=args.levels, dt=args.dt)
    changes = {}
    for step in args.steps:
        changes[str(step)] = {}
        for field in ('DEN', 'PII', 'P', 'DELZ'):
            deltas, levels = [], []
            for k in range(1, args.levels + 1):
                key = ('MP_INPUT', step, args.i, k, args.j)
                a, b = rows['baseline'][key].value(field), rows['probe'][key].value(field)
                if bits(a) != bits(b):
                    levels.append(k)
                    deltas.append(abs(float(b) - float(a)))
            changes[str(step)][field] = {'changed_levels': levels, 'count': len(levels),
                                          'max_abs_difference': max(deltas, default=0.)}
    report = {
        'scope': 'selected native column value-only; arm64/GFortran finish profile; no AD or conservation certification',
        'i': args.i, 'j': args.j, 'levels': args.levels, 'steps': args.steps, 'dt': args.dt,
        'trace_sha256': hashes, 'forcing_units': {'DEN': 'kg m-3', 'PII': '1', 'P': 'Pa', 'DELZ': 'm'},
        'forcing_probe_minus_baseline': changes,
        'replay': {name: replay_report(value) for name, value in rows.items()},
        'baseline_vs_reference_record_mismatches': [list(key) for key, value in rows['baseline'].items()
                                                    if value.bits != rows['reference'][key].bits],
    }
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'output': str(args.output), 'samples_per_kind': len(rows['baseline']) // len(TRACE_FIELDS),
                      'baseline_vs_reference_record_mismatches': len(report['baseline_vs_reference_record_mismatches'])}))


if __name__ == '__main__':
    main()
