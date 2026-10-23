"""Standalone Fortran/Python protocol smoke; no host module or WRF execution."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pytest

from harness.native_step_control import (
    HeatingUpdate,
    encode_command,
    read_applied,
    read_ready,
)
import harness.native_step_control_overlay as overlay


def _synthetic_host(root):
    source = root / "share" / "mediation_integrate.F"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("\n".join((
        "MODULE synthetic_mediation",
        "CONTAINS",
        "SUBROUTINE med_before_solve_io ( grid , config_flags )",
        "   USE module_domain    , ONLY : domain, domain_clock_get",
        "   USE module_domain    , ONLY : domain_clock_set, get_ijk_from_grid",
        "   USE module_streams",
        "   INTEGER                                    :: rc",
        "   RETURN",
        "END SUBROUTINE med_before_solve_io",
        "END MODULE synthetic_mediation",
        "")), encoding="utf-8")
    return source


@pytest.fixture(scope="module")
def fortran_step_control(tmp_path_factory):
    compiler = shutil.which("gfortran")
    if compiler is None:
        pytest.skip("gfortran is unavailable; standalone transport smoke not run")
    root = Path(__file__).parents[1]
    module = root / "native_step_control" / "kdm6ad_step_control.f90"
    work = tmp_path_factory.mktemp("fortran-step-control")
    source = work / "driver.f90"
    executable = work / "step_control_driver"
    source.write_text(
        """program step_control_driver
  use, intrinsic :: iso_fortran_env, only: real32, int32
  use kdm6ad_step_control
  implicit none
  integer, allocatable :: ii(:), kk(:), jj(:)
  real(real32), allocatable :: delta(:), old_h(:), new_h(:)
  integer :: ierr, n
  logical :: enabled
  character(len=256) :: message
  integer :: bounds(6)
  bounds = [1, 2, 1, 2, 1, 2]
  call await_step_command(6, 1, '2025-07-19_00:02:00', bounds, 5, &
       enabled, ierr, ii, kk, jj, delta, message)
  if (ierr == step_control_disabled) then
    print '(A)', 'DISABLED'
    stop
  end if
  if (ierr /= step_control_ok) then
    print '(A,I0,1X,A)', 'AWAIT_ERROR ', ierr, trim(message)
    error stop 31
  end if
  allocate(old_h(size(delta)))
  old_h = 0.0_real32
  if (size(old_h) > 0) old_h(1) = transfer(int(z'80000000',int32), 0.0_real32)
  call prepare_h_diabatic_updates(old_h, delta, new_h, ierr, message)
  if (ierr /= step_control_ok) then
    print '(A,I0,1X,A)', 'PREPARE_ERROR ', ierr, trim(message)
    error stop 32
  end if
  call write_applied_ack(6, 1, ii, kk, jj, old_h, delta, new_h, ierr, message)
  if (ierr /= step_control_ok) then
    print '(A,I0,1X,A)', 'ACK_ERROR ', ierr, trim(message)
    error stop 33
  end if
  print '(A,I0)', 'APPLIED ', size(delta)
end program step_control_driver
""",
        encoding="ascii",
    )
    env = os.environ.copy()
    if "SDKROOT" not in env and sys.platform == "darwin":
        xcrun = shutil.which("xcrun")
        if xcrun:
            sdk = subprocess.run([xcrun, "--show-sdk-path"], capture_output=True, text=True)
            if sdk.returncode == 0 and sdk.stdout.strip():
                env["SDKROOT"] = sdk.stdout.strip()
    build = subprocess.run(
        [compiler, "-ffp-contract=off", "-ffree-line-length-none", "-J", str(work),
         str(module), str(source), "-o", str(executable)],
        capture_output=True, text=True, env=env,
    )
    if build.returncode:
        if (sys.platform == "darwin" and "SDKROOT" not in env
                and "library 'System' not found" in build.stderr):
            pytest.skip("Fortran compiler works but macOS SDK linker runtime is unavailable")
        pytest.fail(f"standalone Fortran transport build failed: {build.stderr}")
    return executable


def _run_waiting_process(executable, control_root, packet=None):
    env = os.environ.copy()
    env.pop("KDM6AD_STEP_CONTROL_ROOT", None)
    env["KDM6AD_STEP_CONTROL_ROOT"] = str(control_root)
    process = subprocess.Popen([str(executable)], env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    ready_path = control_root / "ready_0000000006.txt"
    deadline = time.monotonic() + 5
    while not ready_path.exists() and process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.01)
    if packet is not None and ready_path.exists():
        (control_root / "command_0000000006.txt").write_bytes(packet)
    try:
        output, _ = process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        output, _ = process.communicate()
        pytest.fail(f"standalone protocol process timed out; output={output!r}")
    return process.returncode, output, ready_path


def test_overlay_check_apply_and_idempotence_are_narrow_and_mode_preserving(tmp_path):
    source = _synthetic_host(tmp_path)
    source.chmod(0o640)
    before = source.read_bytes()

    checked = overlay.overlay_host_root(tmp_path)
    assert checked["status"] == "ready"
    assert source.read_bytes() == before

    applied = overlay.overlay_host_root(tmp_path, apply=True)
    assert applied["status"] == "applied"
    assert source.stat().st_mode & 0o777 == 0o640
    patched = source.read_text(encoding="utf-8")
    assert patched.count(overlay._HOOK[0]) == 1
    assert patched.count(overlay._HOOK[-1]) == 1
    assert "CALL await_step_command" in patched
    assert "CALL prepare_h_diabatic_updates" in patched

    repeated = overlay.overlay_host_root(tmp_path, apply=True)
    assert repeated["status"] == "already_applied"
    assert source.read_text(encoding="utf-8") == patched


def test_step_control_hook_fences_domain_rank_and_thread_but_not_internal_tile_count(tmp_path):
    source = _synthetic_host(tmp_path)
    result = overlay.overlay_host_root(tmp_path, apply=True)
    assert result["status"] == "applied"
    patched = source.read_text(encoding="utf-8")
    begin = patched.index(overlay._HOOK[0])
    end = patched.index(overlay._HOOK[-1]) + len(overlay._HOOK[-1])
    hook = patched[begin:end]

    # Domain/rank/thread are process-level ownership fences. Internal WRF tiles
    # may be sequential within one rank and do not change that ownership.
    assert "grid%id .NE. 1" in hook
    assert "ntasks .NE. 1" in hook
    assert "omp_get_max_threads() .NE. 1" in hook
    assert "grid%num_tiles" not in hook
    assert "CALL await_step_command" in hook
    assert "CALL prepare_h_diabatic_updates" in hook
    assert not any(line.lstrip().upper().startswith("!$OMP")
                   for line in hook.splitlines())
    assert hook.index("CALL await_step_command") < hook.index("CALL prepare_h_diabatic_updates")
    assert hook.index(overlay._HOOK[-1]) < patched.index("   RETURN", end)


def test_analysis_tq_hook_selects_state_fields_captures_cold_start_and_applies_after_full_preparation(
        tmp_path):
    source = _synthetic_host(tmp_path)
    result = overlay.overlay_host_root(tmp_path, apply=True)
    assert result["status"] == "applied"
    patched = source.read_text(encoding="utf-8")
    begin = patched.index(overlay._HOOK[0])
    end = patched.index(overlay._HOOK[-1], begin) + len(overlay._HOOK[-1])
    hook = patched[begin:end]

    assert "KDM6AD_STEP_CONTROL_FAMILY" in hook
    assert "ANALYSIS_TQ" in hook and "H_RATE" in hook
    assert "grid%t_2(bctx_i(bctx_m),bctx_k(bctx_m),bctx_j(bctx_m))" in hook
    assert "grid%moist(bctx_i(bctx_m),bctx_k(bctx_m), &" in hook
    assert "P_QV" in hook
    assert "grid%h_diabatic" in hook  # retained in the separate default family
    assert "IF (bctx_is_tq .AND. grid%itimestep .LT. 0)" in hook
    assert "IF (.NOT. bctx_is_tq .AND. grid%itimestep .LT. 1)" in hook

    capture = hook.index("CALL med_restart_out(grid, config_flags)")
    ready_tq = hook.index("CALL await_analysis_command")
    assert capture < ready_tq
    assert "currTime .EQ. startTime" in hook
    assert "CALL prepare_analysis_updates" in hook
    assert hook.index("CALL prepare_analysis_updates") < hook.index("IF (bctx_status .NE. 0) CALL wrf_error_fatal(TRIM(bctx_error))", hook.index("CALL prepare_analysis_updates"))
    prepare = hook.index("CALL prepare_analysis_updates")
    fatal = hook.index("IF (bctx_status .NE. 0) CALL wrf_error_fatal(TRIM(bctx_error))", prepare)
    writeback = hook.index("grid%t_2(bctx_i(bctx_m)", prepare)
    assert prepare < fatal < writeback < hook.index("CALL write_analysis_ack")


def test_overlay_refuses_comment_only_anchor_and_leaves_source_unchanged(tmp_path):
    source = _synthetic_host(tmp_path)
    text = source.read_text(encoding="utf-8")
    text = text.replace(overlay._DOMAIN_OLD,
        "!" + overlay._DOMAIN_OLD + "\n   USE module_domain    , ONLY : domain, domain_clock_get, alternate", 1)
    source.write_text(text, encoding="utf-8")
    before = source.read_bytes()

    result = overlay.overlay_host_root(tmp_path, apply=True)

    assert result["status"] == "blocked"
    assert source.read_bytes() == before


def test_overlay_comment_only_markers_cannot_claim_hook_is_already_applied(tmp_path):
    source = _synthetic_host(tmp_path)
    text = source.read_text(encoding="utf-8")
    text = text.replace(
        "   RETURN",
        "!" + overlay._HOOK[0] + "\n! synthetic commented-out hook\n!" + overlay._HOOK[-1]
        + "\n   RETURN",
        1,
    )
    source.write_text(text, encoding="utf-8")
    before = source.read_bytes()

    result = overlay.overlay_host_root(tmp_path)

    # Ambiguous marker remnants must refuse the overlay rather than claim it
    # is applied or silently layer a second hook over a partial edit.
    assert result["status"] == "blocked"
    assert source.read_bytes() == before


def test_overlay_refuses_corrupted_active_marker_block_without_rewriting(tmp_path):
    source = _synthetic_host(tmp_path)
    assert overlay.overlay_host_root(tmp_path, apply=True)["status"] == "applied"
    text = source.read_text(encoding="utf-8")
    text = text.replace(
        "       CALL prepare_h_diabatic_updates(bctx_old, bctx_delta, bctx_new, &",
        "       CALL wrong_prepare_h_diabatic_updates(bctx_old, bctx_delta, bctx_new, &",
        1,
    )
    source.write_text(text, encoding="utf-8")
    before = source.read_bytes()

    result = overlay.overlay_host_root(tmp_path, apply=True)

    assert result["status"] == "blocked"
    assert source.read_bytes() == before


def test_overlay_failed_atomic_replace_leaves_source_unchanged(tmp_path, monkeypatch):
    source = _synthetic_host(tmp_path)
    before = source.read_bytes()

    def fail_replace(*args, **kwargs):
        raise OSError("injected replacement failure")

    monkeypatch.setattr(overlay, "_atomic_replace", fail_replace)
    result = overlay.overlay_host_root(tmp_path, apply=True)

    assert result["status"] == "blocked"
    assert source.read_bytes() == before


def test_fortran_ready_command_and_ack_match_python_raw_float32_protocol(
        tmp_path, fortran_step_control):
    update = HeatingUpdate(1, 1, 1, 0.25)
    control_root = tmp_path / "control"
    control_root.mkdir()
    code, output, ready_path = _run_waiting_process(
        fortran_step_control, control_root,
        encode_command(6, (update,), (1, 2, 1, 2, 1, 2)))

    assert code == 0, output
    assert "APPLIED 1" in output
    ready = read_ready(ready_path, expected_step=6)
    assert ready.time == "2025-07-19_00:02:00"
    assert ready.bounds == (1, 2, 1, 2, 1, 2)
    applied, = read_applied(control_root / "applied_0000000006.txt",
                            expected_step=6, updates=(update,))
    assert applied.old_bits == 0x80000000  # signed negative zero survives the Fortran transfer
    assert applied.delta_bits == 0x3E800000
    assert applied.new_bits == 0x3E800000


def test_fortran_empty_command_ack_is_identity_and_disabled_mode_does_not_wait(
        tmp_path, fortran_step_control):
    control_root = tmp_path / "control"
    control_root.mkdir()
    code, output, _ = _run_waiting_process(
        fortran_step_control, control_root, encode_command(6, (), (1, 2, 1, 2, 1, 2)))
    assert code == 0, output
    assert "APPLIED 0" in output
    assert read_applied(control_root / "applied_0000000006.txt",
                        expected_step=6, updates=()) == ()

    disabled_root = tmp_path / "disabled"
    disabled_root.mkdir()
    env = os.environ.copy()
    env.pop("KDM6AD_STEP_CONTROL_ROOT", None)
    disabled = subprocess.run([str(fortran_step_control)], env=env,
                              capture_output=True, text=True, timeout=5)
    assert disabled.returncode == 0
    assert "DISABLED" in disabled.stdout
    assert not list(disabled_root.iterdir())


@pytest.mark.parametrize("badrow", [
    "H_DIABATIC 0000000001 0000000001 0000000001 00000000",  # zero delta
    "H_DIABATIC 0000000001 0000000001 0000000001 7F800000",  # infinity
])
def test_fortran_rejects_invalid_nonempty_control_before_ack(
        tmp_path, fortran_step_control, badrow):
    control_root = tmp_path / "control"
    control_root.mkdir()
    bad = ("KDM6AD_STEP_V1\n0000000006 0000000001\n" + badrow + "\n").encode("ascii")
    code, output, _ = _run_waiting_process(fortran_step_control, control_root, bad)
    assert code != 0
    assert "AWAIT_ERROR" in output
    assert not (control_root / "applied_0000000006.txt").exists()


@pytest.mark.parametrize("packet", [
    # Formatted sequential IO can otherwise accept a final record without LF.
    b"KDM6AD_STEP_V1\n0000000006 0000000001\n"
    b"H_DIABATIC 0000000001 0000000001 0000000001 3E800000",
    # Fixed-width protocol rows cannot grow whitespace beyond the hex field.
    b"KDM6AD_STEP_V1\n0000000006 0000000001\n"
    b"H_DIABATIC 0000000001 0000000001 0000000001 3E800000 \n",
    # CRLF is not the protocol's byte-level LF framing.
    b"KDM6AD_STEP_V1\r\n0000000006 0000000001\r\n"
    b"H_DIABATIC 0000000001 0000000001 0000000001 3E800000\r\n",
    # Declared row count is exact: extra records are rejected.
    b"KDM6AD_STEP_V1\n0000000006 0000000001\n"
    b"H_DIABATIC 0000000001 0000000001 0000000001 3E800000\nEXTRA\n",
])
def test_fortran_rejects_noncanonical_command_record_framing(
        tmp_path, fortran_step_control, packet):
    control_root = tmp_path / "control"
    control_root.mkdir()
    code, output, _ = _run_waiting_process(fortran_step_control, control_root, packet)
    assert code != 0
    assert "AWAIT_ERROR" in output
    assert not (control_root / "applied_0000000006.txt").exists()
