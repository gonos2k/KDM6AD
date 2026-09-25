from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


_SCRIPT = Path(__file__).resolve().parents[1] / "make_s8_abi_capture.py"
_SPEC = importlib.util.spec_from_file_location("make_s8_abi_capture", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_CAPTURE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_CAPTURE)


def test_capture_shadow_is_strip_exact_and_at_host_abi_boundaries() -> None:
    source = """MODULE module_mp_kdm6ad_cons
  USE kdm6_iso_c, ONLY: KDM6_PHYSICS_CONSERVATIVE_INTERFACE
CONTAINS
  SUBROUTINE kdm6ad_cons
    ARGS%struct_size = INT(c_sizeof(ARGS), c_int32_t)
    ARGS%abi_version = INT(KDM6_ABI_VERSION, c_int32_t)
    ARGS%im = INT(IM, c_int32_t)
    ARGS%kme = INT(KM, c_int32_t)
    ARGS%jme = INT(JM, c_int32_t)
    ARGS%dt = REAL(DELT, c_double)
    ARGS%value_only = 1_c_int32_t
    ARGS%param_grad_flags = 0_c_int32_t
    ARGS%physics_variant = KDM6_PHYSICS_CONSERVATIVE_INTERFACE
    ! ── v2 call: conservative-interface variant, forward-only ───────────────
    RC = kdm6_step_v2_c(ARGS)
    IF (RC /= KDM6_OK) THEN
      CALL wrf_error_fatal('kdm6ad_cons: kdm6_step_v2_c failed')
    END IF
    DO J = JTS, JTE
      TH(I, K, J) = REAL(TH_OUT(II, KK, JJ))
    END DO
    ! Effective radii for radiation — same post-micro diagnostic as the legacy
  END SUBROUTINE kdm6ad_cons
END MODULE module_mp_kdm6ad_cons
"""
    shadow = _CAPTURE.build_shadow(source.encode("utf-8")).decode("utf-8")
    assert _CAPTURE.remove_marked_blocks(shadow) == source
    _CAPTURE.validate_shadow_placement(shadow)

    assert shadow.count("CALL kdm6ad_cons_s8_capture_begin(") == 1
    assert shadow.count("CALL kdm6ad_cons_s8_capture_return(") == 1
    assert shadow.count("CALL kdm6ad_cons_s8_capture_host(") == 1
    assert len(_CAPTURE.INPUT_FIELDS) == 17
    assert len(_CAPTURE.RETURN_FIELDS) == 16
    assert len(_CAPTURE.HOST_FIELDS) == 13

    moved_call = shadow.replace(
        "! S8_CAPTURE_BEGIN_CALL_END\n    RC = kdm6_step_v2_c(ARGS)",
        "! S8_CAPTURE_BEGIN_CALL_END\n    ARGS%dt = 10.0_c_double\n"
        "    RC = kdm6_step_v2_c(ARGS)",
        1,
    )
    with pytest.raises(ValueError, match="immediately precede"):
        _CAPTURE.validate_shadow_placement(moved_call)
