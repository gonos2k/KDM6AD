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


def test_generated_bindings_are_current():
    run = subprocess.run(
        [sys.executable, str(ROOT / "harness/g33_fixture_v1.py"), "--check"],
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
