from pathlib import Path

import harness.patch_restart_state_init as patcher
from harness.patch_restart_state_init import SOURCE_PATCHES, patch_host_root


def _synthetic_host(root: Path):
    for source in SOURCE_PATCHES:
        target = root / source.relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(snippet.old for snippet in source.snippets) + "\n", encoding="utf-8")


def test_default_check_only_reports_changes_without_writing(tmp_path):
    _synthetic_host(tmp_path)
    paths = [tmp_path / item.relative_path for item in SOURCE_PATCHES]
    before = [path.read_bytes() for path in paths]

    report = patch_host_root(tmp_path)

    assert report["status"] == "ready"
    assert report["mode"] == "check-only"
    assert all(path.read_bytes() == content for path, content in zip(paths, before))
    assert all(file["before_sha256"] != file["after_sha256"] for file in report["files"])


def test_apply_is_idempotent_and_guards_only_requested_initializers(tmp_path):
    _synthetic_host(tmp_path)

    first = patch_host_root(tmp_path, apply=True)
    second = patch_host_root(tmp_path, apply=True)

    assert first["status"] == "applied"
    assert second["status"] == "already_applied"
    physics = (tmp_path / SOURCE_PATCHES[0].relative_path).read_text(encoding="utf-8")
    urban = (tmp_path / SOURCE_PATCHES[1].relative_path).read_text(encoding="utf-8")
    assert "IF ((itree_canopy .ne. 0) .AND. (.NOT. restart)) then" in physics
    assert "IF (.NOT.restart) THEN\n      SH_URB2D" in urban
    assert "IF (.NOT.restart) QC_URB2D(I,J)=0.01" in urban
    assert urban.count("IF (.NOT.restart) THEN") == 1


def test_any_failed_preflight_leaves_both_target_files_unchanged(tmp_path):
    _synthetic_host(tmp_path)
    physics_path = tmp_path / SOURCE_PATCHES[0].relative_path
    urban_path = tmp_path / SOURCE_PATCHES[1].relative_path
    physics_before = physics_path.read_bytes()
    urban_path.write_text("unrecognized source context\n", encoding="utf-8")
    urban_before = urban_path.read_bytes()

    report = patch_host_root(tmp_path, apply=True)

    assert report["status"] == "refused"
    assert physics_path.read_bytes() == physics_before
    assert urban_path.read_bytes() == urban_before


def test_duplicate_or_partially_patched_context_is_refused(tmp_path):
    _synthetic_host(tmp_path)
    physics_path = tmp_path / SOURCE_PATCHES[0].relative_path
    physics_path.write_text(
        physics_path.read_text(encoding="utf-8") + SOURCE_PATCHES[0].snippets[0].old + "\n",
        encoding="utf-8",
    )
    before = {item.relative_path: (tmp_path / item.relative_path).read_bytes() for item in SOURCE_PATCHES}

    report = patch_host_root(tmp_path, apply=True)

    assert report["status"] == "refused"
    assert all((tmp_path / name).read_bytes() == content for name, content in before.items())


def test_comment_only_old_tree_guard_with_active_alternate_is_refused(tmp_path):
    _synthetic_host(tmp_path)
    physics_path = tmp_path / SOURCE_PATCHES[0].relative_path
    physics_path.write_text(
        "!   IF (itree_canopy .ne. 0) then\n"
        "   IF (itree_canopy .GT. 0) then\n",
        encoding="utf-8",
    )
    paths = [tmp_path / item.relative_path for item in SOURCE_PATCHES]
    before = [path.read_bytes() for path in paths]

    report = patch_host_root(tmp_path, apply=True)

    assert report["status"] == "refused"
    assert all(path.read_bytes() == content for path, content in zip(paths, before))


def test_comment_only_patched_tree_guard_with_active_alternate_is_refused(tmp_path):
    _synthetic_host(tmp_path)
    physics_path = tmp_path / SOURCE_PATCHES[0].relative_path
    physics_path.write_text(
        "!   IF ((itree_canopy .ne. 0) .AND. (.NOT. restart)) then\n"
        "   IF (itree_canopy .GT. 0) then\n",
        encoding="utf-8",
    )
    paths = [tmp_path / item.relative_path for item in SOURCE_PATCHES]
    before = [path.read_bytes() for path in paths]

    report = patch_host_root(tmp_path, apply=True)

    assert report["status"] == "refused"
    assert all(path.read_bytes() == content for path, content in zip(paths, before))



def test_mixed_patched_and_original_sources_are_refused(tmp_path):
    _synthetic_host(tmp_path)
    source = SOURCE_PATCHES[0]
    path = tmp_path / source.relative_path
    path.write_text(path.read_text().replace(source.snippets[0].old, source.snippets[0].new))
    before = {item.relative_path: (tmp_path / item.relative_path).read_bytes() for item in SOURCE_PATCHES}
    report = patch_host_root(tmp_path, apply=True)
    assert report["status"] == "refused"
    assert "mixed" in " ".join(report["errors"])
    assert all((tmp_path / name).read_bytes() == value for name, value in before.items())


def test_caught_second_file_replace_failure_rolls_back_both_sources(tmp_path, monkeypatch):
    _synthetic_host(tmp_path)
    targets = [tmp_path / item.relative_path for item in SOURCE_PATCHES]
    before = [path.read_bytes() for path in targets]
    replace = patcher.os.replace
    failed = False

    def fail_urban_patch_once(source, destination):
        nonlocal failed
        if Path(destination) == targets[1] and str(source).endswith(".patch-tmp") and not failed:
            failed = True
            raise OSError("injected second-source replace failure")
        return replace(source, destination)

    monkeypatch.setattr(patcher.os, "replace", fail_urban_patch_once)
    report = patch_host_root(tmp_path, apply=True)

    assert failed
    assert report["status"] == "apply_failed"
    assert [path.read_bytes() for path in targets] == before


def test_missing_host_root_is_an_explicit_skip(tmp_path):
    report = patch_host_root(tmp_path / "no-host")
    assert report["status"] == "skipped"
    assert "does not exist" in report["errors"][0]
