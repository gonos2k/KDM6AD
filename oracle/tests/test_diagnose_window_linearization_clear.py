from __future__ import annotations

import torch

from scripts.diagnose_window_linearization_clear import _state_fd_metrics
from kdm6.state import State


def test_state_fd_metric_reports_exact_linear_unroll():
    plus = State(*(torch.full((1, 1), 2.0 + i) for i in range(len(State._fields))))
    minus = State(*(torch.full((1, 1), 1.0 + i) for i in range(len(State._fields))))
    tangent = State(*(torch.full((1, 1), 5.0) for _ in State._fields))
    metrics = _state_fd_metrics(plus, minus, 0.1, tangent)
    assert all(row["max_abs_error"] == 0.0 for row in metrics.values())
