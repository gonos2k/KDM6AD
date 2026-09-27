"""One fixed CPU/fp64 KDM6 regression run; writes one JSON result."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import sys

import torch

from kdm6.runtime import kdm6_step
from kdm6.state import Forcing, State, state_dot


DT = 20.0
REFERENCE = Path(__file__).with_name("rc09_reference.json")


def pair(a: float, b: float, *, grad: bool = False) -> torch.Tensor:
    return torch.tensor([[a, b]], dtype=torch.float64, requires_grad=grad)


def fixture(*, grad: bool) -> tuple[State, Forcing]:
    # Fixed smooth two-cell case from test_handle_vjp_jvp.py.
    state = State(
        th=pair(296.8, 282.4, grad=grad),
        qv=pair(1.4e-2, 2.0e-3, grad=grad),
        qc=pair(1.0e-3, 5.0e-4, grad=grad),
        qr=pair(1.0e-4, 1.0e-5, grad=grad),
        qi=pair(0.0, 1.0e-6, grad=grad),
        qs=pair(0.0, 5.0e-5, grad=grad),
        qg=pair(0.0, 1.0e-5, grad=grad),
        nccn=pair(1.0e9, 1.0e9, grad=grad),
        nc=pair(1.0e8, 1.0e8, grad=grad),
        ni=pair(0.0, 1.0e8, grad=grad),
        nr=pair(1.0e4, 1.0e3, grad=grad),
        bg=pair(0.0, 0.0, grad=grad),
    )
    forcing = Forcing(
        rho=pair(1.089, 0.9567),
        pii=pair(0.9704, 0.9031),
        p=pair(9.0e4, 7.0e4),
        delz=pair(500.0, 500.0),
    )
    return state, forcing


def fixed_direction(state: State) -> State:
    zero = {name: torch.zeros_like(value) for name, value in zip(State._fields, state)}
    return State(**zero)._replace(
        th=pair(0.01, -0.02),
        qv=pair(1.0e-6, -1.0e-6),
        qc=pair(1.0e-7, -1.0e-7),
    )


def run(reference: dict[str, object]) -> dict[str, object]:
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    state, forcing = fixture(grad=True)
    direction = fixed_direction(state)
    seed = State(
        **{name: torch.zeros_like(value) for name, value in zip(State._fields, state)}
    )
    seed = seed._replace(th=pair(1.0, -0.5))

    output, handle = kdm6_step(state, forcing, dt=DT)
    try:
        tangent = handle.jvp(direction)
        adjoint = handle.vjp(seed)
    finally:
        handle.close()
    for group in (output, tangent, adjoint):
        if not all(torch.isfinite(field).all() for field in group):
            raise RuntimeError("nonfinite state or derivative")
    if (
        reference["schema"] != "kdm6ad-rc09-forward-reference-v1"
        or reference["fixture"] != "mixed_phase_two_cell_v1"
    ):
        raise RuntimeError("forward reference identity mismatch")
    if reference["dt_seconds"] != DT:
        raise RuntimeError("forward reference timestep mismatch")
    max_forward_ratio = 0.0
    for name, actual in zip(State._fields, output):
        expected = torch.tensor(
            reference["state_out"][name], dtype=torch.float64
        ).reshape(1, 2)
        tolerance = reference["atol"] + reference["rtol"] * expected.abs()
        ratio = float(((actual.detach() - expected).abs() / tolerance).max())
        max_forward_ratio = max(max_forward_ratio, ratio)
    if not math.isfinite(max_forward_ratio) or max_forward_ratio >= 1.0:
        raise RuntimeError(f"forward reference mismatch: ratio={max_forward_ratio:.3e}")

    jvp_dot = float(state_dot(tangent, seed))
    vjp_dot = float(state_dot(direction, adjoint))
    with torch.no_grad():
        base, _ = fixture(grad=False)
        plus = State(*(x + v for x, v in zip(base, direction)))
        minus = State(*(x - v for x, v in zip(base, direction)))
        yp, hp = kdm6_step(plus, forcing, dt=DT, value_only=True)
        ym, hm = kdm6_step(minus, forcing, dt=DT, value_only=True)
        hp.close()
        hm.close()
        fd_dot = float((state_dot(yp, seed) - state_dot(ym, seed)) / 2.0)

    dual_rel = abs(jvp_dot - vjp_dot) / max(abs(jvp_dot), abs(vjp_dot), 1e-30)
    fd_rel = abs(jvp_dot - fd_dot) / max(abs(jvp_dot), abs(fd_dot), 1e-30)
    if not all(math.isfinite(v) for v in (jvp_dot, vjp_dot, fd_dot, dual_rel, fd_rel)):
        raise RuntimeError("nonfinite scalar diagnostic")
    if dual_rel >= 1e-12 or fd_rel >= 1e-6:
        raise RuntimeError(
            f"derivative check failed: dual={dual_rel:.3e}, fd={fd_rel:.3e}"
        )

    return {
        "fixture": "mixed_phase_two_cell_v1",
        "dt_seconds": DT,
        "scope": "CPU fp64 fixed-forcing Python oracle; one branch-local step",
        "state_out": {
            name: value.tolist() for name, value in zip(State._fields, output)
        },
        "checks": {
            "forward_max_tolerance_ratio": max_forward_ratio,
            "jvp_dot": jvp_dot,
            "vjp_dot": vjp_dot,
            "fd_dot": fd_dot,
            "duality_relative_error": dual_rel,
            "fd_relative_error": fd_rel,
        },
        "observation": "NOT_EVALUATED",
    }


def provenance() -> dict[str, object]:
    root = Path(__file__).resolve().parents[2]
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return {
        "source_commit": commit,
        "source_clean": not bool(dirty),
        "entrypoint_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "runtime_sha256": hashlib.sha256(
            (root / "oracle/kdm6/runtime.py").read_bytes()
        ).hexdigest(),
        "reference_sha256": hashlib.sha256(REFERENCE.read_bytes()).hexdigest(),
        "python": sys.version.split()[0],
        "torch": torch.__version__,
        "platform": sys.platform,
        "arch": platform.machine(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, required=True, help="new JSON result path"
    )
    args = parser.parse_args()
    result: dict[str, object] = {"schema": "kdm6ad-rc09-regression-v1"}
    try:
        result.update(provenance())
        reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
        if not result["source_clean"]:
            raise RuntimeError("source checkout is not clean")
        for key in ("python", "torch", "platform", "arch"):
            if result[key] != reference[key]:
                raise RuntimeError(f"unsupported {key}: {result[key]}")
        result.update(run(reference))
        result["status"] = "PASS"
        code = 0
    except Exception as exc:
        result.update(status="FAIL", error=type(exc).__name__, message=str(exc))
        code = 1
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
