#!/usr/bin/env python3
"""Verify S9 manifest structure, semantic edges, receipts, and retained bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
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
    "installs_as": "install", "resolves_to": "loader_observation",
}
KDM6_OBJECTS = (
    "module_mp_kdm6.o", "module_mp_kdm6_cons.o", "module_mp_kdm6ad.o",
    "module_mp_kdm6ad_cons.o", "kdm6_iso_c.o", "module_microphysics_driver.o",
)
SOURCE_FOR_OBJECT = {Path(name).stem + ".F": name for name in KDM6_OBJECTS if name != "kdm6_iso_c.o"}
SOURCE_FOR_OBJECT["kdm6_iso_c.f90"] = "kdm6_iso_c.o"
CPP_LINEAGE_SOURCES = {
    "libtorch/src/runtime.cpp", "libtorch/src/coordinator.cpp",
    "libtorch/bridge/kdm6_c_api.cpp",
}


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


def verify_manifest_semantics(manifest: dict[str, Any]) -> list[str]:
    """Require the declared six-edge graph to bind actual S9 artifacts/steps."""
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return ["manifest root must be an object"]

    artifacts = manifest.get("artifacts", [])
    if not isinstance(artifacts, list):
        return ["artifacts must be an array"]
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
        for field in ("stdout_receipt", "stderr_receipt"):
            receipt = inventory_ref(step.get(field), f"build_steps[{index}].{field}")
            if receipt is not None:
                if receipt.get("kind") != "receipt":
                    errors.append(f"build_steps[{index}].{field} must reference kind=receipt")
                receipts.add(receipt.get("sha256", ""))
                referenced_ids.add(receipt["artifact_id"])

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
            if step.get("kind") == RELATION_STEP_KIND.get(relation)
            and edge.get("from_artifact") in inputs
            and edge.get("to_artifact") in (inputs if relation == "resolves_to" else outputs)
            and edge.get("receipt_sha256") in (
                step.get("stdout_receipt", {}).get("sha256"),
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
    exe_list = [a for a in artifacts if isinstance(a, dict) and a.get("kind") == "executable" and PurePosixPath(a.get("path", "")).name == "wrf.exe"]
    if len(archive_list) != 1 or not PurePosixPath(archive_list[0].get("path", "")).as_posix().endswith("main/libwrflib.a"):
        errors.append("inventory must identify exactly one main/libwrflib.a")
    if len(exe_list) != 1 or not PurePosixPath(exe_list[0].get("path", "")).as_posix().endswith("main/wrf.exe"):
        errors.append("inventory must identify exactly one main/wrf.exe")
    if len(archive_list) == 1:
        archive = archive_list[0]
        members = archive.get("archive_members", [])
        member_keys: set[tuple[str, str, str]] = set()
        member_names: set[str] = set()
        for j, ref in enumerate(members):
            member = inventory_ref(ref, f"libwrflib.a.archive_members[{j}]")
            if member is None:
                continue
            if member.get("kind") != "object":
                errors.append(f"archive member is not an object: {member.get('path')}")
            member_keys.add(_key(ref))
            member_names.add(PurePosixPath(member.get("path", "")).name)
            referenced_ids.add(member["artifact_id"])
        missing = sorted(set(KDM6_OBJECTS) - member_names)
        if missing:
            errors.append(f"archive member inventory omits KDM6 objects: {', '.join(missing)}")
        for edge, src, dst in edge_nodes:
            if edge.get("relation") == "archives_into" and dst.get("artifact_id") == archive.get("artifact_id") and _key(edge["from_artifact"]) not in member_keys:
                errors.append("archives_into edge is not represented by the exact archive member reference")
        for name in KDM6_OBJECTS:
            obj = object_by_name.get(name)
            if obj and (obj["artifact_id"] not in {e[1]["artifact_id"] for e in edge_nodes if e[0].get("relation") == "archives_into" and e[2].get("artifact_id") == archive.get("artifact_id")}):
                errors.append(f"KDM6 archive member lacks its archives_into edge: {name}")
        if len(exe_list) == 1 and not edge_exists("links_into", archive["artifact_id"], exe_list[0]["artifact_id"]):
            errors.append("libwrflib.a lacks a links_into edge to wrf.exe")

    # Tie public C++ entry sources through objects into the built dylib; the
    # installed dylib and WRF executable are checked as a separate branch.
    for path in CPP_LINEAGE_SOURCES:
        source = source_by_path.get(path)
        if source is None or source.get("role") != "cpp_source":
            errors.append(f"required C++ source absent from source_tree.files: {path}")
            continue
        obj_edges = [e for e, src, dst in edge_nodes if e.get("relation") == "compiles_to" and src.get("artifact_id") == source.get("artifact_id") and dst.get("kind") == "object"]
        if len(obj_edges) != 1:
            errors.append(f"C++ source must compile to exactly one inventoried object: {path}")
            continue
        obj_id = obj_edges[0]["to_artifact"]["artifact_id"]
        build_lib_edges = [e for e, src, dst in edge_nodes if e.get("relation") == "links_into" and src.get("artifact_id") == obj_id and dst.get("kind") == "shared_library" and "build" in PurePosixPath(dst.get("path", "")).parts]
        if len(build_lib_edges) != 1:
            errors.append(f"C++ object must link into one KDM6 build dylib: {path}")

    loader = manifest.get("runtime_loader", {})
    resolved = None
    if isinstance(loader, dict) and loader.get("observed_resolution") is not None:
        resolved = inventory_ref(loader["observed_resolution"], "runtime_loader.observed_resolution")
        if resolved is not None:
            referenced_ids.add(resolved["artifact_id"])
            if resolved.get("kind") != "shared_library":
                errors.append("observed loader target must be the inventoried installed shared-library file")
            if "install" not in PurePosixPath(resolved.get("path", "")).parts or not PurePosixPath(resolved.get("path", "")).name.startswith("libkdm6_c"):
                errors.append("observed loader target must be the installed KDM6 C ABI dylib")
            name = PurePosixPath(resolved.get("path", "")).as_posix()
            if not name.endswith("libtorch/install/lib/" + PurePosixPath(name).name):
                errors.append("observed loader target must be under libtorch/install/lib")
    if len(exe_list) == 1 and isinstance(loader, dict):
        if loader.get("executable_sha256") != exe_list[0].get("sha256"):
            errors.append("runtime_loader executable_sha256 differs from inventoried wrf.exe")
    resolves = [e for e, _, _ in edge_nodes if e.get("relation") == "resolves_to"]
    if len(resolves) != 1:
        errors.append("exactly one KDM6 C ABI resolves_to edge is required")
    elif resolved is not None:
        if _key(resolves[0].get("to_artifact", {})) != _key({k: resolved.get(k) for k in ("artifact_id", "path", "sha256")}):
            errors.append("observed loader target differs from resolves_to target path/hash")
        if len(exe_list) == 1 and resolves[0].get("from_artifact", {}).get("artifact_id") != exe_list[0].get("artifact_id"):
            errors.append("resolves_to source is not the inventoried wrf.exe")
        if loader.get("observation_receipt_sha256") != resolves[0].get("receipt_sha256"):
            errors.append("loader observation receipt differs from resolves_to edge receipt")
        install_edges = [
            (e, src, dst) for e, src, dst in edge_nodes
            if e.get("relation") == "installs_as" and dst.get("artifact_id") == resolved.get("artifact_id")
        ]
        if len(install_edges) != 1:
            errors.append("observed loader target must be the unique installs_as target")
        elif install_edges[0][1].get("kind") != "shared_library" or not PurePosixPath(install_edges[0][1].get("path", "")).as_posix().endswith("libtorch/build/" + PurePosixPath(install_edges[0][1].get("path", "")).name):
            errors.append("installs_as source must be the inventoried libtorch/build shared library")
        if len(exe_list) == 1 and not edge_exists("links_into", resolved["artifact_id"], exe_list[0]["artifact_id"]):
            errors.append("observed installed dylib is not linked into wrf.exe")
        install_names = loader.get("install_names", []) if isinstance(loader, dict) else []
        if not any(
            PurePosixPath(name).name.startswith("libkdm6_c.")
            and PurePosixPath(name).suffix == ".dylib"
            for name in install_names
            if isinstance(name, str)
        ):
            errors.append("Mach-O install_names omit the KDM6 C ABI dylib")
        rpaths = loader.get("rpaths", []) if isinstance(loader, dict) else []
        if not any("libtorch/install/lib" in path.replace("\\", "/") for path in rpaths if isinstance(path, str)):
            errors.append("Mach-O rpaths omit the isolated libtorch/install/lib prefix")

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
    elif status == "failed" and not failures:
        errors.append("failed lineage_gate must name at least one failure")
    return errors


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
        for ref in archive.get("archive_members", []):
            member = by_id.get(ref.get("artifact_id"))
            if member is None or _key(ref) != _key({k: member.get(k) for k in ("artifact_id", "path", "sha256")}):
                continue
            if PurePosixPath(member.get("path", "")).name not in KDM6_OBJECTS:
                continue
            try:
                result = subprocess.run(["ar", "-p", str(archive_path), PurePosixPath(member["path"]).name], capture_output=True, check=False)
            except OSError as exc:
                errors.append(f"cannot inspect archive member {member.get('path')}: {exc}")
                continue
            if result.returncode != 0 or hashlib.sha256(result.stdout).hexdigest() != member.get("sha256"):
                errors.append(f"archive member bytes differ from object inventory: {member.get('path')}")
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
    errors = verify_manifest_semantics(manifest)
    errors.extend(verify_artifact_bytes(manifest, args.root or args.manifest.parent))
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"PASS: manifest checks; lineage_gate.status={manifest['lineage_gate']['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
