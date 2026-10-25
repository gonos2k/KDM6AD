"""Synthetic T_2/QV wire and Fortran preparation tests; never native evidence."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import textwrap
import time

import numpy as np
import pytest

from harness.native_analysis_control import (
    AnalysisUpdate,
    PreparedEffectiveAnalysis,
    apply_pair,
    encode_analysis_command,
    prepare_effective_analysis,
    read_analysis_applied,
)


BOUNDS = (1, 2, 1, 3, 1, 2)


def _bits(value):
    return struct.unpack(">I", struct.pack(">f", float(value)))[0]


def _ack_row(update, old_t, old_q, new_t=None, new_q=None,
             delta_t=None, delta_q=None):
    delta_t = _bits(np.float32(update.delta_theta_m)) if delta_t is None else delta_t
    delta_q = _bits(np.float32(update.delta_qv)) if delta_q is None else delta_q
    old_t_bits, old_q_bits = _bits(old_t), _bits(old_q)
    if new_t is None or new_q is None:
        predicted_t, predicted_q = apply_pair(old_t, old_q,
                                             np.asarray([delta_t], np.uint32).view(np.float32)[0],
                                             np.asarray([delta_q], np.uint32).view(np.float32)[0])
        new_t = predicted_t if new_t is None else new_t
        new_q = predicted_q if new_q is None else new_q
    return (
        f"THETA_M_QV {update.i:010d} {update.k:010d} {update.j:010d} "
        f"{old_t_bits:08X} {old_q_bits:08X} {delta_t:08X} {delta_q:08X} "
        f"{_bits(new_t):08X} {_bits(new_q):08X}"
    )


def _ack(step, rows):
    return (f"KDM6AD_TQ_APPLIED_V1\n{step:010d} {len(rows):010d}\n"
            + "".join(row + "\n" for row in rows)).encode("ascii")


def _write(path, data):
    path.write_bytes(data)
    return path


def test_analysis_command_fixed_width_pair_bits_and_61_byte_rows():
    updates = (
        AnalysisUpdate(1, 1, 1, 0.0, 0.25),
        AnalysisUpdate(2, 3, 2, 0.5, 0.0),
    )
    packet = encode_analysis_command(6, updates, BOUNDS)
    rows = packet.decode("ascii").splitlines()

    assert rows[0] == "KDM6AD_TQ_V1"
    assert rows[1] == "0000000006 0000000002"
    assert rows[2] == (
        f"THETA_M_QV 0000000001 0000000001 0000000001 00000000 {_bits(.25):08X}"
    )
    assert rows[3] == (
        f"THETA_M_QV 0000000002 0000000003 0000000002 {_bits(.5):08X} 00000000"
    )
    assert len(rows[2]) == len(rows[3]) == 61
    assert len(packet) == 35 + 2 * 62


@pytest.mark.parametrize("update", [
    AnalysisUpdate(1, 1, 1, 0.0, 0.0),
    AnalysisUpdate(0, 1, 1, 0.1, 0.0),
    AnalysisUpdate(1, 4, 1, 0.1, 0.0),
    AnalysisUpdate(1, 1, 3, 0.1, 0.0),
    AnalysisUpdate(True, 1, 1, 0.1, 0.0),
    AnalysisUpdate(1, 1, 1, float("nan"), 0.0),
    AnalysisUpdate(1, 1, 1, float("inf"), 0.0),
    AnalysisUpdate(1, 1, 1, 1e100, 0.0),
    AnalysisUpdate(1, 1, 1, 0.0, 1e-50),
])
def test_command_rejects_empty_nonfinite_or_out_of_domain_controls(update):
    with pytest.raises(ValueError):
        encode_analysis_command(6, (update,), BOUNDS)


def test_command_rejects_duplicate_points_and_overlarge_step():
    update = AnalysisUpdate(1, 1, 1, 0.1, 0.0)
    with pytest.raises(ValueError, match="duplicate"):
        encode_analysis_command(6, (update, update), BOUNDS)
    with pytest.raises(ValueError):
        encode_analysis_command(2**31, (), BOUNDS)


def test_ack_preserves_zero_component_signed_zero_bits_and_validates_other_component(tmp_path):
    updates = (
        AnalysisUpdate(1, 1, 1, 0.0, 0.25),
        AnalysisUpdate(2, 3, 2, 0.5, 0.0),
    )
    rows = (
        _ack_row(updates[0], -0.0, 0.125),
        _ack_row(updates[1], 270.0, -0.0),
    )
    path = _write(tmp_path / "ack.txt", _ack(6, rows))
    applied = read_analysis_applied(path, expected_step=6, updates=updates)

    assert applied[0].old_t_bits == applied[0].new_t_bits == 0x80000000
    assert applied[0].old_q_bits == _bits(0.125)
    assert applied[0].new_q_bits == _bits(0.375)
    assert applied[0].delta_t_bits == 0
    assert applied[1].old_q_bits == applied[1].new_q_bits == 0x80000000
    assert applied[1].old_t_bits == _bits(270.0)
    assert applied[1].new_t_bits == _bits(270.5)
    assert applied[1].delta_q_bits == 0


@pytest.mark.parametrize("packet", [
    b"KDM6AD_TQ_APPLIED_V2\n0000000006 0000000000\n",
    b"KDM6AD_TQ_APPLIED_V1\n0000000007 0000000000\n",
    b"KDM6AD_TQ_APPLIED_V1\n0000000006 0000000001\n",
    b"KDM6AD_TQ_APPLIED_V1\n0000000006 0000000000\nextra\n",
    b"KDM6AD_TQ_APPLIED_V1\n0000000006 0000000000",  # no final LF
])
def test_ack_rejects_wrong_version_step_count_or_framing(tmp_path, packet):
    path = _write(tmp_path / "bad.txt", packet)
    with pytest.raises(ValueError):
        read_analysis_applied(path, expected_step=6, updates=())


@pytest.mark.parametrize("badrow", [
    "THETA_M_QV 0000000001 0000000001 0000000001 80000000 3DCCCCCD 00000000 3E800000 80000000 3E4CCCCD",  # zero dT preserves -0
    "THETA_M_QV 0000000001 0000000001 0000000001 3F800000 3DCCCCCD 3F000000 3E800000 3F000000 3E4CCCCD",  # wrong old T
    "THETA_M_QV 0000000001 0000000001 0000000001 3F800000 3DCCCCCD 3F000000 7F800000 3FC00000 3E4CCCCD",  # nonfinite q increment
    "THETA_M_QV 0000000001 0000000001 0000000001 3F800000 3DCCCCCD 3F000000 3E800000 3F800000 3E4CCCCD",  # wrong arithmetic
    "THETA_M_QV 0000000001 0000000001 0000000001 3F800000 3DCCCCCD 3F000000 3E80000Z 3FC00000 3E4CCCCD",  # malformed hex
    "THETA_M_QV 0000000001 0000000001 0000000001 3F800000 3DCCCCCD 3F000000 3E800000 3FC00000 BDCCCCCD",  # negative new Q
])
def test_ack_rejects_bad_coordinates_or_float32_pair(tmp_path, badrow):
    update = AnalysisUpdate(1, 1, 1, 0.5, 0.25)
    path = _write(tmp_path / "badrow.txt", _ack(6, (badrow,)))
    with pytest.raises(ValueError):
        read_analysis_applied(path, expected_step=6, updates=(update,))


def test_ack_rejects_pair_that_rounds_to_identity(tmp_path):
    update = AnalysisUpdate(1, 1, 1, 1.0, 1e-20)
    row = _ack_row(update, 1e30, 1.0, delta_t=_bits(1.0), delta_q=_bits(1e-20),
                   new_t=np.float32(1e30), new_q=np.float32(1.0))
    path = _write(tmp_path / "identity.txt", _ack(6, (row,)))
    with pytest.raises(ValueError, match="no applied change"):
        read_analysis_applied(path, expected_step=6, updates=(update,))


def test_numpy_coordinate_encoding_imports_and_runs_when_torch_is_unavailable():
    repo = str(Path(__file__).parents[2])
    script = textwrap.dedent("""
        import builtins, json, numpy as np
        real_import = builtins.__import__
        def without_torch(name, *args, **kwargs):
            if name == 'torch':
                raise ImportError('Torch intentionally blocked for this test')
            return real_import(name, *args, **kwargs)
        builtins.__import__ = without_torch
        from harness.native_analysis_increment import (
            AnalysisStamp, ThermodynamicState, encode_native_increment,
            theta_m_jvp, theta_m_total,
        )
        assert __import__('harness.native_analysis_increment', fromlist=['torch']).torch is None
        base = AnalysisStamp('2025-07-19_00:02:00','2025-07-19_00:02:00','grid-a','bg')
        post = AnalysisStamp('2025-07-19_00:02:00','2025-07-19_00:02:00','grid-a','post',
                             background_checkpoint_id='bg')
        b = ThermodynamicState(np.array([280.0]),np.array([0.01]),base)
        a = ThermodynamicState(np.array([281.0]),np.array([0.02]),post)
        inc = encode_native_increment(b,a)
        tangent = theta_m_jvp(b.theta_dry,b.qv,np.array([1.0]),np.array([0.01]))
        value = theta_m_total(b.theta_dry,b.qv)
        assert np.isfinite(inc.delta_theta_m).all() and np.isfinite(inc.delta_qv).all()
        assert np.isfinite(tangent).all() and np.isfinite(value).all()
        print(json.dumps({'dt':inc.delta_theta_m.tolist(),'dq':inc.delta_qv.tolist()}))
    """).strip()
    env = os.environ.copy()
    env["PYTHONPATH"] = repo + os.pathsep + env.get("PYTHONPATH", "")
    run = subprocess.run([sys.executable, "-c", script], env=env,
                         capture_output=True, text=True, timeout=10)
    assert run.returncode == 0, run.stderr
    assert '"dt"' in run.stdout and '"dq"' in run.stdout


@pytest.fixture(scope="module")
def fortran_analysis_control(tmp_path_factory):
    compiler = shutil.which("gfortran")
    if compiler is None:
        pytest.skip("gfortran unavailable; Fortran analysis protocol smoke not run")
    source_module = Path(__file__).parents[1] / "native_step_control" / "kdm6ad_step_control.f90"
    work = tmp_path_factory.mktemp("fortran-analysis-control")
    caller = work / "analysis_driver.f90"
    module_object = work / "kdm6ad_step_control.o"
    caller_object = work / "analysis_driver.o"
    executable = work / "analysis_driver"
    caller.write_text(
        """program analysis_driver
  use, intrinsic :: iso_fortran_env, only: real32, int32
  use kdm6ad_step_control
  implicit none
  integer, allocatable :: ii(:), kk(:), jj(:)
  real(real32), allocatable :: dt(:), dq(:), oldt(:), oldq(:), newt(:), newq(:)
  real(real32), allocatable :: gridt(:), gridq(:)
  integer :: ierr, n, step, arg_status
  logical :: enabled
  character(len=256) :: message
  character(len=16) :: step_arg
  character(len=8) :: expect_reject
  character(len=8) :: negative_old_q
  integer :: bounds(6)
  bounds = [1,2,1,3,1,2]
  step=6
  call get_command_argument(1,step_arg,status=arg_status)
  if(arg_status == 0 .and. len_trim(step_arg) > 0) read(step_arg,*) step
  call await_analysis_command(step,1,'2025-07-19_00:02:00',bounds,5,enabled,ierr, &
       ii,kk,jj,dt,dq,message)
  if(ierr == step_control_disabled) then
    print '(A)','DISABLED'
    stop
  endif
  if(ierr /= step_control_ok) then
    print '(A,I0,1X,A)','AWAIT_ERROR ',ierr,trim(message)
    error stop 41
  endif
  allocate(oldt(size(dt)),oldq(size(dq)))
  oldt=270.0_real32
  oldq=0.125_real32
  call get_environment_variable('KDM6AD_TQ_TEST_NEGATIVE_OLD_Q',value=negative_old_q)
  if(trim(negative_old_q) == '1') oldq(1)=-0.125_real32
  if(size(dt) >= 1) then
    oldt(1)=transfer(int(z'80000000',int32),0.0_real32)
    dt(1)=0.0_real32
  endif
  if(size(dt) >= 2) then
    oldq(2)=transfer(int(z'80000000',int32),0.0_real32)
    dq(2)=0.0_real32
  endif
  allocate(gridt(size(dt)),gridq(size(dq)))
  gridt=oldt
  gridq=oldq
  call prepare_analysis_updates(oldt,oldq,dt,dq,newt,newq,ierr,message)
  if(ierr /= step_control_ok) then
    call get_environment_variable('KDM6AD_TQ_TEST_EXPECT_REJECT',value=expect_reject)
    if(trim(expect_reject) == '1') then
      do n=1,size(dt)
        if(transfer(gridt(n),0_int32) /= transfer(oldt(n),0_int32)) error stop 46
        if(transfer(gridq(n),0_int32) /= transfer(oldq(n),0_int32)) error stop 47
      enddo
      print '(A)','REJECTED_NO_PARTIAL_MUTATION'
      stop
    endif
    print '(A,I0,1X,A)','PREPARE_ERROR ',ierr,trim(message)
    error stop 42
  endif
  gridt=newt
  gridq=newq
  if(size(dt) >= 1 .and. transfer(oldt(1),0_int32) /= transfer(newt(1),0_int32)) error stop 43
  if(size(dq) >= 2 .and. transfer(oldq(2),0_int32) /= transfer(newq(2),0_int32)) error stop 44
  call write_analysis_ack(step,1,ii,kk,jj,oldt,oldq,dt,dq,newt,newq,ierr,message)
  if(ierr /= step_control_ok) then
    print '(A,I0,1X,A)','ACK_ERROR ',ierr,trim(message)
    error stop 45
  endif
  print '(A,I0)','APPLIED ',size(dt)
end program analysis_driver
""",
        encoding="ascii",
    )
    env = os.environ.copy()
    if "SDKROOT" not in env and sys.platform == "darwin":
        xcrun = shutil.which("xcrun")
        if xcrun:
            sdk = subprocess.run([xcrun,"--show-sdk-path"],capture_output=True,text=True)
            if sdk.returncode == 0 and sdk.stdout.strip():
                env["SDKROOT"] = sdk.stdout.strip()
    module_build = subprocess.run(
        [compiler,"-ffp-contract=off","-ffree-line-length-none","-J",str(work),
         "-c",str(source_module),"-o",str(module_object)],
        capture_output=True,text=True,env=env,cwd=work,
    )
    if module_build.returncode:
        pytest.fail(f"standalone Fortran analysis module compile failed: {module_build.stderr}")
    caller_build = subprocess.run(
        [compiler,"-ffp-contract=off","-ffree-line-length-none","-I",str(work),
         "-c",str(caller),"-o",str(caller_object)],
        capture_output=True,text=True,env=env,cwd=work,
    )
    if caller_build.returncode:
        pytest.fail(f"standalone Fortran caller compile failed: {caller_build.stderr}")
    link = subprocess.run([compiler,str(module_object),str(caller_object),"-o",str(executable)],
                          capture_output=True,text=True,env=env,cwd=work)
    if link.returncode:
        if sys.platform == "darwin" and "SDKROOT" not in env and "library 'System' not found" in link.stderr:
            pytest.skip("Fortran compiler works but macOS system linker SDK is unavailable")
        pytest.fail(f"standalone Fortran analysis-control link failed: {link.stderr}")
    return executable


def _run_fortran_waiting(executable, control, packet, *, step=6, expect_reject=False,
                         negative_old_q=False):
    env = os.environ.copy()
    env["KDM6AD_STEP_CONTROL_ROOT"] = str(control)
    env["KDM6AD_STEP_CONTROL_FAMILY"] = "ANALYSIS_TQ"
    if expect_reject:
        env["KDM6AD_TQ_TEST_EXPECT_REJECT"] = "1"
    if negative_old_q:
        env["KDM6AD_TQ_TEST_NEGATIVE_OLD_Q"] = "1"
    proc = subprocess.Popen([str(executable),str(step)],env=env,stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,text=True)
    ready=control/f"ready_{step:010d}.txt"
    deadline=time.monotonic()+5
    while not ready.exists() and proc.poll() is None and time.monotonic()<deadline:
        time.sleep(.01)
    if ready.exists():
        (control/f"command_{step:010d}.txt").write_bytes(packet)
    try:
        output,_=proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill(); output,_=proc.communicate()
        pytest.fail(f"Fortran analysis caller timed out: {output!r}")
    return proc.returncode,output


def test_fortran_analysis_pair_roundtrip_signed_zero_and_ack(tmp_path,fortran_analysis_control):
    updates=(AnalysisUpdate(1,1,1,0.0,.25),AnalysisUpdate(2,3,2,.5,0.0))
    control=tmp_path/"control";control.mkdir()
    code,output=_run_fortran_waiting(fortran_analysis_control,control,
        encode_analysis_command(6,updates,BOUNDS))
    assert code==0,output
    assert "APPLIED 2" in output
    applied=read_analysis_applied(control/"applied_0000000006.txt",
                                  expected_step=6,updates=updates)
    assert applied[0].old_t_bits==applied[0].new_t_bits==0x80000000
    assert applied[1].old_q_bits==applied[1].new_q_bits==0x80000000
    assert applied[0].delta_t_bits==0 and applied[1].delta_q_bits==0


def test_analysis_family_accepts_step_zero_for_cold_start_identity_command(
        tmp_path,fortran_analysis_control):
    control=tmp_path/"cold_control";control.mkdir()
    packet=encode_analysis_command(0,(),BOUNDS)
    code,output=_run_fortran_waiting(fortran_analysis_control,control,packet,step=0)
    assert code==0,output
    assert "APPLIED 0" in output
    assert read_analysis_applied(control/"applied_0000000000.txt",
                                 expected_step=0,updates=())==()


def test_fortran_prepare_rejects_invalid_later_row_without_partial_host_mutation(
        tmp_path,fortran_analysis_control):
    updates=(AnalysisUpdate(1,1,1,0.0,.25),AnalysisUpdate(2,2,2,0.0,-.5))
    control=tmp_path/"control";control.mkdir()
    code,output=_run_fortran_waiting(
        fortran_analysis_control,control,encode_analysis_command(6,updates,BOUNDS),
        expect_reject=True)
    assert code==0,output
    assert "REJECTED_NO_PARTIAL_MUTATION" in output
    assert not (control/"applied_0000000006.txt").exists()


def test_fortran_prepare_rejects_negative_old_qv_even_if_delta_would_repair_it(
        tmp_path,fortran_analysis_control):
    # The requested increment would change QV from -0.125 to +0.125. The
    # invalid base state must be rejected before any prepared value is applied.
    updates=(AnalysisUpdate(1,1,1,0.0,.25),)
    control=tmp_path/"negative_old_qv";control.mkdir()
    code,output=_run_fortran_waiting(
        fortran_analysis_control,control,encode_analysis_command(6,updates,BOUNDS),
        expect_reject=True,negative_old_q=True)
    assert code==0,output
    assert "REJECTED_NO_PARTIAL_MUTATION" in output
    assert not (control/"applied_0000000006.txt").exists()


@pytest.mark.parametrize("packet",[
    b"KDM6AD_TQ_V1\n0000000006 0000000001\nTHETA_M_QV 0000000001 0000000001 0000000001 00000000 00000000\n",
    b"KDM6AD_TQ_V1\n0000000006 0000000001\nTHETA_M_QV 0000000001 0000000001 0000000001 7F800000 3F800000\n",
    b"KDM6AD_TQ_V1\r\n0000000006 0000000001\r\nTHETA_M_QV 0000000001 0000000001 0000000001 00000000 3F800000\r\n",
    b"KDM6AD_TQ_V1\n0000000006 0000000001\nTHETA_M_QV 0000000001 0000000001 0000000001 00000000 3F800000 \n",
    b"KDM6AD_TQ_V1\n0000000006 0000000001\nTHETA_M_QV 0000000001 0000000001 0000000001 00000000 3F800000\nEXTRA\n",
    b"KDM6AD_TQ_V1\n0000000006 0000000001\nTHETA_M_QV 0000000001 0000000001 0000000001 00000000 3F800000",
    b"KDM6AD_TQ_V1\n0000000006 0000000002\nTHETA_M_QV 0000000001 0000000001 0000000001 00000000 3F800000\n",
    b"KDM6AD_TQ_V1\n0000000007 0000000000\n",
    b"KDM6AD_TQ_V1\n0000000006 0000000002\n"
    b"THETA_M_QV 0000000001 0000000001 0000000001 00000000 3F800000\n"
    b"THETA_M_QV 0000000001 0000000001 0000000001 3F800000 00000000\n",
])
def test_fortran_analysis_parser_rejects_invalid_pair_and_framing(tmp_path,fortran_analysis_control,packet):
    control=tmp_path/"control";control.mkdir()
    code,output=_run_fortran_waiting(fortran_analysis_control,control,packet)
    assert code!=0
    assert "AWAIT_ERROR" in output
    assert not (control/"applied_0000000006.txt").exists()


def test_effective_analysis_filters_float32_noop_points_and_matches_scalar_pairs():
    old_t = np.full((2, 3, 2), 300.0, dtype=np.float32)
    old_q = np.full((2, 3, 2), 0.01, dtype=np.float32)
    min_subnormal = np.nextafter(np.float32(0.0), np.float32(1.0))
    old_t[0, 0, 0] = np.float32(-min_subnormal)
    old_q[0, 0, 0] = np.float32(-0.0)
    old_t[1, 1, 1] = np.float32(1.0e30)
    requested_t = np.zeros_like(old_t, dtype=np.float64)
    requested_q = np.zeros_like(old_q, dtype=np.float64)
    requested_t[0, 0, 0] = float(min_subnormal)
    requested_t[0, 1, 0] = 0.25
    requested_q[0, 1, 0] = 0.001
    requested_t[1, 1, 1] = 1.0  # representable, but rounds away at this background
    unchanged = (requested_t == 0.0) & (requested_q == 0.0)

    prepared = prepare_effective_analysis(
        old_t, old_q, requested_t, requested_q, unchanged, bounds=BOUNDS
    )

    assert isinstance(prepared, PreparedEffectiveAnalysis)
    assert prepared.counts == {
        "requested_points": 3,
        "noop_points": 1,
        "applied_points": 2,
        "empty_points": 9,
        "requested_nonzero_components": 4,
        "applied_components": 3,
        "zero_effect_components": 1,
    }
    assert not prepared.all_noop
    assert prepared.changed_mask[0, 0, 0] and prepared.changed_mask[0, 1, 0]
    assert not prepared.changed_mask[1, 1, 1]
    assert [(u.i, u.k, u.j) for u in prepared.updates] == [(1, 1, 1), (1, 2, 1)]
    # A real nonzero addition changes -minsubnormal to +0 and is not filtered.
    assert _bits(old_t[0, 0, 0]) == 0x80000001
    assert _bits(prepared.effective_theta_m[0, 0, 0]) == 0
    # A zero component preserves the input's signed-zero bit pattern.
    assert _bits(prepared.effective_qv[0, 0, 0]) == 0x80000000
    assert prepared.delta_theta_m[1, 1, 1] == 0.0
    assert prepared.delta_qv[1, 1, 1] == 0.0

    for update in prepared.updates:
        i, k, j = update.i - 1, update.k - 1, update.j - 1
        expected_t, expected_q = apply_pair(
            old_t[i, k, j], old_q[i, k, j],
            prepared.delta_theta_m[i, k, j], prepared.delta_qv[i, k, j])
        assert _bits(expected_t) == _bits(prepared.effective_theta_m[i, k, j])
        assert _bits(expected_q) == _bits(prepared.effective_qv[i, k, j])


def test_effective_analysis_all_noop_is_identity_with_signed_zero_bits():
    old_t = np.full((2, 3, 2), 300.0, dtype=np.float32)
    old_q = np.full_like(old_t, 0.01)
    old_t[0, 0, 0] = np.float32(-0.0)
    old_q[1, 1, 1] = np.float32(-0.0)
    zero = np.zeros(old_t.shape, dtype=np.float64)
    prepared = prepare_effective_analysis(
        old_t, old_q, zero, zero.copy(), np.ones(old_t.shape, dtype=bool),
        bounds=BOUNDS)
    assert prepared.all_noop and prepared.updates == ()
    assert prepared.counts["requested_points"] == 0
    assert prepared.counts["applied_points"] == 0
    assert prepared.effective_theta_m.tobytes() == old_t.tobytes()
    assert prepared.effective_qv.tobytes() == old_q.tobytes()
    assert not prepared.changed_mask.any()


@pytest.mark.parametrize("mutate,match", [
    ("integer_mask", "unchanged_mask must be a Boolean"),
    ("wrong_mask", "exactly identify zero requested"),
    ("bad_bounds", "bounds must equal the full native array domain shape"),
    ("underflow", "underflows binary32"),
    ("overflow", "overflows binary32"),
    ("negative_qv", "qv must be nonnegative"),
    ("negative_background_qv", "background_qv must be nonnegative"),
])
def test_effective_analysis_rejects_invalid_metadata_and_physical_values(mutate, match):
    old_t = np.full((2, 3, 2), 300.0, dtype=np.float32)
    old_q = np.full_like(old_t, 0.01)
    dt = np.zeros(old_t.shape, dtype=np.float64)
    dq = np.zeros(old_q.shape, dtype=np.float64)
    mask = np.ones(old_t.shape, dtype=bool)
    bounds = BOUNDS
    if mutate == "integer_mask":
        mask = mask.astype(np.int32)
    elif mutate == "wrong_mask":
        dt[0, 0, 0] = 0.25
        mask[0, 0, 0] = True
    elif mutate == "bad_bounds":
        bounds = (1, 3, 1, 2, 1, 2)
    elif mutate == "underflow":
        dt[0, 0, 0] = 1.0e-50
        mask[0, 0, 0] = False
    elif mutate == "overflow":
        dt[0, 0, 0] = 1.0e100
        mask[0, 0, 0] = False
    elif mutate == "negative_qv":
        dq[0, 0, 0] = -0.02
        mask[0, 0, 0] = False
    elif mutate == "negative_background_qv":
        old_q[0, 0, 0] = -0.01
    with pytest.raises(ValueError, match=match):
        prepare_effective_analysis(old_t, old_q, dt, dq, mask, bounds=bounds)
