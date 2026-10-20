from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from harness.native_trace_overlay import SOURCE_OVERLAYS, patch_host_root


def _synthetic_host(root: Path) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for overlay in SOURCE_OVERLAYS:
        path = root / overlay.relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"  {overlay.insertions[0].scope_start}fixture("]
        for insertion in overlay.insertions:
            lines.extend(insertion.anchor)
        lines.append(f"  {overlay.insertions[0].scope_end}")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        paths[overlay.relative_path] = path
    return paths


def test_overlay_is_check_only_by_default_and_apply_is_idempotent(tmp_path):
    paths = _synthetic_host(tmp_path)
    before = {name: path.read_bytes() for name, path in paths.items()}

    checked = patch_host_root(tmp_path)

    assert checked["status"] == "ready"
    assert all(paths[name].read_bytes() == value for name, value in before.items())

    applied = patch_host_root(tmp_path, apply=True)
    repeated = patch_host_root(tmp_path, apply=True)

    assert applied["status"] == "applied"
    assert repeated["status"] == "already_applied"
    for path in paths.values():
        text = path.read_text(encoding="utf-8")
        assert "CALL trace_set_step(ITIMESTEP)" in text or "trace_record('FINISH_PRE'" in text


@pytest.mark.parametrize("comment_patched", [False, True], ids=["commented-old", "commented-new"])
def test_comment_only_anchor_or_patch_cannot_pass_preflight(tmp_path, comment_patched):
    paths = _synthetic_host(tmp_path)
    target_overlay = SOURCE_OVERLAYS[0]
    target = target_overlay.insertions[3]  # The exact post-pack finite-check anchor.
    target_path = paths[target_overlay.relative_path]
    lines = target_path.read_text(encoding="utf-8").splitlines()

    # Keep the procedure and every other anchor valid, but replace this target
    # with a commented old/new context and a different active call line.
    target_index = next(i for i in range(len(lines)) if lines[i] == target.anchor[0])
    commented_lines = target.replacement if comment_patched else target.anchor
    comment_block = ["!" + line for line in commented_lines]
    alternate = target.anchor[0] + " ! active alternate; not the selected anchor"
    lines[target_index:target_index + 1] = comment_block + [alternate]
    target_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    before = {name: path.read_bytes() for name, path in paths.items()}

    report = patch_host_root(tmp_path, apply=True)

    assert report["status"] == "refused"
    assert all(paths[name].read_bytes() == value for name, value in before.items())


def test_overlay_rejects_drifted_anchor_without_changing_either_file(tmp_path):
    paths = _synthetic_host(tmp_path)
    wrapper = paths[SOURCE_OVERLAYS[0].relative_path]
    wrapper.write_text(
        wrapper.read_text(encoding="utf-8").replace(
            SOURCE_OVERLAYS[0].insertions[2].anchor[0],
            "    IM = ITE - ITS + 2",
            1,
        ),
        encoding="utf-8",
    )
    before = {name: path.read_bytes() for name, path in paths.items()}

    report = patch_host_root(tmp_path, apply=True)

    assert report["status"] == "refused"
    assert all(paths[name].read_bytes() == value for name, value in before.items())


def test_fortran_writer_disabled_and_raw_float32_hex(tmp_path):
    compiler = shutil.which("gfortran")
    if compiler is None:
        pytest.skip("gfortran is unavailable; standalone Fortran writer smoke was not run")

    module_path = Path(__file__).parents[1] / "native_trace" / "kdm6ad_native_trace.f90"
    driver_path = tmp_path / "trace_smoke.f90"
    executable = tmp_path / "trace_smoke"
    driver_path.write_text(
        """program trace_smoke
  use, intrinsic :: iso_fortran_env, only: real32, int32
  use kdm6ad_native_trace
  implicit none
  real(real32) :: values(3)
  values(1) = 1.0_real32
  values(2) = transfer(int(z'80000000', int32), 0.0_real32)
  values(3) = transfer(int(z'3F800001', int32), 0.0_real32)
  call trace_set_step(7)
  if (trace_enabled) then
    print '(A)', 'TRACE_ENABLED=T'
  else
    print '(A)', 'TRACE_ENABLED=F'
  end if
  call trace_record('KNOWN', 7, 156, 3, 21, values)
end program trace_smoke
""",
        encoding="utf-8",
    )
    module_object = tmp_path / "kdm6ad_native_trace.o"
    driver_object = tmp_path / "trace_smoke.o"
    subprocess.run(
        [compiler, "-ffp-contract=off", "-J", str(tmp_path), "-c", str(module_path), "-o", str(module_object)],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [compiler, "-ffp-contract=off", "-I", str(tmp_path), "-c", str(driver_path), "-o", str(driver_object)],
        check=True,
        capture_output=True,
        text=True,
    )
    link_env = os.environ.copy()
    if "SDKROOT" not in link_env and sys.platform == "darwin":
        xcrun = shutil.which("xcrun")
        if xcrun is not None:
            sdk = subprocess.run([xcrun, "--show-sdk-path"], capture_output=True, text=True)
            if sdk.returncode == 0 and sdk.stdout.strip():
                link_env["SDKROOT"] = sdk.stdout.strip()
    link = subprocess.run(
        [compiler, str(module_object), str(driver_object), "-o", str(executable)],
        capture_output=True,
        text=True,
        env=link_env,
    )
    if link.returncode:
        if "SDKROOT" not in link_env and sys.platform == "darwin" and "library 'System' not found" in link.stderr:
            pytest.skip(f"Fortran module and caller compile, but macOS system linker runtime is unavailable: {link.stderr.strip()}")
        pytest.fail(f"Fortran trace smoke link failed: {link.stderr.strip()}")

    disabled_path = tmp_path / "disabled.trace"
    disabled_env = os.environ.copy()
    disabled_env.pop("KDM6AD_NATIVE_TRACE_FILE", None)
    disabled_run = subprocess.run([str(executable)], check=True, env=disabled_env, capture_output=True, text=True)
    assert "TRACE_ENABLED=F" in disabled_run.stdout
    assert not disabled_path.exists()

    trace_path = tmp_path / "enabled.trace"
    enabled_env = os.environ.copy()
    enabled_env["KDM6AD_NATIVE_TRACE_FILE"] = str(trace_path)
    enabled_env["KDM6AD_NATIVE_TRACE_I"] = "156"
    enabled_env["KDM6AD_NATIVE_TRACE_J"] = "21"
    enabled_run = subprocess.run([str(executable)], check=True, env=enabled_env, capture_output=True, text=True)
    assert "TRACE_ENABLED=T" in enabled_run.stdout
    lines = trace_path.read_text(encoding="ascii").splitlines()
    rows = [line for line in lines if line and not line.startswith("#")]
    assert lines[0].startswith("# KDM6AD_NATIVE_TRACE_V1 ")
    assert rows == ["KNOWN 7 156 3 21 3 3F800000 80000000 3F800001"]
