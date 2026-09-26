"""Regression tests for fail-closed S9 lineage edge verification."""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
capture_tool = importlib.import_module("capture_s9_dyld")
verifier = importlib.import_module("verify_s9_source_build_manifest")

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - schema dependency is optional for semantic unit tests
    Draft202012Validator = None


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _ar_record(name: str, payload: bytes) -> bytes:
    fields = (f"{name}/", "0", "0", "0", "100644", str(len(payload)))
    widths = (16, 12, 6, 6, 8, 10)
    header = "".join(value.ljust(width) for value, width in zip(fields, widths)).encode() + b"`\n"
    return header + payload + (b"\n" if len(payload) % 2 else b"")


def _manifest() -> dict:
    artifacts: list[dict] = []
    source_files: list[dict] = []
    edges: list[dict] = []
    steps: list[dict] = []

    def add(kind: str, path: str, *, role: str | None = None, members: list | None = None, member_inventory: list | None = None) -> dict:
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
        if member_inventory is not None:
            artifact["member_inventory"] = copy.deepcopy(member_inventory)
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
    archive = add("archive", "main/libwrflib.a", members=[ref(a) for a in fortran_objects], member_inventory=[{"name":Path(a["path"]).name,"sha256":a["sha256"]} for a in fortran_objects])
    _, archive_receipt = step("archive", fortran_objects, [archive])
    for obj in fortran_objects:
        edge("archives_into", obj, archive, archive_receipt)

    core_members = [{"name":Path(obj["path"]).name,"sha256":obj["sha256"]} for obj in core_objects]
    core_archive = add("archive", "libtorch/build/libkdm6.a", members=[ref(obj) for obj in core_objects], member_inventory=core_members)
    _, core_archive_receipt = step("archive", core_objects, [core_archive])
    for obj in core_objects:
        edge("archives_into", obj, core_archive, core_archive_receipt)
    build_dylib = add("shared_library", "libtorch/build/libkdm6_c.2.0.0.dylib")
    _, cpp_link_receipt = step("link", [core_archive, bridge_obj], [build_dylib])
    edge("links_into", core_archive, build_dylib, cpp_link_receipt)
    edge("links_into", bridge_obj, build_dylib, cpp_link_receipt)

    installed_core = add("archive", "libtorch/install/lib/libkdm6.a", members=[ref(obj) for obj in core_objects], member_inventory=core_members)
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
            "compiler": {"path": "<FC>", "version": "fc 1", "sha256": _sha("fc")},
            "linker": {"path": "<LD>", "version": "ld 1", "sha256": _sha("ld")},
            "build_system": {"path": "<BUILD_SYSTEM>", "version": "make 1", "sha256": _sha("make")},
            "mpi_launcher": {"path": "<MPI_LAUNCHER>", "version": "Open MPI 5", "sha256": _sha("mpirun")},
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
            "verifier": {"path": "<S9_VERIFIER>", "version": "verifier 1", "sha256": _sha("verifier")},
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
    loader_step = next(s for s in manifest["build_steps"] if s["kind"] == "loader_inspection")
    stdout = next(a for a in manifest["artifacts"] if a["artifact_id"] == loader_step["stdout_receipt"]["artifact_id"])
    stderr = next(a for a in manifest["artifacts"] if a["artifact_id"] == loader_step["stderr_receipt"]["artifact_id"])
    manifest["artifacts"] = [a for a in manifest["artifacts"] if a["artifact_id"] not in {stdout["artifact_id"], stderr["artifact_id"]}]
    loader_step.pop("stdout_receipt")
    loader_step.pop("stderr_receipt")

    expected_library_path = str((root / library["path"]).resolve())
    fake_line = f"dyld[4242]: FABRICATED: loaded {expected_library_path} "
    stdout_bytes = (fake_line + "\n").encode()
    stderr_bytes = b""
    manifest_id = manifest["manifest_id"]
    stdout_rel = f"host/s9-captures/{manifest_id}.stdout.log"
    stderr_rel = f"host/s9-captures/{manifest_id}.stderr.log"
    for relative, payload in ((stdout_rel, stdout_bytes), (stderr_rel, stderr_bytes)):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

    exe = next(a for a in manifest["artifacts"] if a["path"] == "main/wrf.exe")
    library = next(a for a in manifest["artifacts"] if a["path"] == "libtorch/install/lib/libkdm6_c.2.0.0.dylib")
    raw_env = {
        "PATH": "/Users/example-user/bin:/usr/bin",
        "DYLD_PRINT_LIBRARIES": "1",
        "DYLD_PRINT_RPATHS": "1",
        "DYLD_LIBRARY_PATH": "/private/tmp/example-project/libtorch/install/lib",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "OMP_THREAD_LIMIT": "1",
    }
    public_env = capture_tool._public_environment(raw_env)
    env_digest = capture_tool._environment_digest(public_env)
    receipt_path = "harness/evidence/fabricated-loader-capture.json"
    receipt_artifact = {
        "artifact_id": "fabricated-loader-capture",
        "kind": "receipt",
        "path": receipt_path,
        "sha256": "0" * 64,
        "mtime_utc": None,
    }
    process_argv = ["/bin/echo", "dyld[4242]: FABRICATED: loaded", expected_library_path, ""]
    manifest["toolchain"]["mpi_launcher"] = {
        "path": "<MPI_LAUNCHER>",
        "version": "echo fake launcher",
        "sha256": hashlib.sha256(Path("/bin/echo").resolve().read_bytes()).hexdigest(),
    }
    private_path = f"host/s9-captures/{manifest_id}.raw.json"
    capture_argv = capture_tool._public_capture_argv(manifest_id, exe["artifact_id"], library["artifact_id"])
    capture = {
        "schema_version": "s9-dyld-capture/v1",
        "capture_tool_path": verifier.CAPTURE_TOOL_PATH,
        "capture_tool_sha256": verifier.CAPTURE_TOOL_SHA256,
        "manifest_id": manifest_id,
        "capture_argv": capture_argv,
        "process_argv": capture_tool._public_process_argv(),
        "launcher_sha256": hashlib.sha256(Path("/bin/echo").resolve().read_bytes()).hexdigest(),
        "process_cwd": "<RUN_DIR>",
        "process_environment": public_env,
        "process_environment_sha256": env_digest,
        "process_exit_code": 0,
        "executable": _ref(exe),
        "loaded_library": _ref(library),
        "stdout_sha256": hashlib.sha256(stdout_bytes).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr_bytes).hexdigest(),
        "dyld_image_lines": capture_tool._public_dyld_lines([fake_line]),
    }
    raw_argv = [
        "--root", str(root), "--manifest-id", manifest_id,
        "--executable", exe["path"], "--executable-id", exe["artifact_id"],
        "--library", library["path"], "--library-id", library["artifact_id"],
        "--cwd", "run", "--launcher", "/bin/echo",
        "--receipt", receipt_path, "--private-receipt", private_path,
        "--stdout", stdout_rel, "--stderr", stderr_rel,
    ]
    raw_capture = {
        "schema_version": "s9-dyld-raw-capture/v1",
        "manifest_id": manifest_id,
        "capture_tool_sha256": verifier.CAPTURE_TOOL_SHA256,
        "raw_capture_argv": [sys.executable, str(copied_tool.resolve()), *raw_argv],
        "raw_process_argv": process_argv,
        "raw_launcher_sha256": hashlib.sha256(Path("/bin/echo").resolve().read_bytes()).hexdigest(),
        "raw_process_cwd": str(run_dir.resolve()),
        "raw_process_environment": raw_env,
        "process_exit_code": 0,
        "raw_executable_path": str((root / exe["path"]).resolve()),
        "raw_executable_sha256": exe["sha256"],
        "raw_loaded_library_path": str((root / library["path"]).resolve()),
        "raw_loaded_library_sha256": library["sha256"],
        "raw_stdout_path": str((root / stdout_rel).resolve()),
        "raw_stderr_path": str((root / stderr_rel).resolve()),
        "stdout_sha256": hashlib.sha256(stdout_bytes).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr_bytes).hexdigest(),
        "dyld_image_lines": [fake_line],
    }
    private_path_full = root / private_path
    private_path_full.parent.mkdir(parents=True, exist_ok=True)
    raw_receipt_bytes = (json.dumps(raw_capture, sort_keys=True, indent=2) + "\n").encode()
    private_path_full.write_bytes(raw_receipt_bytes)
    capture["private_receipt_sha256"] = hashlib.sha256(raw_receipt_bytes).hexdigest()
    receipt_bytes = (json.dumps(capture, sort_keys=True, indent=2) + "\n").encode()
    receipt_artifact["sha256"] = hashlib.sha256(receipt_bytes).hexdigest()
    receipt_file = root / receipt_path
    receipt_file.parent.mkdir(parents=True, exist_ok=True)
    receipt_file.write_bytes(receipt_bytes)
    manifest["artifacts"].append(receipt_artifact)

    step = next(s for s in manifest["build_steps"] if s["kind"] == "loader_inspection")
    step["kind"] = "loader_observation"
    step["argv"] = capture_argv
    step["cwd"] = "<BUILD_ROOT>"
    step["inputs"].append(_ref(tool_artifact))
    step["outputs"] = [_ref(receipt_artifact)]
    step["stdout_sha256"] = hashlib.sha256(stdout_bytes).hexdigest()
    step["stderr_sha256"] = hashlib.sha256(stderr_bytes).hexdigest()
    step["capture_receipt"] = _ref(receipt_artifact)
    runtime_loader = manifest["runtime_loader"]
    runtime_loader["evidence_level"] = "observed_loader_resolution"
    runtime_loader["observed_resolution"] = _ref(library)
    runtime_loader["observation_receipt_sha256"] = receipt_artifact["sha256"]
    runtime_loader["capture_receipt"] = _ref(receipt_artifact)
    runtime_loader["capture_stdout_sha256"] = hashlib.sha256(stdout_bytes).hexdigest()
    runtime_loader["capture_stderr_sha256"] = hashlib.sha256(stderr_bytes).hexdigest()
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


def test_unproven_gate_cannot_accept_proven_resolves_edge_without_capture():
    manifest = _manifest()
    loader_step = next(step for step in manifest["build_steps"] if step["kind"] == "loader_inspection")
    stdout = next(a for a in manifest["artifacts"] if a["artifact_id"] == loader_step["stdout_receipt"]["artifact_id"])
    stderr = next(a for a in manifest["artifacts"] if a["artifact_id"] == loader_step["stderr_receipt"]["artifact_id"])
    loader_step["kind"] = "loader_observation"
    loader_step["capture_receipt"] = _ref(stdout)
    loader_step["stdout_sha256"] = stdout["sha256"]
    loader_step["stderr_sha256"] = stderr["sha256"]
    edge = next(edge for edge in manifest["lineage_gate"]["edge_results"] if edge["relation"] == "resolves_to")
    edge["status"] = "proven"
    manifest["lineage_gate"]["status"] = "unproven"

    assert not _schema_errors(manifest), "the counterexample is shape-valid without a runtime_loader.capture"
    errors = verifier.verify_manifest_semantics(manifest)
    assert any("resolves_to cannot be proven without an independent signed loader attestation" in error for error in errors)


def test_echo_dyld_transcript_cannot_claim_a_proven_loader(tmp_path: Path):
    manifest = _manifest()
    _attach_echo_loader_capture(manifest, tmp_path)
    assert not _schema_errors(manifest), "fabricated transcript is shape-valid so semantic checks must reject it"
    public_receipt = json.dumps(manifest["runtime_loader"]["capture"], sort_keys=True)
    assert "/Users/example-user" not in public_receipt
    assert "/private/tmp/example-project" not in public_receipt
    assert "AWS_ACCESS_KEY_ID" not in public_receipt
    assert "raw_process_argv" not in public_receipt
    errors = verifier.verify_manifest_semantics(manifest, tmp_path)
    assert any("private loader command is outside allowlist" in error for error in errors)
    assert any("disabled without an independent signed loader attestation" in error for error in errors)


def test_environment_projection_drops_credentials_and_aliases_paths():
    public = capture_tool._public_environment({
        "HOME": "/Users/example-user",
        "PWD": "/private/tmp/example-project/run",
        "TMPDIR": "/var/folders/private",
        "AWS_ACCESS_KEY_ID": "AKIA-DO-NOT-SERIALIZE",
        "AWS_SECRET_ACCESS_KEY": "secret-do-not-serialize",
        "PATH": "/Users/example-user/bin:/usr/bin",
        "DYLD_LIBRARY_PATH": "/Users/example-user/project/libtorch/install/lib",
        "DYLD_PRINT_LIBRARIES": "1",
        "OMP_NUM_THREADS": "1",
    })
    serialized = json.dumps(public, sort_keys=True)
    assert set(public) == {"PATH", "DYLD_LIBRARY_PATH", "DYLD_PRINT_LIBRARIES", "OMP_NUM_THREADS"}
    assert public["PATH"].startswith("<redacted-path-sha256:")
    assert public["DYLD_LIBRARY_PATH"].startswith("<redacted-path-sha256:")
    assert all(token not in serialized for token in ("/Users/example-user", "/private/tmp", "var/folders", "AKIA-DO-NOT-SERIALIZE", "secret-do-not-serialize", "HOME", "PWD", "TMPDIR", "AWS_ACCESS_KEY_ID"))


def test_collector_produces_path_redacted_public_and_private_raw_receipts(tmp_path: Path, monkeypatch):
    root = tmp_path / "build-root"
    tool_path = root / verifier.CAPTURE_TOOL_PATH
    exe_rel = "host/KIM-meso_v1.0/main/wrf.exe"
    library_rel = "libtorch/install/lib/libkdm6_c.2.0.0.dylib"
    cwd_rel = "host/KIM-meso_v1.0/run"
    launcher = tmp_path / "bin/mpirun"
    for path in (tool_path, root / exe_rel, root / library_rel, root / cwd_rel, launcher):
        path.parent.mkdir(parents=True, exist_ok=True)
    (root / cwd_rel).mkdir(parents=True, exist_ok=True)
    tool_path.write_bytes((HARNESS / "capture_s9_dyld.py").read_bytes())
    tool_bytes = tool_path.read_bytes()
    (root / exe_rel).write_bytes(b"fake wrf executable")
    (root / library_rel).write_bytes(b"fake kdm6 dylib")
    launcher.write_text("trusted launcher placeholder; subprocess is mocked")
    launcher.chmod(0o755)
    for key, value in {
        "PATH": "/Users/example-user/bin:/usr/bin",
        "HOME": "/Users/example-user",
        "PWD": "/private/tmp/example-project",
        "TMPDIR": "/var/folders/private",
        "AWS_ACCESS_KEY_ID": "AKIA-DO-NOT-SERIALIZE",
        "AWS_SECRET_ACCESS_KEY": "secret-do-not-serialize",
        "DYLD_LIBRARY_PATH": "/Users/example-user/KDM6AD/libtorch/install/lib",
    }.items():
        monkeypatch.setenv(key, value)
    library_abs = str((root / library_rel).resolve())
    stdout = b"fake WRF stdout\n"
    stderr = f"dyld[777]: loaded {library_abs}\n".encode()
    child_argv = [str(launcher.resolve()), "-n", "1", str((root / exe_rel).resolve())]

    def fake_run(argv, *, cwd, env, capture_output, check):
        assert argv == child_argv
        assert cwd == (root / cwd_rel).resolve()
        assert capture_output and not check
        assert "AWS_ACCESS_KEY_ID" not in env and "HOME" not in env and "TMPDIR" not in env
        assert env["DYLD_PRINT_LIBRARIES"] == "1" and env["OMP_NUM_THREADS"] == "1"
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(capture_tool.subprocess, "run", fake_run)
    manifest_id = "collector-projection-test"
    public_receipt = "harness/evidence/collector-projection.json"
    private_receipt = f"host/s9-captures/{manifest_id}.raw.json"
    stdout_path = f"host/s9-captures/{manifest_id}.stdout.log"
    stderr_path = f"host/s9-captures/{manifest_id}.stderr.log"
    monkeypatch.setattr(sys, "argv", [
        str(tool_path), "--root", str(root), "--manifest-id", manifest_id,
        "--executable", exe_rel, "--executable-id", "wrf-exe",
        "--library", library_rel, "--library-id", "kdm6-c-dylib",
        "--cwd", cwd_rel, "--launcher", str(launcher), "--receipt", public_receipt,
        "--private-receipt", private_receipt, "--stdout", stdout_path, "--stderr", stderr_path,
    ])

    assert capture_tool.main() == 0
    public_path = root / public_receipt
    public = json.loads(public_path.read_text())
    public_json = public_path.read_text()
    private_path = root / private_receipt
    private = json.loads(private_path.read_text())
    assert hashlib.sha256(private_path.read_bytes()).hexdigest() == public["private_receipt_sha256"]
    assert private["raw_process_argv"] == child_argv
    assert public["process_argv"] == ["<MPI_LAUNCHER>", "-n", "1", "<WRF_EXE>"]
    assert public["process_cwd"] == "<RUN_DIR>"
    assert public["dyld_image_lines"] == ["dyld: loaded <INSTALLED_KDM6_C_ABI_DYLIB>"]
    assert all(token not in public_json for token in ("/Users/example-user", "/private/tmp/example-project", "/var/folders/private", "AKIA-DO-NOT-SERIALIZE", "secret-do-not-serialize", "HOME", "PWD", "TMPDIR", "AWS_ACCESS_KEY_ID"))
    assert (root / stdout_path).is_relative_to(root / "host")
    assert (root / stderr_path).is_relative_to(root / "host")

    def artifact(artifact_id: str, kind: str, path: str, payload: bytes) -> dict:
        return {"artifact_id": artifact_id, "kind": kind, "path": path, "sha256": hashlib.sha256(payload).hexdigest(), "mtime_utc": None}

    exe_ref = {"artifact_id": "wrf-exe", "path": exe_rel, "sha256": hashlib.sha256((root / exe_rel).read_bytes()).hexdigest()}
    library_ref = {"artifact_id": "kdm6-c-dylib", "path": library_rel, "sha256": hashlib.sha256((root / library_rel).read_bytes()).hexdigest()}
    tool_ref = {"artifact_id": "capture-tool", "path": verifier.CAPTURE_TOOL_PATH, "sha256": hashlib.sha256(tool_path.read_bytes()).hexdigest()}
    capture_ref = {"artifact_id": "capture-receipt", "path": public_receipt, "sha256": hashlib.sha256(public_path.read_bytes()).hexdigest()}
    manifest = {
        "artifacts": [
            artifact("wrf-exe", "executable", exe_rel, (root / exe_rel).read_bytes()),
            artifact("kdm6-c-dylib", "shared_library", library_rel, (root / library_rel).read_bytes()),
            artifact("capture-tool", "source", verifier.CAPTURE_TOOL_PATH, tool_bytes),
            artifact("capture-receipt", "receipt", public_receipt, public_path.read_bytes()),
        ],
        "toolchain": {"mpi_launcher": {"path": "<MPI_LAUNCHER>", "version": "mpirun fake fixture", "sha256": hashlib.sha256(launcher.read_bytes()).hexdigest()}},
        "runtime_loader": {
            "evidence_level": "observed_loader_resolution",
            "executable_sha256": exe_ref["sha256"],
            "observed_resolution": library_ref,
            "capture_receipt": capture_ref,
            "capture_stdout_sha256": public["stdout_sha256"],
            "capture_stderr_sha256": public["stderr_sha256"],
            "capture": public,
        },
        "build_steps": [{
            "kind": "loader_observation",
            "argv": public["capture_argv"],
            "inputs": [exe_ref, library_ref, tool_ref],
            "outputs": [capture_ref],
            "capture_receipt": capture_ref,
            "stdout_sha256": public["stdout_sha256"],
            "stderr_sha256": public["stderr_sha256"],
        }],
    }
    assert verifier.verify_loader_capture(manifest, root) == []


def test_cmake_static_and_shared_targets_match_manifest_contract():
    assert len(verifier.CPP_CORE_SOURCES) == 14
    assert verifier.verify_cmake_target_contract(HARNESS.parent) == []


def test_public_toolchain_rejects_absolute_executable_paths():
    manifest = _manifest()
    manifest["toolchain"]["compiler"]["path"] = "/Users/example-user/bin/gfortran"
    errors = verifier.verify_manifest_semantics(manifest)
    assert any("toolchain.compiler.path must be a path-redacted alias" in error for error in errors)
    assert _schema_errors(manifest)


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


@pytest.mark.parametrize("mutation", ["reverse", "extra_physical", "duplicate_pair"])
def test_core_archive_members_are_an_exact_ordered_bijection(mutation: str):
    manifest = _manifest()
    archive = next(a for a in manifest["artifacts"] if a.get("path") == "libtorch/build/libkdm6.a")
    if mutation == "reverse":
        archive["archive_members"].reverse()
    elif mutation == "extra_physical":
        archive["member_inventory"].append({"name": "hidden-extra.o", "sha256": _sha("hidden-extra")})
    else:
        archive["archive_members"].append(copy.deepcopy(archive["archive_members"][0]))
        archive["member_inventory"].append(copy.deepcopy(archive["member_inventory"][0]))
    errors = verifier.verify_manifest_semantics(manifest)
    assert any("archive_members must exactly match physical object members in order and multiplicity" in error for error in errors)


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
        "member_inventory": verifier.read_archive_member_inventory(archive_path),
    }
    errors = verifier.verify_artifact_bytes({"artifacts": [object, archive]}, tmp_path)
    assert any("archive member bytes differ from inventoried object" in error for error in errors)


def test_unlisted_physical_archive_member_is_rejected(tmp_path: Path):
    archive_path = tmp_path / "libkdm6.a"
    archive_bytes = b"!<arch>\n" + _ar_record("ops.cpp.o", b"ops") + _ar_record("hidden-extra.o", b"extra")
    archive_path.write_bytes(archive_bytes)
    actual = verifier.read_archive_member_inventory(archive_path)
    declared = [actual[0]]
    manifest = {"artifacts": [{
        "artifact_id": "core-archive",
        "kind": "archive",
        "path": "libkdm6.a",
        "sha256": hashlib.sha256(archive_bytes).hexdigest(),
        "mtime_utc": None,
        "archive_members": [],
        "member_inventory": declared,
    }]}
    errors = verifier.verify_artifact_bytes(manifest, tmp_path)
    assert any("physical archive member inventory/order/hash mismatch" in error for error in errors)


def test_ordered_physical_inventory_preserves_duplicate_member_names(tmp_path: Path):
    archive_path = tmp_path / "duplicates.a"
    archive_bytes = b"!<arch>\n" + _ar_record("same.o", b"first") + _ar_record("same.o", b"second")
    archive_path.write_bytes(archive_bytes)
    actual = verifier.read_archive_member_inventory(archive_path)
    assert len(actual) == 2
    assert [member["name"].rstrip("/") for member in actual] == ["same.o", "same.o"]
    assert actual[0]["sha256"] != actual[1]["sha256"]
    manifest = {"artifacts": [{
        "artifact_id": "duplicate-archive",
        "kind": "archive",
        "path": "duplicates.a",
        "sha256": hashlib.sha256(archive_bytes).hexdigest(),
        "mtime_utc": None,
        "archive_members": [],
        "member_inventory": actual,
    }]}
    assert verifier.verify_artifact_bytes(manifest, tmp_path) == []
