import struct
import hashlib
import json
import os

import numpy as np
import pytest

from harness.ice_factorial_batch import (
    IN_HEADER, OUT_HEADER, _child_environment, _same_bits, execute_prepared_manifest,
    pack_request, plan_chunks, plan_prepared_manifest, unpack_response,
)


def inputs(b=2, levels=3):
    state = np.arange(12*b*levels, dtype=np.float64).reshape(12,b,levels)
    forcing = np.ones((4,b,levels), dtype=np.float64)
    xland = np.resize(np.array([1.,2.]), b)
    return state, forcing, xland


def test_request_header_and_field_major_payload():
    s, f, x = inputs()
    payload = pack_request(s, f, x, 60., 1.e6, 2.e6)
    magic, version, b, l, dt, nl, ns = IN_HEADER.unpack_from(payload)
    assert (magic, version, b, l, dt, nl, ns) == (b"K6BATI1\0", 1, 2, 3, 60., 1.e6, 2.e6)
    values = np.frombuffer(payload, dtype="<f8", offset=IN_HEADER.size)
    np.testing.assert_array_equal(values[:s.size].reshape(s.shape), s)
    np.testing.assert_array_equal(values[s.size:s.size+f.size].reshape(f.shape), f)
    np.testing.assert_array_equal(values[-b:], x)


def test_response_decodes_contract_and_rejects_trailing_data():
    b, l = 2, 3
    arrays = [np.arange(12*b*l), np.arange(4*b*l), np.arange(12*b*l), np.arange(3*b)]
    payload = OUT_HEADER.pack(b"K6BATO1\0", 1, b, l) + np.concatenate(arrays).astype("<f8").tobytes()
    out = unpack_response(payload)
    assert out["state_out"].shape == (12,b,l)
    assert out["precip"].shape == (3,b)
    with pytest.raises(ValueError, match="length"):
        unpack_response(payload + b"x")


def test_chunk_plan_is_stable_and_covers_columns_once():
    plan = plan_chunks(10, 4)
    assert plan == [(0,4),(4,8),(8,10)]
    assert [i for start,end in plan for i in range(start,end)] == list(range(10))


@pytest.mark.parametrize("bad", [0, 4097])
def test_chunk_plan_rejects_out_of_range_sizes(bad):
    with pytest.raises(ValueError):
        plan_chunks(10, bad)


def test_pack_rejects_invalid_per_column_xland_and_forcing():
    s,f,x = inputs()
    x[1] = 0
    with pytest.raises(ValueError, match="xland"):
        pack_request(s,f,x,60.,0.,0.)
    x[1] = 2
    f[2,1,0] = 0
    with pytest.raises(ValueError, match="positive"):
        pack_request(s,f,x,60.,0.,0.)


def test_pack_rejects_silent_f32_widening():
    s,f,x = inputs()
    with pytest.raises(ValueError, match="already be fp64"):
        pack_request(s.astype(np.float32),f,x,60.,0.,0.)


def test_manifest_plan_verifies_fp64_chunk_and_expands_four_arms(tmp_path):
    s, f, x = inputs(2, 3)
    chunk = tmp_path / "chunk_00000_00002.npz"
    np.savez(chunk, state=s, forcing=f, xland=x, flat_indices=np.array([0,1]),
             i=np.array([0,1]), j=np.array([0,0]))
    entry = {"path": chunk.name, "start_flat": 0, "stop_flat_exclusive": 2,
             "columns": 2, "sha256": hashlib.sha256(chunk.read_bytes()).hexdigest()}
    manifest = {"schema": "kdm6.ice_factorial_endpoint_preparation.v1",
        "coverage": {"columns_expected": 2, "columns_written": 2, "missing": 0, "duplicate": 0},
        "mapping": {"state_order": ["TH","Q","QC","QR","QI","QS","QG","NN","NC","NI","NR","BG"],
                    "forcing_order": ["DEN","PII","P","DELZ"]}, "chunks": [entry]}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    plan = plan_prepared_manifest(path)
    assert plan["execution"] == "dry_run_only"
    assert plan["coverage"] == {"missing": 0, "duplicate": 0}
    assert set(plan["arms"]) == {"raw_cap","norm_cap","raw_actual","norm_actual"}
    assert all(len(rows) == 1 and rows[0]["B"] == 2 for rows in plan["arms"].values())
    assert plan["runtime_config"]["workers_per_arm"] == 1


def test_execution_env_defaults_to_single_thread_and_clears_inherited_traces(monkeypatch):
    monkeypatch.setenv("OMP_NUM_THREADS", "8")
    monkeypatch.setenv("KDM6_ICE_BOUNDARY_TRACE", "/tmp/unwanted.tsv")
    child = _child_environment("raw_cap")
    assert child["OMP_NUM_THREADS"] == child["MKL_NUM_THREADS"] == "1"
    assert child["OMP_THREAD_LIMIT"] == child["OPENBLAS_NUM_THREADS"] == "1"
    assert "KDM6_ICE_BOUNDARY_TRACE" not in child
    assert _child_environment("raw_cap", {"KDM6_ICE_BOUNDARY_TRACE": "explicit.tsv"})[
        "KDM6_ICE_BOUNDARY_TRACE"] == "explicit.tsv"


def test_echo_verification_compares_signed_zero_bits():
    assert not _same_bits(np.array([-0.0]), np.array([0.0]))


@pytest.mark.parametrize("bad", [0, 11, True, 1.5])
def test_worker_count_is_bounded_integer(bad, tmp_path):
    with pytest.raises(ValueError, match="workers"):
        plan_prepared_manifest(tmp_path / "missing.json", workers=bad)


def test_prepared_manifest_workers_execute_all_chunks_in_stable_order(tmp_path):
    state, forcing, xland = inputs(5, 3)
    chunks=[]
    for idx, (start,end) in enumerate(((0,2),(2,4),(4,5))):
        path=tmp_path/f"chunk-{idx}.npz"
        ix=np.arange(start,end,dtype=np.int32)
        np.savez(path,state=state[:,start:end],forcing=forcing[:,start:end],
                 xland=xland[start:end],flat_indices=ix,i=ix,j=np.zeros_like(ix))
        chunks.append({"path":path.name,"start_flat":start,"stop_flat_exclusive":end,
            "columns":end-start,"bytes":path.stat().st_size,
            "sha256":hashlib.sha256(path.read_bytes()).hexdigest()})
    manifest={"schema":"kdm6.ice_factorial_endpoint_preparation.v1",
        "coverage":{"columns_expected":5,"columns_written":5,"missing":0,"duplicate":0},
        "mapping":{"state_order":["TH","Q","QC","QR","QI","QS","QG","NN","NC","NI","NR","BG"],
                   "forcing_order":["DEN","PII","P","DELZ"]},"chunks":chunks}
    manifest_path=tmp_path/"manifest.json"; manifest_path.write_text(json.dumps(manifest))
    fake=tmp_path/"fake_batch_tool.py"
    fake.write_text("#!/usr/bin/env python3\n" +
        "import pathlib,struct,sys\n"
        "args=sys.argv; src=pathlib.Path(args[args.index('--input')+1]); dst=pathlib.Path(args[args.index('--output')+1])\n"
        "b=src.read_bytes(); h=struct.Struct('<8sIII3d'); magic,v,B,L,dt,nl,ns=h.unpack_from(b)\n"
        "p=h.size; n=(12+4)*B*L; echo=b[p:p+n*8]; s=b[p:p+12*B*L*8]\n"
        "out=struct.pack('<8sIII',b'K6BATO1\\0',1,B,L)+echo+s+bytes(3*B*8); dst.write_bytes(out)\n")
    fake.chmod(fake.stat().st_mode | 0o111)
    result=execute_prepared_manifest(fake,manifest_path,tmp_path/"run",mode="raw_cap",
        dt=60.,ncmin_land=0.,ncmin_sea=0.,chunk_size=2,workers=3)
    assert result["workers"] == 3
    assert [(r["index"],r["start"],r["end"]) for r in result["fixed_chunk_plan"]] == [
        (0,0,2),(1,2,4),(2,4,5)]
    assert len(list((tmp_path/"run").glob("*.response.bin"))) == 3
