#!/usr/bin/env python3
"""The five-field result record: what it hashes, what it holds a bundle to,
and that a pre-format manifest converts to the same five fields."""
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


def test_convert_reads_the_five_fields_out_of_a_manifest_and_drops_the_pins():
    man = {
        "repo_commit": "9" * 40, "tree_dirty": True,
        "fixture_path": "harness/g33_fortran/g33_fixture_multisubcycle_v1.f90",
        "fixture_sha256": "1" * 64, "module_sha256": "2" * 64, "rho_profile": "uniform",
        "algorithm": "nmass", "arm": "probe", "instrumented": True,
        "members": [{"file": "n6.rezero.txt", "output_sha256": "3" * 64, "nsplit": 6, "mode": "rezero"},
                    {"file": "n3.rezero.txt", "output_sha256": "4" * 64, "nsplit": 3, "mode": "rezero"}],
        "analyses": [{"file": "n3.rezero.cap_interface.json", "sha256": "5" * 64, "analysis": "cap_interface",
                      "nsplit": 3, "analyzer": "harness/g33_cap_interface.py", "analyzer_sha256": "6" * 64,
                      "analyzer_commit": "7" * 40, "analyzer_blob_sha": "8" * 40}],
        "build_artifacts": [{"file": "g33_refine_driver", "sha256": "a" * 64}],
        "producer_modules": [{"module": "x", "sha256": "b" * 64}], "identity": {"role_graph": {}},
    }
    rec = res.convert(man)
    assert sorted(rec) == ["binary_sha256", "command", "commit", "input_sha256", "result"]
    assert rec["commit"] == "9" * 40 + "+dirty"
    assert rec["command"] == ["--fixture", "g33_fixture_multisubcycle_v1", "--algo", "nmass",
                              "--mode", "rezero", "--nsplit", "3,6", "--nflux",
                              "--rho-profile", "uniform", "--arm", "probe"]
    assert rec["binary_sha256"] == "a" * 64
    assert rec["input_sha256"] == res.input_digest_from("1" * 64, "2" * 64, "uniform")
    assert [m["sha256"] for m in rec["result"]["members"]] == ["3" * 64, "4" * 64]
    assert rec["result"]["analyses"] == [{"file": "n3.rezero.cap_interface.json", "sha256": "5" * 64,
                                          "analysis": "cap_interface", "nsplit": 3}]


def test_applicability_refuses_an_unlisted_analysis_rather_than_defaulting():
    assert res.applicable("metric_trajectory", "f32") and not res.applicable("metric_trajectory", "f64")
    with pytest.raises(KeyError):
        res.applicable("brand_new", "f32")


def test_the_converter_cli_writes_the_file_and_verify_reads_it_back(tmp_path):
    exe = b"#!fake\n"
    (tmp_path / "g33_refine_driver").write_bytes(exe)
    (tmp_path / "manifest.json").write_text(json.dumps({
        "repo_commit": "9" * 40, "fixture_path": "x/fx.f90", "fixture_sha256": "1" * 64,
        "module_sha256": "2" * 64, "members": [], "analyses": []}))
    assert res.main(["convert", str(tmp_path)]) == 0
    assert res.load(tmp_path)["binary_sha256"] == hashlib.sha256(exe).hexdigest()
    assert res.main(["verify", str(tmp_path)]) == 0


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
