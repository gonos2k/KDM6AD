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

from harness.analyze_qnc_candidate_inputs import read_faces, read_writer
from harness.analyze_qnc_selected_adaptive_pilot import (
    DEFAULT_MAX_ULP, _apply_scale_map, _f32, _find_first_pass, _writer_word,
)
from harness.native_qnc_candidate_face_overlay import receiver_union
from harness.native_qnc_domain_preflight_advect_overlay import failure_layer_coordinates


ROOT = Path(__file__).resolve().parents[1]
TILE_SOURCE = ROOT / "qnc_live_guard_tile.f90"
SIGN_SOURCE = ROOT / "qnc_live_guard_sign_probe.f90"
PREDICT_SOURCE = ROOT / "qnc_live_guard_f32_probe.f90"
ROUNDING_SOURCE = ROOT / "qnc_rounding_env.c"
PACKET = ROOT / "evidence/native_qnc_candidate_inputs_2026-10-28"
FAILURES = ROOT / "evidence/native_qnc_host_backoff_review_2026-10-28/residual_reason_rows.json"
FIELDS = (
    "FIELD_OLD", "C1H", "C2H", "MU_OLD", "MU_BASE", "DT", "MSFTX", "MSFTY",
    "RDX", "RDY", "RDZW", "PH_LOW", "FLUX_OUT", "SCALE",
    "FX_LOW_WEST", "FX_LOW_EAST", "FY_LOW_SOUTH", "FY_LOW_NORTH",
    "FZ_LOW_BOTTOM", "FZ_LOW_TOP", "FX_POST_WEST", "FX_POST_EAST",
    "FY_POST_SOUTH", "FY_POST_NORTH", "FZ_POST_BOTTOM", "FZ_POST_TOP",
)
PRE_FIELDS = ("FX_PRE_WEST", "FX_PRE_EAST", "FY_PRE_SOUTH", "FY_PRE_NORTH",
              "FZ_PRE_BOTTOM", "FZ_PRE_TOP")


@pytest.fixture(scope="module")
def tile_module(tmp_path_factory):
    fc = shutil.which("gfortran")
    cc = shutil.which("cc")
    if fc is None or cc is None:
        pytest.skip("gfortran/cc unavailable for QNC live tile fixture")
    build = tmp_path_factory.mktemp("qnc-live-tile")
    shim = build / "qnc_rounding_env.o"
    library_path = build / ("libqnc_live_guard_tile.dylib" if platform.system() == "Darwin"
                            else "libqnc_live_guard_tile.so")
    env = os.environ.copy()
    if platform.system() == "Darwin":
        sdk = subprocess.run(["xcrun", "--show-sdk-path"], check=True,
                             capture_output=True, text=True).stdout.strip()
        env["SDKROOT"] = sdk
        env["MACOSX_DEPLOYMENT_TARGET"] = "26.7"
    subprocess.run([cc, "-std=c11", "-DQNC_TEST_ROUNDING", "-fPIC", "-c",
                    str(ROUNDING_SOURCE), "-o", str(shim)], check=True, env=env)
    cmd = [fc, "-std=f2008", "-O2", "-ffp-contract=off", "-fPIC", "-shared",
           "-J", str(build), str(SIGN_SOURCE), str(PREDICT_SOURCE), str(TILE_SOURCE),
           str(shim), "-o", str(library_path)]
    subprocess.run(cmd, check=True, cwd=build, env=env)
    library = ctypes.CDLL(str(library_path))

    coord = library.qnc_live_guard_target_coord
    coord.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_int),
                      ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
    coord.restype = None

    apply_compact = library.qnc_live_guard_apply_compact
    f32_2d = np.ctypeslib.ndpointer(dtype=np.float32, ndim=2, flags="F_CONTIGUOUS")
    f32_1d = np.ctypeslib.ndpointer(dtype=np.float32, ndim=1, flags="C_CONTIGUOUS")
    i32_1d = np.ctypeslib.ndpointer(dtype=np.int32, ndim=1, flags="C_CONTIGUOUS")
    apply_compact.argtypes = [
        f32_2d, f32_2d, i32_1d, f32_1d, i32_1d, f32_1d,
        f32_1d, ctypes.c_int,
        f32_2d, f32_1d, i32_1d, ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_int),
    ]
    apply_compact.restype = None
    receiver_guard = library.qnc_live_guard_receiver_failure_ok
    receiver_guard.argtypes = [ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_float),
                               ctypes.c_int, ctypes.c_int]
    receiver_guard.restype = ctypes.c_int
    return library, coord, apply_compact, receiver_guard, build, env


def _case_inputs(case: str):
    failure_json = FAILURES.read_bytes()
    selected = receiver_union(failure_json)
    directory = PACKET / "data" / case
    faces = read_faces(directory / "faces.tsv", selected)
    writer = read_writer(directory / "rk_writer.tsv")
    return failure_json, selected, faces, writer


def _compact_inputs(faces: dict, writer: dict, selected, tile_id: int):
    words = np.empty((26, 382), dtype=np.float32, order="F")
    pre = np.empty((6, 382), dtype=np.float32, order="F")
    seen = np.zeros(382, dtype=np.int32)
    scale = np.empty(382, dtype=np.float32)
    hit = np.empty(382, dtype=np.int32)
    source = np.empty(382, dtype=np.float32)
    mu_new = np.empty(382, dtype=np.float32)
    for n, coord in enumerate(selected):
        row = faces["values"][coord]
        words[:, n] = np.asarray([int(row[name], 16) for name in FIELDS],
                                 dtype=np.uint32).view(np.float32)
        pre[:, n] = np.asarray([int(row[name], 16) for name in PRE_FIELDS],
                               dtype=np.uint32).view(np.float32)
        seen[n] = int(row["call_id"] == tile_id)
        scale[n] = _f32(row["SCALE"])
        hit[n] = int(row["limit_hit"])
        source[n] = _f32(_writer_word(writer, coord, "RKSCALAR_BEFORE", "SCALAR_TEND"))
        mu_new[n] = _f32(_writer_word(writer, coord, "RKSCALAR_BEFORE", "MU_NEW"))
    return words, pre, seen, scale, hit, source, mu_new


def _all_mode_choices(faces: dict, writer: dict, donors, tile_id: int):
    axis_modes = tuple(product((False, True), repeat=3))
    rk_modes = tuple((*sites, nm) for sites in product((False, True), repeat=3)
                     for nm in range(3))
    modes = {coord: (axis_modes, rk_modes) for coord in faces["values"]}
    operands = {
        coord: {field: _f32(_writer_word(writer, coord, "RKSCALAR_BEFORE", field))
                for field in ("MU_OLD", "MU_BASE", "MU_NEW", "C1H", "C2H",
                              "MSFTY", "SCALAR_TEND", "DT_RK", "SCALAR_OLD")}
        for coord in faces["values"]}
    choices = {}
    offsets = {}
    for donor_index, coord in enumerate(donors):
        if faces["values"][coord]["call_id"] != tile_id:
            continue
        result = _find_first_pass(faces, writer, modes, operands, coord, DEFAULT_MAX_ULP)
        assert result is not None
        choices[coord] = {"scale_hex": result["candidate_scale_hex"]}
        offsets[donor_index] = result["ulp_steps"]
    return choices, offsets


def test_target_coordinate_order_matches_pr475_capture(tile_module):
    _, get_coord, _, _, _, _ = tile_module
    failure_json, selected, _, _ = _case_inputs("control")
    assert failure_json == FAILURES.read_bytes()
    observed = []
    for index in range(1, 383):
        i, k, j = ctypes.c_int(), ctypes.c_int(), ctypes.c_int()
        get_coord(index, ctypes.byref(i), ctypes.byref(k), ctypes.byref(j))
        observed.append((i.value, k.value, j.value))
    assert tuple(observed) == selected
    assert len(failure_layer_coordinates(failure_json)) == 54


@pytest.mark.parametrize("case", ["control", "alpha025"])
def test_tile_local_compact_pilot_matches_all_mode_python_rows(tile_module, case):
    _, _, apply_compact, _, _, _ = tile_module
    failure_json, selected, faces, writer = _case_inputs(case)
    donors = failure_layer_coordinates(failure_json)
    for tile_id, expected_local_donors in ((1, 19), (2, 35)):
        words, pre, seen, scale, hit, source, mu_new = _compact_inputs(
            faces, writer, selected, tile_id)
        choices, offsets = _all_mode_choices(faces, writer, donors, tile_id)
        expected_rows, _ = _apply_scale_map(faces, choices)
        candidate = np.empty_like(words, order="F")
        selected_scale = np.empty(54, dtype=np.float32)
        nulp = np.empty(54, dtype=np.int32)
        status, local_donors = ctypes.c_int(), ctypes.c_int()
        apply_compact(words, pre, seen, scale, hit, source, mu_new, tile_id,
                      candidate, selected_scale, nulp, ctypes.byref(status),
                      ctypes.byref(local_donors))
        assert status.value == 1
        assert local_donors.value == expected_local_donors
        for donor_index, donor in enumerate(donors):
            expected_step = offsets.get(donor_index, -1)
            assert nulp[donor_index] == expected_step
            if expected_step >= 0:
                # The row SCALE is preserved in the face record; selected_scale
                # is the output chosen by the sequential n-ULP search.
                expected_bits = int(faces["values"][donor]["SCALE"], 16) - expected_step
                assert int(np.asarray([selected_scale[donor_index]], dtype=np.float32)
                           .view(np.uint32)[0]) == expected_bits
        for row_index, coord in enumerate(selected):
            if seen[row_index] == 0:
                assert np.array_equal(candidate[:, row_index], words[:, row_index])
                continue
            expected = np.asarray([int(expected_rows[coord][name], 16) for name in FIELDS],
                                  dtype=np.uint32)
            observed = candidate[:, row_index].copy().view(np.uint32)
            assert np.array_equal(observed, expected), (case, tile_id, coord)


def test_preexisting_failed_receiver_may_persist_only_if_row_is_bitwise_unchanged(tile_module):
    _, _, _, guard, _, _ = tile_module
    failure_json, selected, faces, _ = _case_inputs("control")
    adaptive = json.loads((ROOT / "evidence/native_qnc_selected_adaptive_2026-10-29"
                           / "analysis.json").read_text())
    choices = {
        tuple(row["coord_ikj"]): {"scale_hex": row["candidate_scale_hex"]}
        for row in adaptive["cases"]["control"]["scale_search"]["choice_rows"]
    }
    candidate_rows, _ = _apply_scale_map(faces, choices)
    coord = (152, 12, 268)
    assert coord in receiver_union(failure_json)
    baseline = np.asarray([int(faces["values"][coord][name], 16) for name in FIELDS],
                          dtype=np.uint32).view(np.float32)
    candidate = np.asarray([int(candidate_rows[coord][name], 16) for name in FIELDS],
                           dtype=np.uint32).view(np.float32)
    assert np.array_equal(baseline.view(np.uint32), candidate.view(np.uint32))
    before_c = (ctypes.c_float * 26)(*map(float, baseline))
    after_c = (ctypes.c_float * 26)(*map(float, candidate))
    assert guard(before_c, after_c, 1, 1) == 1

    mutated = candidate.copy()
    mutated.view(np.uint32)[25] ^= np.uint32(1)
    mutated_c = (ctypes.c_float * 26)(*map(float, mutated))
    assert guard(before_c, mutated_c, 1, 1) == 0
    assert guard(before_c, mutated_c, 0, 1) == 0
    assert guard(before_c, mutated_c, 1, 0) == 1


def test_live_context_clear_deactivates_guard(tile_module):
    _, _, _, _, build, env = tile_module
    driver = build / "context_lifecycle.f90"
    executable = build / "context_lifecycle"
    driver.write_text("""\
PROGRAM context_lifecycle
  USE qnc_live_guard_tile, ONLY: qnc_live_guard_set_context, &
       qnc_live_guard_is_active, qnc_live_guard_clear_context
  USE, INTRINSIC :: ISO_C_BINDING, ONLY: C_INT
  IMPLICIT NONE
  REAL, ALLOCATABLE :: source(:,:,:), mu_new(:,:)
  INTEGER(C_INT) :: status
  ALLOCATE(source(1:235,1:40,1:283),mu_new(1:235,1:283))
  source=1.0E-5
  mu_new=90000.0
  CALL qnc_live_guard_set_context(source,mu_new,1,235,1,40,1,283, &
       1,235,1,283,1,40,1,1,status)
  IF (status/=1 .OR. .NOT.qnc_live_guard_is_active()) ERROR STOP 1
  CALL qnc_live_guard_clear_context()
  IF (qnc_live_guard_is_active()) ERROR STOP 2
END PROGRAM context_lifecycle
""")
    lifecycle_env = env.copy()
    lifecycle_env.update({"KDM6AD_QNC_LIVE_GUARD": "1", "OMP_NUM_THREADS": "1",
                          "MKL_NUM_THREADS": "1", "OMP_THREAD_LIMIT": "1",
                          "VECLIB_MAXIMUM_THREADS": "1"})
    compiler = shutil.which("gfortran")
    shim = build / "qnc_rounding_env.o"
    command = [compiler, "-std=f2008", "-ffp-contract=off", "-J", str(build),
               "-I", str(build), str(SIGN_SOURCE), str(PREDICT_SOURCE),
               str(TILE_SOURCE), str(driver), str(shim), "-o", str(executable)]
    subprocess.run(command, check=True, cwd=build, env=lifecycle_env)
    subprocess.run([str(executable)], check=True, cwd=build, env=lifecycle_env)
