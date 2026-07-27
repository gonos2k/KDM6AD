#!/usr/bin/env python3
"""Pure regressions for the shared four-backend raw-bit fixture authority."""
from __future__ import annotations

import copy
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))
import g33_fixture_v1 as fixture  # noqa: E402


@pytest.mark.parametrize("fixture_id", sorted(fixture.FIXTURES))
def test_generated_bindings_are_current(fixture_id):
    # EVERY registry entry, not just the default: a fixture whose JSON is edited
    # without regenerating its header/module would otherwise pass on existence alone
    run = subprocess.run(
        [sys.executable, str(ROOT / "harness/g33_fixture_v1.py"), "--check",
         "--fixture-id", fixture_id],
        cwd=ROOT, capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr


def test_fixture_protocol_round_trip_and_identity():
    data = fixture.load_manifest()
    text = fixture.render_fixture_protocol(data)
    assert fixture.parse_fixture_protocol(text, data) == (
        fixture.fixture_sha256(data), fixture.parameter_sha256(data))
    assert data["science_role"] == "arithmetic_synthetic"
    assert data["vertical_layout"] == "top_first"
    assert len(fixture.manifest_sha256(data)) == 64
    assert len(fixture.fortran_parameter_sha256(data)) == 64


@pytest.mark.parametrize("mutation", [
    "drop", "duplicate", "wrong_bit", "reorder", "wrong_k", "wrong_param"])
def test_fixture_protocol_rejects_incomplete_or_mutated_stream(mutation):
    data = fixture.load_manifest()
    lines = fixture.render_fixture_protocol(data).splitlines()
    i = next(i for i, line in enumerate(lines) if line.startswith("KDM6FIX FIXIN qr "))
    if mutation == "drop":
        lines.pop(i)
    elif mutation == "duplicate":
        lines.insert(i, lines[i])
    elif mutation == "wrong_bit":
        lines[i] = lines[i][:-1] + ("0" if lines[i][-1] != "0" else "1")
    elif mutation == "reorder":
        lines[i], lines[i + 1] = lines[i + 1], lines[i]
    elif mutation == "wrong_k":
        tok = lines[i].split(); tok[4] = "99"; lines[i] = " ".join(tok)
    else:
        j = next(j for j, line in enumerate(lines) if line.startswith("KDM6FIX PARAM dt "))
        lines[j] = lines[j][:-1] + ("0" if lines[j][-1] != "0" else "1")
    with pytest.raises(ValueError):
        fixture.parse_fixture_protocol("\n".join(lines) + "\n", data)


def test_one_bit_authority_mutation_changes_fixture_hash():
    data = fixture.load_manifest()
    mutant = copy.deepcopy(data)
    mutant["fields"]["qr"][0] = f"{int(mutant['fields']['qr'][0], 16) ^ 1:08x}"
    assert fixture.fixture_sha256(mutant) != fixture.fixture_sha256(data)
    with pytest.raises(ValueError):
        fixture.parse_fixture_protocol(fixture.render_fixture_protocol(mutant), data)


def test_actual_physical_fields_are_the_vertical_and_column_anchors():
    data = fixture.load_manifest()
    B, K = data["B"], data["K"]
    assert data["anchor_fields"] == {"vertical": "p", "column": "qv"}
    p = data["fields"]["p"]
    qv = data["fields"]["qv"]
    assert len(set(p[:K])) == K
    assert all(p[b*K:(b+1)*K] == p[:K] for b in range(B))
    assert len({qv[b*K] for b in range(B)}) == B
    assert all(len(set(qv[b*K:(b+1)*K])) == 1 for b in range(B))


def test_generated_cpp_binding_compiles(tmp_path):
    cxx = shutil.which("c++")
    if not cxx:
        pytest.skip("c++ not installed")
    src = tmp_path / "fixture.cpp"
    src.write_text(
        '#include "g33_fixture_v1.h"\n'
        'int main(){ return g33_fixture_v1::B==3 && g33_fixture_v1::K==4 ? 0:1; }\n')
    run = subprocess.run(
        [cxx, "-std=c++17", "-I", str(ROOT / "harness/g33_overlay"),
         str(src), "-o", str(tmp_path / "fixture")], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr


def test_generated_fortran_binding_compiles(tmp_path):
    fc = shutil.which("gfortran")
    if not fc:
        pytest.skip("gfortran not installed")
    run = subprocess.run(
        [fc, "-c", str(ROOT / "harness/g33_fortran/g33_fixture_v1.f90"),
         "-J", str(tmp_path), "-o", str(tmp_path / "fixture.o")],
        capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr


# ---- fixture registry --------------------------------------------------------

def test_every_registry_entry_matches_its_own_manifest():
    # a mislabelled row must not be able to pass one fixture off as another
    for fid in fixture.FIXTURES:
        assert fixture.spec(fid).fixture_id == fid


def test_registry_entries_have_distinct_identities():
    shas = {fid: fixture.fixture_sha256(fixture.load_manifest(fixture.spec(fid).manifest))
            for fid in fixture.FIXTURES}
    assert len(set(shas.values())) == len(shas), f"fixtures share an identity: {shas}"


def test_registry_artifacts_all_exist():
    for fid in fixture.FIXTURES:
        sp = fixture.spec(fid)
        for path in (sp.manifest, sp.cpp_header, sp.fortran_module):
            assert path.is_file(), f"{fid}: missing {path}"


@pytest.mark.parametrize("fixture_id", sorted(fixture.FIXTURES))
def test_fixture_protocol_round_trips_for_every_entry(fixture_id):
    _, data = fixture.load_fixture(fixture_id)
    text = fixture.render_fixture_protocol(data)
    assert fixture.parse_fixture_protocol(text, data) == (
        fixture.fixture_sha256(data), fixture.parameter_sha256(data))


def test_unknown_fixture_id_is_refused():
    with pytest.raises(fixture.UnknownFixture):
        fixture.spec("no_such_fixture")


def test_each_backend_build_selector_is_derived_from_one_id():
    # the two builds spell their flags differently; the registry is what stops a
    # caller pairing one backend's fixture with the other's
    ms = fixture.spec("arithmetic_multisubcycle_v1")
    assert ms.fortran_build_name == "g33_fixture_multisubcycle_v1"
    assert ms.cpp_define == "multisubcycle"
    base = fixture.spec(fixture.DEFAULT_FIXTURE_ID)
    assert base.fortran_build_name == "g33_fixture_v1" and base.cpp_define == ""
