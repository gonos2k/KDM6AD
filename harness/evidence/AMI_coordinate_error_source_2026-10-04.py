"""Replay local BT-coordinate ratios; estimate or assign no observation covariance."""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'harness/evidence'
SOURCE = EVIDENCE / 'AMI_bt_coordinate_source_2026-10-04.py'
RESULT = EVIDENCE / 'AMI_bt_coordinate_result_2026-10-04.json'
CAL = ROOT / 'oracle/kdm6/obs/data/gk2a_ami_cal_202507190000.json'
spec = importlib.util.spec_from_file_location('coordinate_math', SOURCE)
math = importlib.util.module_from_spec(spec)
spec.loader.exec_module(math)
data = json.loads(RESULT.read_text())
calibration = json.loads(CAL.read_text())['channels']
rows = {}
for channel in data['scope']['channels']:
    obs = data['observed_channel_transform_and_window_statistics'][channel]
    rttov = {'wavenumber_cm1': obs['pinned_rttov_wavenumber_cm1'],
             'offset_K': obs['pinned_rttov_band_offset_K'],
             'slope': obs['pinned_rttov_band_slope']}
    radiance = obs['slots']['202507190000']['raw_radiance_window'][1][1]
    coeff = calibration[channel]
    derivative = float(math.ami_phi_prime(radiance, coeff, coeff['bt_wavenumber_cm1'])
                       / math.rttov_psi_prime(radiance, rttov))
    residual = data['model_base_plus_minus_radiance_bt_and_residuals'][channel][
        'model_minus_202507190000_observation_residual_K']
    exact = residual['kma_v3_0_source_paired_coordinate']
    linear = derivative * residual['pinned_rttov_coordinate']
    rows[channel] = {
        'at_observation_center_dphi_dpsi': derivative,
        'local_variance_coordinate_ratio': derivative * derivative,
        'exact_common_coordinate_residual_K': exact,
        'locally_rescaled_rttov_residual_K': linear,
        'finite_residual_linearization_difference_K': exact - linear,
        'is_calibrated_observation_variance': False,
    }
result = {
    'scope': 'deterministic local coordinate ratios from retained data; no covariance estimated or assigned',
    'channels': rows,
    'base_R_approved': False,
    'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in (Path(__file__), SOURCE, RESULT, CAL)},
}
print(json.dumps(result, indent=2))
