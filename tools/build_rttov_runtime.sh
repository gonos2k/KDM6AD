#!/bin/sh
# Build the self-contained, project-local RTTOV execution bundle.
#
# The bundle (<repo>/rttov_runtime/) lets the all-sky cloud path run WITHOUT the
# external AD-RTTOV source tree: it carries the prebuilt rttov_test.exe, the AMI
# coef + hydrotable, and the ami/501 (clear) + ami/cloud (all-sky) fixture cases,
# with the baked-in absolute paths (exe path in out/run.sh, coef_prefix in
# out/rttov_test.txt) rewritten to the bundle. kdm6.obs.rttov_runner.rttov_runtime_root()
# discovers it; the fixture resolvers prefer it and fall back to AD_RTTOV_HOME.
#
# It is NOT a full source build: the copied exe still dynamically links the system
# dylibs (MacPorts libnetcdf*/Homebrew gcc libgfortran/libgomp/libquadmath) -- those
# must be present. The bundle is gitignored (~12 MB of binaries); rerun this script
# after a fresh clone or an AD-RTTOV coef/exe update.
#
# Usage: tools/build_rttov_runtime.sh [AD_RTTOV_HOME]
#   AD_RTTOV_HOME defaults to $AD_RTTOV_HOME or /Users/yhlee/AD-RTTOV.
set -eu

AD="${1:-${AD_RTTOV_HOME:-/Users/yhlee/AD-RTTOV}}"
SRC="$AD/external/rttov14/src"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
RT="$REPO/rttov_runtime"

EXE="$SRC/bin/rttov_test.exe"
COEF="$SRC/rtcoef_rttov14/rttov13pred54L/rtcoef_gkompsat2_1_ami_o3co2.dat"
HYDRO="$SRC/rtcoef_rttov14/hydrotable_visir/rttov_hydrotable_gkompsat2_1_ami.dat"
FIX="$SRC/rttov_test/tests.1.gfortran-openmp/ami"

for f in "$EXE" "$COEF" "$HYDRO" "$FIX/501" "$FIX/cloud"; do
  [ -e "$f" ] || { echo "ERROR: missing source asset: $f" >&2; exit 1; }
done

echo "Building $RT from $SRC ..."
rm -rf "$RT"
mkdir -p "$RT/bin" \
         "$RT/rtcoef/rtcoef_rttov14/rttov13pred54L" \
         "$RT/rtcoef/rtcoef_rttov14/hydrotable_visir" \
         "$RT/cases/ami"
cp -p  "$EXE"   "$RT/bin/"
cp -p  "$COEF"  "$RT/rtcoef/rtcoef_rttov14/rttov13pred54L/"
cp -p  "$HYDRO" "$RT/rtcoef/rtcoef_rttov14/hydrotable_visir/"
cp -Rp "$FIX/501"   "$RT/cases/ami/501"
cp -Rp "$FIX/cloud" "$RT/cases/ami/cloud"

# Rewrite the baked-in absolute paths in each fixture to the project-local bundle.
RT="$RT" python3 - <<'PY'
import os, re
from pathlib import Path
RT = Path(os.environ["RT"])
exe = str(RT / "bin" / "rttov_test.exe")
coef_prefix = str(RT / "rtcoef")
for case in ("501", "cloud"):
    out = RT / "cases" / "ami" / case / "out"
    rs = out / "run.sh"
    txt, n = re.subn(r"\S+rttov_test\.exe", exe, rs.read_text())
    assert n == 1, f"{rs}: expected 1 exe path, found {n}"
    rs.write_text(txt)
    rt_txt = out / "rttov_test.txt"
    t, m = re.subn(r"(?m)^(\s*defn%coef_prefix\s*=\s*)'[^']*'", rf"\g<1>'{coef_prefix}'", rt_txt.read_text())
    assert m == 1, f"{rt_txt}: expected 1 coef_prefix, found {m}"
    rt_txt.write_text(t)
    print(f"  patched ami/{case}: exe + coef_prefix")
PY

# Provenance manifest (sizes + md5 of the heavy binary assets).
{
  echo "# rttov_runtime MANIFEST (provenance)"
  echo "# built from: $SRC"
  echo "# host: $(uname -srm)"
  echo
  for rel in bin/rttov_test.exe \
             rtcoef/rtcoef_rttov14/rttov13pred54L/rtcoef_gkompsat2_1_ami_o3co2.dat \
             rtcoef/rtcoef_rttov14/hydrotable_visir/rttov_hydrotable_gkompsat2_1_ami.dat; do
    md5 -r "$RT/$rel" 2>/dev/null || md5sum "$RT/$rel"
  done
} > "$RT/MANIFEST.txt"

echo "Done. Bundle size: $(du -sh "$RT" | cut -f1)"
echo "Verify shared libs are present:"
otool -L "$RT/bin/rttov_test.exe" 2>/dev/null | sed -n '2,7p' || true
