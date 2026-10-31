#!/usr/bin/env python3
"""Offline independent replay of the GG/PP coordinate transformation."""

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import io
import re

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
PACKET = ROOT / "harness/evidence/east_optical_derivative_2026-10-31/packet"
COEF_SHA = "73401691b9e5777daf0e4d8ba6d77dfc912c0d32bd8b70937886fcd91b54a7b5"
CAL_SHA = "a6f830aa04e19f6982aa6ff36e832464a5b32fdcf8200211956969d5eb48325d"
PACKET_SHA = "02b4d7efb574154480bc8b5e213d21f66905d7fb501880eb9b17de013eff230a"
NAMES = ("wv073", "ir087", "ir096", "ir105", "ir112", "ir123", "ir133")


def verified_bytes(path, digest):
    data = path.read_bytes()
    require(hashlib.sha256(data).hexdigest() == digest, str(path) + " SHA mismatch")
    return data


def require(ok, message):
    if not ok:
        raise ValueError(message)


def filters(path):
    text = verified_bytes(path, COEF_SHA).decode("ascii")
    rows = {}
    for line in text.split("FILTER_FUNCTIONS", 1)[1].splitlines():
        fields = line.split("!", 1)[0].split()
        if len(fields) != 6:
            if rows:
                break
            continue
        try:
            ch, status = map(int, fields[:2])
            nu, off, slope, _ = map(float, fields[2:])
        except ValueError:
            if rows:
                break
            continue
        require(ch not in rows, "duplicate channel")
        rows[ch] = (status, nu, off, slope)
    require(
        all(c in rows and rows[c][0] == 1 for c in range(10, 17)),
        "missing or inactive channel",
    )
    return {c: rows[c][1:] for c in range(10, 17)}


def derive(radiance, filt, cal):
    nu, off, slope = filt
    a = 1.438776878 * nu
    b = 1.191042972e-5 * nu**3
    q = math.log1p(b / radiance)
    psi = (a / q - off) / slope
    dp = (a / q**2) * (b / (radiance * (radiance + b))) / slope
    wn = cal["bt_wavenumber_cm1"] * 100
    h, c, k = (
        cal[x] for x in ("Plank_constant_h", "light_speed", "Boltzmann_constant_k")
    )
    a = h * c * wn / k
    b = 2 * h * c * c * wn**3
    x = radiance * 1e-5
    q = math.log1p(b / x)
    t = a / q
    phi = cal["Teff_to_Tbb_c0"] + t * (
        cal["Teff_to_Tbb_c1"] + cal["Teff_to_Tbb_c2"] * t
    )
    dt = (a / q**2) * (b / (x * (x + b))) * 1e-5
    df = (cal["Teff_to_Tbb_c1"] + 2 * cal["Teff_to_Tbb_c2"] * t) * dt
    return psi, phi, df / dp


def parse_blocks(data, pattern):
    # Bounded parser: only named fields used here; reject duplicates, malformed
    # tokens, non-finite values, missing rows and unexpected lengths downstream.
    text = data.decode("ascii")
    found = {}
    regex = re.compile(pattern + r"\s*=\s*\((.*?)\)", re.S)
    for match in regex.finditer(text):
        key = tuple(match.groups()[:-1])
        require(key not in found, "duplicate ASCII block")
        values = np.array(
            [
                float(token.replace("D", "E"))
                for token in match.group(match.lastindex).split()
            ]
        )
        require(values.size > 0 and np.isfinite(values).all(), "invalid ASCII values")
        found[key] = values
    return found


def run(coef):
    fs = filters(coef)
    cal_path = ROOT / "oracle/kdm6/obs/data/gk2a_ami_cal_202507190000.json"
    cal = json.loads(verified_bytes(cal_path, CAL_SHA))["channels"]
    files = json.loads(verified_bytes(PACKET / "packet.json", PACKET_SHA))["files"]
    metrics = {"ratio": 0.0, "kma_bt_K": 0.0, "native_bt_K": 0.0, "K_relative": 0.0}
    for corner in ("GG", "PP"):
        d = PACKET / (corner + "_K")
        data = {}
        for name in ("values.npz", "k_radiance.txt", "profiles_k.txt.gz"):
            rel = corner + "_K/" + name
            data[name] = verified_bytes(d / name, files[rel])
        with np.load(io.BytesIO(data["values.npz"]), allow_pickle=False) as archive:
            saved = {
                key: archive[key].copy()
                for key in ("bt", "ratio", "total", "hydro7", "deff7")
            }
        for key, value in saved.items():
            require(np.isfinite(value).all(), "non-finite saved " + key)
        require(
            all(saved[key].shape == (10, 7) for key in ("bt", "ratio", "total")),
            "saved shape",
        )
        blocks = parse_blocks(data["k_radiance.txt"], r"RADIANCE%(TOTAL|BT|QUALITY)")
        require(set(blocks) == {("TOTAL",), ("BT",), ("QUALITY",)}, "radiance blocks")
        require(all(value.size == 70 for value in blocks.values()), "radiance length")
        total = blocks[("TOTAL",)].reshape(10, 7)
        native = blocks[("BT",)].reshape(10, 7)
        require(
            np.array_equal(total, saved["total"])
            and np.all(total > 0)
            and not np.any(blocks[("QUALITY",)]),
            "raw total/quality",
        )
        ratio = np.empty((10, 7))
        for i in range(10):
            for j, name in enumerate(NAMES):
                ps, ph, rr = derive(float(total[i, j]), fs[j + 10], cal[name])
                require(
                    all(math.isfinite(x) and x > 0 for x in (ps, ph, rr)),
                    "invalid result",
                )
                metrics["native_bt_K"] = max(
                    metrics["native_bt_K"], abs(ps - native[i, j])
                )
                metrics["kma_bt_K"] = max(
                    metrics["kma_bt_K"], abs(ph - saved["bt"][i, j])
                )
                metrics["ratio"] = max(metrics["ratio"], abs(rr - saved["ratio"][i, j]))
                ratio[i, j] = rr
        raw_k = parse_blocks(
            gzip.decompress(data["profiles_k.txt.gz"]),
            r"PROFILES_K\(\s*(\d+)\s*\)%(HYDRO_DEFF|HYDRO)",
        )
        require(
            set(raw_k)
            == {
                (str(i), field)
                for i in range(1, 71)
                for field in ("HYDRO", "HYDRO_DEFF")
            },
            "raw K row inventory",
        )
        for field, ntype, key in (("HYDRO", 8, "hydro7"), ("HYDRO_DEFF", 7, "deff7")):
            target = saved[key]
            nlay = target.shape[-1]
            require(target.ndim == 3 and target.shape[:2] == (10, 7), "saved K shape")
            rows = [raw_k[(str(i), field)] for i in range(1, 71)]
            require(all(row.size == ntype * nlay for row in rows), "raw K row length")
            ice = np.asarray(rows).reshape(10, 7, ntype, nlay)[:, :, 6, :]
            got = ice * ratio[:, :, None]
            scale = np.maximum(np.abs(target), np.finfo(float).tiny)
            metrics["K_relative"] = max(
                metrics["K_relative"], float(np.max(np.abs(got - target) / scale))
            )
            require(
                np.all(
                    np.abs(got - target)
                    <= 64 * np.finfo(float).eps * scale + np.nextafter(0.0, 1.0)
                ),
                field + " transformed K mismatch",
            )
    require(metrics["ratio"] <= 64 * np.finfo(float).eps, "ratio mismatch")
    require(metrics["kma_bt_K"] <= 64 * np.finfo(float).eps * 300, "KMA BT mismatch")
    require(
        metrics["native_bt_K"] <= 64 * np.finfo(float).eps * 300, "native BT mismatch"
    )
    return {
        "schema": "east-optical-coordinate-factor-v1",
        "status": "INCONCLUSIVE",
        "cells": 140,
        "max_abs": metrics,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--coefficient", type=Path, required=True)
    print(json.dumps(run(p.parse_args().coefficient), indent=2))
