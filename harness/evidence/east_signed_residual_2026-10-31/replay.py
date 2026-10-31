#!/usr/bin/env python3
"""Offline signed residual and equal-relative-change optical synthesis, v1."""

import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from fractions import Fraction
from decimal import Decimal, localcontext, ROUND_HALF_EVEN
import numpy as np

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE.parent
HS = (0.0001, 0.0002, 0.0004, 0.0008)
CHANNELS = ("wv073", "ir087", "ir096", "ir105", "ir112", "ir123", "ir133")
KINDS = {
    "content": ("east_optical_onehot_2026-10-31", "hydro7"),
    "diameter": ("east_optical_deff_onehot_2026-10-31", "deff7"),
}


def require(ok, msg):
    if not ok:
        raise ValueError(msg)


def ratio(n, d):
    require(math.isfinite(n) and math.isfinite(d) and d != 0, "invalid ratio")
    return n / d


def product(k, direction, value):
    exact = Fraction.from_float(float(k)) * Fraction.from_float(float(direction))
    u = Fraction(1, 2**53)
    bound = 2 * u / (1 - 2 * u) * abs(exact) + Fraction(1, 2**1074)
    require(
        math.isfinite(float(value))
        and abs(Fraction.from_float(float(value)) - exact) <= bound,
        "product roundoff",
    )


def synth(q, d):
    q = np.asarray(q, dtype=np.float64)
    d = np.asarray(d, dtype=np.float64)
    require(
        q.shape == (7,)
        and d.shape == (7,)
        and np.isfinite(q).all()
        and np.isfinite(d).all(),
        "invalid vectors",
    )
    # Exact binary64 operands and rational reductions avoid BLAS ordering.
    fq = [Fraction.from_float(float(x)) for x in q]
    fd = [Fraction.from_float(float(x)) for x in d]
    q2 = sum((x * x for x in fq), Fraction())
    d2 = sum((x * x for x in fd), Fraction())
    s2 = sum(((x + y) ** 2 for x, y in zip(fq, fd)), Fraction())
    dot = sum((x * y for x, y in zip(fq, fd)), Fraction())
    require(q2 > 0 and d2 > 0, "zero or nonfinite norm")
    with localcontext() as ctx:
        ctx.prec = 100
        ctx.rounding = ROUND_HALF_EVEN

        def dec(value):
            return Decimal(value.numerator) / Decimal(value.denominator)

        nq, nd, ns = (dec(value).sqrt() for value in (q2, d2, s2))
        result = {
            "cosine": float(dec(dot) / (nq * nd)),
            "cancellation": float(Decimal(1) - ns / (nq + nd)),
            "sum_over_content": float(ns / nq),
        }
    require(all(map(math.isfinite, result.values())), "nonfinite synthesis")
    return result


def replay():
    prior = EVIDENCE / "east_optical_derivative_2026-10-31" / "packet"
    out = {
        "schema": "east-signed-residual-v1",
        "channels": CHANNELS,
        "hs": HS,
        "results": {},
        "synthesis": {},
    }
    for corner in ("GG", "PP"):
        with np.load(prior / f"{corner}_K" / "values.npz", allow_pickle=False) as z:
            ks = {name: z[key].copy() for name, (_, key) in KINDS.items()}
        out["results"][corner] = {}
        out["synthesis"][corner] = []
        for kind, (directory, _) in KINDS.items():
            packet = EVIDENCE / directory / "packet"
            pins = json.loads((packet / "pins.json").read_text())
            summary = json.loads((packet / "summary.json").read_text())
            entries = pins["checks"][corner]
            require(len(entries) == 10, "profile count")
            residuals = []
            results = []
            for j, h in enumerate(HS):
                values = []
                for sign in ("plus", "minus"):
                    with np.load(
                        packet / f"{corner}_{j}_{sign}" / "values.npz",
                        allow_pickle=False,
                    ) as z:
                        values.append(z["bt"].copy())
                fd = (values[0] - values[1]) / (2 * h)
                require(
                    fd.shape == (10, 7) and np.isfinite(fd).all(), "fd shape/finite"
                )
                k = ks[kind]
                require(
                    k.ndim == 3
                    and k.shape[:2] == (10, 7)
                    and k.shape[2] > 39
                    and np.isfinite(k).all(),
                    "K shape/finite",
                )
                direction = np.array(
                    [
                        (
                            float(e["serialized"][f"{h:g}_plus"])
                            - float(e["serialized"][f"{h:g}_minus"])
                        )
                        / (2 * h)
                        for e in entries
                    ]
                )
                require(
                    np.isfinite(direction).all() and np.all(direction != 0), "direction"
                )
                pred = k[:, :, 39] * direction[:, None]
                stored = summary["results"][corner][f"{h:g}"]
                require(
                    np.array_equal(
                        fd.view(np.uint64),
                        np.asarray(stored["fd"], dtype=np.float64).view(np.uint64),
                    ),
                    "FD bits",
                )
                saved = np.asarray(stored["k_v"], dtype=np.float64)
                require(saved.shape == (10, 7), "K shape")
                for i in range(10):
                    require(
                        entries[i]["profile"] == i + 1
                        and entries[i]["layer_zero_based"] == 39,
                        "profile coordinate",
                    )
                    for c in range(7):
                        product(k[i, c, 39], direction[i], pred[i, c])
                        product(k[i, c, 39], direction[i], saved[i, c])
                err = fd - pred
                require(np.isfinite(err).all(), "residual finite")
                residuals.append(err)
                results.append(
                    {
                        "h": h,
                        "direction": direction.tolist(),
                        "fd": fd.tolist(),
                        "k_v": pred.tolist(),
                        "signed_fd_minus_k": err.tolist(),
                    }
                )
            for j in range(3):
                # Signed elementwise ratio: larger-h residual divided by preceding smaller-h residual.
                denom = residuals[j]
                num = residuals[j + 1]
                results[j + 1]["ratio_to_previous"] = [
                    [
                        None if x == 0 else ratio(float(y), float(x))
                        for x, y in zip(rowx, rowy)
                    ]
                    for rowx, rowy in zip(denom, num)
                ]
            out["results"][corner][kind] = results
        cp = json.loads(
            (EVIDENCE / KINDS["content"][0] / "packet/pins.json").read_text()
        )["checks"][corner]
        dp = json.loads(
            (EVIDENCE / KINDS["diameter"][0] / "packet/pins.json").read_text()
        )["checks"][corner]
        for i, (a, b) in enumerate(zip(cp, dp)):
            require(
                a["profile"] == b["profile"] == i + 1
                and a["content"] == b["content"]
                and a["diameter_um"] == b["diameter_um"],
                "baseline mismatch",
            )
            q = float(a["content"])
            d = float(a["diameter_um"])
            require(
                math.isfinite(q) and math.isfinite(d) and q > 0 and d > 0, "baseline"
            )
            sq = q * ks["content"][i, :, 39]
            sd = d * ks["diameter"][i, :, 39]
            for c in range(7):
                product(ks["content"][i, c, 39], q, sq[c])
                product(ks["diameter"][i, c, 39], d, sd[c])
            out["synthesis"][corner].append(
                {
                    "profile": i + 1,
                    "content": q,
                    "diameter_um": d,
                    "Sq": sq.tolist(),
                    "Sd": sd.tolist(),
                    **synth(sq, sd),
                }
            )
    return out


def verify_manifest():
    manifest = json.loads((HERE / "source_manifest.json").read_text())
    require(manifest["schema"] == "east-signed-residual-sources-v1", "source schema")
    require(
        set(manifest["files"])
        == {"replay.py", "test_replay.py", "README.md", "results.json"},
        "source inventory",
    )
    for name, digest in manifest["files"].items():
        require(
            hashlib.sha256((HERE / name).read_bytes()).hexdigest() == digest,
            "source hash " + name,
        )
    require(
        set(manifest["upstream_source_manifests"]) == {x[0] for x in KINDS.values()},
        "upstream inventory",
    )
    for name, digest in manifest["upstream_source_manifests"].items():
        require(
            hashlib.sha256(
                (EVIDENCE / name / "source_manifest.json").read_bytes()
            ).hexdigest()
            == digest,
            "upstream source hash " + name,
        )


def main():
    verify_manifest()
    for directory, _ in KINDS.values():
        subprocess.run(
            [sys.executable, str(EVIDENCE / directory / "verify.py")],
            check=True,
            stdout=subprocess.DEVNULL,
        )
    result = replay()
    path = HERE / "results.json"
    data = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    require(path.read_text() == data, "result differs")
    print("signed residual replay OK; zero model calls")


if __name__ == "__main__":
    main()
