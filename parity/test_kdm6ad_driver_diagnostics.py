from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "KIM-meso_v1.0" / "phys" / "module_microphysics_driver.F"


def _case_body(text: str, case_name: str) -> str:
    match = re.search(rf"CASE \({case_name}\)(.*?)(?=\n\s*CASE \()", text, re.S)
    assert match, f"missing {case_name} case"
    return match.group(1)


def _actual_arguments(call_body: str) -> set[str]:
    return set(re.findall(r",\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", call_body))


def test_kdm6ad_direct_parity_block_is_not_in_production_driver():
    driver = DRIVER.read_text()

    assert "KDM6AD_DIRECT_PARITY_TEMP" not in driver
    assert "CALL report_kdm6ad_direct_parity" not in driver


def test_kdm6ad_driver_preserves_kdm6_host_coupling_arguments():
    driver = DRIVER.read_text()
    kdm6_case = _case_body(driver, "KDM6SCHEME")
    kdm6ad_case = _case_body(driver, "KDM6ADSCHEME")

    kdm6_args = _actual_arguments(kdm6_case)
    kdm6ad_args = _actual_arguments(kdm6ad_case)

    required = {
        "diag_rhog",
        "G", "CPD", "CPV", "CCN0", "RD", "RV", "T0C", "EP1", "EP2", "QMIN",
        "XLS", "XLV0", "XLF0", "DEN0", "DENR", "scale_h", "ncmin_land", "ncmin_sea",
        "CLIQ", "CICE", "PSAT", "RAIN", "RAINNCV", "SNOW", "SNOWNCV", "SR",
        "REFL_10CM", "diagflag", "do_radar_ref", "GRAUPEL", "GRAUPELNCV",
        "has_reqc", "has_reqi", "has_reqs", "re_cloud", "re_ice", "re_snow",
    }

    assert required <= kdm6_args
    assert required <= kdm6ad_args
