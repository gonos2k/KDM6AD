"""The dictionary callback must enforce the same quality/gate domain as ingestion."""
import pytest
import torch

from kdm6.obs.obs_loss import compute_obs_loss
from kdm6.obs.rttov_obs_operator import _build_mask


@pytest.mark.parametrize("key,value", [
    ("obs_quality", [[0., float("nan")], [0., 0.]]),
    ("obs_quality", [0., 0.]),
    ("channel_gate", [[-1., 1.]]),
    ("channel_gate", [[float("inf"), 1.]]),
    ("channel_gate", [[2., 1.]]),
    ("channel_gate", [1., 1., 1.]),
])
def test_callback_rejects_invalid_quality_and_gate(key, value):
    with pytest.raises(ValueError, match=key):
        _build_mask({key: value}, torch.zeros((2, 2)))


def test_channel_gate_broadcast_preserves_flag_convention():
    quality = torch.tensor([[0., 1.], [2., 0.]])
    mask = _build_mask({"obs_quality": torch.zeros((2, 2)),
                        "channel_gate": [[0.5, 1.]]}, quality)
    assert torch.equal(mask, torch.tensor([[0.5, 0.], [0., 1.]], dtype=torch.float64))


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1., 2.])
def test_loss_rejects_invalid_keep_weights(bad):
    bt = torch.zeros((1, 1), dtype=torch.float64)
    with pytest.raises(ValueError, match="masks"):
        compute_obs_loss(bt, {"bt": bt}, [[bad]], 1.)
