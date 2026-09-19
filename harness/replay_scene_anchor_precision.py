#!/usr/bin/env python3
"""Replay the retained PR221 scene-anchor arithmetic without RTTOV.

This is deliberately evidence-specific: it checks the stored ellipsoid/ECEF
geometry and the decimal endpoint finite-difference arithmetic in the compact
JSON. It does not rerun a model, read external files, or certify pixel-time
navigation.
"""

from __future__ import annotations

import json
import math
import sys
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path


getcontext().prec = 60
HERE = Path(__file__).resolve().parent
DEFAULT_JSON = HERE / "evidence" / "scene_anchor_precision_2026-09-19.json"
EXPECTED_CONTROLS = ("deposition", "riming")
EXPECTED_EPSILONS = ("0.03", "0.1")
EXPECTED_CHANNELS = ("wv073", "ir087", "ir096", "ir105", "ir112", "ir123", "ir133")
EXPECTED_ANCHORS = ("first", "center", "last")


def _d(value: object, label: str) -> Decimal:
    try:
        # Fortran list-directed output may use either E or D exponents.
        out = Decimal(str(value).replace("D", "E").replace("d", "e"))
    except (InvalidOperation, ValueError) as exc:
        raise AssertionError(f"{label}: not a Decimal value: {value!r}") from exc
    if not out.is_finite():
        raise AssertionError(f"{label}: non-finite value {value!r}")
    return out


def _vec(value: object, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 3:
        raise AssertionError(f"{label}: expected finite 3-vector")
    out = [float(_d(x, f"{label}[{i}]")) for i, x in enumerate(value)]
    if not all(math.isfinite(x) for x in out):
        raise AssertionError(f"{label}: non-finite vector")
    return out


def _bool(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise AssertionError(f"{label}: expected JSON boolean")
    return value


def _target_ecef(lat_deg: float, lon_deg: float, h_m: float, a: float, b: float) -> list[float]:
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    e2 = 1.0 - (b * b) / (a * a)
    n = a / math.sqrt(1.0 - e2 * math.sin(lat) ** 2)
    return [
        (n + h_m) * math.cos(lat) * math.cos(lon),
        (n + h_m) * math.cos(lat) * math.sin(lon),
        (n * (1.0 - e2) + h_m) * math.sin(lat),
    ]


def _angles(target: list[float], spacecraft: list[float], lat_deg: float, lon_deg: float) -> tuple[float, float]:
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    east = [-math.sin(lon), math.cos(lon), 0.0]
    north = [
        -math.sin(lat) * math.cos(lon),
        -math.sin(lat) * math.sin(lon),
        math.cos(lat),
    ]
    up = [math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat)]
    delta = [spacecraft[i] - target[i] for i in range(3)]
    e = sum(east[i] * delta[i] for i in range(3))
    n = sum(north[i] * delta[i] for i in range(3))
    u = sum(up[i] * delta[i] for i in range(3))
    return math.degrees(math.atan2(math.hypot(e, n), u)), math.degrees(math.atan2(e, n)) % 360.0


def check(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text())
    if data.get("schema") != "scene-anchor-precision-v1":
        raise AssertionError("unexpected or missing schema")
    if tuple(data.get("usable_channels", ())) != EXPECTED_CHANNELS:
        raise AssertionError("unexpected usable-channel contract")
    if tuple(data.get("controls", {})) != EXPECTED_CONTROLS:
        raise AssertionError("unexpected control contract")
    geometry = data["geometry"]
    ellipsoid = geometry["ellipsoid_m"]
    a = float(_d(ellipsoid["equatorial_radius"], "equatorial radius"))
    b = float(_d(ellipsoid["polar_radius"], "polar radius"))
    target_geo = geometry["target_geodetic"]
    lat = float(_d(target_geo["latitude_deg"], "target latitude"))
    lon = float(_d(target_geo["longitude_deg"], "target longitude"))
    h = float(_d(target_geo["height_m"], "target height"))
    expected_target = _target_ecef(lat, lon, h, a, b)
    recorded_target = _vec(geometry["target_ecef_m"], "target ECEF")
    target_error = max(abs(x - y) for x, y in zip(expected_target, recorded_target))
    if target_error > 1.0e-6:
        raise AssertionError(f"target ECEF mismatch: {target_error} m")

    anchor_count = 0
    if tuple(geometry.get("anchors", {})) != EXPECTED_ANCHORS:
        raise AssertionError("unexpected anchor contract")
    for name in EXPECTED_ANCHORS:
        record = geometry["anchors"][name]
        anchor_count += 1
        sc = _vec(record["ecef_m"], f"{name} anchor")
        zen, azi = _angles(recorded_target, sc, lat, lon)
        recorded_angles = record["angles_deg"]
        if abs(zen - float(_d(recorded_angles["zenith"], f"{name} zenith"))) > 1.0e-10:
            raise AssertionError(f"{name} zenith mismatch")
        if abs(azi - float(_d(recorded_angles["azimuth"], f"{name} azimuth"))) > 1.0e-10:
            raise AssertionError(f"{name} azimuth mismatch")

    channel_count = 0
    text_pass = 0
    observed_pass = 0
    for control, control_data in data["controls"].items():
        if tuple(control_data.get("epsilons", {})) != EXPECTED_EPSILONS:
            raise AssertionError(f"{control}: unexpected epsilon contract")
        control_jvp = _d(control_data["cost_jvp"], f"{control} cost JVP")
        control_vjp = _d(control_data["cost_vjp"], f"{control} cost VJP")
        for epsilon, run in control_data["epsilons"].items():
            channels = run["channels"]
            if set(channels) != set(data["usable_channels"]):
                raise AssertionError(f"{control} {epsilon}: missing or unexpected usable channels")
            eps = _d(epsilon, f"{control} epsilon")
            if eps <= 0:
                raise AssertionError(f"{control} {epsilon}: non-positive epsilon")
            quantum = _d(run["bt_decimal_quantum_K"], f"{control} {epsilon} quantum")
            if quantum != Decimal("1e-9"):
                raise AssertionError(f"{control} {epsilon}: expected exact 1e-9 BT quantum")
            bound = quantum / (Decimal(2) * eps)
            if bound != _d(run["bt_text_bound_K_per_control"], f"{control} {epsilon} bound"):
                raise AssertionError(f"{control} {epsilon}: text bound mismatch")
            plus_j = _d(run["plus_cost"], f"{control} {epsilon} plus cost")
            minus_j = _d(run["minus_cost"], f"{control} {epsilon} minus cost")
            fd_cost = (plus_j - minus_j) / (Decimal(2) * eps)
            if fd_cost != _d(run["cost_fd_decimal"], f"{control} {epsilon} cost FD"):
                raise AssertionError(f"{control} {epsilon}: cost FD mismatch")
            if control_jvp != _d(run["cost_jvp"], f"{control} {epsilon} cost JVP"):
                raise AssertionError(f"{control} {epsilon}: cost JVP mismatch")
            if control_vjp != _d(run["cost_vjp"], f"{control} {epsilon} cost VJP"):
                raise AssertionError(f"{control} {epsilon}: cost VJP mismatch")
            for channel in data["usable_channels"]:
                channel_count += 1
                entry = channels[channel]
                plus = _d(entry["plus_bt_text"], f"{control} {epsilon} {channel} plus")
                minus = _d(entry["minus_bt_text"], f"{control} {epsilon} {channel} minus")
                if plus.as_tuple().exponent != -9 or minus.as_tuple().exponent != -9:
                    raise AssertionError(
                        f"{control} {epsilon} {channel}: raw BT token is not E/D.12 precision"
                    )
                fd = (plus - minus) / (Decimal(2) * eps)
                if fd != _d(entry["fd_decimal"], f"{control} {epsilon} {channel} FD"):
                    raise AssertionError(f"{control} {epsilon} {channel}: FD mismatch")
                ad = _d(entry["ad_jvp"], f"{control} {channel} AD")
                _d(entry["ad_vjp"], f"{control} {epsilon} {channel} VJP")
                raw_rel = abs(fd - ad) / max(abs(ad), Decimal("1e-12"))
                text_lhs = abs(fd - ad) + bound
                text_rhs = Decimal("0.05") * abs(ad)
                observed = raw_rel <= Decimal("0.05")
                text_aware = text_lhs <= text_rhs
                if observed != _bool(entry["observed_5pct"], f"{control} {epsilon} {channel} observed verdict"):
                    raise AssertionError(f"{control} {epsilon} {channel}: observed verdict mismatch")
                if text_aware != _bool(entry["text_aware_5pct"], f"{control} {epsilon} {channel} text verdict"):
                    raise AssertionError(f"{control} {epsilon} {channel}: text verdict mismatch")
                if text_aware:
                    text_pass += 1
                if observed:
                    observed_pass += 1

    return {
        "status": "verified",
        "target_ecef_max_abs_error_m": target_error,
        "anchors_verified": anchor_count,
        "channel_fd_cases_verified": channel_count,
        "observed_5pct_passes": observed_pass,
        "text_aware_5pct_passes": text_pass,
    }


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT_JSON
    try:
        result = check(path)
    except (AssertionError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"REPLAY FAILED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
