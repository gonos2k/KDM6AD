from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import native_moment_trace_overlay as overlay


def _fixture_sources(root: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for rel, insertions in (
        ("phys/module_mp_kdm6ad.f90", overlay._MP_INSERTIONS),
        ("dyn_em/solve_em.f90", overlay._SOLVE_INSERTIONS),
    ):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        ordered = sorted((anchor for _, anchor, _, _ in insertions), key=len, reverse=True)
        text = ""
        for anchor in ordered:
            anchor_text = "\n".join(anchor)
            if anchor_text not in text:
                text += anchor_text + "\n"
        if rel.startswith("phys/"):
            text = text.replace(
                "         trace_set_step, trace_record\n",
                "    USE kdm6ad_native_trace, ONLY: trace_real_kind, trace_enabled, &\n"
                "         trace_target_i, trace_target_j, trace_current_step, &\n"
                "         trace_set_step, trace_record\n",
            )
            text += "! preserved V1 trace marker\n"
        else:
            text = (
                "       its = max(grid%i_start(ij),ids)\n"
                "       ite = min(grid%i_end(ij),ide-1)\n"
                "       jts = max(grid%j_start(ij),jds)\n"
                "       jte = min(grid%j_end(ij),jde-1)\n"
                + text
            )
        path.write_text(text, encoding="utf-8")
        files[rel] = text.encode("utf-8")
    return files


def test_pins_match_authoritative_compiled_inputs():
    assert overlay.SOURCE_PINS == {
        "phys/module_mp_kdm6ad.f90": "457c9b904711397f4cbc01fbcd588c48a7739200ce50d00e30098209d220207a",
        "dyn_em/solve_em.f90": "2e82c883af596e50bb7daa879ff8597a8c572ce03d2b14d0859629201f61c0ea",
    }


def test_default_plan_is_read_only_and_apply_is_source_pinned(tmp_path, monkeypatch):
    originals = _fixture_sources(tmp_path)
    original_modes = {rel: (tmp_path / rel).stat().st_mode & 0o777 for rel in originals}
    monkeypatch.setattr(
        overlay,
        "SOURCE_PINS",
        {rel: hashlib.sha256(data).hexdigest() for rel, data in originals.items()},
    )

    plan = overlay.build_overlay_plan(tmp_path)
    assert plan["status"] == "ready"
    assert all(value == "inserted" for item in plan["files"] for value in item["insertions"].values())
    for rel, original in originals.items():
        assert (tmp_path / rel).read_bytes() == original

    applied = overlay.apply_overlay(tmp_path)
    assert applied["status"] == "applied"
    assert {rel: (tmp_path / rel).stat().st_mode & 0o777 for rel in originals} == original_modes
    mp = (tmp_path / "phys/module_mp_kdm6ad.f90").read_text(encoding="utf-8")
    solve = (tmp_path / "dyn_em/solve_em.f90").read_text(encoding="utf-8")
    for stage in ("MP_INPUT", "MP_OUTPUT", "HOST_WRITEBACK", "WRAPPER_POST"):
        assert f"'{stage}'" in mp
    for stage in ("ZERO_OUT_PRE", "MOMENTS_PRE", "MOMENTS_POST"):
        assert f"'{stage}'" in solve
    assert solve.index("jte = min(grid%j_end(ij),jde-1)") < solve.index(
        "CALL moment_trace_finish_values('ZERO_OUT_PRE'"
    )
    assert solve.index("CALL moment_trace_finish_values('ZERO_OUT_PRE'") < solve.index(
        "IF ( config_flags%mp_zero_out > 0 ) THEN"
    ) < solve.index("CALL microphysics_zero_outb")
    assert "kdm6ad_native_trace" in mp
    assert "kdm6ad_native_trace" not in solve


@pytest.mark.parametrize("anchor_mode", ("missing", "duplicated"))
def test_missing_or_duplicated_anchor_refuses_without_writing(tmp_path, monkeypatch, anchor_mode):
    originals = _fixture_sources(tmp_path)
    solve_path = tmp_path / "dyn_em/solve_em.f90"
    source = solve_path.read_text(encoding="utf-8")
    anchor = "       IF ( config_flags%mp_zero_out > 0 ) THEN"
    if anchor_mode == "missing":
        changed = source.replace(anchor, "", 1)
    else:
        block = anchor + "\n       CALL microphysics_zero_outb (                                    &"
        changed = source.replace(block, block + "\n" + block, 1)
    solve_path.write_text(changed, encoding="utf-8")
    monkeypatch.setattr(
        overlay,
        "SOURCE_PINS",
        {
            "phys/module_mp_kdm6ad.f90": hashlib.sha256(originals["phys/module_mp_kdm6ad.f90"]).hexdigest(),
            "dyn_em/solve_em.f90": hashlib.sha256(solve_path.read_bytes()).hexdigest(),
        },
    )
    before = {path: (tmp_path / path).read_bytes() for path in originals}
    plan = overlay.build_overlay_plan(tmp_path)
    assert plan["status"] == "blocked"
    assert plan["errors"]
    assert {path: (tmp_path / path).read_bytes() for path in originals} == before


def test_overlay_keeps_unrelated_v1_text_and_uses_host_moments(tmp_path, monkeypatch):
    originals = _fixture_sources(tmp_path)
    mp_path = tmp_path / "phys/module_mp_kdm6ad.f90"
    solve_path = tmp_path / "dyn_em/solve_em.f90"
    monkeypatch.setattr(
        overlay,
        "SOURCE_PINS",
        {
            "phys/module_mp_kdm6ad.f90": hashlib.sha256(originals["phys/module_mp_kdm6ad.f90"]).hexdigest(),
            "dyn_em/solve_em.f90": hashlib.sha256(originals["dyn_em/solve_em.f90"]).hexdigest(),
        },
    )
    before = mp_path.read_bytes()
    report = overlay.apply_overlay(tmp_path)
    assert report["status"] == "applied"
    result = mp_path.read_bytes()
    assert b"trace_target_i, trace_target_j, trace_current_step" in result
    assert b"CALL moment_trace_host_values('WRAPPER_POST'" in result
    assert b"! preserved V1 trace marker" in result
    assert len(result) > len(before)
    assert "P_QNC" in solve_path.read_text(encoding="utf-8")


@pytest.mark.parametrize("source_rel", tuple(overlay.SOURCE_PINS))
@pytest.mark.parametrize("alias_kind", ("direct", "symlink", "hardlink"))
@pytest.mark.parametrize("apply", (False, True))
def test_report_alias_refused_before_plan_or_apply(tmp_path, monkeypatch, source_rel, alias_kind, apply):
    originals = _fixture_sources(tmp_path)
    if apply:
        monkeypatch.setattr(
            overlay,
            "SOURCE_PINS",
            {rel: hashlib.sha256(data).hexdigest() for rel, data in originals.items()},
        )
    source = tmp_path / source_rel
    report = source if alias_kind == "direct" else tmp_path / "report.json"
    if alias_kind == "symlink":
        report.symlink_to(source)
    elif alias_kind == "hardlink":
        os.link(source, report)
    before = {rel: (tmp_path / rel).read_bytes() for rel in originals}
    args = ["--host-root", str(tmp_path), "--report", str(report)]
    if apply:
        args.append("--apply")
    with pytest.raises(SystemExit) as exc:
        overlay.main(args)
    assert exc.value.code == 2
    assert {rel: (tmp_path / rel).read_bytes() for rel in originals} == before


def test_fresh_report_records_blocked_plan_without_changing_inputs(tmp_path):
    originals = _fixture_sources(tmp_path)
    report = tmp_path / "report.json"
    assert overlay.main(["--host-root", str(tmp_path), "--report", str(report)]) == 2
    assert json.loads(report.read_text())["status"] == "blocked"
    assert {rel: (tmp_path / rel).read_bytes() for rel in originals} == originals


def test_report_tilde_path_is_written_where_it_was_checked(tmp_path, monkeypatch):
    _fixture_sources(tmp_path / "host")
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert overlay.main(["--host-root", str(tmp_path / "host"), "--report", "~/trace.json"]) == 2
    assert (tmp_path / "trace.json").is_file()
    assert not (work / "~").exists()


def test_source_parent_symlink_outside_host_root_is_refused(tmp_path, monkeypatch):
    root = tmp_path / "host"
    originals = _fixture_sources(root)
    outside = tmp_path / "outside"
    outside.mkdir()
    shutil.move(str(root / "phys"), str(outside / "phys"))
    (root / "phys").symlink_to(outside / "phys", target_is_directory=True)
    monkeypatch.setattr(
        overlay,
        "SOURCE_PINS",
        {rel: hashlib.sha256(data).hexdigest() for rel, data in originals.items()},
    )
    assert overlay.build_overlay_plan(root)["status"] == "blocked"
    assert overlay.apply_overlay(root)["status"] == "blocked"
    assert (outside / "phys/module_mp_kdm6ad.f90").read_bytes() == originals["phys/module_mp_kdm6ad.f90"]
