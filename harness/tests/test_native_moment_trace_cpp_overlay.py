"""Value-only diagnostic format and exact source-insertion checks."""
from pathlib import Path
import os
import shutil
import subprocess
import sys

import numpy as np
import pytest

from harness.native_moment_trace_cpp_overlay import overlay_cpp_source

ROOT = Path(__file__).resolve().parents[2]


def test_overlay_preserves_operational_and_ad_source_bytes():
    original = (ROOT / "libtorch/bridge/kdm6_c_api.cpp").read_text()
    actual = overlay_cpp_source(original)
    begin = original.index('extern "C" int kdm6_native_fp64_value_c(')
    expected_prefix = original[:begin].replace(
        "#include <limits>\n", '#include <limits>\n#include "native_moment_trace_v2.hpp"\n')
    assert actual[:actual.index('extern "C" int kdm6_native_fp64_value_c(')] == expected_prefix
    assert actual.count('record("FP64_INPUT"') == 1
    assert actual.count('record("FP64_OUTPUT"') == 1
    assert actual.index('record("FP64_OUTPUT"') < actual.index(
        "// Value-only output admission before any REAL4 buffer is written.")
    # Removing the two inserted blocks restores the entire original body.
    import re
    restored = re.sub(
        r'        if \(kdm6_moment_trace_v2::enabled\(\)\) \{.*?\n        \}\n\n',
        '', actual, flags=re.S)
    restored = restored.replace('#include "native_moment_trace_v2.hpp"\n', '')
    assert restored == original
    with pytest.raises(ValueError, match="already present"):
        overlay_cpp_source(actual)


def test_cpp_writer_nonsquare_native_order_and_fresh_output(tmp_path):
    compiler = shutil.which("c++")
    if compiler is None:
        pytest.skip("C++ compiler unavailable for the diagnostic-only fixture")
    source = tmp_path / "probe.cpp"
    source.write_text('''#include "native_moment_trace_v2.hpp"
int main() {
  try {
  double qc[24], nc[24];
  for (int n=0;n<24;++n) { qc[n]=n+1; nc[n]=-(n+1); }
  kdm6_moment_trace_context_c(1,3,154,156,1,2,24,27);
  kdm6_moment_trace_v2::record("FP64_INPUT",qc,nc,3,2,4,20.,10.,10.);
  kdm6_moment_trace_v2::record("FP64_OUTPUT",qc,nc,3,2,4,20.,10.,10.);
  } catch (...) { return 2; }
}
''')
    binary = tmp_path / "probe"
    subprocess.run([compiler, "-std=c++17", "-ffp-contract=off", "-UNDEBUG",
                    "-I" + str(ROOT / "harness/native_trace"), str(source),
                    "-o", str(binary)], check=True, capture_output=True)
    env = {k: v for k, v in os.environ.items() if k != "KDM6AD_MOMENT_TRACE_V2_DIR"}
    subprocess.run([binary], env=env, check=True, capture_output=True)
    assert not (tmp_path / "kernel.hex").exists()
    env["KDM6AD_MOMENT_TRACE_V2_DIR"] = str(tmp_path)
    subprocess.run([binary], env=env, check=True, capture_output=True)
    rows = (tmp_path / "kernel.hex").read_text().splitlines()
    assert rows[0] == "# KDM6AD_MOMENT_TRACE_V2"
    assert rows[1].split()[:12] == ["CALL", "1", "3", "154", "156", "1", "2",
                                  "24", "27", "3", "2", "4"]
    values = [line.split() for line in rows if line.startswith("VAL ")]
    # Target (155,25) has local (i,j)=(1,1); B=1*4+1=5, levels 0/1.
    assert len(values) == 8
    first = values[0]
    assert first[:8] == ["VAL", "1", "FP64_INPUT", "155", "1", "25", "f64", "QC"]
    assert int(first[8], 16) == int(np.asarray([11.0], dtype=np.float64).view(np.uint64)[0])
    before = (tmp_path / "kernel.hex").read_bytes()
    failed = subprocess.run([binary], env=env, capture_output=True)
    assert failed.returncode != 0
    assert (tmp_path / "kernel.hex").read_bytes() == before


@pytest.mark.parametrize("storage_extra", [0, 1])
def test_fortran_cpp_reader_join_and_finish_call_ownership(tmp_path, storage_extra):
    """Exercise real writers together; the second call owns no witness."""
    compiler, fortran = shutil.which("c++"), shutil.which("gfortran")
    if compiler is None or fortran is None:
        pytest.skip("C++/Fortran compilers unavailable for diagnostic writer fixture")
    from harness.native_moment_trace_records import (
        read_moment_trace_v2, validate_moment_trace_v2,
    )
    cpp = tmp_path / "probe.cpp"
    cpp.write_text('''#include "native_moment_trace_v2.hpp"
#include <vector>
extern "C" void probe(const float* qc,const float* nc,int im,int km,int jm) {
  std::vector<double> q(im*km*jm),n(im*km*jm);
  for(int i=0;i<im;++i) for(int j=0;j<jm;++j) for(int k=0;k<km;++k) {
    int f=i+im*(k+km*j),b=(i*jm+j)*km+k; q[b]=qc[f]; n[b]=nc[f];
  }
  kdm6_moment_trace_v2::record("FP64_INPUT",q.data(),n.data(),im,km,jm,20.,10.,10.);
  kdm6_moment_trace_v2::record("FP64_OUTPUT",q.data(),n.data(),im,km,jm,20.,10.,10.);
}
''')
    main = tmp_path / "main.f90"
    main.write_text('''program check_join
use iso_c_binding, only:c_int,c_float,c_double
use kdm6ad_moment_trace_v2
implicit none
interface
 subroutine probe(qc,nc,im,km,jm) bind(C)
 import c_float,c_int
 real(c_float),intent(in)::qc(*),nc(*)
 integer(c_int),value::im,km,jm
 end subroutine
end interface
integer,parameter::sk=__STORAGE_KME__
real(c_float)::q(3,2,4),n(3,2,4),hq(154:156,1:sk,24:27),hn(154:156,1:sk,24:27)
integer(c_int)::cid,i,j,k
do i=1,3
 do j=1,4
  do k=1,2
   q(i,k,j)=100*i+10*j+k; n(i,k,j)=-q(i,k,j)
  end do
 end do
end do
hq=999.0;hn=-999.0
hq(:,1:2,:)=q;hn(:,1:2,:)=n
cid=moment_trace_begin_call(3,154,156,1,2,24,27,3,2,4,20.0_c_double,10.0_c_double,10.0_c_double)
call moment_trace_buffer_values('MP_INPUT',cid,154,156,1,2,24,27,3,2,4,q,n)
call probe(q,n,3,2,4)
call moment_trace_buffer_values('MP_OUTPUT',cid,154,156,1,2,24,27,3,2,4,q,n)
call moment_trace_host_values('HOST_WRITEBACK',cid,154,156,1,sk,24,27,154,156,1,2,24,27,hq,hn)
call moment_trace_host_values('WRAPPER_POST',cid,154,156,1,sk,24,27,154,156,1,2,24,27,hq,hn)
! A later wrapper call has no selected target. Finish must still reference call 1.
cid=moment_trace_begin_call(3,1,3,1,2,1,4,3,2,4,20.0_c_double,10.0_c_double,10.0_c_double)
call probe(q,n,3,2,4)
! Caller storage may include an extra upper slot. It is not a native mass level.
call moment_trace_finish_values('ZERO_OUT_PRE',3,154,156,1,sk,24,27,154,156,1,sk,24,27,hq,hn)
call moment_trace_finish_values('MOMENTS_PRE',3,154,156,1,sk,24,27,154,156,1,sk,24,27,hq,hn)
call moment_trace_finish_values('MOMENTS_POST',3,154,156,1,sk,24,27,154,156,1,sk,24,27,hq,hn)
end program
'''.replace("__STORAGE_KME__", str(2 + storage_extra)))
    subprocess.run([compiler, "-std=c++17", "-ffp-contract=off", "-UNDEBUG", "-c",
                    "-I" + str(ROOT / "harness/native_trace"), str(cpp),
                    "-o", str(tmp_path / "probe.o")], check=True, capture_output=True)
    subprocess.run([fortran, "-ffp-contract=off", "-ffree-line-length-none", "-c",
                    "-J" + str(tmp_path), str(ROOT / "harness/native_trace/kdm6ad_moment_trace_v2.f90"),
                    "-o", str(tmp_path / "writer.o")], check=True, capture_output=True)
    binary = tmp_path / "joined"
    runtime_link = ["-lstdc++"]
    if sys.platform == "darwin":
        sdk = subprocess.run(["xcrun", "--show-sdk-path"], check=True,
                             capture_output=True, text=True).stdout.strip()
        runtime_link = ["-Wl,-syslibroot," + sdk, "-L" + sdk + "/usr/lib", "-lc++"]
    subprocess.run([fortran, "-ffp-contract=off", "-ffree-line-length-none",
                    "-I" + str(tmp_path), str(main), str(tmp_path / "writer.o"),
                    str(tmp_path / "probe.o"), *runtime_link,
                    "-o", str(binary)], check=True, capture_output=True)
    trace = tmp_path / "trace"
    trace.mkdir()
    env = {**os.environ, "KDM6AD_MOMENT_TRACE_V2_DIR": str(trace)}
    subprocess.run([binary], env=env, check=True, capture_output=True)
    assert [line for line in (trace / "host.hex").read_text().splitlines() if line.startswith("CALL ")] == [
        line for line in (trace / "kernel.hex").read_text().splitlines() if line.startswith("CALL ")]
    inventory = read_moment_trace_v2(trace / "host.hex", trace / "kernel.hex")
    coverage = validate_moment_trace_v2(
        inventory, targets={"selected": (155, 25)}, levels=2,
        expected_call_count=2, expected_ncmin_land=10.0, expected_ncmin_sea=10.0,
        expected_global_shape=(234, 2, 282), require_complete=True)
    assert coverage.complete
    assert coverage.calls_without_kernel_witness == (2,)
    assert len(inventory.values) == 2 * 2 * 9
    assert inventory.values[(1, "MOMENTS_POST", 155, 1, 25, "QC")].value == 221.0
    assert inventory.values[(1, "FP64_INPUT", 155, 2, 25, "NC")].value == -222.0
