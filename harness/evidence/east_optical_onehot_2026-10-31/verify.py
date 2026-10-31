#!/usr/bin/env python3
"""Offline arithmetic and capture checks; never executes RTTOV."""

import hashlib
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


def check_raw(path):
    # Narrow parser for the two required 70-element blocks; no imported helpers.
    text = path.read_text()
    check(len(text) < 1000000, "raw size")
    for name in ("BT", "QUALITY"):
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
    check(
        sha(P / "manifest.json")
        == "f1b7e41e18b12a7151beb82d0782b0dd2a3c35897421863c437002aa9ec26384",
        "manifest digest",
    )
    manifest = load(P / "manifest.json")["files"]
    actual = {str(p.relative_to(P)) for p in P.rglob("*") if p.is_file()} - {
        "manifest.json"
    }
    check(actual == set(manifest), "inventory")
    for name, digest in manifest.items():
        check(sha(P / name) == digest, name)
    pins = load(P / "pins.json")
    summary = load(P / "summary.json")
    attempt = load(P / "attempt.json")
    check(
        sha(P / "pins.json") == attempt["manifest_sha256"]
        and sha(P / "runner.py") == attempt["runner_sha256"],
        "launch pins",
    )
    check(
        attempt["planned_calls"]
        == summary["calls"]
        == pins["calls"]
        == {"direct": 16, "K": 0},
        "call counts",
    )
    prior = load(PRIOR / "preflight.json")
    old = load(PRIOR / "pins.json")
    check(pins["old_pins"] == old, "prior manifest")
    check(
        sha(PRIOR / "preflight.json")
        == "a0515c1da6025b4b069f21039e0012274ba6136251eb192d6e93733699dd222e",
        "prior preflight",
    )
    out = {}
    for c in ("GG", "PP"):
        check(
            sha(PRIOR / f"{c}_K/values.npz")
            == next(
                v for k, v in pins["extra"].items() if k.endswith(f"/{c}_K/values.npz")
            ),
            "K pin",
        )
        with np.load(PRIOR / f"{c}_K/values.npz") as z:
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
                r = load(P / k / "receipt.json")
                inventory = pins["cases"][k]
                base = old["cases"][f"{c}_K"]
                check(
                    r["mode"] == "direct"
                    and r["do_k"] is False
                    and r["input_hashes"] == r["post_input_hashes"] == inventory
                    and r["value_sha256"] == sha(P / k / "values.npz"),
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
                check_raw(P / k / "direct_radiance.txt")
                with np.load(P / k / "values.npz") as z:
                    bt = z["bt"].copy()
                check(bt.shape == (10, 7) and np.isfinite(bt).all(), "BT")
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
            {"status": "INCONCLUSIVE", "public_replay_calls": 0, "metrics": out},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
