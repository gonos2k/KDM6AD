from __future__ import annotations

import ctypes
import json
import os
import platform
import shutil
import subprocess
from itertools import product
from pathlib import Path

import numpy as np
import pytest

from harness.analyze_qnc_selected_adaptive_pilot import (
    _axis_tendency, _f32, _rk_update, _word, _writer_word,
    load_v2_inputs,
)
from harness.native_qnc_candidate_face_overlay import receiver_union


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "qnc_live_guard_f32_probe.f90"
C_SOURCE = ROOT / "qnc_rounding_env.c"
PACKET = ROOT / "evidence/native_qnc_candidate_inputs_2026-10-28"
FAILURES = ROOT / "evidence/native_qnc_host_backoff_review_2026-10-28/residual_reason_rows.json"
ADAPTIVE = ROOT / "evidence/native_qnc_selected_adaptive_2026-10-29/analysis.json"
WORDS = (
    "FIELD_OLD", "C1H", "C2H", "MU_OLD", "MU_BASE", "DT", "MSFTX", "MSFTY",
    "RDX", "RDY", "RDZW", "PH_LOW", "FLUX_OUT", "SCALE",
    "FX_LOW_WEST", "FX_LOW_EAST", "FY_LOW_SOUTH", "FY_LOW_NORTH",
    "FZ_LOW_BOTTOM", "FZ_LOW_TOP", "FX_POST_WEST", "FX_POST_EAST",
    "FY_POST_SOUTH", "FY_POST_NORTH", "FZ_POST_BOTTOM", "FZ_POST_TOP",
)


@pytest.fixture(scope="module")
def predictor(tmp_path_factory):
    compiler = shutil.which("gfortran")
    c_compiler = shutil.which("cc")
    if compiler is None or c_compiler is None:
        pytest.skip("Fortran/C compiler is unavailable")
    build = tmp_path_factory.mktemp("qnc_f32_probe")
    shim = build / "qnc_rounding_env.o"
    library_path = build / "libqnc_live_guard_f32_probe.dylib" if platform.system() == "Darwin" \
        else build / "libqnc_live_guard_f32_probe.so"
    env = os.environ.copy()
    if platform.system() == "Darwin":
        sdk_query = subprocess.run(["xcrun", "--show-sdk-path"], check=True,
                                   capture_output=True, text=True)
        env["SDKROOT"] = sdk_query.stdout.strip()
        env["MACOSX_DEPLOYMENT_TARGET"] = "26.7"
    subprocess.run([c_compiler, "-std=c11", "-DQNC_TEST_ROUNDING", "-fPIC", "-c", str(C_SOURCE),
                    "-o", str(shim)], check=True, env=env)
    link = [compiler, "-std=f2008", "-ffp-contract=off", "-fPIC", "-shared",
            "-J", str(build), str(SOURCE), str(shim), "-o", str(library_path)]
    subprocess.run(link, check=True, env=env, cwd=build)
    library = ctypes.CDLL(str(library_path))
    function = library.qnc_live_guard_predict_f32
    function.argtypes = [ctypes.POINTER(ctypes.c_float), ctypes.c_float, ctypes.c_float,
                         ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_int),
                         ctypes.POINTER(ctypes.c_int)]
    function.restype = None
    return function, library


def _input_words(row: dict) -> np.ndarray:
    return np.asarray([int(row[field], 16) for field in WORDS], dtype=np.uint32).view(np.float32)


def _call(function, words: np.ndarray, mu_new: np.float32, source: np.float32):
    word_array = (ctypes.c_float * 26)(*map(float, words))
    predicted = (ctypes.c_int32 * 192)()
    all_positive = ctypes.c_int(0)
    status = ctypes.c_int(0)
    function(word_array, ctypes.c_float(float(mu_new)), ctypes.c_float(float(source)),
             predicted, ctypes.byref(all_positive), ctypes.byref(status))
    return tuple(f"{int(bits) & 0xFFFFFFFF:08X}" for bits in predicted), \
        all_positive.value, status.value


def _all_python_predictions(row: dict, writer: dict,
                            coord: tuple[int, int, int]) -> tuple[str, ...]:
    predictions = []
    for axis_mode in product((False, True), repeat=3):
        advect = _axis_tendency(row, axis_mode)
        for sites in product((False, True), repeat=3):
            for numerator_mode in range(3):
                predictions.append(_word(_rk_update(
                    writer, coord, advect, (*sites, numerator_mode))))
    assert len(predictions) == 8 * 24
    return tuple(predictions)


def _candidate_rows(faces: dict, failure_json: bytes, case: str) -> dict:
    adaptive = json.loads(ADAPTIVE.read_text())
    choices = {
        tuple(row["coord_ikj"]): {"scale_hex": row["candidate_scale_hex"]}
        for row in adaptive["cases"][case]["scale_search"]["choice_rows"]
    }
    assert len(choices) == 54
    from harness.analyze_qnc_selected_adaptive_pilot import _apply_scale_map

    rows, _ = _apply_scale_map(faces, choices)
    assert set(rows) == set(receiver_union(failure_json))
    return rows


@pytest.mark.parametrize("case_index,case", [(0, "control"), (2, "alpha025")])
def test_f32_probe_matches_python_all_192_modes_original_and_candidate(
        predictor, case_index, case):
    function, _ = predictor
    control_faces, control_writer, alpha_faces, alpha_writer, failure_json = \
        load_v2_inputs(PACKET, FAILURES)
    faces = (control_faces, control_writer, alpha_faces, alpha_writer)[case_index]
    writer = (control_faces, control_writer, alpha_faces, alpha_writer)[case_index + 1]
    candidate = _candidate_rows(faces, failure_json, case)
    coords = ((57, 3, 159), (91, 4, 94), (113, 12, 70),
              (137, 15, 100), (195, 11, 131), (214, 14, 181))
    operands = {coord: {field: _f32(_writer_word(writer, coord, "RKSCALAR_BEFORE", field))
                        for field in ("MU_NEW", "SCALAR_TEND")}
                for coord in coords}
    for coord in coords:
        for label, row in (("original", faces["values"][coord]),
                           ("PR476 candidate", candidate[coord])):
            words = _input_words(row)
            assert np.all(np.isfinite(words)), (label, coord)
            assert not np.any(((words.view(np.uint32) & 0x7F800000) == 0) &
                              ((words.view(np.uint32) & 0x007FFFFF) != 0)), (label, coord)
            expected = _all_python_predictions(row, writer, coord)
            observed, all_positive, status = _call(
                function, words, operands[coord]["MU_NEW"], operands[coord]["SCALAR_TEND"])
            assert status == 1, (label, coord)
            assert observed == expected, (label, coord)
            expected_positive = all(_f32(word) > 0 for word in expected)
            assert all_positive == int(expected_positive), (label, coord)


def test_f32_probe_rejects_nonfinite_and_subnormal_inputs(predictor):
    function, _ = predictor
    faces = load_v2_inputs(PACKET, FAILURES)[0]
    writer = load_v2_inputs(PACKET, FAILURES)[1]
    coord = (57, 3, 159)
    row = faces["values"][coord]
    words = _input_words(row)
    mu_new = _f32(_writer_word(writer, coord, "RKSCALAR_BEFORE", "MU_NEW"))
    source = _f32(_writer_word(writer, coord, "RKSCALAR_BEFORE", "SCALAR_TEND"))
    for invalid in (np.float32(np.inf), np.asarray([1], dtype=np.uint32).view(np.float32)[0]):
        bad_words = words.copy()
        bad_words[0] = invalid
        _, all_positive, status = _call(function, bad_words, mu_new, source)
        assert status == 0
        assert all_positive == 0


def test_f32_probe_rejects_downward_rounding(predictor):
    function, library = predictor
    faces, writer = load_v2_inputs(PACKET, FAILURES)[:2]
    coord = (57, 3, 159)
    words = _input_words(faces["values"][coord])
    mu_new = _f32(_writer_word(writer, coord, "RKSCALAR_BEFORE", "MU_NEW"))
    source = _f32(_writer_word(writer, coord, "RKSCALAR_BEFORE", "SCALAR_TEND"))
    assert _call(function, words, mu_new, source)[2] == 1
    mode = ctypes.CDLL(None)
    mode.fegetround.restype = ctypes.c_int
    mode.fesetround.argtypes = [ctypes.c_int]
    mode.fesetround.restype = ctypes.c_int
    library.qnc_rounding_downward_code.restype = ctypes.c_int
    old = mode.fegetround()
    if mode.fesetround(library.qnc_rounding_downward_code()) != 0:
        pytest.skip("downward rounding mode unavailable")
    try:
        assert _call(function, words, mu_new, source)[2] == 0
    finally:
        assert mode.fesetround(old) == 0


def test_f32_probe_rejects_hardware_ftz(predictor):
    function, library = predictor
    faces, writer = load_v2_inputs(PACKET, FAILURES)[:2]
    coord = (57, 3, 159)
    words = _input_words(faces["values"][coord])
    mu_new = _f32(_writer_word(writer, coord, "RKSCALAR_BEFORE", "MU_NEW"))
    source = _f32(_writer_word(writer, coord, "RKSCALAR_BEFORE", "SCALAR_TEND"))
    library.qnc_test_set_ftz.argtypes = [ctypes.c_int]
    library.qnc_test_set_ftz.restype = ctypes.c_int
    old = library.qnc_test_set_ftz(1)
    if old < 0:
        pytest.skip("FTZ control unavailable on this architecture")
    try:
        assert _call(function, words, mu_new, source)[2] == 0
    finally:
        assert library.qnc_test_set_ftz(old) >= 0


def test_f32_probe_rejects_fiz_when_available(predictor):
    function, library = predictor
    faces, writer = load_v2_inputs(PACKET, FAILURES)[:2]
    coord = (113, 12, 70)
    words = _input_words(faces["values"][coord])
    mu_new = _f32(_writer_word(writer, coord, "RKSCALAR_BEFORE", "MU_NEW"))
    source = _f32(_writer_word(writer, coord, "RKSCALAR_BEFORE", "SCALAR_TEND"))
    library.qnc_test_set_fiz.argtypes = [ctypes.c_int]
    library.qnc_test_set_fiz.restype = ctypes.c_int
    old = library.qnc_test_set_fiz(1)
    if old < 0:
        pytest.skip("AArch64 FEAT_AFP FIZ control unavailable")
    try:
        assert _call(function, words, mu_new, source)[2] == 0
    finally:
        assert library.qnc_test_set_fiz(old) >= 0


def test_f32_probe_rejects_arm_alternate_handling_when_available(predictor):
    function, library = predictor
    faces, writer = load_v2_inputs(PACKET, FAILURES)[:2]
    coord = (113, 12, 70)
    words = _input_words(faces["values"][coord])
    mu_new = _f32(_writer_word(writer, coord, "RKSCALAR_BEFORE", "MU_NEW"))
    source = _f32(_writer_word(writer, coord, "RKSCALAR_BEFORE", "SCALAR_TEND"))
    library.qnc_test_set_ah.argtypes = [ctypes.c_int]
    library.qnc_test_set_ah.restype = ctypes.c_int
    old = library.qnc_test_set_ah(1)
    if old < 0:
        pytest.skip("AArch64 FEAT_AFP alternate handling control unavailable")
    try:
        assert _call(function, words, mu_new, source)[2] == 0
    finally:
        assert library.qnc_test_set_ah(old) >= 0
