
import numpy as np
import pytest

from harness.analyze_qi_m0_direct_semantics import chunk_loss, validate_receipt


def fixture():
    capture = {'flat_indices': np.arange(10, 13, dtype=np.int32),
               'profile_valid': np.array([True, False, True])}
    receipt = {'direct_calls': 1, 'K_calls': 0, 'rttov_receipt': {
        'source_flat_indices': [10, 12], 'nprofiles': 2,
        'channels': list(range(10, 17)), 'bt_coordinate': 'kma_v3_0',
        'per_profile_geometry_surface': True,
        'driver_flags': {'case_do_direct': True, 'case_do_k': False,
                         'template_do_k': True},
        'K_recovered': 0, 'direct_calls': 1, 'K_calls': 0, 'mode': 'direct'}}
    return receipt, capture


def test_receipt_accepts_template_k_flag_without_case_k():
    receipt, capture = fixture()
    validate_receipt(receipt, capture, 10, 13)


@pytest.mark.parametrize('key,value', [
    ('source_flat_indices', [12, 10]), ('source_flat_indices', [10, 10]),
    ('nprofiles', 1), ('channels', list(range(11, 18))),
    ('bt_coordinate', 'other'), ('per_profile_geometry_surface', False),
    ('K_recovered', 1), ('direct_calls', 0), ('K_calls', 1),
])
def test_receipt_rejects_mutations(key, value):
    receipt, capture = fixture()
    receipt['rttov_receipt'][key] = value
    with pytest.raises(ValueError):
        validate_receipt(receipt, capture, 10, 13)


def test_receipt_rejects_case_k():
    receipt, capture = fixture()
    receipt['rttov_receipt']['driver_flags']['case_do_k'] = True
    with pytest.raises(ValueError):
        validate_receipt(receipt, capture, 10, 13)


def test_chunk_loss_uses_mask_and_huber_branches():
    bt = np.zeros((2, 7), dtype=np.float64)
    obs = np.zeros_like(bt)
    mask = np.zeros_like(bt, dtype=np.bool_)
    bt[0, :3] = [0.5, 1.0, 2.0]
    bt[1, 0] = 1000
    mask[0, :3] = True
    assert chunk_loss(bt, obs, mask) == 0.125 + 0.5 + 1.5
