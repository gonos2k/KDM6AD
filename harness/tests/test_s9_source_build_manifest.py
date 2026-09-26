"""Regression tests for fail-closed S9 lineage edge verification."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
import verify_s9_source_build_manifest as verifier  # noqa: E402

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - schema dependency is optional for semantic unit tests
    Draft202012Validator = None


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _manifest() -> dict:
    artifacts: list[dict] = []
    source_files: list[dict] = []
    edges: list[dict] = []
    steps: list[dict] = []

    def add(kind: str, path: str, *, role: str | None = None, members: list | None = None) -> dict:
        artifact = {
            "artifact_id": f"a{len(artifacts)}",
            "kind": kind,
            "path": path,
            "sha256": _sha(path),
            "mtime_utc": None,
        }
        if role:
            artifact["role"] = role
        if members is not None:
            artifact["archive_members"] = copy.deepcopy(members)
        artifacts.append(artifact)
        return artifact

    def ref(artifact: dict) -> dict:
        return {key: artifact[key] for key in ("artifact_id", "path", "sha256")}

    def step(kind: str, inputs: list[dict], outputs: list[dict]) -> tuple[dict, str]:
        stdout = add("receipt", f"receipts/{len(steps)}-{kind}.stdout.log")
        stderr = add("receipt", f"receipts/{len(steps)}-{kind}.stderr.log")
        if kind == "loader_observation" and not outputs:
            outputs = [stdout]
        record = {
            "step_id": f"step-{len(steps)}",
            "kind": kind,
            "cwd": ".",
            "argv": [kind, "captured"],
            "environment": {},
            "stdout_receipt": ref(stdout),
            "stderr_receipt": ref(stderr),
            "inputs": [ref(artifact) for artifact in inputs],
            "outputs": [ref(artifact) for artifact in outputs],
        }
        steps.append(record)
        return record, stdout["sha256"]

    def edge(relation: str, src: dict, dst: dict, receipt_sha: str) -> None:
        edges.append({
            "from_artifact": ref(src),
            "to_artifact": ref(dst),
            "relation": relation,
            "status": "proven",
            "receipt_sha256": receipt_sha,
        })

    for source_name, object_name in verifier.SOURCE_FOR_OBJECT.items():
        source = add("source", f"phys/{source_name}")
        source_files.append({**ref(source), "role": "fortran_source"})
        obj = add("object", f"phys/{object_name}")
        if source_name.endswith(".F"):
            preprocessed = add("preprocessed_source", f"phys/{Path(source_name).stem}.f90")
            _, preprocess_receipt = step("preprocess", [source], [preprocessed])
            edge("preprocesses_to", source, preprocessed, preprocess_receipt)
            _, compile_receipt = step("compile", [preprocessed], [obj])
            edge("compiles_to", preprocessed, obj, compile_receipt)
        else:
            _, compile_receipt = step("compile", [source], [obj])
            edge("compiles_to", source, obj, compile_receipt)

    cpp_objects: list[dict] = []
    for cpp_path in sorted(verifier.CPP_LINEAGE_SOURCES):
        source = add("source", cpp_path)
        source_files.append({**ref(source), "role": "cpp_source"})
        obj = add("object", f"libtorch/build/objects/{Path(cpp_path).stem}.o")
        _, compile_receipt = step("compile", [source], [obj])
        edge("compiles_to", source, obj, compile_receipt)
        cpp_objects.append(obj)

    archive = add("archive", "main/libwrflib.a", members=[ref(a) for a in artifacts if a["kind"] == "object" and a["path"].startswith("phys/")])
    for obj in (a for a in artifacts if a["kind"] == "object" and a["path"].startswith("phys/")):
        edge("archives_into", obj, archive, "")
    _, archive_receipt = step("archive", [a for a in artifacts if a["kind"] == "object" and a["path"].startswith("phys/")], [archive])
    for item in edges:
        if item["relation"] == "archives_into":
            item["receipt_sha256"] = archive_receipt

    build_dylib = add("shared_library", "libtorch/build/libkdm6_c.2.0.0.dylib")
    _, cpp_link_receipt = step("link", cpp_objects, [build_dylib])
    for obj in cpp_objects:
        edge("links_into", obj, build_dylib, cpp_link_receipt)
    installed = add("shared_library", "libtorch/install/lib/libkdm6_c.2.0.0.dylib")
    _, install_receipt = step("install", [build_dylib], [installed])
    edge("installs_as", build_dylib, installed, install_receipt)

    executable = add("executable", "main/wrf.exe")
    _, exe_link_receipt = step("link", [archive, installed], [executable])
    edge("links_into", archive, executable, exe_link_receipt)
    edge("links_into", installed, executable, exe_link_receipt)
    _, loader_receipt = step("loader_observation", [executable, installed], [])
    edge("resolves_to", executable, installed, loader_receipt)

    return {
        "schema_version": "s9-source-build-manifest/v1",
        "manifest_id": "synthetic-valid-fixture",
        "recorded_at_utc": "2026-09-26T00:00:00Z",
        "source_tree": {
            "host_revision": "private-host-rev",
            "public_revision": "public-rev",
            "dirty": False,
            "files": source_files,
        },
        "toolchain": {
            "platform": "darwin",
            "architecture": "arm64",
            "compiler": {"path": "/tool/fc", "version": "fc 1", "sha256": _sha("fc")},
            "linker": {"path": "/tool/ld", "version": "ld 1", "sha256": _sha("ld")},
            "build_system": {"path": "/tool/make", "version": "make 1", "sha256": _sha("make")},
            "environment": {},
        },
        "build_steps": steps,
        "artifacts": artifacts,
        "runtime_loader": {
            "evidence_level": "observed_loader_resolution",
            "executable_sha256": executable["sha256"],
            "install_names": ["@rpath/libkdm6_c.2.dylib"],
            "rpaths": ["libtorch/install/lib"],
            "observed_resolution": ref(installed),
            "observation_receipt_sha256": loader_receipt,
        },
        "lineage_gate": {
            "status": "proven",
            "verifier": {"path": "/tool/verifier", "version": "verifier 1", "sha256": _sha("verifier")},
            "required_edges": list(verifier.REQUIRED_RELATIONS),
            "edge_results": edges,
            "failures": [],
        },
        "limitations": [],
    }


def _schema_errors(manifest: dict) -> list[str]:
    if Draft202012Validator is None:
        pytest.skip("jsonschema package not installed")
    schema = json.loads((HARNESS / "evidence/s9_source_build_manifest.schema.json").read_text())
    return [error.message for error in Draft202012Validator(schema).iter_errors(manifest)]


def test_complete_s9_graph_has_one_hash_bound_step_per_edge():
    manifest = _manifest()
    assert not _schema_errors(manifest)
    assert verifier.verify_manifest_semantics(manifest) == []


def test_schema_valid_single_ghost_resolves_edge_cannot_prove_lineage(tmp_path: Path):
    manifest = _manifest()
    unrelated_source = {
        "artifact_id": "unrelated-source",
        "kind": "source",
        "path": "other/unrelated.F",
        "sha256": _sha("unrelated-source"),
        "mtime_utc": None,
    }
    unrelated_receipt = {
        "artifact_id": "unrelated-receipt",
        "kind": "receipt",
        "path": "receipts/unrelated.log",
        "sha256": _sha("unrelated-receipt"),
        "mtime_utc": None,
    }
    manifest["artifacts"].extend([unrelated_source, unrelated_receipt])
    manifest["source_tree"]["files"].append({
        "artifact_id": unrelated_source["artifact_id"],
        "path": unrelated_source["path"],
        "role": "fortran_source",
        "sha256": unrelated_source["sha256"],
    })
    ghost = {"artifact_id": "ghost", "path": "ghost/libkdm6_c.dylib", "sha256": "f" * 64}
    executable = {"artifact_id": "ghost-exe", "path": "ghost/wrf.exe", "sha256": "e" * 64}
    manifest["runtime_loader"]["executable_sha256"] = "d" * 64
    manifest["runtime_loader"]["observed_resolution"] = ghost
    manifest["runtime_loader"]["observation_receipt_sha256"] = "c" * 64
    manifest["lineage_gate"]["edge_results"] = [{
        "from_artifact": executable,
        "to_artifact": ghost,
        "relation": "resolves_to",
        "status": "proven",
        "receipt_sha256": "b" * 64,
    }]

    assert not _schema_errors(manifest), "counterexample must pass shape-only JSON Schema validation"
    errors = verifier.verify_manifest_semantics(manifest)
    assert any("exactly the six required relation types" in error for error in errors)
    assert any("unknown artifact_id 'ghost'" in error for error in errors)
    assert any("runtime_loader executable_sha256" in error for error in errors)
    assert any("source artifact is not used" in error for error in errors)
    assert any("unrelated/unreferenced receipt artifact" in error for error in errors)
    manifest_path = tmp_path / "counterexample.json"
    manifest_path.write_text(json.dumps(manifest))
    result = subprocess.run(
        [sys.executable, str(HARNESS / "verify_s9_source_build_manifest.py"), str(manifest_path), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "edge_results must cover exactly the six required relation types" in result.stderr


def test_missing_kdm6_archive_member_is_rejected():
    manifest = _manifest()
    archive = next(a for a in manifest["artifacts"] if a.get("kind") == "archive")
    archive["archive_members"] = [r for r in archive["archive_members"] if not r["path"].endswith("module_mp_kdm6.o")]
    errors = verifier.verify_manifest_semantics(manifest)
    assert any("archive member inventory omits KDM6 objects" in error for error in errors)


def test_edge_endpoint_hash_must_match_inventory():
    manifest = _manifest()
    manifest["lineage_gate"]["edge_results"][0]["from_artifact"]["sha256"] = "f" * 64
    errors = verifier.verify_manifest_semantics(manifest)
    assert any("path/hash differs from inventory" in error for error in errors)


def test_inventory_sha_is_checked_against_file_bytes(tmp_path: Path):
    payload = b"captured source bytes"
    source = tmp_path / "source.F"
    source.write_bytes(payload)
    manifest = {"artifacts": [{
        "artifact_id": "source",
        "kind": "source",
        "path": "source.F",
        "sha256": _sha("different bytes"),
    }]}
    assert any("artifact bytes do not match SHA-256" in error for error in verifier.verify_artifact_bytes(manifest, tmp_path))
