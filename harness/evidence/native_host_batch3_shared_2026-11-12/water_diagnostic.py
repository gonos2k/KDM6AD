#!/usr/bin/env python3
"""Conditional fixed-measure inventory from the archived f32 B=1 call.

The exact decimal arithmetic is a diagnostic of archived f32 words, not an
emulation of the kernel's operation order or a conservation certification.
"""

from decimal import Decimal, localcontext
import hashlib
import json
import math
from pathlib import Path
import re
import struct

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "native_host_column_f32_2026-11-11/raw/selected_full.json"
SOURCE_SHA = "e3117d277a073042bbae648b87e7dd6661d14b600fc8245f6aeabc19fe715eae"
TILE_SHA = "a13d3aafdc4d71ffe5ea7a59616a48f4ea7c6ab3da813b8883bb7277df71ecce"
WATER = ("qv", "qc", "qr", "qi", "qs", "qg")
RESULT = HERE / "water_diagnostic.json"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def decode(raw):
    require(
        isinstance(raw, str) and re.fullmatch(r"[0-9a-f]{8}", raw) is not None,
        "invalid f32 word",
    )
    value = struct.unpack("<f", struct.pack("<I", int(raw, 16)))[0]
    require(math.isfinite(value), "nonfinite f32 word")
    return Decimal.from_float(value)


def load_source(path=SOURCE):
    raw = path.read_bytes()
    require(
        hashlib.sha256(raw).hexdigest() == SOURCE_SHA,
        "selected source SHA-256 mismatch",
    )
    data = json.loads(raw)
    require(
        data["schema"] == "kdm6.selected_native_f32.v1"
        and data["source_tile_sha256"] == TILE_SHA,
        "source identity",
    )
    require(
        data["column_native"] == [203, 149]
        and data["column_zero_based"] == [201, 6]
        and data["tile_shape"] == [232, 39, 139]
        and data["call_index"] == 2,
        "source column",
    )
    require(
        data["model_start"] == "2025-07-19_00:00:00"
        and data["model_step_end"] == "2025-07-19_00:00:20"
        and data["dt"] == 20.0
        and data["tile_return_code"] == 0,
        "source time/status",
    )
    return data


def calculate(data):
    """Calculate exactly from binary32 values, with no intermediate f32 rounding."""
    with localcontext() as ctx:
        ctx.prec = 600
        inputs, outputs = data["input_words_hex"], data["output_words_hex"]
        fields = ("rho", "delz", *WATER)
        for name in fields:
            require(
                isinstance(inputs[name], list) and len(inputs[name]) == 39,
                "input shape: " + name,
            )
        for name in WATER:
            require(
                isinstance(outputs[name], list) and len(outputs[name]) == 39,
                "output shape: " + name,
            )
        layers = []
        win = wout = Decimal(0)
        for k in range(39):
            rho, dz = decode(inputs["rho"][k]), decode(inputs["delz"][k])
            require(rho > 0 and dz > 0, "nonpositive density or layer thickness")
            water_in = sum((decode(inputs[name][k]) for name in WATER), Decimal(0))
            water_out = sum((decode(outputs[name][k]) for name in WATER), Decimal(0))
            weight = rho * dz
            old, new = weight * water_in, weight * water_out
            win += old
            wout += new
            layers.append(
                {
                    "level_zero_bottom_first": k,
                    "density_word": inputs["rho"][k],
                    "thickness_word": inputs["delz"][k],
                    "water_in_kg_m2": str(old),
                    "water_out_kg_m2": str(new),
                    "change_kg_m2": str(new - old),
                }
            )
        # rain is already total rain+snow+graupel+ice in the C ABI; subsets are not added.
        rain = decode(data["increments_words_hex"]["rain"])
        delta = wout - win
        return {
            "schema": "kdm6.conditional_f32_same_call_water.v1",
            "source_sha256": SOURCE_SHA,
            "source_tile_sha256": TILE_SHA,
            "column_native": data["column_native"],
            "levels": 39,
            "source_window": [data["model_start"], data["model_step_end"]],
            "measure_assumption": "rho is compatible dry-air mass density and water fields are dry-air mixing ratios; unverified for this operational call",
            "scope": "archived B=1 kernel call only; before host cleanup and transport; no physical conservation approval",
            "physical_conservation_approved": False,
            "arithmetic": "exact Decimal conversion of f32 words; 600-digit precision, no intermediate f32 rounding",
            "water_fields": list(WATER),
            "precipitation_field": "rain total only",
            "precipitation_word": data["increments_words_hex"]["rain"],
            "precipitation_kg_m2": str(rain),
            "water_in_kg_m2": str(win),
            "water_out_kg_m2": str(wout),
            "water_change_kg_m2": str(delta),
            "conditional_residual_kg_m2": str(delta + rain),
            "layers": layers,
        }


def verify(result_path=RESULT, source_path=SOURCE):
    expected = calculate(load_source(source_path))
    require(
        json.loads(result_path.read_text()) == expected, "water diagnostic mismatch"
    )
    return expected


if __name__ == "__main__":
    result = verify()
    print(
        "Conditional same-call water residual:",
        result["conditional_residual_kg_m2"],
        "kg m^-2 under stated measure assumption",
    )
