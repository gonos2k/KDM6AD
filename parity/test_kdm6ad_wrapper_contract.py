from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "KIM-meso_v1.0" / "phys" / "module_mp_kdm6ad.F"
C_BRIDGE = ROOT / "kdm6_libtorch" / "bridge" / "kdm6_c_api.cpp"

STATE_FIELDS = ("TH", "Q", "QC", "QR", "QI", "QS", "QG", "NN", "NC", "NI", "NR", "BG")


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", text.upper())


def test_kdm6ad_wrapper_uses_value_only_c_abi_call():
    wrapper = _compact(WRAPPER.read_text())

    assert "0_C_INT, 1_C_INT" in wrapper
    assert "RC = KDM6_STEP(" in wrapper
    assert "RC = KDM6_HANDLE_CLOSE(HANDLE)" in wrapper


def test_kdm6ad_wrapper_copies_all_state_fields_back():
    wrapper = WRAPPER.read_text().upper()

    for field in STATE_FIELDS:
        assert f"{field}_IN" in wrapper
        assert f"{field}_OUT" in wrapper

    for field in STATE_FIELDS:
        target = "Q" if field == "Q" else field
        assert re.search(rf"\b{target}\(I, K, J\)\s*=\s*REAL\({field}_OUT\(II, KK, JJ\)\)", wrapper)


def test_c_bridge_value_only_returns_null_handle():
    bridge = _compact(C_BRIDGE.read_text())

    assert "IF (VALUE_ONLY != 0) { *HANDLE = NULLPTR; }" in bridge
    assert "KDM6::KDM6_STEP(STATE_IN, FORCING, PARAMS, DT, VALUE_ONLY != 0)" in bridge
