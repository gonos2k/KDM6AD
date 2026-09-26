#!/usr/bin/env python3
"""Verify S9 manifest structure, semantic edges, receipts, and retained bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA = Path(__file__).resolve().parent / "evidence" / "s9_source_build_manifest.schema.json"
REQUIRED_RELATIONS = (
    "preprocesses_to", "compiles_to", "archives_into", "links_into",
    "installs_as", "resolves_to",
)
RELATION_STEP_KIND = {
    "preprocesses_to": "preprocess", "compiles_to": "compile",
    "archives_into": "archive", "links_into": "link",
    "installs_as": "install", "resolves_to": "loader_inspection",
}
KDM6_OBJECTS = (
    "module_mp_kdm6.o", "module_mp_kdm6_cons.o", "module_mp_kdm6ad.o",
    "module_mp_kdm6ad_cons.o", "kdm6_iso_c.o", "module_microphysics_driver.o",
)
SOURCE_FOR_OBJECT = {Path(name).stem + ".F": name for name in KDM6_OBJECTS if name != "kdm6_iso_c.o"}
SOURCE_FOR_OBJECT["kdm6_iso_c.f90"] = "kdm6_iso_c.o"
CPP_CORE_SOURCES = (
    "libtorch/src/ops.cpp",
    "libtorch/src/slope.cpp",
    "libtorch/src/progb.cpp",
    "libtorch/src/warm.cpp",
    "libtorch/src/satadj.cpp",
    "libtorch/src/cold.cpp",
    "libtorch/src/melt_freeze.cpp",
    "libtorch/src/sedimentation.cpp",
    "libtorch/src/sedimentation_conservative.cpp",
    "libtorch/src/thermo.cpp",
    "libtorch/src/state.cpp",
    "libtorch/src/runtime.cpp",
    "libtorch/src/coordinator.cpp",
    "libtorch/src/cloud_dsd.cpp",
)
CPP_BRIDGE_SOURCE = "libtorch/bridge/kdm6_c_api.cpp"
CPP_CORE_OBJECTS = tuple(Path(path).name + ".o" for path in CPP_CORE_SOURCES)
CAPTURE_TOOL_PATH = "harness/capture_s9_dyld.py"
CAPTURE_TOOL_SHA256 = "03426c9df0e849ad6fcbd3820eb7f7fc872a15e725039e2bb4f935100a6d9569"
CAPTURE_ENV_ALLOWLIST = {
    "PATH", "DYLD_PRINT_LIBRARIES", "DYLD_PRINT_RPATHS", "DYLD_LIBRARY_PATH",
    "DYLD_FALLBACK_LIBRARY_PATH", "DYLD_FRAMEWORK_PATH", "DYLD_FALLBACK_FRAMEWORK_PATH",
    "DYLD_INSERT_LIBRARIES", "SDKROOT", "MACOSX_DEPLOYMENT_TARGET", "OMP_NUM_THREADS",
    "MKL_NUM_THREADS", "OMP_THREAD_LIMIT",
}
CAPTURE_PATH_ENV = {
    "PATH", "DYLD_LIBRARY_PATH", "DYLD_FALLBACK_LIBRARY_PATH", "DYLD_FRAMEWORK_PATH",
    "DYLD_FALLBACK_FRAMEWORK_PATH", "DYLD_INSERT_LIBRARIES", "SDKROOT",
}
CAPTURE_ENV_ALLOWLIST = {
    "PATH", "DYLD_PRINT_LIBRARIES", "DYLD_PRINT_RPATHS", "DYLD_LIBRARY_PATH",
    "DYLD_FALLBACK_LIBRARY_PATH", "DYLD_FRAMEWORK_PATH", "DYLD_FALLBACK_FRAMEWORK_PATH",
    "DYLD_INSERT_LIBRARIES", "SDKROOT", "MACOSX_DEPLOYMENT_TARGET", "OMP_NUM_THREADS",
    "MKL_NUM_THREADS", "OMP_THREAD_LIMIT",
}
CAPTURE_PATH_ENV = {
    "PATH", "DYLD_LIBRARY_PATH", "DYLD_FALLBACK_LIBRARY_PATH", "DYLD_FRAMEWORK_PATH",
    "DYLD_FALLBACK_FRAMEWORK_PATH", "DYLD_INSERT_LIBRARIES", "SDKROOT",
}


def _public_capture_environment(raw: dict[str, str]) -> dict[str, str]:
    return {
        key: f"<redacted-path-sha256:{hashlib.sha256(raw[key].encode()).hexdigest()}>" if key in CAPTURE_PATH_ENV else raw[key]
        for key in sorted(raw)
    }


def _public_capture_argv(manifest_id: str, exe_id: str, library_id: str) -> list[str]:
    return [
        CAPTURE_TOOL_PATH, "--root", "<BUILD_ROOT>", "--manifest-id", manifest_id,
        "--executable", "<WRF_EXE>", "--executable-id", exe_id,
        "--library", "<INSTALLED_KDM6_C_ABI_DYLIB>", "--library-id", library_id,
        "--cwd", "<RUN_DIR>", "--launcher", "<MPI_LAUNCHER>",
        "--receipt", "<PUBLIC_CAPTURE_RECEIPT>", "--private-receipt", "<PRIVATE_RAW_RECEIPT>",
        "--stdout", "<PRIVATE_STDOUT>", "--stderr", "<PRIVATE_STDERR>",
    ]


def _key(ref: dict[str, Any]) -> tuple[str, str, str]:
    return (ref.get("artifact_id", ""), ref.get("path", ""), ref.get("sha256", ""))


def _safe_rel(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and all(part not in ("", ".", "..") for part in path.parts)


def _suffix(value: str) -> str:
    return PurePosixPath(value).suffix.lower()


def _role_matches(role: str, path: str) -> bool:
    suffix = _suffix(path)
    if role == "fortran_source":
        return suffix in {".f", ".for", ".f90", ".f95", ".f03", ".f08"}
    if role == "c_source":
        return suffix == ".c"
    if role == "cpp_source":
        return suffix in {".cc", ".cpp", ".cxx"}
    if role == "header":
        return suffix in {".h", ".hh", ".hpp"}
    return True


def verify_manifest_semantics(manifest: dict[str, Any], root: Path | None = None) -> list[str]:
    """Require the declared six-edge graph to bind actual S9 artifacts/steps."""
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return ["manifest root must be an object"]

    artifacts = manifest.get("artifacts", [])
    if not isinstance(artifacts, list):
        return ["artifacts must be an array"]
    toolchain = manifest.get("toolchain", {})
    if isinstance(toolchain, dict):
        for name in ("compiler", "linker", "build_system", "mpi_launcher"):
            tool = toolchain.get(name, {})
            if isinstance(tool, dict) and not re.fullmatch(r"<[^<>/\\]+>", str(tool.get("path", ""))):
                errors.append(f"public toolchain.{name}.path must be a path-redacted alias")
    gate_identity = manifest.get("lineage_gate", {}).get("verifier", {}) if isinstance(manifest.get("lineage_gate"), dict) else {}
    if isinstance(gate_identity, dict) and not re.fullmatch(r"<[^<>/\\]+>", str(gate_identity.get("path", ""))):
        errors.append("public lineage_gate.verifier.path must be a path-redacted alias")
    by_id: dict[str, dict[str, Any]] = {}
    by_name: dict[str, list[dict[str, Any]]] = {}
    path_ids: dict[str, str] = {}
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            errors.append("artifact inventory contains a non-object")
            continue
        artifact_id, path = artifact.get("artifact_id"), artifact.get("path")
        if not isinstance(artifact_id, str) or not artifact_id:
            errors.append("artifact has missing/empty artifact_id")
            continue
        if artifact_id in by_id:
            errors.append(f"duplicate artifact_id: {artifact_id}")
        else:
            by_id[artifact_id] = artifact
        if not _safe_rel(path):
            errors.append(f"artifact path must be normalized and manifest-relative: {artifact_id}")
            continue
        if path in path_ids:
            errors.append(f"duplicate artifact path: {path} ({path_ids[path]}, {artifact_id})")
        else:
            path_ids[path] = artifact_id
        by_name.setdefault(PurePosixPath(path).name, []).append(artifact)
        kind = artifact.get("kind")
        expected_suffixes = {
            "object": {".o"}, "module_file": {".mod"}, "archive": {".a"},
            "executable": {".exe"}, "shared_library": {".dylib", ".so"},
            "receipt": {".log", ".txt", ".json"},
        }
        if kind in expected_suffixes and _suffix(path) not in expected_suffixes[kind]:
            errors.append(f"artifact kind/path mismatch: {kind} {path}")

    def inventory_ref(ref: Any, where: str) -> dict[str, Any] | None:
        if not isinstance(ref, dict):
            errors.append(f"{where} must be a full artifact reference")
            return None
        artifact = by_id.get(ref.get("artifact_id"))
        if artifact is None:
            errors.append(f"{where} references unknown artifact_id {ref.get('artifact_id')!r}")
            return None
        if _key(ref) != _key({k: artifact.get(k) for k in ("artifact_id", "path", "sha256")}):
            errors.append(f"{where} path/hash differs from inventory: {ref.get('artifact_id')!r}")
        return artifact

    source_tree = manifest.get("source_tree", {})
    source_files = source_tree.get("files", []) if isinstance(source_tree, dict) else []
    source_by_path: dict[str, dict[str, Any]] = {}
    source_ids: set[str] = set()
    for index, source in enumerate(source_files):
        artifact = inventory_ref(source, f"source_tree.files[{index}]")
        if artifact is None:
            continue
        path = source.get("path", "")
        if path in source_by_path:
            errors.append(f"duplicate source_tree path: {path}")
        source_by_path[path] = source
        source_ids.add(artifact["artifact_id"])
        if artifact.get("kind") != "source":
            errors.append(f"source_tree.files[{index}] must refer to kind=source")
        if not _role_matches(source.get("role", ""), path):
            errors.append(f"source role/path mismatch: {source.get('role')} {path}")
    source_by_basename: dict[str, list[dict[str, Any]]] = {}
    for source in source_files:
        if isinstance(source, dict) and isinstance(source.get("path"), str):
            source_by_basename.setdefault(PurePosixPath(source["path"]).name, []).append(source)

    steps = manifest.get("build_steps", [])
    if not isinstance(steps, list):
        errors.append("build_steps must be an array")
        steps = []
    step_ids: set[str] = set()
    receipts: set[str] = set()
    step_records: list[tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]] = []
    step_input_ids: set[str] = set()
    referenced_ids: set[str] = set(source_ids)
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append(f"build_steps[{index}] must be an object")
            continue
        step_id = step.get("step_id")
        if not isinstance(step_id, str) or not step_id or step_id in step_ids:
            errors.append(f"build_steps[{index}] has missing/duplicate step_id")
        if isinstance(step_id, str):
            step_ids.add(step_id)
        refs: dict[str, list[dict[str, Any]]] = {"inputs": [], "outputs": []}
        for side in ("inputs", "outputs"):
            entries = step.get(side, [])
            if not isinstance(entries, list):
                errors.append(f"build_steps[{index}].{side} must be an array")
                continue
            for j, ref in enumerate(entries):
                artifact = inventory_ref(ref, f"build_steps[{index}].{side}[{j}]")
                if artifact is not None:
                    refs[side].append(ref)
                    referenced_ids.add(artifact["artifact_id"])
                    if side == "inputs":
                        step_input_ids.add(artifact["artifact_id"])
        step_records.append((step, refs["inputs"], refs["outputs"]))
        if step.get("kind") == "loader_observation":
            receipts.update((step.get("stdout_sha256", ""), step.get("stderr_sha256", "")))
        else:
            for field in ("stdout_receipt", "stderr_receipt"):
                receipt = inventory_ref(step.get(field), f"build_steps[{index}].{field}")
                if receipt is not None:
                    if receipt.get("kind") != "receipt":
                        errors.append(f"build_steps[{index}].{field} must reference kind=receipt")
                    receipts.add(receipt.get("sha256", ""))
                    referenced_ids.add(receipt["artifact_id"])
        if step.get("capture_receipt") is not None:
            capture_receipt = inventory_ref(step["capture_receipt"], f"build_steps[{index}].capture_receipt")
            if capture_receipt is not None:
                if capture_receipt.get("kind") != "receipt":
                    errors.append(f"build_steps[{index}].capture_receipt must reference kind=receipt")
                receipts.add(capture_receipt.get("sha256", ""))
                referenced_ids.add(capture_receipt["artifact_id"])

    gate = manifest.get("lineage_gate", {})
    edges = gate.get("edge_results", []) if isinstance(gate, dict) else []
    if not isinstance(edges, list):
        errors.append("lineage_gate.edge_results must be an array")
        edges = []
    relations = [edge.get("relation") for edge in edges if isinstance(edge, dict)]
    if set(relations) != set(REQUIRED_RELATIONS):
        errors.append("edge_results must cover exactly the six required relation types")
    edge_keys: set[tuple[str, str, str]] = set()
    edge_nodes: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            errors.append(f"edge_results[{index}] must be an object")
            continue
        relation = edge.get("relation")
        source = inventory_ref(edge.get("from_artifact"), f"edge[{index}].from_artifact")
        target = inventory_ref(edge.get("to_artifact"), f"edge[{index}].to_artifact")
        if source is not None and target is not None:
            key = (relation, source["artifact_id"], target["artifact_id"])
            if key in edge_keys:
                errors.append(f"duplicate lineage edge: {key}")
            edge_keys.add(key)
            edge_nodes.append((edge, source, target))
            referenced_ids.update((source["artifact_id"], target["artifact_id"]))
        matching = [
            step for step, inputs, outputs in step_records
            if step.get("kind") == ("loader_observation" if relation == "resolves_to" and edge.get("status") == "proven" else RELATION_STEP_KIND.get(relation))
            and edge.get("from_artifact") in inputs
            and edge.get("to_artifact") in (inputs if relation == "resolves_to" else outputs)
            and edge.get("receipt_sha256") in (
                step.get("capture_receipt", {}).get("sha256")
                if relation == "resolves_to" and edge.get("status") == "proven"
                else step.get("stdout_receipt", {}).get("sha256"),
                step.get("stderr_receipt", {}).get("sha256"),
            )
        ]
        if len(matching) != 1:
            errors.append(f"edge[{index}] must match exactly one typed build step and its retained receipt")
        if edge.get("status") == "proven" and edge.get("receipt_sha256") not in receipts:
            errors.append(f"edge[{index}] receipt is not in the receipt artifact inventory")

    def edge_exists(relation: str, src_id: str, dst_id: str) -> bool:
        return any(e.get("relation") == relation and e.get("from_artifact", {}).get("artifact_id") == src_id and e.get("to_artifact", {}).get("artifact_id") == dst_id for e, _, _ in edge_nodes)

    # Every KDM6 Fortran object has its own source -> preprocessed source ->
    # object chain. Wrapper module dependencies describe build ordering only.
    object_by_name: dict[str, dict[str, Any]] = {}
    for name, objs in by_name.items():
        if len(objs) == 1:
            object_by_name[name] = objs[0]
    for source_name, object_name in SOURCE_FOR_OBJECT.items():
        source_list = source_by_basename.get(source_name, [])
        obj = object_by_name.get(object_name)
        if len(source_list) != 1 or source_list[0].get("role") != "fortran_source":
            errors.append(f"required KDM6 Fortran source missing/ambiguous: {source_name}")
            continue
        if obj is None or obj.get("kind") != "object":
            errors.append(f"required KDM6 object missing/ambiguous: {object_name}")
            continue
        source = source_list[0]
        if not PurePosixPath(source.get("path", "")).as_posix().endswith(f"phys/{source_name}"):
            errors.append(f"KDM6 source must come from phys/: {source_name}")
        if not PurePosixPath(obj.get("path", "")).as_posix().endswith(f"phys/{object_name}"):
            errors.append(f"KDM6 object must come from phys/: {object_name}")
        if PurePosixPath(source_name).suffix.lower() == ".f":
            generated = [a for a in artifacts if isinstance(a, dict) and a.get("kind") == "preprocessed_source" and PurePosixPath(a.get("path", "")).stem.lower() == PurePosixPath(source_name).stem.lower()]
            if len(generated) != 1:
                errors.append(f"source needs one same-stem preprocessed artifact: {source_name}")
                continue
            if not PurePosixPath(generated[0].get("path", "")).as_posix().endswith(f"phys/{PurePosixPath(source_name).stem}.f90"):
                errors.append(f"KDM6 preprocessed artifact must be the matching phys/*.f90: {source_name}")
            if not edge_exists("preprocesses_to", source["artifact_id"], generated[0]["artifact_id"]):
                errors.append(f"source lacks its preprocesses_to edge: {source_name}")
            if not edge_exists("compiles_to", generated[0]["artifact_id"], obj["artifact_id"]):
                errors.append(f"preprocessed source lacks its own compiles_to edge: {source_name}")
        elif not edge_exists("compiles_to", source["artifact_id"], obj["artifact_id"]):
            errors.append(f"Fortran source lacks its direct compiles_to edge: {source_name}")

    archive_list = [a for a in artifacts if isinstance(a, dict) and a.get("kind") == "archive" and PurePosixPath(a.get("path", "")).name == "libwrflib.a"]
    core_archive_list = [a for a in artifacts if isinstance(a, dict) and a.get("kind") == "archive" and a.get("path", "").endswith("libtorch/build/libkdm6.a")]
    installed_core_archive_list = [a for a in artifacts if isinstance(a, dict) and a.get("kind") == "archive" and a.get("path", "").endswith("libtorch/install/lib/libkdm6.a")]
    exe_list = [a for a in artifacts if isinstance(a, dict) and a.get("kind") == "executable" and PurePosixPath(a.get("path", "")).name == "wrf.exe"]
    if len(archive_list) != 1 or not PurePosixPath(archive_list[0].get("path", "")).as_posix().endswith("main/libwrflib.a"):
        errors.append("inventory must identify exactly one main/libwrflib.a")
    if len(exe_list) != 1 or not PurePosixPath(exe_list[0].get("path", "")).as_posix().endswith("main/wrf.exe"):
        errors.append("inventory must identify exactly one main/wrf.exe")
    def check_archive(archive: dict[str, Any], name: str, expected_members: set[str], require_member_edges: bool, exact: bool) -> set[str]:
        members = archive.get("archive_members", [])
        member_names: set[str] = set()
        member_name_list: list[str] = []
        for j, ref in enumerate(members):
            member = inventory_ref(ref, f"{name}.archive_members[{j}]")
            if member is None:
                continue
            if member.get("kind") != "object":
                errors.append(f"{name} member is not an object: {member.get('path')}")
            member_names.add(PurePosixPath(member.get("path", "")).name)
            member_name_list.append(PurePosixPath(member.get("path", "")).name)
            referenced_ids.add(member["artifact_id"])
        missing = sorted(expected_members - member_names)
        if missing:
            errors.append(f"{name} archive member inventory omits required objects: {', '.join(missing)}")
        if exact and member_names != expected_members:
            extra = sorted(member_names - expected_members)
            if extra:
                errors.append(f"{name} archive member inventory has unexpected objects: {', '.join(extra)}")
        physical = archive.get("member_inventory", [])
        if exact:
            physical_objects = [
                {"name": row.get("name"), "sha256": row.get("sha256")}
                for row in physical
                if isinstance(row, dict) and row.get("name") not in {"__.SYMDEF", "__.SYMDEF SORTED"}
            ]
            declared_objects = [
                {"name": PurePosixPath(ref.get("path", "")).name, "sha256": ref.get("sha256")}
                for ref in members
                if isinstance(ref, dict)
            ]
            if physical_objects != declared_objects or len(members) != len(expected_members):
                errors.append(f"{name} archive_members must exactly match physical object members in order and multiplicity")
            symbol_tables = [row for row in physical if isinstance(row, dict) and row.get("name") in {"__.SYMDEF", "__.SYMDEF SORTED"}]
            if len(symbol_tables) > 1:
                errors.append(f"{name} physical inventory contains duplicate archive symbol tables")
        physical_pairs = Counter((row.get("name"), row.get("sha256")) for row in physical if isinstance(row, dict))
        used_pairs: Counter = Counter()
        for ref in members:
            key = (PurePosixPath(ref.get("path", "")).name, ref.get("sha256"))
            used_pairs[key] += 1
            if used_pairs[key] > physical_pairs[key]:
                errors.append(f"{name} source/object member is absent from the ordered physical inventory: {key[0]}")
        edge_object_ids = set()
        for edge, src, dst in edge_nodes:
            if edge.get("relation") == "archives_into" and dst.get("artifact_id") == archive.get("artifact_id"):
                edge_object_ids.add(src.get("artifact_id"))
                if _key(edge["from_artifact"]) not in {_key(ref) for ref in members}:
                    errors.append(f"{name} archives_into edge lacks an identical member reference")
        if require_member_edges:
            for object_name in expected_members:
                obj = object_by_name.get(object_name)
                if obj and obj.get("artifact_id") not in edge_object_ids:
                    errors.append(f"{name} member lacks its archives_into edge: {object_name}")
        return member_names

    if len(archive_list) == 1:
        check_archive(archive_list[0], "libwrflib.a", set(KDM6_OBJECTS), True, False)
        if len(exe_list) == 1 and not edge_exists("links_into", archive_list[0]["artifact_id"], exe_list[0]["artifact_id"]):
            errors.append("libwrflib.a lacks a links_into edge to wrf.exe")
    if len(core_archive_list) != 1:
        errors.append("inventory must contain exactly one build-tree libkdm6.a")
    if len(installed_core_archive_list) != 1:
        errors.append("inventory must contain exactly one installed libkdm6.a")
    if len(core_archive_list) == 1:
        check_archive(core_archive_list[0], "libkdm6.a", set(CPP_CORE_OBJECTS), True, True)
    if len(installed_core_archive_list) == 1:
        check_archive(installed_core_archive_list[0], "installed libkdm6.a", set(CPP_CORE_OBJECTS), False, True)

    build_shared_list = [a for a in artifacts if isinstance(a, dict) and a.get("kind") == "shared_library" and "libtorch/build/" in a.get("path", "") and PurePosixPath(a.get("path", "")).name.startswith("libkdm6_c")]
    installed_shared_list = [a for a in artifacts if isinstance(a, dict) and a.get("kind") == "shared_library" and a.get("path", "").endswith("libtorch/install/lib/" + PurePosixPath(a.get("path", "")).name) and PurePosixPath(a.get("path", "")).name.startswith("libkdm6_c")]
    if len(build_shared_list) != 1 or len(installed_shared_list) != 1:
        errors.append("inventory must identify one build and one installed libkdm6_c shared library")

    if len(core_archive_list) == 1 and len(build_shared_list) == 1 and not edge_exists(
        "links_into", core_archive_list[0]["artifact_id"], build_shared_list[0]["artifact_id"]
    ):
        errors.append("libkdm6.a must link into the build-tree libkdm6_c shared library")

    core_object_ids: set[str] = set()
    actual_core_sources = {path for path in source_by_path if path.startswith("libtorch/src/") and PurePosixPath(path).suffix.lower() == ".cpp"}
    if actual_core_sources != set(CPP_CORE_SOURCES):
        errors.append("source inventory's libtorch/src/*.cpp set differs from CMake's full 14-TU static library contract")
    for source_path in CPP_CORE_SOURCES:
        source = source_by_path.get(source_path)
        if source is None or source.get("role") != "cpp_source":
            errors.append(f"CMake kdm6 static target source absent: {source_path}")
            continue
        object_name = PurePosixPath(source_path).name + ".o"
        objects = [a for a in artifacts if isinstance(a, dict) and a.get("kind") == "object" and PurePosixPath(a.get("path", "")).name == object_name]
        if len(objects) != 1 or not PurePosixPath(objects[0].get("path", "")).as_posix().endswith(f"CMakeFiles/kdm6.dir/src/{object_name}"):
            errors.append(f"CMake kdm6 source must compile to its own CMake object: {source_path}")
            continue
        obj = objects[0]
        core_object_ids.add(obj["artifact_id"])
        if not edge_exists("compiles_to", source["artifact_id"], obj["artifact_id"]):
            errors.append(f"CMake kdm6 source lacks its compiles_to edge: {source_path}")
        if len(core_archive_list) == 1 and not edge_exists("archives_into", obj["artifact_id"], core_archive_list[0]["artifact_id"]):
            errors.append(f"CMake kdm6 object lacks its libkdm6.a archive edge: {object_name}")
        if len(build_shared_list) == 1 and edge_exists("links_into", obj["artifact_id"], build_shared_list[0]["artifact_id"]):
            errors.append(f"CMake kdm6 object must link through libkdm6.a, not directly into the dylib: {object_name}")

    bridge = source_by_path.get(CPP_BRIDGE_SOURCE)
    bridge_objects = [a for a in artifacts if isinstance(a, dict) and a.get("kind") == "object" and PurePosixPath(a.get("path", "")).name == "kdm6_c_api.cpp.o"]
    if bridge is None or bridge.get("role") != "cpp_source":
        errors.append(f"CMake shared target bridge source absent: {CPP_BRIDGE_SOURCE}")
    elif len(bridge_objects) != 1 or not PurePosixPath(bridge_objects[0].get("path", "")).as_posix().endswith("CMakeFiles/kdm6_c.dir/bridge/kdm6_c_api.cpp.o"):
        errors.append("kdm6_c_api.cpp must compile to the shared-target bridge object")
    elif len(build_shared_list) == 1 and not edge_exists("compiles_to", bridge["artifact_id"], bridge_objects[0]["artifact_id"]):
        errors.append("kdm6_c_api.cpp lacks its compiles_to edge")
    elif len(build_shared_list) == 1 and not edge_exists("links_into", bridge_objects[0]["artifact_id"], build_shared_list[0]["artifact_id"]):
        errors.append("kdm6_c_api.cpp object must link into libkdm6_c")

    if len(core_archive_list) == 1 and len(installed_core_archive_list) == 1 and not edge_exists("installs_as", core_archive_list[0]["artifact_id"], installed_core_archive_list[0]["artifact_id"]):
        errors.append("libkdm6.a lacks an installs_as edge to its installed archive")
    if len(build_shared_list) == 1 and len(installed_shared_list) == 1 and not edge_exists("installs_as", build_shared_list[0]["artifact_id"], installed_shared_list[0]["artifact_id"]):
        errors.append("libkdm6_c lacks an installs_as edge to its installed shared library")

    loader = manifest.get("runtime_loader", {})
    evidence = loader.get("evidence_level") if isinstance(loader, dict) else None
    resolution_field = "observed_resolution" if evidence == "observed_loader_resolution" else "expected_library"
    resolution = inventory_ref(loader[resolution_field], f"runtime_loader.{resolution_field}") if isinstance(loader, dict) and loader.get(resolution_field) is not None else None
    if resolution is not None:
        referenced_ids.add(resolution["artifact_id"])
        if resolution.get("kind") != "shared_library" or not PurePosixPath(resolution.get("path", "")).as_posix().endswith("libtorch/install/lib/" + PurePosixPath(resolution.get("path", "")).name):
            errors.append("loader target must be the inventoried installed libkdm6_c shared-library file")
        if not PurePosixPath(resolution.get("path", "")).name.startswith("libkdm6_c"):
            errors.append("loader target is not the KDM6 C ABI dylib")
    if len(installed_shared_list) == 1 and resolution is not None and resolution["artifact_id"] != installed_shared_list[0]["artifact_id"]:
        errors.append("loader target differs from the unique installed libkdm6_c artifact")
    if len(exe_list) == 1 and isinstance(loader, dict) and loader.get("executable_sha256") != exe_list[0].get("sha256"):
        errors.append("runtime_loader executable_sha256 differs from inventoried wrf.exe")
    resolves = [e for e, _, _ in edge_nodes if e.get("relation") == "resolves_to"]
    if len(resolves) != 1:
        errors.append("exactly one KDM6 C ABI resolves_to edge is required")
    elif resolution is not None:
        if _key(resolves[0].get("to_artifact", {})) != _key({k: resolution.get(k) for k in ("artifact_id", "path", "sha256")}):
            errors.append("loader target differs from resolves_to target path/hash")
        if len(exe_list) == 1 and resolves[0].get("from_artifact", {}).get("artifact_id") != exe_list[0].get("artifact_id"):
            errors.append("resolves_to source is not the inventoried wrf.exe")
        if len(exe_list) == 1 and not edge_exists("links_into", resolution["artifact_id"], exe_list[0]["artifact_id"]):
            errors.append("installed dylib is not linked into wrf.exe")
        install_edges = [
            (e, src, dst) for e, src, dst in edge_nodes
            if e.get("relation") == "installs_as" and dst.get("artifact_id") == resolution.get("artifact_id")
        ]
        if len(install_edges) != 1 or (install_edges and install_edges[0][1].get("artifact_id") != (build_shared_list[0].get("artifact_id") if len(build_shared_list) == 1 else None)):
            errors.append("loader target must be installed from the unique libtorch/build libkdm6_c dylib")
        names = loader.get("install_names", []) if isinstance(loader, dict) else []
        if not any(PurePosixPath(name).name.startswith("libkdm6_c.") and PurePosixPath(name).suffix == ".dylib" for name in names if isinstance(name, str)):
            errors.append("Mach-O install_names omit the KDM6 C ABI dylib")
        rpaths = loader.get("rpaths", []) if isinstance(loader, dict) else []
        if not any("libtorch/install/lib" in path.replace("\\", "/") for path in rpaths if isinstance(path, str)):
            errors.append("Mach-O rpaths omit the isolated libtorch/install/lib prefix")
        if evidence == "observed_loader_resolution" and loader.get("observation_receipt_sha256") != resolves[0].get("receipt_sha256"):
            errors.append("loader observation receipt differs from resolves_to edge receipt")

    for source_id in source_ids:
        if source_id not in step_input_ids:
            errors.append(f"source artifact is not used as a build-step input: {by_id[source_id].get('path')}")
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        if artifact.get("kind") == "receipt" and artifact.get("sha256") not in receipts:
            errors.append(f"unrelated/unreferenced receipt artifact: {artifact.get('path')}")
        if artifact.get("artifact_id") not in referenced_ids:
            errors.append(f"unreferenced inventory artifact: {artifact.get('path')}")

    status = gate.get("status") if isinstance(gate, dict) else None
    failures = gate.get("failures", []) if isinstance(gate, dict) else []
    if status == "proven":
        if failures:
            errors.append("proven lineage_gate must have no failures")
        if any(e.get("status") != "proven" for e in edges if isinstance(e, dict)):
            errors.append("proven lineage_gate contains non-proven edge results")
        if not isinstance(loader, dict) or loader.get("evidence_level") != "observed_loader_resolution":
            errors.append("proven lineage_gate requires observed loader resolution")
        errors.append("proven lineage_gate is disabled without an independent signed loader attestation")
    elif status == "unverified_loader":
        if evidence not in {"unverified_loader", "observed_loader_resolution"}:
            errors.append("unverified_loader gate status requires static or captured loader evidence")
        if resolves and resolves[0].get("status") != "unproven":
            errors.append("unverified_loader gate cannot mark resolves_to as proven")
    elif status == "failed" and not failures:
        errors.append("failed lineage_gate must name at least one failure")
    if isinstance(loader, dict) and loader.get("capture") is not None:
        if root is None:
            errors.append("loader capture content requires an artifact root")
        else:
            errors.extend(verify_loader_capture(manifest, root))
    return errors


def verify_loader_capture(manifest: dict[str, Any], root: Path) -> list[str]:
    """Parse the retained dyld receipt and enforce the hash-pinned command allowlist."""
    errors: list[str] = []
    root = root.resolve()
    loader = manifest.get("runtime_loader", {})
    capture = loader.get("capture", {}) if isinstance(loader, dict) else {}
    artifacts = {a.get("artifact_id"): a for a in manifest.get("artifacts", []) if isinstance(a, dict)}

    def ref_matches(ref: Any, artifact: dict[str, Any] | None) -> bool:
        return isinstance(ref, dict) and artifact is not None and _key(ref) == _key({k: artifact.get(k) for k in ("artifact_id", "path", "sha256")})

    def verify_local_bytes(artifact: dict[str, Any] | None, label: str) -> None:
        if artifact is None:
            return
        try:
            path = root.joinpath(*PurePosixPath(artifact["path"]).parts).resolve(strict=True)
            if not path.is_relative_to(root) or hashlib.sha256(path.read_bytes()).hexdigest() != artifact.get("sha256"):
                errors.append(f"{label} bytes/path do not match the inventoried identity")
        except (OSError, KeyError):
            errors.append(f"{label} artifact bytes are unavailable")

    if not isinstance(capture, dict):
        return ["runtime_loader.capture must be an object"]
    if capture.get("capture_tool_path") != CAPTURE_TOOL_PATH or capture.get("capture_tool_sha256") != CAPTURE_TOOL_SHA256:
        errors.append("loader capture tool identity is not in the pinned allowlist")
    tool_path = root.joinpath(*PurePosixPath(CAPTURE_TOOL_PATH).parts)
    try:
        if hashlib.sha256(tool_path.read_bytes()).hexdigest() != CAPTURE_TOOL_SHA256:
            errors.append("on-disk loader capture tool differs from the pinned allowlist digest")
    except OSError:
        errors.append("pinned loader capture tool is missing from the artifact root")

    tool_artifact = artifacts.get(next((a.get("artifact_id") for a in artifacts.values() if a.get("path") == CAPTURE_TOOL_PATH), ""))
    if tool_artifact is None or tool_artifact.get("kind") != "source" or tool_artifact.get("sha256") != CAPTURE_TOOL_SHA256:
        errors.append("pinned capture tool is not present as the exact source artifact")

    capture_ref = loader.get("capture_receipt")
    capture_artifact = artifacts.get(capture_ref.get("artifact_id")) if isinstance(capture_ref, dict) else None
    if not ref_matches(capture_ref, capture_artifact) or not isinstance(capture_artifact, dict) or capture_artifact.get("kind") != "receipt":
        errors.append("loader capture receipt is not bound to a receipt artifact")
        receipt_payload = None
    else:
        if PurePosixPath(capture_artifact.get("path", "")).parts[:1] == ("host",):
            errors.append("public loader projection receipt must not be stored under private host/")
        try:
            receipt_path = root.joinpath(*PurePosixPath(capture_artifact["path"]).parts)
            verify_local_bytes(capture_artifact, "loader capture receipt")
            receipt_payload = json.loads(receipt_path.read_text())
        except (OSError, json.JSONDecodeError, KeyError):
            errors.append("loader capture receipt file is missing or invalid JSON")
            receipt_payload = None
    if receipt_payload is not None and receipt_payload != capture:
        errors.append("parsed loader capture receipt differs from manifest capture fields")

    manifest_id = capture.get("manifest_id", "")
    private_path = root / "host" / "s9-captures" / f"{manifest_id}.raw.json"
    try:
        private_bytes = private_path.read_bytes()
        raw = json.loads(private_bytes)
    except (OSError, json.JSONDecodeError):
        errors.append("ignored host raw loader receipt is missing or invalid JSON")
        return errors
    if hashlib.sha256(private_bytes).hexdigest() != capture.get("private_receipt_sha256"):
        errors.append("private raw receipt bytes do not match the public receipt digest")
    if raw.get("schema_version") != "s9-dyld-raw-capture/v1" or raw.get("manifest_id") != manifest_id:
        errors.append("private raw receipt schema/manifest identity mismatch")
    if raw.get("capture_tool_sha256") != CAPTURE_TOOL_SHA256:
        errors.append("private raw receipt does not identify the pinned capture tool")
    if capture.get("manifest_id") != manifest_id or capture.get("private_receipt_sha256") != hashlib.sha256(private_bytes).hexdigest():
        errors.append("public capture projection does not bind its private receipt digest")
    if capture.get("process_argv") != ["<MPI_LAUNCHER>", "-n", "1", "<WRF_EXE>"] or capture.get("process_cwd") != "<RUN_DIR>":
        errors.append("public capture projection contains non-aliased process paths")
    capture_json = json.dumps(capture, sort_keys=True)
    if any(token in capture_json for token in ("/Users/", "/private/tmp/", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", '"HOME"', '"PWD"', '"TMPDIR"')):
        errors.append("public capture projection contains private path or credential identifiers")

    exe = next((a for a in artifacts.values() if a.get("kind") == "executable" and PurePosixPath(a.get("path", "")).name == "wrf.exe"), None)
    installed = next((a for a in artifacts.values() if a.get("kind") == "shared_library" and a.get("path", "").endswith("libtorch/install/lib/" + PurePosixPath(a.get("path", "")).name) and PurePosixPath(a.get("path", "")).name.startswith("libkdm6_c")), None)
    verify_local_bytes(exe, "captured WRF executable")
    verify_local_bytes(installed, "captured installed dylib")
    if not ref_matches(capture.get("executable"), exe) or not ref_matches(loader.get("observed_resolution"), installed):
        errors.append("capture executable/loaded-library references do not match the inventoried WRF and installed dylib")

    launcher_identity = manifest.get("toolchain", {}).get("mpi_launcher", {})
    if launcher_identity.get("path") != "<MPI_LAUNCHER>" or capture.get("process_argv") != ["<MPI_LAUNCHER>", "-n", "1", "<WRF_EXE>"]:
        errors.append("public loader command projection is not the path-aliased mpirun -n 1 WRF form")
    raw_argv = raw.get("raw_process_argv", [])
    if len(raw_argv) != 4 or Path(raw_argv[0]).name != "mpirun" or raw_argv[1:3] != ["-n", "1"]:
        errors.append("private loader command is outside allowlist: mpirun -n 1 <wrf.exe>")
    else:
        if exe is not None:
            try:
                expected_exe = str(root.joinpath(*PurePosixPath(exe["path"]).parts).resolve(strict=True))
                if raw_argv[3] != expected_exe or raw.get("raw_executable_path") != expected_exe:
                    errors.append("private process argv does not name the exact WRF executable")
            except OSError:
                errors.append("inventoried WRF executable is missing during loader receipt validation")
        try:
            launcher_sha = hashlib.sha256(Path(raw_argv[0]).resolve(strict=True).read_bytes()).hexdigest()
            if launcher_sha != raw.get("raw_launcher_sha256") or launcher_sha != capture.get("launcher_sha256") or launcher_sha != launcher_identity.get("sha256"):
                errors.append("private mpirun identity differs from public/toolchain launcher digests")
        except OSError:
            errors.append("private mpirun executable is unavailable for identity validation")

    raw_cwd = Path(raw.get("raw_process_cwd", ""))
    try:
        raw_cwd_resolved = raw_cwd.resolve(strict=True)
        if not raw_cwd_resolved.is_relative_to(root):
            errors.append("private run directory is outside the artifact root")
            raw_cwd_relative = "<OUTSIDE_ROOT>"
        else:
            raw_cwd_relative = raw_cwd_resolved.relative_to(root).as_posix()
    except OSError:
        raw_cwd_resolved = root
        raw_cwd_relative = "<MISSING_RUN_DIR>"
        errors.append("private run directory is unavailable")

    raw_capture_argv = raw.get("raw_capture_argv", [])
    if len(raw_capture_argv) < 4 or not Path(raw_capture_argv[0]).name.startswith("python"):
        errors.append("private collector argv does not name its Python launcher and script")
    else:
        expected_script = str((root / CAPTURE_TOOL_PATH).resolve(strict=True))
        if str(Path(raw_capture_argv[1]).resolve(strict=True)) != expected_script:
            errors.append("private collector argv does not invoke the pinned capture script")
        options = raw_capture_argv[2:]
        if len(options) % 2:
            errors.append("private collector argv has malformed option/value pairs")
        else:
            raw_options = dict(zip(options[::2], options[1::2]))
            expected_options = {
                "--manifest-id": manifest_id,
                "--executable": exe.get("path") if exe else "",
                "--executable-id": exe.get("artifact_id") if exe else "",
                "--library": installed.get("path") if installed else "",
                "--library-id": installed.get("artifact_id") if installed else "",
                "--cwd": raw_cwd_relative,
                "--launcher": raw_argv[0] if raw_argv else "",
                "--receipt": capture_artifact.get("path") if capture_artifact else "",
                "--private-receipt": f"host/s9-captures/{manifest_id}.raw.json",
                "--stdout": f"host/s9-captures/{manifest_id}.stdout.log",
                "--stderr": f"host/s9-captures/{manifest_id}.stderr.log",
            }
            if set(raw_options) != set(expected_options) | {"--root"} or any(raw_options.get(key) != value for key, value in expected_options.items()):
                errors.append("private collector argv arguments do not match the manifest artifacts")
            try:
                if Path(raw_options.get("--root", "")).resolve(strict=True) != root:
                    errors.append("private collector root argv differs from verification root")
            except OSError:
                errors.append("private collector root argv is unavailable")
            expected_public_argv = _public_capture_argv(
                manifest_id,
                exe.get("artifact_id", "") if exe else "",
                installed.get("artifact_id", "") if installed else "",
            )
            if capture.get("capture_argv") != expected_public_argv:
                errors.append("public collector argv is not the path-aliased allowlisted projection")

    raw_env = raw.get("raw_process_environment", {})
    if not isinstance(raw_env, dict) or set(raw_env) - CAPTURE_ENV_ALLOWLIST:
        errors.append("private raw receipt environment contains variables outside the allowlist")
        raw_env = {}
    public_env = _public_capture_environment(raw_env)
    if capture.get("process_environment") != public_env:
        errors.append("public process environment projection differs from the allowlisted raw environment")
    if set(capture.get("process_environment", {})) - CAPTURE_ENV_ALLOWLIST:
        errors.append("public process environment includes a variable outside the allowlist")
    for key, value in capture.get("process_environment", {}).items():
        if key in CAPTURE_PATH_ENV and not re.fullmatch(r"<redacted-path-sha256:[a-f0-9]{64}>", str(value)):
            errors.append(f"public process environment path value is not redacted: {key}")
        elif key not in CAPTURE_PATH_ENV and isinstance(value, str) and value.startswith("/"):
            errors.append(f"public process environment contains an absolute path: {key}")
    if set(capture.get("process_environment", {})) - CAPTURE_ENV_ALLOWLIST:
        errors.append("public process environment includes a variable outside the allowlist")
    env_bytes = b"\0".join(f"{key}={public_env[key]}".encode() for key in sorted(public_env))
    if hashlib.sha256(env_bytes).hexdigest() != capture.get("process_environment_sha256"):
        errors.append("public process environment map does not match its SHA-256")
    if set(capture.get("process_environment", {})) & {"HOME", "PWD", "TMPDIR", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"}:
        errors.append("public environment projection contains a private or credential variable")
    for key in ("DYLD_PRINT_LIBRARIES", "DYLD_PRINT_RPATHS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "OMP_THREAD_LIMIT"):
        if raw_env.get(key) != "1":
            errors.append(f"private process environment lacks required {key}=1")
    if raw.get("process_exit_code") != 0 or capture.get("process_exit_code") != raw.get("process_exit_code"):
        errors.append("captured WRF process did not exit successfully or projection mismatch")
    if exe is not None and loader.get("executable_sha256") != exe.get("sha256"):
        errors.append("runtime_loader executable_sha256 differs from exact captured WRF executable")

    output_paths: dict[str, bytes] = {}
    raw_outputs = (("capture_stdout_sha256", "raw_stdout_path", "stdout_sha256"), ("capture_stderr_sha256", "raw_stderr_path", "stderr_sha256"))
    for field, raw_field, digest_field in raw_outputs:
        expected_rel = f"host/s9-captures/{manifest_id}.{'stdout' if field == 'capture_stdout_sha256' else 'stderr'}.log"
        try:
            raw_path = Path(raw.get(raw_field, "")).resolve(strict=True)
            if not raw_path.is_relative_to(root / "host") or raw_path != (root / expected_rel).resolve(strict=True):
                raise OSError("raw output does not match the ignored host receipt path")
            output_paths[field] = raw_path.read_bytes()
            digest = hashlib.sha256(output_paths[field]).hexdigest()
            if digest != loader.get(field) or digest != capture.get(digest_field) or digest != raw.get(digest_field):
                errors.append(f"{field} bytes do not match public/private capture hashes")
        except OSError:
            errors.append(f"private raw {field} file is missing or not under ignored host/")

    if installed is not None:
        try:
            expected_lib = str(root.joinpath(*PurePosixPath(installed["path"]).parts).resolve(strict=True))
        except OSError:
            expected_lib = ""
            errors.append("installed KDM6 C ABI dylib is missing during loader receipt validation")
        raw_lines = raw.get("dyld_image_lines", [])
        actual_lines = []
        for output in output_paths.values():
            actual_lines.extend(line for line in output.decode("utf-8", errors="replace").splitlines() if "dyld[" in line and "libkdm6_c" in line)
        if raw_lines != actual_lines:
            errors.append("private dyld_image_lines do not match raw stdout/stderr bytes")
        if not any(expected_lib in line for line in actual_lines):
            errors.append("captured dyld output does not name the exact installed KDM6 C ABI dylib path")
        if capture.get("dyld_image_lines") != ["dyld: loaded <INSTALLED_KDM6_C_ABI_DYLIB>" for _ in raw_lines if "dyld[" in _ and "libkdm6_c" in _]:
            errors.append("public dyld image projection is not path-redacted or differs from raw output")

    steps = manifest.get("build_steps", [])
    observation_steps = [s for s in steps if isinstance(s, dict) and s.get("kind") == "loader_observation"]
    if len(observation_steps) != 1:
        errors.append("loader capture must be produced by exactly one loader_observation build step")
    elif isinstance(capture_ref, dict):
        step = observation_steps[0]
        if step.get("argv") != capture.get("capture_argv") or step.get("argv") != _public_capture_argv(manifest_id, capture.get("executable", {}).get("artifact_id", ""), capture.get("loaded_library", {}).get("artifact_id", "")):
            errors.append("loader_observation argv is not the path-redacted pinned collector command")
        if not step.get("argv") or step["argv"][0] != CAPTURE_TOOL_PATH:
            errors.append("loader_observation command is not the allowlisted capture tool")
        if tool_artifact is not None and not any(ref_matches(ref, tool_artifact) for ref in step.get("inputs", [])):
            errors.append("loader_observation step does not bind the capture tool source input")
        if not ref_matches(step.get("capture_receipt"), capture_artifact):
            errors.append("loader_observation step does not output the retained capture receipt")
        if step.get("stdout_sha256") != loader.get("capture_stdout_sha256") or step.get("stderr_sha256") != loader.get("capture_stderr_sha256"):
            errors.append("loader_observation step output hashes differ from the private child output hashes")

    raw_args = raw.get("raw_capture_argv", [])
    if len(raw_args) < 2 or not Path(raw_args[0]).name.startswith("python"):
        errors.append("private collector invocation does not record a Python interpreter argv")
    else:
        try:
            expected_tool = str((root / CAPTURE_TOOL_PATH).resolve(strict=True))
            if str(Path(raw_args[1]).resolve(strict=True)) != expected_tool:
                errors.append("private collector invocation did not execute the pinned capture script")
        except OSError:
            errors.append("private capture script is unavailable for invocation validation")
    return errors


def read_archive_member_inventory(archive_path: Path) -> list[dict[str, str]]:
    """Return physical ar members in order, preserving duplicate names."""
    data = archive_path.read_bytes()
    if data[:8] != b"!<arch>\n":
        raise ValueError("unsupported archive magic (thin archives are not accepted)")
    pos = 8
    long_names = b""
    members: list[dict[str, str]] = []
    while pos < len(data):
        header = data[pos : pos + 60]
        if len(header) != 60 or header[58:60] != b"`\n":
            raise ValueError(f"invalid ar member header at byte {pos}")
        name_field = header[:16].decode("ascii", errors="strict").strip()
        size = int(header[48:58].decode("ascii").strip())
        body_start = pos + 60
        body_end = body_start + size
        if body_end > len(data):
            raise ValueError(f"truncated ar member at byte {pos}")
        body = data[body_start:body_end]
        name = name_field
        payload = body
        if name_field.startswith("#1/"):
            name_size = int(name_field[3:])
            name = body[:name_size].decode("utf-8", errors="surrogateescape").rstrip("\0")
            payload = body[name_size:]
        elif name_field == "//":
            long_names = body
            name = "//"
        elif name_field in {"/", "/SYM64/"}:
            name = name_field
        elif name_field.startswith("/") and name_field[1:].isdigit():
            offset = int(name_field[1:])
            end = long_names.find(b"/\n", offset)
            if end < 0:
                end = long_names.find(b"\n", offset)
            if end < 0:
                raise ValueError(f"invalid GNU ar long-name offset: {name_field}")
            name = long_names[offset:end].decode("utf-8", errors="surrogateescape")
        if name not in {"//", "/", "/SYM64/"}:
            members.append({"name": name, "sha256": hashlib.sha256(payload).hexdigest()})
        pos = body_end + (size & 1)

    listed = subprocess.run(["ar", "-t", str(archive_path)], capture_output=True, check=True, text=True).stdout.splitlines()
    if len([member for member in members]) != len(listed) or any(
        parsed.rstrip("/") != actual.rstrip("/")
        for parsed, actual in zip((member["name"] for member in members), listed)
    ):
        raise ValueError("parsed archive member order/names disagree with `ar -t`")
    for member, displayed_name in zip(members, listed):
        member["name"] = displayed_name
    return members


def verify_artifact_bytes(manifest: dict[str, Any], root: Path) -> list[str]:
    """Hash every inventoried file and compare retained KDM6 archive members."""
    errors: list[str] = []
    root = root.resolve()
    artifacts = manifest.get("artifacts", [])
    by_id = {a.get("artifact_id"): a for a in artifacts if isinstance(a, dict)}
    resolved_paths: dict[str, Path] = {}
    for artifact in by_id.values():
        rel = artifact.get("path", "")
        if not _safe_rel(rel):
            continue
        path = root.joinpath(*PurePosixPath(rel).parts)
        try:
            resolved = path.resolve(strict=True)
        except OSError:
            errors.append(f"missing artifact: {rel}")
            continue
        if not resolved.is_relative_to(root):
            errors.append(f"artifact resolves outside verification root: {rel}")
            continue
        if artifact.get("kind") == "symlink":
            if not path.is_symlink() or os.readlink(path) != artifact.get("symlink_target"):
                errors.append(f"symlink identity mismatch: {rel}")
                continue
        elif path.is_symlink():
            errors.append(f"undeclared symlink artifact: {rel}")
            continue
        if not resolved.is_file():
            errors.append(f"artifact is not a regular file: {rel}")
            continue
        resolved_paths[artifact["artifact_id"]] = resolved
        if hashlib.sha256(resolved.read_bytes()).hexdigest() != artifact.get("sha256"):
            errors.append(f"artifact bytes do not match SHA-256: {rel}")

    for archive in (a for a in by_id.values() if a.get("kind") == "archive"):
        archive_path = resolved_paths.get(archive["artifact_id"])
        if archive_path is None:
            continue
        try:
            actual_members = read_archive_member_inventory(archive_path)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            errors.append(f"cannot enumerate archive members for {archive.get('path')}: {exc}")
            continue
        declared_members = archive.get("member_inventory", [])
        normalized_declared = [{"name": item.get("name"), "sha256": item.get("sha256")} for item in declared_members if isinstance(item, dict)]
        if actual_members != normalized_declared:
            errors.append(f"physical archive member inventory/order/hash mismatch: {archive.get('path')}")
        actual_pairs = Counter((member["name"].rstrip("/"), member["sha256"]) for member in actual_members)
        required_pairs: Counter = Counter()
        for ref in archive.get("archive_members", []):
            required_pairs[(PurePosixPath(ref.get("path", "")).name, ref.get("sha256"))] += 1
        for pair, count in required_pairs.items():
            if actual_pairs[pair] < count:
                errors.append(f"archive member bytes differ from inventoried object: {pair[0]}")
    return errors


def verify_cmake_target_contract(root: Path) -> list[str]:
    """Check the current CMake target graph against the pinned 14-TU contract."""
    errors: list[str] = []
    cmake_path = root / "libtorch/CMakeLists.txt"
    try:
        content = cmake_path.read_text()
    except OSError:
        return ["libtorch/CMakeLists.txt is missing from the verification root"]

    def sources_for(target: str, target_kind: str) -> list[str] | None:
        pattern = rf"add_library\s*\(\s*{re.escape(target)}\s+{re.escape(target_kind)}\s+(.*?)\)"
        match = re.search(pattern, content, re.DOTALL)
        if not match:
            return None
        return re.findall(r"(?m)^\s*((?:src|bridge)/[A-Za-z0-9_.-]+\.cpp)\s*$", match.group(1))

    core_sources = sources_for("kdm6", "STATIC")
    expected_core = [path.removeprefix("libtorch/") for path in CPP_CORE_SOURCES]
    if core_sources != expected_core:
        errors.append("CMake kdm6 STATIC translation-unit list differs from the 14-source verifier contract")
    bridge_sources = sources_for("kdm6_c", "SHARED")
    if bridge_sources != ["bridge/kdm6_c_api.cpp"]:
        errors.append("CMake kdm6_c SHARED direct source must be only bridge/kdm6_c_api.cpp")
    if not re.search(r"target_link_libraries\s*\(\s*kdm6_c\s+PUBLIC\s+kdm6\s*\)", content):
        errors.append("CMake kdm6_c must link the static kdm6 target")
    if not re.search(r"install\s*\(\s*TARGETS\s+kdm6\s+kdm6_c\b", content):
        errors.append("CMake install target list must include both kdm6 and kdm6_c")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--root", type=Path, help="artifact root; defaults to the manifest directory")
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text())
        schema = json.loads(SCHEMA.read_text())
        from jsonschema import Draft202012Validator
    except (OSError, json.JSONDecodeError, ImportError) as exc:
        print(f"S9 verifier cannot load inputs/dependency: {exc}", file=sys.stderr)
        return 2
    invalid = sorted(Draft202012Validator(schema).iter_errors(manifest), key=lambda error: list(error.path))
    if invalid:
        for error in invalid:
            print(f"SCHEMA: {list(error.path)}: {error.message}", file=sys.stderr)
        return 1
    root = args.root or args.manifest.parent
    errors = verify_manifest_semantics(manifest, root)
    errors.extend(verify_artifact_bytes(manifest, root))
    errors.extend(verify_cmake_target_contract(root))
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"PASS: manifest checks; lineage_gate.status={manifest['lineage_gate']['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
