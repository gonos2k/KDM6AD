#!/usr/bin/env python3
"""Run bounded G3 experiments; no production adapter or native host adoption."""

import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "oracle"))
import torch  # noqa:E402
from moment_representation_probe import run_probe  # noqa:E402
from moment_transfer_probe import inventory_reference, transport, validate  # noqa:E402
from moment_validity import classify_volume_moments  # noqa:E402


def run():
    results = []
    dtype = torch.float64
    moments = torch.tensor([[[1e-5, 2e-5, 3e-6]], [[1e4, 2e4, 3e3]]], dtype=dtype)
    rho = torch.tensor([[0.25, 0.8, 1.3]], dtype=dtype)
    dz = torch.tensor([[10.0, 17.0, 11.0]], dtype=dtype)
    velocity = torch.tensor([[[2.0, 1.0, 3.0]], [[1.0, 3.0, 2.0]]], dtype=dtype)
    for steps, dt in ((1, 2.0), (1, 30.0), (3, 30.0)):
        validate(moments, rho, dz, velocity, dt=dt, steps=steps)
        out = transport(moments, rho, dz, velocity, dt=dt, steps=steps)
        volume = transport(
            moments * rho.unsqueeze(0),
            rho,
            dz,
            velocity,
            dt=dt,
            steps=steps,
            basis="volume",
        )
        ref = inventory_reference(moments, rho, dz, velocity, dt=dt, steps=steps)
        initial = (moments * rho.unsqueeze(0) * dz).sum(-1)
        torch.testing.assert_close(out, ref, rtol=32 * torch.finfo(dtype).eps, atol=0)
        torch.testing.assert_close(
            out, volume, rtol=32 * torch.finfo(dtype).eps, atol=0
        )
        torch.testing.assert_close(
            out.sum(-1), initial, rtol=32 * torch.finfo(dtype).eps, atol=0
        )
        results.append(
            dict(
                steps=steps,
                dt=dt,
                moments_dry=moments.tolist(),
                rho_d=rho.tolist(),
                dz=dz.tolist(),
                velocity=velocity.tolist(),
                physical_cell_and_surface=out.tolist(),
                independent_inventory_reference=ref.tolist(),
                initial_inventory=initial.tolist(),
                relative_inventory_residual=(
                    (out.sum(-1) - initial) / initial
                ).tolist(),
            )
        )
    source_files = [
        "harness/moment_representation_probe.py",
        "harness/moment_transfer_probe.py",
        "harness/moment_validity.py",
        "oracle/kdm6/cloud_dsd.py",
        "oracle/kdm6/warm.py",
        "oracle/kdm6/sed_conservative.py",
    ]
    validity = classify_volume_moments(
        [1e-4, 1e-4, 1e-30],
        [1e5, 0.0, 1e-24],
        mass_floor_kg_m3=1e-12,
        number_floor_m3=1e-8,
        mean_particle_mass_bounds_kg=(1e-12, 1e-6),
        basis="volume",
    )
    return dict(
        moment_validity=dict(
            kind="synthetic caller-declared interval, not KDM threshold policy",
            mass_floor=1e-12,
            number_floor=1e-8,
            mean_mass_bounds=[1e-12, 1e-6],
            C=[1e-4, 1e-4, 1e-30],
            N=[1e5, 0.0, 1e-24],
            reasons=validity.reason.tolist(),
        ),
        schema="physical-moment-contract-v1",
        execution=dict(
            python=platform.python_version(),
            torch=torch.__version__,
            device="cpu",
            precision="binary64 with inherited KDM constants",
        ),
        collection=run_probe(),
        generated_transfer=results,
        source_sha256={
            p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in source_files
        },
        scope=dict(
            native_runs=0,
            rttov_runs=0,
            production_changed=False,
            physical_number_basis_resolved=False,
            operational_p1_closed=False,
            accepted_observation_cost=False,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    text = json.dumps(run(), indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end="")
