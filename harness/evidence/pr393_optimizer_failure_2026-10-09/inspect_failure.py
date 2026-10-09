#!/opt/local/bin/python3
"""One-variable synthetic probe of exception behavior in the installed LBFGS."""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import math
import sys
from pathlib import Path

import torch


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("RESULT.json"),
        help="new output path; existing files are never overwritten",
    )
    args = parser.parse_args()

    x = torch.nn.Parameter(torch.tensor([0.0], dtype=torch.float64))
    optimizer = torch.optim.LBFGS(
        [x], lr=1.0, max_iter=5, max_eval=12, line_search_fn="strong_wolfe")
    closure_states: list[float] = []
    closure_losses: list[float] = []
    rejected_threshold = 0.5

    def closure() -> torch.Tensor:
        optimizer.zero_grad(set_to_none=True)
        value = float(x.detach()[0])
        closure_states.append(value)
        if value > rejected_threshold:
            raise ValueError("synthetic trial rejected above x=0.5")
        loss = (x - 2.0).square().sum()
        loss.backward()
        closure_losses.append(float(loss.detach()))
        return loss

    step_returned = False
    optimizer_result = None
    caught: BaseException | None = None
    try:
        optimizer_result = optimizer.step(closure)
        step_returned = True
    except ValueError as exc:  # only the expected synthetic failure is consumed
        caught = exc

    source_path = Path(inspect.getsourcefile(torch.optim.LBFGS)).resolve()
    directional_source, first_line = inspect.getsourcelines(
        torch.optim.LBFGS._directional_evaluate)
    state = optimizer.state[x]
    trial_state = closure_states[1] if len(closure_states) > 1 else None
    final_state = float(x.detach()[0])
    checks = {
        "baseline_closure_at_x0_returns": (
            closure_states[:1] == [0.0] and closure_losses[:1] == [4.0]),
        "first_line_search_trial_crosses_rejection_threshold": (
            trial_state is not None and trial_state > rejected_threshold),
        "trial_exception_propagates_from_step": (
            isinstance(caught, ValueError) and not step_returned),
        "trial_parameter_is_not_restored_after_exception": (
            trial_state is not None and math.isclose(final_state, trial_state)),
        "no_post_error_recovery_closure_or_result": (
            len(closure_states) == 2 and optimizer_result is None),
    }
    if not all(checks.values()):
        raise RuntimeError(f"synthetic LBFGS probe did not match expectations: {checks}")

    result = {
        "study": "Installed PyTorch LBFGS exception-boundary probe",
        "scope": (
            "One scalar x with f(x)=(x-2)^2; a synthetic ValueError is raised "
            "when x>0.5. No KDM6 code, model data, RTTOV, host, or project "
            "optimizer entry point is used. This probes this installed PyTorch "
            "build only; it does not establish behavior for other versions or "
            "other optimizer implementations."
        ),
        "runtime": {
            "python_executable": sys.executable,
            "python_version": sys.version,
            "torch_version": torch.__version__,
            "torch_lbfgs_source": str(source_path),
            "torch_lbfgs_source_sha256": sha256(source_path),
            "probe_script_sha256": sha256(Path(__file__).resolve()),
            "directional_evaluate_first_line": first_line,
            "directional_evaluate_source": "".join(directional_source),
        },
        "experiment": {
            "initial_x": 0.0,
            "objective": "f(x)=(x-2)^2",
            "rejection_condition": "raise ValueError if x>0.5",
            "line_search": "strong_wolfe",
            "closure_x_values": closure_states,
            "successful_closure_losses": closure_losses,
            "exception_type": type(caught).__name__ if caught else None,
            "exception_message": str(caught) if caught else None,
            "step_returned": step_returned,
            "result_object_returned": optimizer_result is not None,
            "parameter_after_exception": final_state,
            "optimizer_state_after_exception": {
                key: (int(value) if isinstance(value, int) else str(type(value).__name__))
                for key, value in state.items()
            },
            "checks": checks,
        },
        "interpretation": (
            "In this installed build, LBFGS calls the closure at x=0, then at "
            "the strong-Wolfe trial x=1. The ValueError escapes step(); the "
            "directional-evaluate helper does not reach its parameter-restore "
            "statement, the parameter remains at x=1, no later closure runs, "
            "and no optimizer result is returned. This is exception propagation, "
            "not an automatic line-search rejection/backtrack."
        ),
        "project_source_review": {
            "da_minimizer": (
                "run_minimizer calls opt.step(closure) before constructing and "
                "returning MinimizeResult; exceptions bypass its final audit/result."
            ),
            "da_dual": (
                "run_dual_minimizer has the same opt.step-before-final-audit/result "
                "ordering. The normalized-dry frozen-quality callback raises on "
                "invalid support, and has no local retry/catch."
            ),
            "fulldomain_pool": (
                "run_fulldomain_analysis wraps evaluator/minimizer/diagnostics in "
                "try/finally and closes/joins its pool; the exception propagates "
                "before report/save_fields publication."
            ),
        },
        "limits": [
            "Synthetic scalar experiment only; it does not invoke run_minimizer or run_dual_minimizer.",
            "Does not reproduce a KDM6, RTTOV, host, or user optimizer experiment.",
            "No recovery, retry, rollback, or general error handling was added or tested.",
            "The current fail-closed policy is sufficient to avoid publishing an accepted result after a quality mismatch; future smaller-step recovery would need an explicit invalid-trial protocol and owner decision.",
        ],
        "analysis_script_sha256": sha256(Path(__file__).resolve()),
    }
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
