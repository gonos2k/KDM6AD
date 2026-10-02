"""Input-only selector for the fixed two-tile, two-call native census."""
import hashlib
from pathlib import Path

import numpy as np

TILES = ((2, 233, 2, 142), (2, 233, 143, 281))
STEPS = (1, 2)


def read_tile(path):
    lines = Path(path).read_text().splitlines()
    if lines[:2] != ['KDM6_INPUT_CENSUS_V1', 'selectors physics_variant=2 dry_number=1']:
        raise ValueError('unexpected census header')
    records = [line.split() for line in lines[2:]]
    if len(records) < 3 or [row[0] for row in records[:3]] != ['tile', 'counts', 'settings']:
        raise ValueError('missing census metadata')
    tile = tuple(map(int, records[0][1:])); counts = tuple(map(int, records[1][1:]))
    if len(tile) != 7 or len(counts) != 6 or tile[5:] != (1, 39):
        raise ValueError('wrong census shape/counts')
    step, il, ir, jl, jr, _, _ = tile
    if tuple(map(float, records[2][1:])) != (20., 10., 10.):
        raise ValueError('changed census settings')
    total = (ir - il + 1) * (jr - jl + 1)
    if counts[0] != total or not all(0 <= value <= total for value in counts):
        raise ValueError('wrong census totals')
    if not all(counts[i] >= counts[i+1] for i in range(5)) or counts[4] != counts[5]:
        raise ValueError('inconsistent nested eligibility counts')
    result = dict(step=step, box=(il, ir, jl, jr), counts=counts,
                  sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(), best=None)
    if counts[-1] == 0:
        if len(records) != 3:
            raise ValueError('unexpected profile for empty candidate set')
        return result
    if len(records) != 628 or records[3][0] != 'best' or len(records[3]) != 5:
        raise ValueError('missing/extra best profile records')
    i, j = map(int, records[3][1:3]); score, land = map(float, records[3][3:])
    if not (il <= i <= ir and jl <= j <= jr) or land not in (1., 2.):
        raise ValueError('best profile outside tile or invalid land')
    arrays = {'STATE_IN': np.empty((12, 39)), 'FORCING': np.empty((4, 39))}
    seen = set()
    for row in records[4:]:
        if len(row) != 4 or row[0] not in arrays:
            raise ValueError('unexpected profile record')
        tag, f, k, value = row[0], int(row[1])-1, int(row[2])-1, float(row[3])
        if not (0 <= f < arrays[tag].shape[0] and 0 <= k < 39) or (tag, f, k) in seen:
            raise ValueError('duplicate/invalid profile index')
        arrays[tag][f, k] = value; seen.add((tag, f, k))
    if len(seen) != 624:
        raise ValueError('incomplete best profile')
    state, forcing = arrays['STATE_IN'], arrays['FORCING']
    if not np.isfinite(state).all() or not np.isfinite(forcing).all() or not np.isfinite(score):
        raise ValueError('nonfinite best profile')
    if (state[0] <= 0).any() or (state[1:] < 0).any() or (forcing <= 0).any():
        raise ValueError('best profile fails numerical preconditions')
    for mass, moment in ((2, 8), (3, 10), (4, 9), (6, 11)):
        if ((state[mass] == 0) != (state[moment] == 0)).any():
            raise ValueError('best profile fails strict pair admission')
    rho_d = forcing[0] / (1. + state[1])
    if not ((state[4] > 1e-14) & (rho_d * state[9] > 10.)).any() or not (state[7] > 0).any():
        raise ValueError('best profile is not active ice with a nonempty NCCN seed')
    expected_score = 0.
    for value in state[4]:  # mirror the declared sequential input-only score
        expected_score += float(value)
    if score.hex() != expected_score.hex():
        raise ValueError('reported input score does not match saved profile')
    result['best'] = dict(i=i, j=j, score=score, xland=land, state=state, forcing=forcing)
    return result


def select(paths):
    records = [read_tile(path) for path in paths]
    keys = [(r['step'], r['box']) for r in records]
    expected = {(step, box) for step in STEPS for box in TILES}
    if len(keys) != len(expected) or set(keys) != expected:
        raise ValueError('census requires complete, unique predeclared tile/call coverage')
    for step in STEPS:
        candidates = [r for r in records if r['step'] == step and r['best'] is not None]
        if candidates:
            chosen = min(candidates, key=lambda r: (-r['best']['score'], r['best']['j'], r['best']['i']))
            return dict(selected=chosen, records=records)
    return dict(selected=None, records=records)
