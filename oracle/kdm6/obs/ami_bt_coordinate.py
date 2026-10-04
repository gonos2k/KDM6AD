"""Narrow RTTOV-native to audited KMA AMI BT coordinate conversion."""
from __future__ import annotations

import json
import math
import numbers
from pathlib import Path

import numpy as np

from .gk2a_l1b import AMI_CHANNELS

RTTOV_C1 = 1.191042972e-5
RTTOV_C2 = 1.438776878
BT_REPLAY_ATOL_K = 3.0e-6
KMA_CHANNELS = tuple(range(8, 17))
_CAL_PATH = Path(__file__).parent / "data/gk2a_ami_cal_202507190000.json"


def read_kma_calibration() -> dict:
    """Load the bundled audited KMA channel tuples for a factory snapshot."""
    channels = json.loads(_CAL_PATH.read_text()).get("channels")
    if not isinstance(channels, dict):
        raise ValueError("bundled KMA AMI calibration has no channel table")
    for channel_id in KMA_CHANNELS:
        channel = AMI_CHANNELS[channel_id - 1]
        cal = channels.get(channel)
        if cal is None or "bt_wavenumber_cm1" not in cal:
            raise ValueError(f"bundled KMA calibration lacks paired channel {channel}")
    return channels


def read_ami_filters(coef_path: str | Path) -> dict[int, dict[str, float]]:
    """Read AMI FILTER_FUNCTIONS from the coefficient file actually used by RTTOV."""
    path = Path(coef_path)
    text = path.read_text(errors="replace")
    if "IDENTIFICATION" not in text or "FILTER_FUNCTIONS" not in text:
        raise ValueError(f"{path}: missing RTTOV identification or FILTER_FUNCTIONS")
    ident = text.split("IDENTIFICATION", 1)[1].split("LINE-BY-LINE", 1)[0]
    clean = [line.split("!", 1)[0].strip() for line in ident.splitlines()]
    clean = [line for line in clean if line]
    identity_found = False
    for i, line in enumerate(clean[:-3]):
        if line.split() == ["48", "1", "93"]:
            identity_found = (clean[i + 1].casefold().split() == ["gkompsat2-1", "ami-vis"]
                              and clean[i + 2].casefold() == "ir"
                              and clean[i + 3] == "13")
            break
    if not identity_found:
        raise ValueError(f"{path}: coefficient identity is not RTTOV GKOMPSAT-2 AMI IR")

    body = text.split("FILTER_FUNCTIONS", 1)[1]
    rows: dict[int, dict[str, float]] = {}
    for raw in body.splitlines():
        fields = raw.split("!", 1)[0].split()
        if len(fields) != 6:
            if rows:
                break
            continue
        try:
            channel, status = int(fields[0]), int(fields[1])
            nu, offset, slope, gamma = map(float, fields[2:])
        except ValueError:
            if rows:
                break
            continue
        if channel in rows:
            raise ValueError(f"{path}: duplicate FILTER_FUNCTIONS channel {channel}")
        if not all(math.isfinite(v) for v in (nu, offset, slope, gamma)):
            raise ValueError(f"{path}: non-finite FILTER_FUNCTIONS channel {channel}")
        if nu <= 0.0 or slope == 0.0:
            raise ValueError(f"{path}: invalid wavenumber/slope for channel {channel}")
        rows[channel] = {"status": status, "wavenumber_cm1": nu,
                         "offset_K": offset, "slope": slope, "gamma": gamma}
    missing = sorted(set(KMA_CHANNELS) - set(rows))
    if missing:
        raise ValueError(f"{path}: missing AMI FILTER_FUNCTIONS channels {missing}")
    if any(rows[c]["status"] != 1 for c in KMA_CHANNELS):
        raise ValueError(f"{path}: one or more AMI thermal channels are inactive")
    return rows


def _kma_bt_and_prime(radiance: np.ndarray, cal: dict) -> tuple[np.ndarray, np.ndarray]:
    nu = float(cal["bt_wavenumber_cm1"])
    if not math.isfinite(nu) or nu <= 0.0:
        raise ValueError("KMA BT wavenumber must be positive and finite")
    h, c, k = (float(cal[name]) for name in
               ("Plank_constant_h", "light_speed", "Boltzmann_constant_k"))
    sigma_m = nu * 100.0
    a = h * c * sigma_m / k
    b = 2.0 * h * c * c * sigma_m ** 3
    x = radiance * 1.0e-3 / 100.0
    log_term = np.log(b / x + 1.0)
    teff = a / log_term
    bt = (float(cal["Teff_to_Tbb_c0"])
          + float(cal["Teff_to_Tbb_c1"]) * teff
          + float(cal["Teff_to_Tbb_c2"]) * teff * teff)
    poly_prime = float(cal["Teff_to_Tbb_c1"]) + 2.0 * float(cal["Teff_to_Tbb_c2"]) * teff
    teff_prime = a * b / (x * (x + b) * log_term ** 2) * 1.0e-5
    return bt, poly_prime * teff_prime


def _rttov_bt_and_prime(radiance: np.ndarray, filt: dict) -> tuple[np.ndarray, np.ndarray]:
    nu = float(filt["wavenumber_cm1"])
    offset, slope = float(filt["offset_K"]), float(filt["slope"])
    a = RTTOV_C2 * nu
    b = RTTOV_C1 * nu ** 3
    log_term = np.log(b / radiance + 1.0)
    planck_bt = a / log_term
    bt = (planck_bt - offset) / slope
    prime = a * b / (radiance * (radiance + b) * log_term ** 2) / slope
    return bt, prime


def transform_rttov_to_kma(bt_native, radiance_total, k_dict: dict,
                            channels, filters: dict, calibration: dict
                            ) -> tuple[np.ndarray, dict, np.ndarray]:
    """Map native RTTOV BT and every K field to the bundled KMA BT coordinate.

    Returns ``(bt_kma, k_kma, d_bt_kma_d_bt_native)``. This does not mutate
    any caller input; the final derivative ratio scales the channel axis of each
    cached K field so the existing adjoint contraction remains valid.
    """
    channel_ids = tuple(channels)
    if not channel_ids or len(set(channel_ids)) != len(channel_ids):
        raise ValueError("KMA BT conversion needs a nonempty, duplicate-free channel list")
    if any(isinstance(ch, bool) or not isinstance(ch, numbers.Integral)
           or int(ch) not in KMA_CHANNELS for ch in channel_ids):
        raise ValueError("KMA BT research coordinate supports only thermal AMI channels 8..16")
    bt = np.asarray(bt_native, dtype=np.float64)
    radiance = np.asarray(radiance_total, dtype=np.float64)
    if bt.ndim != 2 or radiance.shape != bt.shape or bt.shape[1] != len(channel_ids):
        raise ValueError("BT and total radiance must share [nprofiles,nchannels] shape")
    if not np.isfinite(bt).all() or not np.isfinite(radiance).all() or not (radiance > 0.0).all():
        raise ValueError("KMA BT conversion requires finite BT and positive finite total radiance")

    ratio = np.empty_like(bt)
    converted = np.empty_like(bt)
    for j, raw_id in enumerate(channel_ids):
        channel_id = int(raw_id)
        channel = AMI_CHANNELS[channel_id - 1]
        if channel not in calibration or channel_id not in filters:
            raise ValueError(f"KMA BT conversion lacks calibration/filter for channel {channel_id}")
        psi, psi_prime = _rttov_bt_and_prime(radiance[:, j], filters[channel_id])
        if not np.allclose(psi, bt[:, j], rtol=0.0, atol=BT_REPLAY_ATOL_K):
            raise ValueError(
                f"channel {channel_id}: total-radiance RTTOV BT replay exceeds "
                f"{BT_REPLAY_ATOL_K:g} K")
        phi, phi_prime = _kma_bt_and_prime(radiance[:, j], calibration[channel])
        if (not np.isfinite(phi).all() or not (phi > 0.0).all()
                or not np.isfinite(phi_prime).all() or not (phi_prime > 0.0).all()):
            raise ValueError(f"channel {channel_id}: non-finite KMA BT or derivative")
        if not np.isfinite(psi_prime).all() or not (psi_prime > 0.0).all():
            raise ValueError(f"channel {channel_id}: invalid RTTOV BT derivative")
        d = phi_prime / psi_prime
        if not np.isfinite(d).all():
            raise ValueError(f"channel {channel_id}: non-finite BT coordinate derivative")
        converted[:, j], ratio[:, j] = phi, d

    scaled_k = {}
    for name, value in k_dict.items():
        matrix = np.asarray(value, dtype=np.float64)
        if matrix.ndim != 3 or matrix.shape[:2] != bt.shape:
            raise ValueError(f"K field {name!r} must have [nprofiles,nchannels,L] shape")
        if not np.isfinite(matrix).all():
            raise ValueError(f"K field {name!r} contains non-finite values")
        scaled_k[name] = matrix * ratio[:, :, None]
    return converted, scaled_k, ratio
