#!/usr/bin/env python3
"""Offline arithmetic and capture checks; never executes RTTOV."""

import hashlib
import io
import json
import math
import re
from fractions import Fraction
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]

P = HERE / "packet"
PRIOR = HERE.parent / "east_optical_derivative_2026-10-31" / "packet"
HS = (1e-4, 2e-4, 4e-4, 8e-4)
CAL_SHA = "a6f830aa04e19f6982aa6ff36e832464a5b32fdcf8200211956969d5eb48325d"
CAL_PATH = PROJECT / "oracle/kdm6/obs/data/gk2a_ami_cal_202507190000.json"
CHANNEL_NAMES = ("wv073", "ir087", "ir096", "ir105", "ir112", "ir123", "ir133")
BT_BOUND_K = 64 * np.finfo(np.float64).eps * 300
PACKET_SHA = "f1b7e41e18b12a7151beb82d0782b0dd2a3c35897421863c437002aa9ec26384"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load(p):
    return json.loads(p.read_text())


def check(x, message):
    if not x:
        raise ValueError(message)


def verify_sources(root=HERE):
    manifest = load(root / "source_manifest.json")
    check(manifest.get("schema") == "east-optical-onehot-sources-v1", "source schema")
    files = manifest.get("files")
    check(
        set(files) == {"verify.py", "test_verify.py", "README.md"}, "source inventory"
    )
    for name, digest in files.items():
        check(sha(root / name) == digest, "source hash: " + name)


def check_raw(raw):
    # Narrow parser for the three required 70-element blocks; no imported helpers.
    text = raw.decode("ascii")
    check(len(text) < 1000000, "raw size")
    blocks = {}
    for name in ("TOTAL", "BT", "QUALITY"):
        matches = re.findall(
            r"(?m)^RADIANCE%" + name + r"\s*=\s*\(\s*([\s\S]*?)\s*\)", text
        )
        check(len(matches) == 1, "raw block " + name)
        tokens = matches[0].split()
        check(len(tokens) == 70, "raw shape " + name)
        try:
            values = [float(t.replace("D", "E")) for t in tokens]
        except ValueError as exc:
            raise ValueError("raw number") from exc
        check(all(math.isfinite(x) for x in values), "raw finite")
        if name == "QUALITY":
            check(all(x == 0 for x in values), "raw quality")
        if name == "TOTAL":
            check(all(x > 0 for x in values), "raw TOTAL must be positive")
        blocks[name] = np.asarray(values, dtype=np.float64).reshape(10, 7)
    return blocks


def kma_bt_from_total(total, calibration):
    """Independent scalar Planck inverse on serialized RTTOV TOTAL radiance."""
    out = np.empty((10, 7), dtype=np.float64)
    for channel, name in enumerate(CHANNEL_NAMES):
        cal = calibration[name]
        wavenumber = float(cal["bt_wavenumber_cm1"]) * 100.0
        h = float(cal["Plank_constant_h"])
        c = float(cal["light_speed"])
        k = float(cal["Boltzmann_constant_k"])
        a = h * c * wavenumber / k
        b = 2.0 * h * c * c * wavenumber**3
        for profile in range(10):
            x = float(total[profile, channel]) * 1e-5
            check(x > 0 and math.isfinite(x), "nonpositive TOTAL radiance")
            teff = a / math.log1p(b / x)
            out[profile, channel] = (
                float(cal["Teff_to_Tbb_c0"])
                + float(cal["Teff_to_Tbb_c1"]) * teff
                + float(cal["Teff_to_Tbb_c2"]) * teff * teff
            )
    check(np.isfinite(out).all(), "nonfinite recomputed KMA BT")
    return out


def check_product(k, direction, stored, replay):
    # One binary64 product; gamma(2) also allows a single extra rounding.
    exact = Fraction.from_float(float(k)) * Fraction.from_float(float(direction))
    unit = Fraction(1, 2**53)
    bound = (2 * unit / (1 - 2 * unit)) * abs(exact) + Fraction(1, 2**1074)
    for value in (stored, replay):
        check(math.isfinite(float(value)), "nonfinite product")
        check(
            abs(Fraction.from_float(float(value)) - exact) <= bound, "product roundoff"
        )


def main():
    verify_sources()
    manifest_raw = (P / "manifest.json").read_bytes()
    check(
        hashlib.sha256(manifest_raw).hexdigest() == PACKET_SHA,
        "manifest digest",
    )
    manifest = json.loads(manifest_raw)["files"]
    actual = {str(p.relative_to(P)) for p in P.rglob("*") if p.is_file()} - {
        "manifest.json"
    }
    check(actual == set(manifest), "inventory")
    verified = {}
    for name, digest in manifest.items():
        raw = (P / name).read_bytes()
        check(hashlib.sha256(raw).hexdigest() == digest, name)
        verified[name] = raw
    pins = json.loads(verified["pins.json"])
    summary = json.loads(verified["summary.json"])
    attempt = json.loads(verified["attempt.json"])
    check(
        hashlib.sha256(verified["pins.json"]).hexdigest() == attempt["manifest_sha256"]
        and hashlib.sha256(verified["runner.py"]).hexdigest()
        == attempt["runner_sha256"],
        "launch pins",
    )
    check(
        attempt["planned_calls"]
        == summary["calls"]
        == pins["calls"]
        == {"direct": 16, "K": 0},
        "call counts",
    )
    prior_raw = (PRIOR / "preflight.json").read_bytes()
    old_raw = (PRIOR / "pins.json").read_bytes()
    prior = json.loads(prior_raw)
    old = json.loads(old_raw)
    check(pins["old_pins"] == old, "prior manifest")
    check(
        hashlib.sha256(prior_raw).hexdigest()
        == "a0515c1da6025b4b069f21039e0012274ba6136251eb192d6e93733699dd222e",
        "prior preflight",
    )
    calibration_raw = CAL_PATH.read_bytes()
    check(
        hashlib.sha256(calibration_raw).hexdigest() == CAL_SHA,
        "KMA calibration SHA differs",
    )
    source_cal = [
        digest
        for path, digest in old["sources"].items()
        if path.endswith("/oracle/kdm6/obs/data/gk2a_ami_cal_202507190000.json")
    ]
    check(source_cal == [CAL_SHA], "historical calibration source pin differs")
    calibration = json.loads(calibration_raw)["channels"]
    raw_to_kma_max_abs = 0.0
    raw_to_kma_cells = 0
    out = {}
    for c in ("GG", "PP"):
        k_path = PRIOR / f"{c}_K/values.npz"
        k_raw = k_path.read_bytes()
        check(
            hashlib.sha256(k_raw).hexdigest()
            == next(
                v for k, v in pins["extra"].items() if k.endswith(f"/{c}_K/values.npz")
            ),
            "K pin",
        )
        with np.load(io.BytesIO(k_raw), allow_pickle=False) as z:
            kh = z["hydro7"].copy()
        check(kh.shape[:2] == (10, 7) and np.isfinite(kh).all(), "K shape")
        n = kh.shape[2]
        checks = pins["checks"][c]
        check(len(checks) == 10, "profiles")
        for i, e in enumerate(checks, 1):
            check(
                e["profile"] == i
                and e["rank"] == 3
                and e["layer_zero_based"] == 39
                and e["content"] > 0
                and e["fraction"] > 0
                and 10 < e["diameter_um"] < 120
                and e["diameter_um"] != 20,
                "preflight",
            )
            vec = np.zeros((2 * n, 4))
            vec[39, 0] = e["content"]
            for j, mode in enumerate(("hydro", "deff", "mixed"), 1):
                for t in prior["cases"][c]["checks"]:
                    if t["profile"] == i and t["field"] == mode and t["h"] == 1e-5:
                        layer = t["layer_zero_based"]
                        vec[layer, j] = (t["content_plus"] - t["content_minus"]) / (
                            2e-5
                        )
                        vec[n + layer, j] = (t["deff_plus"] - t["deff_minus"]) / (2e-5)
            norms = np.linalg.norm(vec, axis=0)
            check(
                np.all(norms > 0) and np.linalg.matrix_rank(vec / norms) == 3,
                "direction rank",
            )
        out[c] = {}
        for idx, h in enumerate(HS):
            vals = []
            for s in ("plus", "minus"):
                k = f"{c}_{idx}_{s}"
                r = json.loads(verified[f"{k}/receipt.json"])
                inventory = pins["cases"][k]
                base = old["cases"][f"{c}_K"]
                check(
                    r["mode"] == "direct"
                    and r["do_k"] is False
                    and r["input_hashes"] == r["post_input_hashes"] == inventory
                    and r["value_sha256"]
                    == hashlib.sha256(verified[f"{k}/values.npz"]).hexdigest(),
                    "receipt " + k,
                )
                check(set(inventory) == set(base), "input inventory")
                changed = {p for p in inventory if inventory[p] != base[p]}
                check(
                    changed
                    == (
                        {f"in/profiles/{i:03d}/atm/hydro.txt" for i in range(1, 11)}
                        | {"out/rttov_test.txt"}
                    ),
                    "fixed inputs",
                )
                raw_blocks = check_raw(verified[f"{k}/direct_radiance.txt"])
                with np.load(
                    io.BytesIO(verified[f"{k}/values.npz"]), allow_pickle=False
                ) as z:
                    bt = z["bt"].copy()
                check(bt.shape == (10, 7) and np.isfinite(bt).all(), "BT")
                recomputed_bt = kma_bt_from_total(raw_blocks["TOTAL"], calibration)
                delta = np.abs(recomputed_bt - bt)
                check(
                    np.isfinite(delta).all() and np.max(delta) <= BT_BOUND_K,
                    "raw TOTAL to KMA BT differs",
                )
                raw_to_kma_max_abs = max(raw_to_kma_max_abs, float(np.max(delta)))
                raw_to_kma_cells += delta.size
                vals.append(bt)
            direction = []
            for e in checks:
                plus = float(e["serialized"][f"{h:g}_plus"])
                minus = float(e["serialized"][f"{h:g}_minus"])
                check(0 < minus < e["content"] < plus, "serialized positivity")
                direction.append((plus - minus) / (2 * h))
            fd = (vals[0] - vals[1]) / (2 * h)
            pred = kh[:, :, 39] * np.asarray(direction)[:, None]
            err = fd - pred
            rec = summary["results"][c][f"{h:g}"]
            check(
                np.array_equal(
                    fd.view(np.uint64),
                    np.asarray(rec["fd"], dtype=np.float64).view(np.uint64),
                ),
                "FD replay",
            )
            saved = np.asarray(rec["k_v"], dtype=np.float64)
            check(saved.shape == (10, 7), "K shape")
            for p in range(10):
                for ch in range(7):
                    check_product(
                        kh[p, ch, 39], direction[p], saved[p, ch], pred[p, ch]
                    )
            check(
                np.count_nonzero(vals[0] - vals[1])
                == rec["nonzero_bt_differences"]
                == 70,
                "nonzero signals",
            )
            ma = float(np.max(np.abs(err)))
            rel = float(np.linalg.norm(err) / np.linalg.norm(pred))
            check(
                np.isclose(ma, rec["max_abs_error"], rtol=1e-6, atol=1e-14)
                and np.isclose(rel, rec["relative_l2_error"], rtol=1e-6, atol=1e-14),
                "metrics",
            )
            out[c][f"{h:g}"] = {
                "max_abs_error": ma,
                "relative_l2_error": rel,
                "nonzero": 70,
            }
    print(
        json.dumps(
            {
                "status": "INCONCLUSIVE",
                "public_replay_calls": 0,
                "raw_total_to_kma_bt": {
                    "cells": raw_to_kma_cells,
                    "max_abs_delta_K": raw_to_kma_max_abs,
                    "bound_K": BT_BOUND_K,
                },
                "metrics": out,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
