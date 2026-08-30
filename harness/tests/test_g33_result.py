#!/usr/bin/env python3
"""The five-field result record: what it hashes, and what it holds a bundle to."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_result as res  # noqa: E402


def _rec(**over):
    base = dict(commit="a" * 40, dirty=False,
                command=["--fixture", "fx", "--algo", "legacy", "--mode", "rezero",
                         "--nsplit", "3,6", "--rho-profile", "as-is", "--arm", "reference"],
                binary_sha256="b" * 64, input_sha256="c" * 64,
                members=[], analyses=[])
    base.update(over)
    return res.record(**base)


def test_the_record_has_exactly_five_fields():
    assert sorted(_rec()) == ["binary_sha256", "command", "commit", "input_sha256", "result"]


def test_a_dirty_tree_is_recorded_but_does_not_change_the_identity():
    clean, dirty = _rec(dirty=False), _rec(dirty=True)
    assert clean["commit"] == "a" * 40 and dirty["commit"] == "a" * 40 + "+dirty"
    assert res.identity(clean) == res.identity(dirty)


@pytest.mark.parametrize("field,value", [
    ("commit", "d" * 40), ("binary_sha256", "e" * 64), ("input_sha256", "f" * 64),
    ("command", ["--fixture", "other"]),
])
def test_each_of_the_four_provenance_fields_moves_the_identity(field, value):
    assert res.identity(_rec(**{field: value})) != res.identity(_rec())


def test_the_result_does_not_move_the_identity():
    a = _rec(analyses=[{"file": "x.json", "sha256": "1" * 64, "analysis": "x"}])
    assert res.identity(a) == res.identity(_rec())


def test_a_missing_commit_is_refused():
    with pytest.raises(SystemExit):
        _rec(commit=None)


def _bundle(tmp_path, rec, files):
    for name, data in files.items():
        (tmp_path / name).write_bytes(data)
    res.write(tmp_path, rec)
    return tmp_path


def test_verify_holds_every_named_file_to_its_digest(tmp_path):
    exe = b"#!fake\n"
    mem = b"G33R BEGIN\n"
    an = b"{}\n"
    rec = _rec(binary_sha256=hashlib.sha256(exe).hexdigest(),
               members=[{"file": "n3.rezero.txt", "sha256": hashlib.sha256(mem).hexdigest(), "nsplit": 3}],
               analyses=[{"file": "n3.rezero.x.json", "sha256": hashlib.sha256(an).hexdigest(), "analysis": "x"}])
    b = _bundle(tmp_path, rec, {"g33_refine_driver": exe, "n3.rezero.txt": mem, "n3.rezero.x.json": an})
    assert res.verify(b) == []
    (b / "n3.rezero.x.json").write_bytes(b"{\"edited\": 1}\n")
    assert any("n3.rezero.x.json: MISMATCH" in x for x in res.verify(b))
    (b / "n3.rezero.txt").unlink()
    assert any("n3.rezero.txt: absent" in x for x in res.verify(b))


def test_verify_refuses_a_payload_that_is_a_symlink_out_of_the_bundle(tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"x")
    b = tmp_path / "b"
    b.mkdir()
    (b / "n3.rezero.txt").symlink_to(outside)
    exe = b"#!fake\n"
    (b / "g33_refine_driver").write_bytes(exe)
    res.write(b, _rec(binary_sha256=hashlib.sha256(exe).hexdigest(),
                      members=[{"file": "n3.rezero.txt", "sha256": hashlib.sha256(b"x").hexdigest()}]))
    assert any("NOT-SELF-CONTAINED" in x for x in res.verify(b))


def test_verify_names_the_executable_binary_sha256_points_at(tmp_path):
    b = _bundle(tmp_path, _rec(binary_sha256="0" * 64), {"g33_refine_driver": b"#!fake\n"})
    assert any("g33_refine_driver: MISMATCH" in x for x in res.verify(b))


def test_applicability_refuses_an_unlisted_analysis_rather_than_defaulting():
    assert res.applicable("metric_trajectory", "f32") and not res.applicable("metric_trajectory", "f64")
    with pytest.raises(KeyError):
        res.applicable("brand_new", "f32")


# ---- the raw member goes through the STRICT parser, and the name is bound to the stream ----
sys.path.insert(0, str(ROOT / "tests"))
from test_g33_refine_analyze import _stream  # noqa: E402


def test_a_member_is_admitted_only_through_the_strict_parser(tmp_path):
    good = tmp_path / "n3.rezero.txt"
    good.write_text(_stream(nsplit=3))
    row = res.member_entry(good)
    assert row["file"] == "n3.rezero.txt" and row["nsplit"] == 3 and row["mode"] == "rezero"
    assert row["sha256"] == res.sha256(good)
    lines = _stream(nsplit=6).splitlines()
    del lines[5]                                   # ragged: one state record short
    bad = tmp_path / "n6.rezero.txt"
    bad.write_text("\n".join(lines) + "\n")
    import g33_refine_analyze as ra
    with pytest.raises(ra.RefineError):
        res.member_entry(bad)


def test_the_filename_is_bound_to_the_stream(tmp_path):
    import g33_refine_analyze as ra
    p = tmp_path / "n6.rezero.txt"
    p.write_text(_stream(nsplit=3))                # says n6, is n3
    with pytest.raises(ra.RefineError):
        res.member_entry(p)
    q = tmp_path / "n3.carry.txt"
    q.write_text(_stream(nsplit=3))                # says carry, is rezero
    with pytest.raises(ra.RefineError):
        res.member_entry(q)
    r = tmp_path / "member3.txt"
    r.write_text(_stream(nsplit=3))
    with pytest.raises(ra.RefineError):
        res.member_entry(r)
