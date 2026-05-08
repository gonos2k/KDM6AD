from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "KIM-meso_v1.0" / "phys" / "module_microphysics_driver.F"
KDM6AD = ROOT / "KIM-meso_v1.0" / "phys" / "module_mp_kdm6ad.F"
KDM6 = ROOT / "KIM-meso_v1.0" / "phys" / "module_mp_kdm6.F"
RUNTIME = ROOT / "kdm6_libtorch" / "src" / "runtime.cpp"
COORDINATOR = ROOT / "kdm6_libtorch" / "include" / "kdm6" / "coordinator.h"
COORDINATOR_IMPL = ROOT / "kdm6_libtorch" / "src" / "coordinator.cpp"
WARM = ROOT / "kdm6_libtorch" / "include" / "kdm6" / "warm.h"
SATADJ = ROOT / "kdm6_libtorch" / "include" / "kdm6" / "satadj.h"

COMMON_DRIVER_ARGS = {
    "TH": "th",
    "Q": "qv_curr",
    "QC": "qc_curr",
    "QR": "qr_curr",
    "QI": "qi_curr",
    "QS": "qs_curr",
    "QG": "qg_curr",
    "NN": "qnn_curr",
    "NC": "qnc_curr",
    "NI": "qni_curr",
    "NR": "qnr_curr",
    "BG": "qib_curr",
    "DEN": "rho",
    "PII": "pi_phy",
    "P": "p",
    "DELZ": "dz8w",
}

KDM6AD_REQUIRED_CONTEXT_ARGS = {
    "XLAND": "xland",
    "ITIMESTEP": "itimestep",
}


def _case_block(driver: str, case_name: str) -> str:
    pattern = rf"CASE \({case_name}\)(.*?)(?=\n\s*CASE \(|\n\s*END SELECT)"
    match = re.search(pattern, driver, flags=re.DOTALL)
    assert match, f"Missing CASE block: {case_name}"
    return match.group(1)


def _call_args(block: str, callee: str) -> dict[str, str]:
    match = re.search(rf"CALL\s+{callee}\s*\((.*?)\n\s*\)", block, flags=re.DOTALL | re.IGNORECASE)
    assert match, f"Missing CALL {callee}"
    args = {}
    for key, value in re.findall(r",?\s*([A-Za-z0-9_]+)\s*=\s*([A-Za-z0-9_]+)", match.group(1)):
        args[key.upper()] = value.lower()
    return args


def test_driver_maps_common_kdm6_state_fields_identically_for_37_and_137():
    driver = DRIVER.read_text()
    kdm6_args = _call_args(_case_block(driver, "KDM6SCHEME"), "kdm6")
    kdm6ad_args = _call_args(_case_block(driver, "KDM6ADSCHEME"), "kdm6ad")

    for arg, expected in COMMON_DRIVER_ARGS.items():
        assert kdm6_args[arg] == expected
        assert kdm6ad_args[arg] == expected


def test_kdm6ad_driver_passes_context_needed_to_match_kdm6_initialization():
    driver = DRIVER.read_text()
    kdm6ad_args = _call_args(_case_block(driver, "KDM6ADSCHEME"), "kdm6ad")

    for arg, expected in KDM6AD_REQUIRED_CONTEXT_ARGS.items():
        assert kdm6ad_args[arg] == expected




















def test_warm_phase_outputs_include_nccn_and_temperature_coupling_terms():
    coordinator = COORDINATOR.read_text().lower()
    coordinator_impl = COORDINATOR_IMPL.read_text().lower()

    for field in (
        "rain_complete_evap",
        "cloud_complete_evap",
        "ncact",
        "pcact",
    ):
        assert f"torch::tensor {field}" in coordinator
        assert f"/*{field}=*/" in coordinator_impl
