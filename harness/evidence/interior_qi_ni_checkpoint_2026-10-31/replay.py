#!/usr/bin/env python3
"""Offline, provisional arithmetic replay of a normalized capture; no model calls.

This is a scaffold, not an authentication of a private preflight or an RTTOV
parser. See README for the required independent raw and producer checks.
"""

import hashlib
import json
from pathlib import Path
import numpy as np

HS = (1e-4, 2e-4, 4e-4, 8e-4)
CHANNELS = ("wv073", "ir087", "ir096", "ir105", "ir112", "ir123", "ir133")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def replay(p):
    require(p["schema"] == "interior-qi-ni-normalized-v1", "schema")
    require(
        p["coordinate"]
        == {
            "native_ijk_1based": [164, 242, 21],
            "flat": 56557,
            "chunk": 110,
            "local_result_row": 237,
            "compact_profile": 236,
            "rttov_row_0based": 45,
        },
        "coordinate",
    )
    require(p["channels"] == list(CHANNELS), "channels")
    require(p["calls"] == {"direct_plus_k": 1, "direct_only": 8, "replay": 0}, "calls")
    baseline = p["baseline"]
    bt0 = np.asarray(baseline["bt"], dtype=float)
    hist = np.asarray(baseline["historical_selected_direct_bt"], dtype=float)
    require(
        bt0.shape == hist.shape == (7,)
        and np.isfinite(bt0).all()
        and np.array_equal(bt0, hist),
        "historical BT",
    )
    kh = np.asarray(baseline["k_hydro_slot7_row45"], dtype=float)
    kd = np.asarray(baseline["k_deff_slot7_row45"], dtype=float)
    require(
        kh.shape == kd.shape == (7,)
        and np.isfinite(kh).all()
        and np.isfinite(kd).all(),
        "K shape",
    )
    require(
        baseline["k_slot_one_based"] == 7 and baseline["k_row_zero_based"] == 45,
        "K coordinate",
    )
    base_qi = np.float32(baseline["qi_real4"])
    base_ni = np.float32(baseline["ni_real4"])
    require(
        np.isfinite(base_qi) and np.isfinite(base_ni) and base_qi > 0 and base_ni > 0,
        "moments",
    )
    base_h = np.asarray(baseline["hydro7"], dtype=float)
    base_d = np.asarray(baseline["deff7"], dtype=float)
    require(
        base_h.shape == base_d.shape
        and base_h.ndim == 2
        and base_h.shape[0] > 45
        and base_h.shape[1] == 7,
        "profile shape",
    )
    require(np.isfinite(base_h).all() and np.isfinite(base_d).all(), "profile finite")
    base_fixed = baseline["fixed_fields_sha256"]
    require(
        set(base_fixed) == {"cfrac", "temperature", "humidity", "surface", "geometry"},
        "fixed fields",
    )
    require(
        all(isinstance(v, str) and len(v) == 64 for v in base_fixed.values()),
        "fixed field hashes",
    )
    out = []
    require(len(p["pairs"]) == 4, "four pairs")
    for h, pair in zip(HS, p["pairs"]):
        require(pair["h"] == h, "h order")
        vals = []
        for sign, label in ((1, "plus"), (-1, "minus")):
            case = pair[label]
            # The precise host arithmetic must be established by the producer;
            # compare its serialized REAL4 words to the declared REAL4 expression.
            qi = np.float32(np.float64(base_qi) * (1 + sign * h))
            ni = np.float32(np.float64(base_ni) * (1 - sign * h))
            require(
                np.float32(case["qi_real4"]) == qi
                and np.float32(case["ni_real4"]) == ni,
                "REAL4 perturbation",
            )
            require(case["fixed_fields_sha256"] == base_fixed, "fixed inputs")
            require(case["quality"] == [0] * 7, "quality")
            bt = np.asarray(case["bt"], dtype=float)
            hydro = np.asarray(case["hydro7"], dtype=float)
            deff = np.asarray(case["deff7"], dtype=float)
            require(bt.shape == (7,) and np.isfinite(bt).all(), "BT")
            require(
                hydro.shape == base_h.shape
                and deff.shape == base_d.shape
                and np.isfinite(hydro).all()
                and np.isfinite(deff).all(),
                "profile",
            )
            mask = np.ones(base_h.shape, dtype=bool)
            mask[45, 6] = False
            require(
                np.array_equal(hydro[mask], base_h[mask])
                and np.array_equal(deff[mask], base_d[mask]),
                "off-target profile change",
            )
            require(
                hydro[45, 6] != base_h[45, 6] and deff[45, 6] != base_d[45, 6],
                "both optics must change",
            )
            vals.append((bt, hydro[45, 6], deff[45, 6]))
        plus, minus = vals
        ds_h = (plus[1] - minus[1]) / (2 * h)
        ds_d = (plus[2] - minus[2]) / (2 * h)
        fd = (plus[0] - minus[0]) / (2 * h)
        ch, cd = kh * ds_h, kd * ds_d
        out.append(
            {
                "h": h,
                "fd": fd.tolist(),
                "content_contribution": ch.tolist(),
                "deff_contribution": cd.tolist(),
                "sum": (ch + cd).tolist(),
                "fd_minus_sum": (fd - ch - cd).tolist(),
                "content_secant": ds_h,
                "deff_secant": ds_d,
            }
        )
    require(baseline["quality"] == [0] * 7, "baseline quality")
    return out


def main():
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("capture", type=Path)
    ap.add_argument(
        "--sha256", required=True, help="externally authenticated capture SHA-256"
    )
    args = ap.parse_args()
    raw = args.capture.read_bytes()
    require(digest(raw) == args.sha256, "capture SHA-256")
    print(
        json.dumps(
            {
                "status": "provisional_normalized_only",
                "results": replay(json.loads(raw)),
            },
            indent=2,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
