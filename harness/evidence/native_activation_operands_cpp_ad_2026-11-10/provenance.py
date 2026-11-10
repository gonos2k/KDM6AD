"""Public, read-only provenance checks for the activation-operand packet."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
EVIDENCE = HERE.parent
EXPECTED_FILES = {
    "cpp/main.cpp", "executed_cpp/coordinator.cpp", "raw/cpp_result.json",
    "raw/activation_boundary.json", "raw/private_provenance.json",
    "raw/core_flags.make.gz", "raw/bridge_flags.make.gz",
    "raw/runner_flags.make.gz", "raw/core_cache.txt.gz",
    "raw/runner_cache.txt.gz", "raw/build_receipt.json", "raw/run_receipt.json",
}
ENVIRONMENT = {
    "KDM6AD_QNC_LIVE_GUARD": "1",
    "KDM6_ICE_FACTORIAL_MODE": "norm_actual",
    "KDM6_QR_TRANSPORT": "actual_departure",
    "MKL_NUM_THREADS": "1",
    "OMP_NUM_THREADS": "1",
    "OMP_THREAD_LIMIT": "1",
}


def need(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError(why)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def file_sha(path: Path) -> str:
    return sha(path.read_bytes())


def _new_activation_block_only(old_source: str, new_source: str) -> None:
    start = "    auto sw_ratio = torch::clamp(sw_percent / 0.48, /*min=*/0.0);"
    end = "    // SEED#3 (Fortran module_mp_kdm6.F:2908):"
    need(old_source.count(start) == new_source.count(start) == 1,
         "activation coordinator source start anchor")
    need(old_source.count(end) == new_source.count(end) == 1,
         "activation coordinator source end anchor")
    old_prefix, old_rest = old_source.split(start, 1)
    new_prefix, new_rest = new_source.split(start, 1)
    old_mid, old_suffix = old_rest.split(end, 1)
    new_mid, new_suffix = new_rest.split(end, 1)
    need(old_prefix == new_prefix and old_suffix == new_suffix,
         "instrumented coordinator changes only activation block")
    need(old_mid != new_mid, "activation operand taps actually added")
    need(new_mid.count("ops::safe_pow(sw_ratio, constants::ACTK)") == 1,
         "one live activation safe_pow call")
    need("auto activated_fraction = torch::minimum(activation_fraction_one, activation_fraction_pow);"
         in new_mid, "captured pow tensor consumed by first minimum")
    need("auto ncact_min_output = torch::minimum(ncact_raw, ncact_nccn_rate_cap);"
         in new_mid, "captured rate-cap tensor consumed by second minimum")
    need("auto ncact = ncact_min_output;" in new_mid,
         "captured pre-gate minimum consumed by activation gate")
    need(all(token not in new_mid for token in (".detach()", ".item()", "NoGradGuard", "no_grad")),
         "activation taps preserve the live AD graph")


def verify_provenance() -> dict[str, object]:
    """Check packaged bytes, public parent pins, source scope and build/run records."""
    manifest = json.loads((HERE / "manifest.json").read_text())
    need(manifest["schema"] == "kdm6.native_activation_operands_cpp_ad_packet.v1",
         "activation operand manifest schema")
    files = manifest["files"]
    need(set(files) == EXPECTED_FILES, "activation operand manifest inventory")
    for relative, expected in files.items():
        path = HERE / relative
        need(path.is_file() and file_sha(path) == expected,
             "activation operand manifest SHA: " + relative)

    build = json.loads((HERE / "raw/build_receipt.json").read_text())
    run = json.loads((HERE / "raw/run_receipt.json").read_text())
    private = json.loads((HERE / "raw/private_provenance.json").read_text())
    need(build["schema"] == "kdm6.native_activation_operands_cpp_ad_build.v1",
         "activation operand build receipt schema")
    need(run["schema"] == "kdm6.native_activation_operands_cpp_ad_run.v1",
         "activation operand run receipt schema")
    need(private["schema"] == "kdm6.native_d1_activation_boundary_operands.private_run.v1",
         "activation operand private provenance schema")
    need(build["parent_research_merge_commit"]
         == "26c95d4e9e15271d19c178e35868fd8db450cd42",
         "activation operand #575 source tree pin")
    need(build["commands"] == private["build"],
         "activation operand build/private receipt agreement")
    pins = build["sha256"]
    public_paths = {
        "new_coordinator": HERE / "executed_cpp/coordinator.cpp",
        "old_coordinator": EVIDENCE / "native_d1_coeres_upstream_cpp_ad_2026-11-10/executed_cpp/coordinator.cpp",
        "new_runner": HERE / "cpp/main.cpp",
        "old_runner": EVIDENCE / "native_activation_upper_boundary_cpp_ad_2026-11-10/cpp/main.cpp",
        "input_binary": EVIDENCE / "native_pre2_input_cpp_ad_2026-11-08/raw/input.bin",
        "parent_boundary": EVIDENCE / "native_activation_upper_boundary_cpp_ad_2026-11-10/raw/activation_boundary.json",
        "parent_cpp_result": EVIDENCE / "native_d1_thermal_input_cpp_ad_2026-11-10/raw/cpp_result.json",
        "new_boundary": HERE / "raw/activation_boundary.json",
        "new_cpp_result": HERE / "raw/cpp_result.json",
        "core_flags": HERE / "raw/core_flags.make.gz",
        "bridge_flags": HERE / "raw/bridge_flags.make.gz",
        "runner_flags": HERE / "raw/runner_flags.make.gz",
        "core_cache": HERE / "raw/core_cache.txt.gz",
        "runner_cache": HERE / "raw/runner_cache.txt.gz",
        "private_provenance": HERE / "raw/private_provenance.json",
    }
    for name, path in public_paths.items():
        need(file_sha(path) == pins[name], "activation operand build source/input SHA: " + name)
    source_pins = private["source_pins"]
    for name, public_name in (
        ("coordinator_preinstrumentation_sha256", "old_coordinator"),
        ("coordinator_instrumented_sha256", "new_coordinator"),
        ("runner_instrumented_sha256", "new_runner"),
        ("input_sha256", "input_binary"),
        ("parent_cpp_result_sha256", "parent_cpp_result"),
        ("parent_activation_boundary_sha256", "parent_boundary"),
    ):
        need(source_pins[name] == pins[public_name],
             "activation operand private/public source pin: " + name)
    for name, private_name in (
        ("new_core_archive", "archive_sha256"),
        ("new_core_dso", "c_abi_dylib_sha256"),
        ("new_runner_executable", "runner_sha256"),
    ):
        need(pins[name] == private["build"][private_name],
             "activation operand private/public binary pin: " + name)

    old_source = public_paths["old_coordinator"].read_text()
    new_source = public_paths["new_coordinator"].read_text()
    _new_activation_block_only(old_source, new_source)
    for name in ("core_flags", "bridge_flags", "runner_flags"):
        flags = gzip.decompress(public_paths[name].read_bytes()).decode()
        need("-ffp-contract=off" in flags and "-std=" in flags,
             "activation operand C++ flags: " + name)
        if name == "runner_flags":
            need("-DNDEBUG" not in flags, "activation operand runner assertions enabled")
    core_cache = gzip.decompress(public_paths["core_cache"].read_bytes()).decode()
    runner_cache = gzip.decompress(public_paths["runner_cache"].read_bytes()).decode()
    need("KDM6_NATIVE_SCALAR_CAPTURE:BOOL=ON" in core_cache
         and "CMAKE_BUILD_TYPE:STRING=Release" in core_cache,
         "activation operand isolated core build cache")
    need("CMAKE_BUILD_TYPE:STRING=" in runner_cache
         and "CMAKE_BUILD_TYPE:STRING=Release" not in runner_cache,
         "activation operand runner assertions build cache")

    need(run["environment"] == ENVIRONMENT
         and private["run_environment"] == ENVIRONMENT,
         "activation operand controlled run environment")
    need(run["returncodes"] == {"default_noninterference": 0,
                                  "activation_operands_boundary": 0},
         "activation operand run return codes")
    need(run["commands"] == {key: value["command"]
                              for key, value in private["runs"].items()},
         "activation operand run command receipt agreement")
    need(run["output_sha256"] == {"default": pins["new_cpp_result"],
                                    "boundary": pins["new_boundary"]},
         "activation operand run output SHA agreement")
    need(run["input_sha256"] == pins["input_binary"]
         and run["runner_sha256"] == pins["new_runner_executable"]
         and run["archive_sha256"] == pins["new_core_archive"],
         "activation operand executed binary/input pins")
    need(run["full_call_forwards"] == {"default": 2, "boundary": 190},
         "activation operand full-call execution counts")
    need(private["runs"]["activation_operands_boundary"]["output_sha256"]
         == pins["new_boundary"]
         and private["runs"]["default_noninterference"]["output_sha256"]
         == pins["new_cpp_result"],
         "activation operand private output hashes")
    return {
        "manifest_files_verified": len(files),
        "coordinator_source_scoped": True,
        "runner_assertions_enabled": True,
        "recorded_core_archive_sha256": pins["new_core_archive"],
        "recorded_runner_sha256": pins["new_runner_executable"],
    }
