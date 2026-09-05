"""Focused regressions for publication anchors and malformed evidence boundaries."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "g33_fortran"))

import g33_bundle_io as bio  # noqa: E402
import g33_build_provenance as provenance  # noqa: E402
import g33_dump as gd  # noqa: E402
import g33_fourcase_fixture_check as cpp_producer  # noqa: E402
import g33_fortran_bundle_io as fbio  # noqa: E402
import g33_result as result  # noqa: E402
import test_g33_bundle_io as cpp_fixture  # noqa: E402
import test_g33_fortran_bundle_io as fortran_fixture  # noqa: E402


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _deep_json_array(depth=2000) -> str:
    return "[" * depth + "0" + "]" * depth


def _rewrite_surface_payload(path: Path) -> None:
    parsed = gd.read_container(path)
    replacement = path.with_suffix(".tmp.g33")
    with gd.G33Writer(replacement, parsed["header"]) as writer:
        for record in parsed["records"]:
            fields = {key: value for key, value in record.items()
                      if key != "payload"}
            payload = record["payload"]
            if record.get("field") == "bottom_fall_qr":
                payload = gd.pack_payload("f32", [123.0] * cpp_fixture.B)
            writer.record(fields, record["dtype"], record["shape"], payload)
        writer.finalize()
    replacement.replace(path)


def test_external_cpp_root_binds_the_consumed_evidence_tree(tmp_path):
    root = cpp_fixture._bundle(tmp_path / "bundle")
    anchored_root = _sha(root / "cpp_abc_manifest.json")
    _rewrite_surface_payload(
        root / "legacy-C-evidence" / "dump" / "cpp_legacy_L1_surface.g33")

    with pytest.raises(bio.BundleError, match="evidence tree sha256"):
        bio.verify_cpp_bundle(
            root,
            expected_manifest_sha256=anchored_root,
            expected_repo_commit=cpp_fixture.COMMIT,
            expected_fixture_id=cpp_fixture.gfx.DEFAULT_FIXTURE_ID,
            expected_fixture_manifest_sha256=(
                cpp_fixture.gfx.manifest_sha256(cpp_fixture.gfx.load_manifest())),
        )


@pytest.mark.parametrize("evidence_options", [{}, {"substeps": 2, "mstep": 2}])
def test_cpp_producer_binds_tree_after_all_artifacts_are_copied(
        tmp_path, evidence_options):
    root = cpp_fixture._bundle(tmp_path / "bundle", **evidence_options)
    manifest_path = root / "cpp_abc_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for algo, meta in manifest["algorithms"].items():
        meta.pop("evidence_tree_sha256")
        manifest["algorithms"][algo] = cpp_producer._bind_evidence_tree(root, meta)
    manifest_path.write_text(json.dumps(manifest))
    anchored_root = _sha(manifest_path)
    _rewrite_surface_payload(
        root / "legacy-C-evidence" / "dump" / "cpp_legacy_L1_surface.g33")

    with pytest.raises(bio.BundleError, match="evidence tree sha256"):
        bio.verify_cpp_bundle(root, expected_manifest_sha256=anchored_root)


def test_evidence_tree_digest_keeps_path_length_framing(tmp_path):
    root = cpp_fixture._bundle(tmp_path / "bundle", substeps=2, mstep=2)
    meta = json.loads((root / "cpp_abc_manifest.json").read_text())[
        "algorithms"]["legacy"]
    files = []
    for directory in (root / meta["evidence_dir"], root / meta["probe_dir"]):
        files.extend(path for path in directory.rglob("*") if path.is_file())
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda p: p.relative_to(root).as_posix()):
        name = path.relative_to(root).as_posix().encode("utf-8")
        data = path.read_bytes()
        digest.update(len(name).to_bytes(8, "big"))
        digest.update(name)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    assert digest.hexdigest() == meta["evidence_tree_sha256"]


def test_cpp_old_root_without_tree_binding_is_rejected(tmp_path):
    root = cpp_fixture._bundle(tmp_path / "bundle")
    manifest_path = root / "cpp_abc_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for meta in manifest["algorithms"].values():
        del meta["evidence_tree_sha256"]
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(bio.BundleError, match="old unbound evidence"):
        bio.verify_cpp_bundle(
            root,
            expected_manifest_sha256=_sha(manifest_path),
            expected_repo_commit=cpp_fixture.COMMIT,
            expected_fixture_id=cpp_fixture.gfx.DEFAULT_FIXTURE_ID,
            expected_fixture_manifest_sha256=(
                cpp_fixture.gfx.manifest_sha256(cpp_fixture.gfx.load_manifest())),
        )


@pytest.mark.parametrize("value", [[], "schedule"])
def test_sealed_schedule_wrong_shape_is_a_bundle_error(tmp_path, value):
    schedule = tmp_path / "schedule.json"
    schedule.write_text(json.dumps(value))
    with pytest.raises(bio.BundleError, match="top level"):
        cpp_producer._sealed_schedule([f"legacy={schedule}"], "legacy")


def test_sealed_schedule_duplicate_key_is_a_bundle_error(tmp_path):
    schedule = tmp_path / "schedule.json"
    schedule.write_text('{"loops": 1, "loops": 2}')
    with pytest.raises(bio.BundleError, match="duplicate JSON key"):
        cpp_producer._sealed_schedule([f"legacy={schedule}"], "legacy")


def test_malformed_sealed_schedule_uses_invalid_evidence_exit(tmp_path, monkeypatch):
    canonical = tmp_path / "canonical-driver"
    diagnostic = tmp_path / "diagnostic-driver"
    canonical.touch()
    diagnostic.touch()
    schedule = tmp_path / "schedule.json"
    schedule.write_text("[]")
    authority = cpp_fixture.gfx.load_manifest()

    def fake_run(_driver, argv, _cwd, _env):
        if "--fixture-only" in argv:
            return cpp_fixture.gfx.render_fixture_protocol(authority).encode()
        return cpp_fixture._abc_stdout(argv[0]).encode()

    monkeypatch.setattr(cpp_producer, "_run", fake_run)
    monkeypatch.setattr(sys, "argv", [
        "g33_fourcase_fixture_check.py",
        "--canonical-driver", str(canonical),
        "--diagnostic-driver", str(diagnostic),
        "--schedule", f"legacy={schedule}",
    ])
    with pytest.raises(SystemExit) as exc:
        cpp_producer.main()
    assert exc.value.code == cpp_producer.EXIT_EVIDENCE


def test_cpp_bundle_deep_json_is_a_typed_error(tmp_path):
    root = cpp_fixture._bundle(tmp_path / "bundle")
    (root / "cpp_abc_manifest.json").write_text(_deep_json_array())
    with pytest.raises(bio.BundleError, match="not valid JSON"):
        bio.verify_cpp_bundle(root)


def test_g33_dump_deep_json_is_a_typed_error():
    with pytest.raises(gd.G33Corruption, match="corrupt header JSON"):
        gd._parse_json(_deep_json_array().encode(), "header")


def test_fortran_manifest_deep_json_is_a_typed_error(tmp_path):
    root = fortran_fixture._bundle(tmp_path / "bundle")
    (root / "abc_manifest.json").write_text(_deep_json_array())
    with pytest.raises(fbio.FortranBundleError, match="not JSON"):
        fbio.verify_fortran_bundle(root, "legacy")


def test_fortran_provenance_deep_json_is_a_typed_error(tmp_path):
    root = fortran_fixture._bundle(tmp_path / "bundle")
    provenance_path = root / "A" / "provenance.json"
    provenance_path.write_text(_deep_json_array())
    manifest_path = root / "abc_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["build_provenance_sha256"]["A"] = _sha(provenance_path)
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(fbio.FortranBundleError, match="provenance is not JSON"):
        fbio.verify_fortran_bundle(root, "legacy")


def test_result_deep_json_is_a_typed_error(tmp_path):
    (tmp_path / "result.json").write_text(_deep_json_array())
    with pytest.raises(SystemExit, match="will not parse"):
        result.load(tmp_path)


def test_build_provenance_deep_json_is_reported(tmp_path):
    (tmp_path / "build_provenance.json").write_text(_deep_json_array())
    errors = provenance.verify(tmp_path)
    assert errors and "not readable JSON" in errors[0]


def test_absolute_in_bundle_symlink_is_rejected_before_resolution(tmp_path):
    root = cpp_fixture._bundle(tmp_path / "bundle")
    link = root / "legacy-evidence-link"
    link.symlink_to(root / "legacy-C-evidence", target_is_directory=True)
    with pytest.raises(bio.BundleError, match="symlink"):
        bio.cpp_evidence_tree_sha256(root, str(link))


@pytest.mark.parametrize("value", [[], None, "manifest"])
def test_cpp_manifest_wrong_top_level_shape_is_a_bundle_error(tmp_path, value):
    root = cpp_fixture._bundle(tmp_path / "bundle")
    (root / "cpp_abc_manifest.json").write_text(json.dumps(value))
    with pytest.raises(bio.BundleError, match="top level"):
        bio.verify_cpp_bundle(root)


@pytest.mark.parametrize("value", [[], None, "manifest"])
def test_fortran_manifest_wrong_top_level_shape_is_a_bundle_error(tmp_path, value):
    root = fortran_fixture._bundle(tmp_path / "bundle")
    (root / "abc_manifest.json").write_text(json.dumps(value))
    with pytest.raises(fbio.FortranBundleError, match="top level"):
        fbio.verify_fortran_bundle(root, "legacy")


def test_fortran_commit_must_be_a_reviewable_git_object_name(tmp_path):
    root = fortran_fixture._bundle(
        tmp_path / "bundle", manifest_edit=lambda m: m.update(repo_commit="x"))
    with pytest.raises(fbio.FortranBundleError, match="40-hex Git object"):
        fbio.verify_fortran_bundle(root, "legacy")


@pytest.mark.parametrize("anchor", ["expected_manifest_sha256",
                                     "expected_repo_commit",
                                     "expected_fixture_manifest_sha256"])
def test_empty_fortran_anchor_is_not_treated_as_absent(tmp_path, anchor):
    root = fortran_fixture._bundle(tmp_path / "bundle")
    with pytest.raises(fbio.FortranBundleError, match="64-hex|40-hex"):
        fbio.verify_fortran_bundle(root, "legacy", **{anchor: ""})


def test_fortran_source_digest_claims_require_sha256_syntax(tmp_path):
    def malformed(_lane, prov):
        prov["host_source_sha256"]["libmassv.F"] = "bogus"

    root = fortran_fixture._bundle(tmp_path / "bundle", prov_edit=malformed)
    with pytest.raises(fbio.FortranBundleError, match="64-hex SHA-256"):
        fbio.verify_fortran_bundle(root, "legacy")


def test_fortran_manifest_summary_shape_is_typed(tmp_path):
    root = fortran_fixture._bundle(
        tmp_path / "bundle", manifest_edit=lambda m: m.update(mstep_per_column=[]))
    with pytest.raises(fbio.FortranBundleError, match="mstep_per_column"):
        fbio.verify_fortran_bundle(root, "legacy")


def test_build_provenance_reports_a_non_digest_source_claim(tmp_path):
    root = tmp_path / "build"
    root.mkdir()
    (root / "sources.txt").write_text("missing-host-source.F\tbogus\n")
    (root / "commands.txt").write_text("gfortran -c missing-host-source.F\n")
    (root / "build_provenance.json").write_text(json.dumps({
        "sources": [{"path": "missing-host-source.F", "role": None,
                     "sha256": "bogus"}],
        "compile_commands": ["gfortran -c missing-host-source.F"],
        "diagnostic": {"outdir": "/build"},
    }))
    errors = provenance.verify(root)
    assert errors and "invalid provenance" in errors[0]


@pytest.mark.parametrize("commit", ["x", "a" * 40 + "+dirty+dirty"])
def test_result_record_rejects_unreviewable_commits(tmp_path, commit):
    rec = {
        "commit": commit,
        "command": ["driver"],
        "binary_sha256": "b" * 64,
        "input_sha256": "c" * 64,
        "result": {"members": [{"file": "out", "sha256": "d" * 64}],
                   "analyses": []},
    }
    (tmp_path / "result.json").write_text(json.dumps(rec))
    with pytest.raises(SystemExit, match="40-hex Git commit"):
        result.load(tmp_path)


@pytest.mark.parametrize("commit", ["x", "a" * 40 + "+dirty"])
def test_result_record_rejects_malformed_commit_before_writing(commit):
    with pytest.raises(SystemExit, match="40-hex Git commit"):
        result.record(commit=commit, dirty=False, command=["driver"],
                      binary_sha256="b" * 64, input_sha256="c" * 64,
                      members=[{"file": "out", "sha256": "d" * 64}],
                      analyses=[])
