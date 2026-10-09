#!/usr/bin/env python3
"""Compile and run bounded, one-rank MPI Init/Finalize controls."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

HERE = Path(__file__).resolve().parent
OBSERVER = Path(
    "/private/tmp/KDM6AD-review388389-resolution-20261008/"
    "graphify-out/review-local/exit_observer/observer.dylib"
)
OBSERVER_SOURCE = OBSERVER.with_name("observer.c")
EXPECTED_OBSERVER_SHA256 = "2dea399e011af3101b7d024b58515ffa2402a6c9394601d7bf6f3407024a16da"
MPI_F90 = "/opt/homebrew/bin/mpif90"
MPI_RUN = "/opt/homebrew/bin/mpirun"
FORTRAN_FLAGS = [
    "-O2", "-ftree-vectorize", "-funroll-loops", "-w", "-ffree-form", "-ffree-line-length-none", "-fconvert=big-endian",
    "-ffp-contract=off",
    "-frecord-marker=4", "-fallow-argument-mismatch", "-fallow-invalid-boz",
]
TIMEOUT_SECONDS = 20
OUT = HERE / "runs"
NATIVE_ROOT = Path("/private/tmp/KDM6AD-viirs-native-run-20261007/isolated_project")
NATIVE_HOST = NATIVE_ROOT / "host/KIM-meso_v1.0"
NATIVE_WRF = NATIVE_HOST / "main/wrf.exe"
NATIVE_CONFIG = NATIVE_HOST / "configure.wrf"
KDM6_LIB = NATIVE_ROOT / "libtorch/install/lib/libkdm6_c.2.0.0.dylib"
EXPECTED_NATIVE_WRF_SHA256 = "f467755ee9952dc2b1806e9dec3220689e2f26a2939234b0959065b1c357cd41"
EXPECTED_KDM6_SHA256 = "64cddefe4fce336a7b9a3979278692324a97a17fe7d5264224bcc05a7f20be2d"
TORCH_LIB_DIR = Path("/private/tmp/KDM6AD-research-rc-20261007/env/lib/python3.10/site-packages/torch/lib")
TORCH_LIBS = [TORCH_LIB_DIR / name for name in ("libtorch.dylib", "libtorch_cpu.dylib", "libc10.dylib")]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def run(command: list[str], *, cwd: Path, env: dict[str, str], log: Path) -> dict:
    start = time.monotonic()
    timed_out = False
    with log.open("w") as stream:
        process = subprocess.Popen(
            command, cwd=cwd, env=env, stdout=stream,
            stderr=subprocess.STDOUT, start_new_session=True,
        )
        try:
            returncode = process.wait(timeout=TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                returncode = process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                returncode = process.wait(timeout=3)
    return {
        "command": command,
        "cwd": str(cwd),
        "deadline_seconds": TIMEOUT_SECONDS,
        "elapsed_seconds": round(time.monotonic() - start, 6),
        "returncode": returncode,
        "timed_out": timed_out,
        "process_status": "deadline_terminated" if timed_out else ("success" if returncode == 0 else "nonzero_exit"),
        "log": str(log),
        "log_sha256": sha256(log),
    }


def main() -> int:
    if sha256(OBSERVER) != EXPECTED_OBSERVER_SHA256:
        raise SystemExit("original observer dylib hash mismatch; refusing to run")
    if sha256(NATIVE_WRF) != EXPECTED_NATIVE_WRF_SHA256 or sha256(KDM6_LIB) != EXPECTED_KDM6_SHA256:
        raise SystemExit("historical native WRF or KDM6 library hash mismatch; refusing to run")
    if not MPI_F90 or not Path(MPI_F90).is_file() or not Path(MPI_RUN).is_file():
        raise SystemExit("expected host Open MPI compiler or launcher is unavailable")

    pinned_inputs = {
        str(path): sha256(path)
        for path in (OBSERVER_SOURCE, OBSERVER, NATIVE_WRF, KDM6_LIB)
    }

    OUT.mkdir(exist_ok=True)
    source = HERE / "mpi_finalize_control.f90"
    # Homebrew GCC currently defaults to an SDK directory removed by an Xcode
    # update. Use the active SDK explicitly; host configure.wrf's flags remain
    # unchanged.
    sdkroot = subprocess.check_output(["xcrun", "--show-sdk-path"], text=True).strip()
    results = []
    for label in (
        "plain_without_observer", "plain_with_observer",
        "nativehostlib_without_observer", "nativehostlib_with_observer",
    ):
        case = OUT / label
        case.mkdir(exist_ok=True)
        executable = case / "wrf.exe"
        compile_command = [MPI_F90, *FORTRAN_FLAGS, str(source), "-o", str(executable)]
        uses_host_libraries = label.startswith("nativehostlib_")
        if uses_host_libraries:
            if not KDM6_LIB.exists() or not all(lib.is_file() for lib in TORCH_LIBS):
                raise SystemExit("configured KDM6AD/libtorch runtime libraries are unavailable")
            compile_command.extend([
                f"-Wl,-rpath,@loader_path/../../../libtorch/install/lib",
            f"-Wl,-rpath,{KDM6_LIB.parent}",
                f"-Wl,-rpath,{TORCH_LIB_DIR}",
                str(KDM6_LIB), *(str(lib) for lib in TORCH_LIBS),
            ])
        compile_env = os.environ.copy()
        compile_env["SDKROOT"] = sdkroot
        compiled = run(compile_command, cwd=case, env=compile_env, log=case / "compile.log")
        compile_record = {
            "command": compile_command,
            "returncode": compiled["returncode"],
            "timed_out": compiled["timed_out"],
            "log": compiled["log"],
            "log_sha256": compiled["log_sha256"],
        }
        if compiled["returncode"] != 0 or compiled["timed_out"]:
            results.append({"label": label, "compile": compile_record, "run": None})
            break

        env = os.environ.copy()
        env.update({
            "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
            "OMP_THREAD_LIMIT": "1", "VECLIB_MAXIMUM_THREADS": "1",
            "SDKROOT": sdkroot,
        })
        uses_observer = label.endswith("with_observer")
        if uses_observer:
            env["DYLD_INSERT_LIBRARIES"] = str(OBSERVER)
        else:
            env.pop("DYLD_INSERT_LIBRARIES", None)
        if uses_host_libraries:
            env["DYLD_PRINT_LIBRARIES"] = "1"
        launch_command = [MPI_RUN, "-np", "1", str(executable)]
        launched = run(launch_command, cwd=case, env=env, log=case / "run.log")
        launched.update({
            "executable_sha256": sha256(executable),
            "observer_env": str(OBSERVER) if uses_observer else None,
            "linked_host_library_load_commands": subprocess.check_output(
                ["otool", "-L", str(executable)], text=True
            ).splitlines()[1:] if uses_host_libraries else [],
            "observed_events": [line.strip() for line in (case / "run.log").read_text(errors="replace").splitlines()
                                if "MPI_CONTROL" in line or "KDM_EXIT_OBSERVER" in line or "libkdm6" in line or "libtorch" in line or "libc10" in line],
        })
        results.append({"label": label, "compile": compile_record, "run": launched})

    direct_controls = []
    for label, observer_enabled in (("direct_without_observer", False), ("direct_with_observer", True)):
        case = OUT / ("plain_with_observer" if observer_enabled else "plain_without_observer")
        env = os.environ.copy()
        env.update({
            "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
            "OMP_THREAD_LIMIT": "1", "VECLIB_MAXIMUM_THREADS": "1",
            "SDKROOT": sdkroot,
        })
        if observer_enabled:
            env["DYLD_INSERT_LIBRARIES"] = str(OBSERVER)
        else:
            env.pop("DYLD_INSERT_LIBRARIES", None)
        direct = run([str(case / "wrf.exe")], cwd=case, env=env, log=OUT / f"{label}.log")
        direct["launch_mode"] = "direct Open MPI singleton; no mpirun parent"
        direct["observer_env"] = str(OBSERVER) if observer_enabled else None
        direct["observed_events"] = [line.strip() for line in (OUT / f"{label}.log").read_text(errors="replace").splitlines()
                                     if "MPI_CONTROL" in line or "KDM_EXIT_OBSERVER" in line]
        direct["direct_child_wait_status"] = direct["returncode"]
        direct_controls.append({"label": label, "run": direct})

    receipt = {
        "schema": "bounded_fortran_mpi_finalize_control_v1",
        "scope": "one-rank standalone Fortran MPI_Init/MPI_Finalize controls; no WRF/model physics",
        "source": str(source),
        "source_sha256": sha256(source),
        "host_build_basis": {
            "configure": str(NATIVE_CONFIG),
            "compiler": MPI_F90,
            "launcher": MPI_RUN,
            "fortran_flags": FORTRAN_FLAGS,
            "configure_sha256": sha256(NATIVE_CONFIG),
            "runner_sha256": sha256(Path(__file__).resolve()),
            "rank_command_shape": [MPI_RUN, "-np", "1", "wrf.exe"],
            "host_runner": "/Users/yhlee/KDM6AD-k/harness/run_ss_case.py",
            "toolchain_environment_adjustment": f"SDKROOT={sdkroot}; the installed Homebrew GCC default SDK path is absent after the Xcode update",
            "historical_native_wrf_executable_sha256_before_and_after": sha256(NATIVE_WRF),
        },
        "observer": {
            "source": str(OBSERVER_SOURCE),
            "source_sha256": sha256(OBSERVER_SOURCE),
            "dylib": str(OBSERVER),
            "dylib_sha256": sha256(OBSERVER),
            "program_name_filter": "wrf.exe",
            "environment": "DYLD_INSERT_LIBRARIES set for the observer arm; Open MPI propagates it to launched rank",
        },
        "preserved_original_inputs": {
            "pins_before": pinned_inputs,
            "pins_after": {path: sha256(Path(path)) for path in pinned_inputs},
            "all_unchanged": all(sha256(Path(path)) == digest for path, digest in pinned_inputs.items()),
        },
        "host_libraries": {
            "kdm6": str(KDM6_LIB),
            "kdm6_sha256": sha256(KDM6_LIB.resolve()),
            "torch": [str(path) for path in TORCH_LIBS],
            "torch_sha256": {str(path): sha256(path) for path in TORCH_LIBS},
            "runtime_loader_tracing": "DYLD_PRINT_LIBRARIES=1 in hostlib arms",
            "historical_source": "/private/tmp/KDM6AD-viirs-native-run-20261007/isolated_project/libtorch/install/lib/libkdm6_c.2.0.0.dylib",
            "torch_runtime_source": str(TORCH_LIB_DIR),
            "historical_wrf_recorded_torch_rpath": str(TORCH_LIB_DIR),
            "operation": "Loaded from a linked MPI control binary; no KDM6AD entry point or physics call is made",
        },
        "controls": results,
        "direct_singleton_controls": direct_controls,
        "limitations": [
            "This validates a standalone Fortran MPI finalize/interpose and C _Exit forwarding path only; it does not establish WRF shutdown behavior.",
            "The observer has no rank-aware MPI launcher status interface; launcher exit code is recorded by this runner.",
            "MPI_INIT entry is marked before initialization, when a communicator rank is unavailable.",
        ],
    }
    outpath = HERE / "result.json"
    outpath.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({
        "result": str(outpath),
        "controls": [{
            "label": row["label"],
            "compile_returncode": row["compile"]["returncode"],
            "launcher_status": row["run"]["process_status"] if row["run"] else "not_run",
            "returncode": row["run"]["returncode"] if row["run"] else None,
            "events": row["run"]["observed_events"] if row["run"] else [],
        } for row in results],
        "direct_singleton_statuses": [{
            "label": row["label"],
            "direct_child_wait_status": row["run"]["direct_child_wait_status"],
            "events": row["run"]["observed_events"],
        } for row in direct_controls],
    }, indent=2))
    all_runs = [row["run"] for row in results] + [row["run"] for row in direct_controls]
    return 0 if all(run and run["returncode"] == 0 and not run["timed_out"] for run in all_runs) else 1


if __name__ == "__main__":
    raise SystemExit(main())
