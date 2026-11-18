import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest


SCRIPT = Path(__file__).resolve().parents[1] / 'analyze_qi_m0_cost_decomposition.py'
spec = importlib.util.spec_from_file_location('qi_decomposition', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_disjoint_geometry_and_strict_thresholds():
    regions = module.geometry(3, 3)
    assert np.all(sum(regions.values()) == 1)
    assert {name: int(value.sum()) for name, value in regions.items()} == {
        'corners': 4, 'west': 1, 'east': 1, 'south': 1, 'north': 1, 'interior': 1}
    mask = np.ones((9, 1), dtype=bool)
    y = np.zeros((9, 1), dtype=np.float64)
    x = y.copy()
    x[:4, 0] = [0.01, 0.1, 1.0, 1.1]
    result = module.comparison(x, y, module.huber(x, y, mask), module.huber(y, y, mask),
                               mask, (0.0, 0.0), 10, width=3, height=3)
    assert [result['strict_abs_bt_thresholds_K'][k]['cells'] for k in ('0.01', '0.1', '1.0')] == [3, 2, 1]
    assert result['geometry']['corners']['changed_profiles'] == 2
    assert result['changed_cells'] == 4


def test_signed_gross_changes_depend_on_grain():
    x = np.array([[2.0, 0.0]], dtype=np.float64)
    y = np.array([[0.0, 2.0]], dtype=np.float64)
    mask = np.ones_like(x, dtype=bool)
    loss_x = module.huber(x, np.zeros_like(x), mask)
    loss_y = module.huber(y, np.zeros_like(y), mask)
    result = module.comparison(x, y, loss_x, loss_y, mask, (0., 0.), 1, width=1, height=1)
    assert result['cellwise_gross']['increase'] == .75
    assert result['cellwise_gross']['decrease'] == -.75
    assert result['profilewise_gross']['zero_count'] == 1
    assert result['regrouped_cell_delta'] == 0


def test_published_packet_cost_decomposition():
    if not module.BASE.exists() or not (module.PACKET / 'data/control.npz').exists():
        pytest.skip('public PR #483 observation packet unavailable')
    out = subprocess.check_output([sys.executable, str(SCRIPT), '--top', '11'], text=True)
    result = json.loads(out)
    control = result['comparisons']['control_minus_baseline']
    alpha = result['comparisons']['alpha025_minus_baseline']
    assert (control['changed_profiles'], control['changed_cells']) == (11, 77)
    assert control['geometry']['east']['changed_profiles'] == 10
    assert control['geometry']['interior']['changed_profiles'] == 1
    assert (alpha['changed_profiles'], alpha['changed_cells']) == (48257, 337714)
    for comparison in result['comparisons'].values():
        assert abs(comparison['roundoff_gap_regrouped_minus_aggregate']) < 2e-14
        assert abs(comparison['channel_sum_minus_regrouped']) < 2e-14
        assert abs(comparison['geometry_sum_minus_regrouped']) < 2e-14
