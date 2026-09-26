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
        if kind in {"loader_inspection", "loader_observation"} and not outputs:
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

    core_objects: list[dict] = []
    for cpp_path in verifier.CPP_CORE_SOURCES:
        source = add("source", cpp_path)
        source_files.append({**ref(source), "role": "cpp_source"})
        object_name = Path(cpp_path).name + ".o"
        obj = add("object", f"libtorch/build/CMakeFiles/kdm6.dir/src/{object_name}")
        _, compile_receipt = step("compile", [source], [obj])
        edge("compiles_to", source, obj, compile_receipt)
        core_objects.append(obj)

    bridge = add("source", verifier.CPP_BRIDGE_SOURCE)
    source_files.append({**ref(bridge), "role": "cpp_source"})
    bridge_obj = add("object", "libtorch/build/CMakeFiles/kdm6_c.dir/bridge/kdm6_c_api.cpp.o")
    _, bridge_compile_receipt = step("compile", [bridge], [bridge_obj])
    edge("compiles_to", bridge, bridge_obj, bridge_compile_receipt)

    cmake = add("source", "libtorch/CMakeLists.txt")
    source_files.append({**ref(cmake), "role": "configure"})
    cmake_cache = add("other", "libtorch/build/CMakeCache.txt")
    step("configure", [cmake], [cmake_cache])

    fortran_objects = [a for a in artifacts if a["kind"] == "object" and a["path"].startswith("phys/")]
    archive = add("archive", "main/libwrflib.a", members=[ref(a) for a in fortran_objects])
    _, archive_receipt = step("archive", fortran_objects, [archive])
    for obj in fortran_objects:
        edge("archives_into", obj, archive, archive_receipt)

    core_archive = add("archive", "libtorch/build/libkdm6.a", members=[ref(obj) for obj in core_objects])
    _, core_archive_receipt = step("archive", core_objects, [core_archive])
    for obj in core_objects:
        edge("archives_into", obj, core_archive, core_archive_receipt)
    build_dylib = add("shared_library", "libtorch/build/libkdm6_c.2.0.0.dylib")
    _, cpp_link_receipt = step("link", [core_archive, bridge_obj], [build_dylib])
    edge("links_into", core_archive, build_dylib, cpp_link_receipt)
    edge("links_into", bridge_obj, build_dylib, cpp_link_receipt)

    installed_core = add("archive", "libtorch/install/lib/libkdm6.a", members=[ref(obj) for obj in core_objects])
    installed = add("shared_library", "libtorch/install/lib/libkdm6_c.2.0.0.dylib")
    _, install_receipt = step("install", [core_archive, build_dylib], [installed_core, installed])
    edge("installs_as", core_archive, installed_core, install_receipt)
    edge("installs_as", build_dylib, installed, install_receipt)

    executable = add("executable", "main/wrf.exe")
    _, exe_link_receipt = step("link", [archive, installed], [executable])
    edge("links_into", archive, executable, exe_link_receipt)
    edge("links_into", installed, executable, exe_link_receipt)
    _, loader_receipt = step("loader_inspection", [executable, installed], [])
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
            "mpi_launcher": {"path": "/opt/open-mpi/bin/mpirun", "version": "Open MPI 5", "sha256": _sha("mpirun")},
            "environment": {},
        },
        "build_steps": steps,
        "artifacts": artifacts,
        "runtime_loader": {
            "evidence_level": "unverified_loader",
            "executable_sha256": executable["sha256"],
            "install_names": ["@rpath/libkdm6_c.2.dylib"],
            "rpaths": ["libtorch/install/lib"],
            "expected_library": ref(installed),
        },
        "lineage_gate": {
            "status": "unverified_loader",
            "verifier": {"path": "/tool/verifier", "version": "verifier 1", "sha256": _sha("verifier")},
            "required_edges": list(verifier.REQUIRED_RELATIONS),
            "edge_results": [dict(edge, status="unproven") if edge["relation"] == "resolves_to" else edge for edge in edges],
            "failures": [],
        },
        "limitations": ["loader target is inferred from static Mach-O inspection; no independently authenticated runtime capture exists"],
    }


def _schema_errors(manifest: dict) -> list[str]:
    if Draft202012Validator is None:
        pytest.skip("jsonschema package not installed")
    schema = json.loads((HARNESS / "evidence/s9_source_build_manifest.schema.json").read_text())
    return [error.message for error in Draft202012Validator(schema).iter_errors(manifest)]


def _ref(artifact: dict) -> dict:
    return {key: artifact[key] for key in ("artifact_id", "path", "sha256")}


def _set_artifact_hash(manifest: dict, artifact_id: str, digest: str) -> None:
    def walk(value):
        if isinstance(value, dict):
            if value.get("artifact_id") == artifact_id:
                value["sha256"] = digest
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(manifest)


def _attach_echo_loader_capture(manifest: dict, root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    exe = next(a for a in manifest["artifacts"] if a["path"] == "main/wrf.exe")
    library = next(a for a in manifest["artifacts"] if a["path"] == "libtorch/install/lib/libkdm6_c.2.0.0.dylib")
    for artifact in (exe, library):
        path = root / artifact["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(artifact["path"].encode())
        _set_artifact_hash(manifest, artifact["artifact_id"], hashlib.sha256(path.read_bytes()).hexdigest())

    tool_path = HARNESS / "capture_s9_dyld.py"
    tool_bytes = tool_path.read_bytes()
    tool_artifact = {
        "artifact_id": "capture-tool",
        "kind": "source",
        "path": verifier.CAPTURE_TOOL_PATH,
        "sha256": hashlib.sha256(tool_bytes).hexdigest(),
        "mtime_utc": None,
    }
    manifest["artifacts"].append(tool_artifact)
    manifest["source_tree"]["files"].append({**_ref(tool_artifact), "role": "other"})
    copied_tool = root / verifier.CAPTURE_TOOL_PATH
    copied_tool.parent.mkdir(parents=True, exist_ok=True)
    copied_tool.write_bytes(tool_bytes)

    run_dir = root / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    stdout = next(a for a in manifest["artifacts"] if a["artifact_id"] == next(s for s in manifest["build_steps"] if s["kind"] == "loader_inspection")["stdout_receipt"]["artifact_id"])
    stderr = next(a for a in manifest["artifacts"] if a["artifact_id"] == next(s for s in manifest["build_steps"] if s["kind"] == "loader_inspection")["stderr_receipt"]["artifact_id"])
    expected_library_path = str((root / library["path"]).resolve())
    fake_line = f"dyld[4242]: FABRICATED: loaded {expected_library_path} "
    stdout_bytes = (fake_line + "\n").encode()
    stderr_bytes = b""
    for artifact, payload in ((stdout, stdout_bytes), (stderr, stderr_bytes)):
        path = root / artifact["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        _set_artifact_hash(manifest, artifact["artifact_id"], hashlib.sha256(payload).hexdigest())

    exe = next(a for a in manifest["artifacts"] if a["path"] == "main/wrf.exe")
    library = next(a for a in manifest["artifacts"] if a["path"] == "libtorch/install/lib/libkdm6_c.2.0.0.dylib")
    stdout = next(a for a in manifest["artifacts"] if a["artifact_id"] == stdout["artifact_id"])
    stderr = next(a for a in manifest["artifacts"] if a["artifact_id"] == stderr["artifact_id"])
    env = {
        "DYLD_PRINT_LIBRARIES": "1",
        "DYLD_PRINT_RPATHS": "1",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "OMP_THREAD_LIMIT": "1",
    }
    env_digest = hashlib.sha256(b"\0".join(f"{key}={env[key]}".encode() for key in sorted(env))).hexdigest()
    receipt_path = "receipts/fabricated-loader-capture.json"
    receipt_artifact = {
        "artifact_id": "fabricated-loader-capture",
        "kind": "receipt",
        "path": receipt_path,
        "sha256": "0" * 64,
        "mtime_utc": None,
    }
    process_argv = ["/bin/echo", "dyld[4242]: FABRICATED: loaded", expected_library_path, ""]
    manifest["toolchain"]["mpi_launcher"] = {
        "path": "/bin/echo",
        "version": "echo fake launcher",
        "sha256": hashlib.sha256(Path("/bin/echo").resolve().read_bytes()).hexdigest(),
    }
    capture_argv = [
        verifier.CAPTURE_TOOL_PATH, "--root", str(root),
        "--executable", exe["path"], "--executable-id", exe["artifact_id"],
        "--library", library["path"], "--library-id", library["artifact_id"],
        "--cwd", "run", "--launcher", "/bin/echo",
        "--receipt", receipt_path, "--stdout", stdout["path"], "--stderr", stderr["path"],
    ]
    capture = {
        "schema_version": "s9-dyld-capture/v1",
        "capture_tool_path": verifier.CAPTURE_TOOL_PATH,
        "capture_tool_sha256": verifier.CAPTURE_TOOL_SHA256,
        "capture_argv": capture_argv,
        "process_argv": process_argv,
        "launcher_sha256": hashlib.sha256(Path("/bin/echo").resolve().read_bytes()).hexdigest(),
        "process_cwd": "run",
        "process_environment": env,
        "process_environment_sha256": env_digest,
        "process_exit_code": 0,
        "executable": _ref(exe),
        "loaded_library": _ref(library),
        "stdout_sha256": stdout["sha256"],
        "stderr_sha256": stderr["sha256"],
        "dyld_image_lines": [fake_line],
    }
    receipt_bytes = (json.dumps(capture, sort_keys=True, indent=2) + "\n").encode()
    receipt_artifact["sha256"] = hashlib.sha256(receipt_bytes).hexdigest()
    receipt_file = root / receipt_path
    receipt_file.parent.mkdir(parents=True, exist_ok=True)
    receipt_file.write_bytes(receipt_bytes)
    manifest["artifacts"].append(receipt_artifact)

    step = next(s for s in manifest["build_steps"] if s["kind"] == "loader_inspection")
    step["kind"] = "loader_observation"
    step["argv"] = capture_argv
    step["inputs"].append(_ref(tool_artifact))
    step["outputs"] = [_ref(receipt_artifact), _ref(stdout), _ref(stderr)]
    step["capture_receipt"] = _ref(receipt_artifact)
    runtime_loader = manifest["runtime_loader"]
    runtime_loader["evidence_level"] = "observed_loader_resolution"
    runtime_loader["observed_resolution"] = _ref(library)
    runtime_loader["observation_receipt_sha256"] = receipt_artifact["sha256"]
    runtime_loader["capture_receipt"] = _ref(receipt_artifact)
    runtime_loader["capture_stdout"] = _ref(stdout)
    runtime_loader["capture_stderr"] = _ref(stderr)
    runtime_loader["capture"] = capture
    gate = manifest["lineage_gate"]
    gate["status"] = "proven"
    gate["edge_results"][-1]["status"] = "proven"
    gate["edge_results"][-1]["receipt_sha256"] = receipt_artifact["sha256"]
    manifest["limitations"] = []


def test_complete_s9_graph_has_one_hash_bound_step_per_edge():
    manifest = _manifest()
    assert not _schema_errors(manifest)
    assert verifier.verify_manifest_semantics(manifest) == []
    assert manifest["lineage_gate"]["status"] == "unverified_loader"
    assert manifest["lineage_gate"]["edge_results"][-1]["status"] == "unproven"


def test_echo_dyld_transcript_cannot_claim_a_proven_loader(tmp_path: Path):
    manifest = _manifest()
    _attach_echo_loader_capture(manifest, tmp_path)
    assert not _schema_errors(manifest), "fabricated transcript is shape-valid so semantic checks must reject it"
    errors = verifier.verify_manifest_semantics(manifest, tmp_path)
    assert any("process command is outside allowlist" in error for error in errors)
    assert any("disabled without an independent signed loader attestation" in error for error in errors)


def test_cmake_static_and_shared_targets_match_manifest_contract():
    assert len(verifier.CPP_CORE_SOURCES) == 14
    assert verifier.verify_cmake_target_contract(HARNESS.parent) == []


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
    archive = next(a for a in manifest["artifacts"] if a.get("path") == "main/libwrflib.a")
    archive["archive_members"] = [r for r in archive["archive_members"] if not r["path"].endswith("module_mp_kdm6.o")]
    errors = verifier.verify_manifest_semantics(manifest)
    assert any("libwrflib.a archive member inventory omits required objects" in error for error in errors)


def test_missing_core_cpp_member_is_rejected():
    manifest = _manifest()
    archive = next(a for a in manifest["artifacts"] if a.get("path") == "libtorch/build/libkdm6.a")
    archive["archive_members"] = [r for r in archive["archive_members"] if not r["path"].endswith("ops.cpp.o")]
    errors = verifier.verify_manifest_semantics(manifest)
    assert any("libkdm6.a archive member inventory omits required objects: ops.cpp.o" in error for error in errors)


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


def test_altered_core_archive_member_bytes_are_rejected(tmp_path: Path):
    object_path = tmp_path / "libtorch/build/CMakeFiles/kdm6.dir/src/ops.cpp.o"
    changed_member = tmp_path / "changed/ops.cpp.o"
    archive_path = tmp_path / "libtorch/build/libkdm6.a"
    object_path.parent.mkdir(parents=True)
    changed_member.parent.mkdir(parents=True)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    expected_bytes, changed_bytes = b"expected-object", b"altered-member"
    object_path.write_bytes(expected_bytes)
    changed_member.write_bytes(changed_bytes)
    subprocess.run(["ar", "-rcs", str(archive_path), str(changed_member)], check=True)
    object = {
        "artifact_id": "ops-object",
        "kind": "object",
        "path": "libtorch/build/CMakeFiles/kdm6.dir/src/ops.cpp.o",
        "sha256": hashlib.sha256(expected_bytes).hexdigest(),
        "mtime_utc": None,
    }
    archive = {
        "artifact_id": "core-archive",
        "kind": "archive",
        "path": "libtorch/build/libkdm6.a",
        "sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        "mtime_utc": None,
        "archive_members": [{key: object[key] for key in ("artifact_id", "path", "sha256")}],
    }
    errors = verifier.verify_artifact_bytes({"artifacts": [object, archive]}, tmp_path)
    assert any("archive member bytes differ from object inventory" in error for error in errors)
