"""Synthetic radiance mixing, observation support and analysis increments.

This is a monochromatic Planck example, not RTTOV or the project's Huber
observation cost. It keeps nonlinear conversion order, channel support and
intentional analysis changes separate from model-physics conservation.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import math
from numbers import Real

import numpy as np

H = 6.62607015e-34  # exact SI constants in this illustrative monochromatic law
C = 299792458.0
K_B = 1.380649e-23


def _positive(value: float, label: str) -> float:
    if (isinstance(value, (bool, np.bool_)) or not isinstance(value, Real)
            or not math.isfinite(value) or value <= 0):
        raise ValueError(f"{label} must be finite and positive")
    return float(value)


def _contains_bool(value) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return True
    if isinstance(value, np.ndarray):
        return value.dtype.kind == "b" or (value.dtype.kind == "O"
                                           and any(_contains_bool(x) for x in value.flat))
    if isinstance(value, (list, tuple)):
        return any(_contains_bool(x) for x in value)
    return False


def _array(values, name: str, *, finite: bool = True) -> np.ndarray:
    if np.ma.isMaskedArray(values):
        raise ValueError(f"{name}: masked array needs an explicit support mask")
    if _contains_bool(values):
        raise ValueError(f"{name}: boolean mask cannot become a physical value")
    array = np.asarray(values)
    if array.ndim != 1 or not array.size or array.dtype != np.float64:
        raise ValueError(f"{name}: nonempty float64 vector required")
    if finite and not np.isfinite(array).all():
        raise ValueError(f"{name}: finite values required")
    return array


def planck_radiance(temperature_k: float, wavelength_m: float) -> float:
    """Monochromatic SI spectral radiance [W sr^-1 m^-3]."""
    t = _positive(temperature_k, "temperature")
    wavelength = _positive(wavelength_m, "wavelength")
    exponent = H * C / (wavelength * K_B * t)
    try:
        radiance = (2 * H * C * C / wavelength**5) / math.expm1(exponent)
    except OverflowError as exc:
        raise ValueError("Planck radiance outside binary64 domain") from exc
    return _positive(radiance, "Planck radiance")


def brightness_temperature(radiance: float, wavelength_m: float) -> float:
    l = _positive(radiance, "radiance")
    wavelength = _positive(wavelength_m, "wavelength")
    a = 2 * H * C * C / wavelength**5
    b = H * C / (wavelength * K_B)
    temperature = b / math.log1p(a / l)
    return _positive(temperature, "brightness temperature")


def brightness_slope(radiance: float, wavelength_m: float) -> float:
    """d BT/d monochromatic radiance at the *combined* radiance."""
    l = _positive(radiance, "radiance")
    wavelength = _positive(wavelength_m, "wavelength")
    a = 2 * H * C * C / wavelength**5
    b = H * C / (wavelength * K_B)
    u = math.log1p(a / l)
    slope = b * a / (l * (l + a) * u * u)
    return _positive(slope, "brightness slope")


def _columns(radiances, weights):
    l = _array(radiances, "column radiances")
    w = _array(weights, "column weights")
    if l.shape != w.shape or np.any(l <= 0) or np.any(w < 0):
        raise ValueError("positive radiances and matching nonnegative weights required")
    if not math.isclose(float(w.sum()), 1., rel_tol=0, abs_tol=1e-12):
        raise ValueError("column weights must sum to one")
    return l, w


def mixed_brightness_temperature(radiances, weights, wavelength_m: float) -> float:
    l, w = _columns(radiances, weights)
    combined = float(w @ l)
    return brightness_temperature(combined, wavelength_m)


def mixed_brightness_directional(radiances, weights, radiance_direction,
                                 weight_direction, wavelength_m: float) -> float:
    """Two-sided feasible BT' = Psi'(sum wL)*(sum wL' + sum w'L)."""
    l, w = _columns(radiances, weights)
    dl = _array(radiance_direction, "radiance direction")
    dw = _array(weight_direction, "weight direction")
    if dl.shape != l.shape or dw.shape != w.shape:
        raise ValueError("column direction shapes must match radiance and weights")
    if not math.isclose(float(dw.sum()), 0., rel_tol=0, abs_tol=1e-12):
        raise ValueError("weight direction must retain normalized column sum")
    if np.any((w == 0) & (dw != 0)):
        raise ValueError("two-sided weight direction leaves the simplex at a zero-weight column")
    combined = float(w @ l)
    derivative = brightness_slope(combined, wavelength_m) * float(w @ dl + dw @ l)
    if not math.isfinite(derivative):
        raise ValueError("mixed brightness derivative overflowed")
    return derivative


@dataclass(frozen=True)
class CostResult:
    value: float
    directional: float
    usable_channels: int
    accepted: bool


def _representable_fraction(value: Fraction, label: str) -> float:
    try:
        numeric = float(value)
    except OverflowError as exc:
        raise ValueError(f"{label} exceeds binary64 range") from exc
    if not math.isfinite(numeric) or (value != 0 and numeric == 0):
        raise ValueError(f"{label} is outside binary64 resolution")
    return numeric


def quadratic_cost_on_support(predicted_bt, observed_bt, sigma_k,
                              predicted_direction, keep_mask) -> CostResult:
    """A synthetic quadratic channel cost; empty support is diagnostic only."""
    if np.ma.isMaskedArray(keep_mask):
        raise ValueError("channel support must not itself be masked")
    mask = np.asarray(keep_mask)
    if mask.ndim != 1 or not mask.size or mask.dtype != np.bool_:
        raise ValueError("explicit nonempty boolean channel support required")
    raw = (predicted_bt, observed_bt, sigma_k, predicted_direction)
    arrays = tuple(np.asarray(values, dtype=object) for values in raw)
    if any(a.shape != mask.shape for a in arrays):
        raise ValueError("BT, observation, sigma, direction and support shapes must match")
    if any(np.ma.isMaskedArray(values) and np.ma.getmaskarray(values)[mask].any()
           for values in raw):
        raise ValueError("kept channel cannot be masked")
    if not mask.any():
        return CostResult(0., 0., 0, False)
    # Excluded positions are never numerically converted or tested. They may
    # hold missing sentinels and are not synthetic zero observations.
    selected_raw = tuple(a[mask] for a in arrays)
    if any(_contains_bool(a) for a in selected_raw):
        raise ValueError("kept boolean mask cannot become a physical BT or observation")
    if any(isinstance(value, (complex, np.complexfloating)) or np.ma.is_masked(value)
           for a in selected_raw for value in a.flat):
        raise ValueError("kept complex or masked value cannot become a real observation")
    selected = tuple(np.asarray(a, dtype=np.float64) for a in selected_raw)
    prediction, observation, sigma, direction = selected
    if (any(not np.isfinite(x).all() for x in selected) or np.any(sigma <= 0)):
        raise ValueError("kept channels require finite BT/obs/direction and positive sigma")
    if np.any(prediction <= 0) or np.any(observation <= 0):
        raise ValueError("kept brightness temperatures in kelvin must be positive")
    # Exact rational arithmetic on the selected *stored binary64* values
    # avoids sigma² overflow and cancellation turning a finite cost/JVP into
    # zero. This is a small verification helper, not the production Huber map.
    cost_terms = []
    gradient_terms = []
    for pred, obs, sig, tangent in zip(prediction, observation, sigma, direction):
        delta = Fraction(float(pred)) - Fraction(float(obs))
        scale = Fraction(float(sig))
        cost_terms.append(delta * delta / (2 * scale * scale))
        gradient_terms.append(delta * Fraction(float(tangent)) / (scale * scale))
    value = _representable_fraction(sum(cost_terms, Fraction(0)), "supported cost")
    directional = _representable_fraction(sum(gradient_terms, Fraction(0)),
                                          "supported cost derivative")
    return CostResult(value, directional, int(mask.sum()), True)


def compare_cost_same_support(before_bt, after_bt, observed_bt, sigma_k,
                              mask_before, mask_after) -> float:
    if np.ma.isMaskedArray(mask_before) or np.ma.isMaskedArray(mask_after):
        raise ValueError("support masks cannot themselves be masked")
    before_mask, after_mask = np.asarray(mask_before), np.asarray(mask_after)
    if (before_mask.dtype != np.bool_ or after_mask.dtype != np.bool_
            or before_mask.shape != after_mask.shape
            or not np.array_equal(before_mask, after_mask)):
        raise ValueError("cost change requires identical declared channel support")
    zero = np.zeros(before_mask.shape, dtype=np.float64)
    before = quadratic_cost_on_support(before_bt, observed_bt, sigma_k, zero, before_mask)
    after = quadratic_cost_on_support(after_bt, observed_bt, sigma_k, zero, after_mask)
    if not before.accepted or not after.accepted:
        raise ValueError("empty support cannot approve a cost comparison")
    return after.value - before.value


def analysis_inventory_increment(before, after, physical_measure) -> float:
    """Record intentional analysis quantity change, not a physics-flux residual."""
    first = _array(before, "background state")
    last = _array(after, "analysis state")
    weight = _array(physical_measure, "physical measure")
    if first.shape != last.shape or first.shape != weight.shape:
        raise ValueError("analysis states and physical measures must share shape")
    if np.any(first < 0) or np.any(last < 0) or np.any(weight <= 0):
        raise ValueError("nonnegative states and positive physical measure required")
    terms = [float(w) * float(a - b) for a, b, w in zip(last, first, weight)]
    if not all(math.isfinite(term) for term in terms):
        raise ValueError("analysis increment term overflowed")
    try:
        result = math.fsum(terms)
    except OverflowError as exc:
        raise ValueError("analysis increment sum overflowed") from exc
    if not math.isfinite(result):
        raise ValueError("analysis increment sum overflowed")
    return result
