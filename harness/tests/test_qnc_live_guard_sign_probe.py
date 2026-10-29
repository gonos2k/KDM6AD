"""Compile the numerical sign certificate and compare saved f32 inputs to exact fractions."""
from __future__ import annotations

import ctypes
from fractions import Fraction
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
import pytest

from harness.analyze_qnc_candidate_inputs import read_faces, read_writer
from harness.analyze_qnc_domain_preflight import FIELDS, _writer_f32
from harness.analyze_qnc_selected_adaptive_pilot import _apply_scale_map
from harness.native_qnc_candidate_face_overlay import receiver_union
from harness.native_qnc_domain_preflight_advect_overlay import failure_layer_coordinates


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence"
SOURCE = ROOT / "qnc_live_guard_sign_probe.f90"
C_SOURCE = ROOT / "qnc_rounding_env.c"
ROWS = (EVIDENCE / "native_qnc_host_backoff_review_2026-10-28"
        / "residual_reason_rows.json").read_bytes()
DONORS = failure_layer_coordinates(ROWS)
CAPTURE = receiver_union(ROWS)


@pytest.fixture(scope="module")
def certificate(tmp_path_factory):
    compiler = shutil.which("gfortran")
    c_compiler = shutil.which("cc")
    if compiler is None or c_compiler is None:
        pytest.skip("Fortran/C compiler unavailable for the sign certificate")
    directory = tmp_path_factory.mktemp("qnc-sign")
    library = directory / ("libqnc_sign_probe.dylib" if sys.platform == "darwin" else
                           "libqnc_sign_probe.so")
    shim = directory / "qnc_rounding_env.o"
    command = [compiler, "-shared", "-fPIC", "-O2", "-ffp-contract=off",
               "-J", str(directory), str(SOURCE), str(shim), "-o", str(library)]
    env = os.environ.copy()
    sdk = Path("/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk")
    if sys.platform == "darwin" and sdk.is_dir():
        env["SDKROOT"] = str(sdk)
        env["MACOSX_DEPLOYMENT_TARGET"] = "26.7"
    compile_c = subprocess.run([c_compiler, "-std=c11", "-DQNC_TEST_ROUNDING", "-fPIC", "-c",
                                str(C_SOURCE), "-o", str(shim)],
                               capture_output=True, text=True, env=env, check=False)
    if compile_c.returncode:
        pytest.fail(f"C rounding shim build failed: {compile_c.stderr[-700:]}")
    result = subprocess.run(command, capture_output=True, text=True, env=env, check=False)
    if result.returncode:
        pytest.fail(f"gfortran sign helper build failed: {result.stderr[-700:]}")
    loaded = ctypes.CDLL(str(library))
    method = loaded.qnc_sign_certificate_f32
    method.argtypes = [
        np.ctypeslib.ndpointer(dtype=np.float32, ndim=1, flags="C_CONTIGUOUS"),
        ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_int),
    ]
    method.restype = None
    return method, loaded


def _call(method, row, mu_new_word: str, source_word: str):
    words = np.array([int(row[name], 16) for name in FIELDS], dtype=np.uint32).view(np.float32).copy()
    mu = ctypes.c_float(np.array([int(mu_new_word, 16)], dtype=np.uint32).view(np.float32)[0])
    src = ctypes.c_float(np.array([int(source_word, 16)], dtype=np.uint32).view(np.float32)[0])
    residual, bound, verdict = ctypes.c_double(), ctypes.c_double(), ctypes.c_int()
    method(words, ctypes.byref(mu), ctypes.byref(src), ctypes.byref(residual),
           ctypes.byref(bound), ctypes.byref(verdict))
    return verdict.value, Fraction.from_float(residual.value), Fraction.from_float(bound.value)


def test_certificate_matches_all_selected_original_and_candidate_exact_signs(certificate):
    method, _ = certificate
    published = json.loads((EVIDENCE / "native_qnc_selected_adaptive_2026-10-29"
                            / "analysis.json").read_text())
    minimum_margin = None
    count = 0
    for case in ("control", "alpha025"):
        directory = EVIDENCE / "native_qnc_candidate_inputs_2026-10-28/data" / case
        faces = read_faces(directory / "faces.tsv", CAPTURE)
        writer = read_writer(directory / "rk_writer.tsv")
        choices = {tuple(item["coord_ikj"]): {"scale_hex": item["candidate_scale_hex"]}
                   for item in published["cases"][case]["scale_search"]["choice_rows"]}
        candidate, _ = _apply_scale_map(faces, choices)
        for label, rows in (("baseline", faces["values"]),
                            ("case_specific_candidate", candidate)):
            for coord in DONORS:
                key = f"i{coord[0]}_j{coord[2]}_k{coord[1]}"
                exact = Fraction(published["cases"][case][label]["cells"][key][
                    "exact_residual"]["exact"])
                verdict, residual, bound = _call(
                    method, rows[coord],
                    _writer_f32(writer, coord, "RKSCALAR_BEFORE", "MU_NEW"),
                    _writer_f32(writer, coord, "RKSCALAR_BEFORE", "SCALAR_TEND"),
                )
                assert verdict == (1 if exact > 0 else -1 if exact < 0 else 0)
                assert abs(residual - exact) <= bound
                assert abs(residual) > bound
                ratio = abs(exact) / bound
                minimum_margin = ratio if minimum_margin is None else min(minimum_margin, ratio)
                count += 1
    assert count == 216
    assert minimum_margin > 500


def test_certificate_fails_closed_for_nonfinite_or_unusable_mass(certificate):
    method, _ = certificate
    row = {name: "3F800000" for name in FIELDS}
    row["RDZW"] = "C2A08E87"
    row["MSFTX"] = "7F800000"
    assert _call(method, row, "3F800000", "00000000")[0] == 0
    row["MSFTX"] = "00000000"
    assert _call(method, row, "3F800000", "00000000")[0] == 0
    row["MSFTX"] = "3F800000"
    row["FIELD_OLD"] = "00000001"  # Raw f32 subnormal is refused under an unknown FTZ mode.
    assert _call(method, row, "3F800000", "00000000")[0] == 0


def test_certificate_rejects_exact_zero_and_downward_rounding(certificate):
    method, library = certificate
    row = {name: "00000000" for name in FIELDS}
    for name in ("C1H", "MU_BASE", "DT", "MSFTX", "MSFTY", "RDX", "RDY"):
        row[name] = "3F800000"
    row["RDZW"] = "BF800000"
    assert _call(method, row, "3F800000", "00000000")[0] == 0
    directory = EVIDENCE / "native_qnc_candidate_inputs_2026-10-28/data/alpha025"
    faces = read_faces(directory / "faces.tsv", CAPTURE)
    writer = read_writer(directory / "rk_writer.tsv")
    coord = (113, 12, 70)
    real_row = faces["values"][coord]
    mu_new = _writer_f32(writer, coord, "RKSCALAR_BEFORE", "MU_NEW")
    source = _writer_f32(writer, coord, "RKSCALAR_BEFORE", "SCALAR_TEND")
    assert _call(method, real_row, mu_new, source)[0] == -1
    mode = ctypes.CDLL(None)
    mode.fegetround.restype = ctypes.c_int
    mode.fesetround.argtypes = [ctypes.c_int]
    mode.fesetround.restype = ctypes.c_int
    library.qnc_rounding_downward_code.restype = ctypes.c_int
    old = mode.fegetround()
    downward = library.qnc_rounding_downward_code()
    if mode.fesetround(downward) != 0:
        pytest.skip("downward rounding mode unavailable")
    try:
        assert _call(method, real_row, mu_new, source)[0] == 0
    finally:
        assert mode.fesetround(old) == 0


def test_certificate_rejects_hardware_ftz(certificate):
    method, library = certificate
    directory = EVIDENCE / "native_qnc_candidate_inputs_2026-10-28/data/alpha025"
    faces = read_faces(directory / "faces.tsv", CAPTURE)
    writer = read_writer(directory / "rk_writer.tsv")
    coord = (113, 12, 70)
    row = faces["values"][coord]
    mu_new = _writer_f32(writer, coord, "RKSCALAR_BEFORE", "MU_NEW")
    source = _writer_f32(writer, coord, "RKSCALAR_BEFORE", "SCALAR_TEND")
    library.qnc_test_set_ftz.argtypes = [ctypes.c_int]
    library.qnc_test_set_ftz.restype = ctypes.c_int
    old = library.qnc_test_set_ftz(1)
    if old < 0:
        pytest.skip("FTZ control unavailable on this architecture")
    try:
        assert _call(method, row, mu_new, source)[0] == 0
    finally:
        assert library.qnc_test_set_ftz(old) >= 0


def test_certificate_rejects_fiz_when_available(certificate):
    method, library = certificate
    directory = EVIDENCE / "native_qnc_candidate_inputs_2026-10-28/data/alpha025"
    faces = read_faces(directory / "faces.tsv", CAPTURE)
    writer = read_writer(directory / "rk_writer.tsv")
    coord = (113, 12, 70)
    row = faces["values"][coord]
    mu_new = _writer_f32(writer, coord, "RKSCALAR_BEFORE", "MU_NEW")
    source = _writer_f32(writer, coord, "RKSCALAR_BEFORE", "SCALAR_TEND")
    library.qnc_test_set_fiz.argtypes = [ctypes.c_int]
    library.qnc_test_set_fiz.restype = ctypes.c_int
    old = library.qnc_test_set_fiz(1)
    if old < 0:
        pytest.skip("AArch64 FEAT_AFP FIZ control unavailable")
    try:
        assert _call(method, row, mu_new, source)[0] == 0
    finally:
        assert library.qnc_test_set_fiz(old) >= 0


def test_certificate_rejects_arm_alternate_handling_when_available(certificate):
    method, library = certificate
    directory = EVIDENCE / "native_qnc_candidate_inputs_2026-10-28/data/alpha025"
    faces = read_faces(directory / "faces.tsv", CAPTURE)
    writer = read_writer(directory / "rk_writer.tsv")
    coord = (113, 12, 70)
    row = faces["values"][coord]
    mu_new = _writer_f32(writer, coord, "RKSCALAR_BEFORE", "MU_NEW")
    source = _writer_f32(writer, coord, "RKSCALAR_BEFORE", "SCALAR_TEND")
    library.qnc_test_set_ah.argtypes = [ctypes.c_int]
    library.qnc_test_set_ah.restype = ctypes.c_int
    old = library.qnc_test_set_ah(1)
    if old < 0:
        pytest.skip("AArch64 FEAT_AFP alternate handling control unavailable")
    try:
        assert _call(method, row, mu_new, source)[0] == 0
    finally:
        assert library.qnc_test_set_ah(old) >= 0
