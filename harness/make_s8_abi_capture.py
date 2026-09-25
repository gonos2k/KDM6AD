#!/usr/bin/env python3
"""Create a marked, runtime-gated capture shadow of the private mp337 wrapper.

The generated source is for a temporary host copy. Removing the four marked
blocks must reproduce the approved source byte-for-byte before it is compiled.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


EXPECTED_SOURCE_SHA256 = "940adce388dff58495710349a62a79dcc66506f3017cc089756d8f3992b7e9bb"
STATE_FIELDS = ("TH", "Q", "QC", "QR", "QI", "QS", "QG", "NN", "NC", "NI", "NR", "BG")
FORCING_FIELDS = ("DEN", "PII", "P", "DELZ")
INPUT_FIELDS = tuple(name + "_IN" for name in STATE_FIELDS + FORCING_FIELDS) + ("XLAND_IN",)
RETURN_FIELDS = tuple(name + "_OUT" for name in STATE_FIELDS) + (
    "RAIN_INC", "SNOW_INC", "GRAUPEL_INC", "RHOG_OUT"
)
HOST_FIELDS = ("TH", "Q", "QC", "QR", "QI", "QS", "QG", "NN", "NC", "NI", "NR", "BG", "DIAG_RHOG")

BEGIN_CALL = """    ! S8_CAPTURE_BEGIN_CALL_START
    CALL kdm6ad_cons_s8_capture_begin(ARGS, HANDLE, TH_IN, Q_IN, QC_IN, QR_IN, &
         QI_IN, QS_IN, QG_IN, NN_IN, NC_IN, NI_IN, NR_IN, BG_IN, DEN_IN, PII_IN, &
         P_IN, DELZ_IN, XLAND_IN)
    ! S8_CAPTURE_BEGIN_CALL_END
"""

RETURN_CALL = """    ! S8_CAPTURE_RETURN_CALL_START
    CALL kdm6ad_cons_s8_capture_return(ARGS, HANDLE, RC, TH_OUT, Q_OUT, QC_OUT, &
         QR_OUT, QI_OUT, QS_OUT, QG_OUT, NN_OUT, NC_OUT, NI_OUT, NR_OUT, BG_OUT, &
         RAIN_INC, SNOW_INC, GRAUPEL_INC, RHOG_OUT)
    ! S8_CAPTURE_RETURN_CALL_END
"""

HOST_CALL = """    ! S8_CAPTURE_HOST_CALL_START
    CALL kdm6ad_cons_s8_capture_host(TH(ITS:ITE,KTS:KTE,JTS:JTE), &
         Q(ITS:ITE,KTS:KTE,JTS:JTE), QC(ITS:ITE,KTS:KTE,JTS:JTE), &
         QR(ITS:ITE,KTS:KTE,JTS:JTE), QI(ITS:ITE,KTS:KTE,JTS:JTE), &
         QS(ITS:ITE,KTS:KTE,JTS:JTE), QG(ITS:ITE,KTS:KTE,JTS:JTE), &
         NN(ITS:ITE,KTS:KTE,JTS:JTE), NC(ITS:ITE,KTS:KTE,JTS:JTE), &
         NI(ITS:ITE,KTS:KTE,JTS:JTE), NR(ITS:ITE,KTS:KTE,JTS:JTE), &
         BG(ITS:ITE,KTS:KTE,JTS:JTE), &
         DIAG_RHOG(ITS:ITE,KTS:KTE,JTS:JTE))
    ! S8_CAPTURE_HOST_CALL_END
"""

HELPERS = r"""! S8_CAPTURE_HELPERS_START
  SUBROUTINE kdm6ad_cons_s8_capture_open(unit, replace_file, enabled)
    USE, INTRINSIC :: iso_c_binding, ONLY: c_int
    INTEGER, INTENT(OUT) :: unit
    LOGICAL, INTENT(IN) :: replace_file
    LOGICAL, INTENT(OUT) :: enabled
    CHARACTER(LEN=1024) :: path
    INTEGER :: env_status, env_length, io_status

    path = ''
    CALL GET_ENVIRONMENT_VARIABLE('KDM6_S8_ABI_CAPTURE_LOG', path, &
                                  LENGTH=env_length, STATUS=env_status)
    enabled = env_status == 0 .AND. env_length > 0
    IF (.NOT. enabled) RETURN
    IF (replace_file) THEN
      OPEN(NEWUNIT=unit, FILE=TRIM(path), FORM='UNFORMATTED', ACCESS='STREAM', &
           STATUS='REPLACE', ACTION='WRITE', IOSTAT=io_status)
    ELSE
      OPEN(NEWUNIT=unit, FILE=TRIM(path), FORM='UNFORMATTED', ACCESS='STREAM', &
           STATUS='OLD', POSITION='APPEND', ACTION='WRITE', IOSTAT=io_status)
    END IF
    IF (io_status /= 0) CALL wrf_error_fatal('S8 ABI capture file open failed')
  END SUBROUTINE kdm6ad_cons_s8_capture_open

  SUBROUTINE kdm6ad_cons_s8_capture_begin(args, handle, th, q, qc, qr, qi, qs, qg, &
      nn, nc, ni, nr, bg, den, pii, p, delz, xland)
    USE, INTRINSIC :: iso_c_binding, ONLY: c_associated, c_int, c_int32_t, c_float, c_double, c_ptr
    TYPE(kdm6_step_v2_args), INTENT(IN) :: args
    TYPE(c_ptr), INTENT(IN) :: handle
    REAL(c_float), INTENT(IN) :: th(:,:,:), q(:,:,:), qc(:,:,:), qr(:,:,:)
    REAL(c_float), INTENT(IN) :: qi(:,:,:), qs(:,:,:), qg(:,:,:)
    REAL(c_float), INTENT(IN) :: nn(:,:,:), nc(:,:,:), ni(:,:,:), nr(:,:,:), bg(:,:,:)
    REAL(c_float), INTENT(IN) :: den(:,:,:), pii(:,:,:), p(:,:,:), delz(:,:,:)
    REAL(c_float), INTENT(IN) :: xland(:,:)
    INTEGER :: unit
    LOGICAL :: enabled

    CALL kdm6ad_cons_s8_capture_open(unit, .TRUE., enabled)
    IF (.NOT. enabled) RETURN
    WRITE(unit) 'S8BGIN01'
    WRITE(unit) args%struct_size, args%abi_version, args%im, args%kme, args%jme, &
                args%value_only, args%param_grad_flags, args%physics_variant
    WRITE(unit) args%dt, args%ncmin_land, args%ncmin_sea
    WRITE(unit) MERGE(1_c_int, 0_c_int, C_ASSOCIATED(handle))
    WRITE(unit) th, q, qc, qr, qi, qs, qg, nn, nc, ni, nr, bg, den, pii, p, delz, xland
    CLOSE(unit)
  END SUBROUTINE kdm6ad_cons_s8_capture_begin

  SUBROUTINE kdm6ad_cons_s8_capture_return(args, handle, rc, th, q, qc, qr, qi, qs, qg, &
      nn, nc, ni, nr, bg, rain, snow, graupel, rhog)
    USE, INTRINSIC :: iso_c_binding, ONLY: c_associated, c_int, c_float, c_ptr
    TYPE(kdm6_step_v2_args), INTENT(IN) :: args
    TYPE(c_ptr), INTENT(IN) :: handle
    INTEGER(c_int), INTENT(IN) :: rc
    REAL(c_float), INTENT(IN) :: th(:,:,:), q(:,:,:), qc(:,:,:), qr(:,:,:)
    REAL(c_float), INTENT(IN) :: qi(:,:,:), qs(:,:,:), qg(:,:,:)
    REAL(c_float), INTENT(IN) :: nn(:,:,:), nc(:,:,:), ni(:,:,:), nr(:,:,:), bg(:,:,:)
    REAL(c_float), INTENT(IN) :: rain(:,:), snow(:,:), graupel(:,:), rhog(:,:,:)
    INTEGER :: unit
    LOGICAL :: enabled

    CALL kdm6ad_cons_s8_capture_open(unit, .FALSE., enabled)
    IF (.NOT. enabled) RETURN
    WRITE(unit) 'S8RETN01'
    WRITE(unit) rc, MERGE(1_c_int, 0_c_int, C_ASSOCIATED(handle))
    WRITE(unit) th, q, qc, qr, qi, qs, qg, nn, nc, ni, nr, bg, rain, snow, graupel, rhog
    CLOSE(unit)
  END SUBROUTINE kdm6ad_cons_s8_capture_return

  SUBROUTINE kdm6ad_cons_s8_capture_host(th, q, qc, qr, qi, qs, qg, nn, nc, ni, nr, bg, rhog)
    REAL, INTENT(IN) :: th(:,:,:), q(:,:,:), qc(:,:,:), qr(:,:,:), qi(:,:,:)
    REAL, INTENT(IN) :: qs(:,:,:), qg(:,:,:), nn(:,:,:), nc(:,:,:), ni(:,:,:), nr(:,:,:), bg(:,:,:)
    REAL, INTENT(IN) :: rhog(:,:,:)
    INTEGER :: unit
    LOGICAL :: enabled

    CALL kdm6ad_cons_s8_capture_open(unit, .FALSE., enabled)
    IF (.NOT. enabled) RETURN
    WRITE(unit) 'S8HOST01'
    WRITE(unit) STORAGE_SIZE(th(1,1,1)) / 8
    WRITE(unit) th, q, qc, qr, qi, qs, qg, nn, nc, ni, nr, bg, rhog
    CLOSE(unit)
  END SUBROUTINE kdm6ad_cons_s8_capture_host
! S8_CAPTURE_HELPERS_END
"""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def remove_marked_blocks(text: str) -> str:
    starts = ["S8_CAPTURE_BEGIN_CALL_START", "S8_CAPTURE_RETURN_CALL_START",
              "S8_CAPTURE_HOST_CALL_START", "S8_CAPTURE_HELPERS_START"]
    ends = ["S8_CAPTURE_BEGIN_CALL_END", "S8_CAPTURE_RETURN_CALL_END",
            "S8_CAPTURE_HOST_CALL_END", "S8_CAPTURE_HELPERS_END"]
    for index in range(len(starts)):
        start_marker, end_marker = starts[index], ends[index]
        start = text.find(start_marker)
        end = text.find(end_marker)
        if start < 0 or end < start or text.find(start_marker, start + 1) >= 0:
            raise ValueError(f"missing or duplicated capture marker {start_marker}")
        end = text.find("\n", end)
        if end < 0:
            end = len(text)
        else:
            end += 1
        line_start = text.rfind("\n", 0, start) + 1
        text = text[:line_start] + text[end:]
    return text


def inject_once(text: str, anchor: str, addition: str, label: str) -> str:
    count = text.count(anchor)
    if count != 1:
        raise ValueError(f"expected one {label} anchor; found {count}")
    return text.replace(anchor, addition + anchor, 1)


def validate_shadow_placement(text: str) -> None:
    entry = text.index("CALL kdm6ad_cons_s8_capture_begin(")
    args_ready = text.index("ARGS%physics_variant = KDM6_PHYSICS_CONSERVATIVE_INTERFACE")
    c_call = text.index("RC = kdm6_step_v2_c(ARGS)")
    returned = text.index("CALL kdm6ad_cons_s8_capture_return(")
    rc_guard = text.index("IF (RC /= KDM6_OK) THEN", c_call)
    host_copy = text.index("TH(I, K, J) = REAL(TH_OUT(II, KK, JJ))")
    host_capture = text.index("CALL kdm6ad_cons_s8_capture_host(")
    diagnostics = text.index("! Effective radii for radiation", host_copy)
    if not args_ready < entry < c_call < returned < rc_guard < host_copy < host_capture < diagnostics:
        raise ValueError("capture calls are not placed at the ABI entry/return/copy-back boundaries")
    begin_end = text.index("! S8_CAPTURE_BEGIN_CALL_END", entry) + len(
        "! S8_CAPTURE_BEGIN_CALL_END"
    )
    if text[begin_end:c_call].strip():
        raise ValueError("entry capture must immediately precede the v2 C ABI call")
    expected_calls = (
        ("kdm6ad_cons_s8_capture_begin", ("ARGS", "HANDLE") + INPUT_FIELDS),
        ("kdm6ad_cons_s8_capture_return", ("ARGS", "HANDLE", "RC") + RETURN_FIELDS),
        ("kdm6ad_cons_s8_capture_host", HOST_FIELDS),
    )
    for name, fields in expected_calls:
        call = text[text.index("CALL " + name + "("):text.index("! S8_CAPTURE_", text.index("CALL " + name + "("))]
        for field in fields:
            if field not in call:
                raise ValueError(f"{name} omits expected field {field}")
        if text.count("CALL " + name + "(") != 1:
            raise ValueError(f"expected exactly one {name} call")


def build_shadow(source: bytes) -> bytes:
    text = source.decode("utf-8")
    call_anchor = "    RC = kdm6_step_v2_c(ARGS)\n"
    text = inject_once(text, call_anchor, BEGIN_CALL, "v2 ABI entry")
    if text.count(call_anchor) != 1:
        raise ValueError("expected one C ABI return anchor")
    text = text.replace(call_anchor, call_anchor + RETURN_CALL, 1)
    text = inject_once(
        text,
        "    ! Effective radii for radiation — same post-micro diagnostic as the legacy\n",
        HOST_CALL,
        "host copy-back",
    )
    end_module = "END MODULE module_mp_kdm6ad_cons"
    if text.count(end_module) != 1:
        raise ValueError("expected one module end anchor")
    text = text.replace(end_module, HELPERS + end_module, 1)
    validate_shadow_placement(text)
    return text.encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--expected-source-sha256", default=EXPECTED_SOURCE_SHA256)
    args = parser.parse_args()
    original = args.source.read_bytes()
    actual_hash = sha256(original)
    if actual_hash != args.expected_source_sha256:
        raise SystemExit(f"source SHA-256 mismatch: {actual_hash}")
    shadow = build_shadow(original)
    stripped = remove_marked_blocks(shadow.decode("utf-8")).encode("utf-8")
    if stripped != original:
        raise SystemExit("capture block removal did not recover exact source bytes")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(shadow)
    print(json.dumps({
        "source": str(args.source),
        "source_sha256": actual_hash,
        "capture_source": str(args.output),
        "capture_source_sha256": sha256(shadow),
        "stripped_source_sha256": sha256(stripped),
        "stripped_byte_exact": True,
    }, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
