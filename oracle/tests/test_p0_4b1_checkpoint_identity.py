"""PR #16 review fix 4 — checkpoint identity regression tests.

The replay-audit checkpoint trust model went through seven review rounds
(stored-provenance trust, code_sha exemption, runtime-version drift, lazy
hashing). This file pins the final contract as pure unit tests — no 37-frame
trajectory, no RTTOV, no host assets: resume requires the checkpoint to match
the resuming session's startup identity on EVERY field (fingerprint + full
provenance), the only tolerated difference being the resume counter itself.
"""
import importlib.util
import pathlib

import pytest
import torch

_SCRIPT = (pathlib.Path(__file__).resolve().parents[1]
           / "scripts" / "p0_4b1_lc05_replay_audit.py")


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("p0_4b1_replay_audit", _SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture()
def identity(mod):
    meta = mod._ckpt_meta("traj-sha", "script-sha", "kdm6-sha")
    prov = {
        "producer_code_sha": "head-at-launch",
        "script_sha256": "script-sha",
        "kdm6_tree_sha256": "kdm6-sha",
        "trajectory": mod.FCST,
        "trajectory_sha256": "traj-sha",
        "restore_manifest_sha256": "manifest-sha",
        "torch_version": "2.8.0",
        "python_version": "3.9.10",
        "dt": mod.DT,
        "frame_start": 0,
        "frame_stop_exclusive": mod.N_CUM_STEPS,
        "xland_used": True,
        "ncmin_land": mod.NCMIN_LAND,
        "ncmin_sea": mod.NCMIN_SEA,
        "n_shards": 16,
    }
    return meta, prov


def _rec(i):
    """A frame record carrying every field the resumed run consumes later."""
    return {"frame": i, "sink_sum_of_column_equivalents_kg_m2": 1.0,
            "affected_fraction": 0.5}


def _ck(meta, prov, n_frames=3, resumes=None, frame_ids=None):
    frames = [_rec(i) for i in (frame_ids if frame_ids is not None
                                else range(n_frames))]
    stored = dict(prov)
    if resumes is not None:
        stored["checkpoint_resumes"] = resumes
    return {"meta": meta, "provenance": stored, "frames": frames,
            "cum36_sink": torch.zeros(4, dtype=torch.float64),
            "cum36_species": {sp: 0.0 for sp in ("qr", "qs", "qg", "qi")},
            "cum36_proj": 0.0}


# ── accept ───────────────────────────────────────────────────────────────────

def test_identical_identity_resumes(mod, identity):
    meta, prov = identity
    resumes = mod._validate_resume(_ck(meta, prov), meta, prov)
    assert resumes == 1


def test_only_resume_counter_differs_is_allowed_and_increments(mod, identity):
    meta, prov = identity
    resumes = mod._validate_resume(_ck(meta, prov, resumes=2), meta, prov)
    assert resumes == 3


# ── refuse: identity drift ───────────────────────────────────────────────────

@pytest.mark.parametrize("field", [
    "producer_code_sha", "script_sha256", "kdm6_tree_sha256",
    "trajectory_sha256", "restore_manifest_sha256",
    "torch_version", "python_version",
])
def test_provenance_field_drift_refuses(mod, identity, field):
    meta, prov = identity
    ck = _ck(meta, dict(prov, **{field: "SOMETHING-ELSE"}))
    with pytest.raises(RuntimeError, match="refusing to resume"):
        mod._validate_resume(ck, meta, prov)


@pytest.mark.parametrize("field,value", [
    ("script_sha256", "OTHER-SCRIPT"),
    ("kdm6_tree_sha256", "OTHER-TREE"),
    ("trajectory_sha256", "OTHER-TRAJ"),
    ("dt", 120.0),
    ("ncmin_land", 0.0),
    ("n_cum_steps", 12),
])
def test_fingerprint_drift_refuses(mod, identity, field, value):
    meta, prov = identity
    ck = _ck(dict(meta, **{field: value}), prov)
    with pytest.raises(RuntimeError):
        mod._validate_resume(ck, meta, prov)


# ── refuse: frame-set integrity ──────────────────────────────────────────────

def test_noncontiguous_frames_refuse(mod, identity):
    meta, prov = identity
    with pytest.raises(RuntimeError):
        mod._validate_resume(_ck(meta, prov, frame_ids=[0, 2, 3]), meta, prov)


@pytest.mark.parametrize("frame_ids", [[], list(range(38))])
def test_empty_or_overlong_frame_set_refuses(mod, identity, frame_ids):
    meta, prov = identity
    with pytest.raises(RuntimeError):
        mod._validate_resume(_ck(meta, prov, frame_ids=frame_ids), meta, prov)


# ── refuse: malformed checkpoints (valid torch files, broken semantics) ──────

def test_checkpoint_root_not_dict_refuses(mod, identity):
    meta, prov = identity
    with pytest.raises(RuntimeError, match="refusing to resume"):
        mod._validate_resume("not-a-dict", meta, prov)


def test_frames_not_list_refuses(mod, identity):
    meta, prov = identity
    ck = _ck(meta, prov)
    ck["frames"] = "abc"
    with pytest.raises(RuntimeError, match="refusing to resume"):
        mod._validate_resume(ck, meta, prov)


@pytest.mark.parametrize("frames", [
    [None],                      # record is not a dict
    [{}],                        # frame key missing
    [{"frame": False}],          # bool must NOT pass as frame 0 (bool < int)
    [{"frame": "0"}],            # string index
], ids=["record-none", "key-missing", "bool-frame", "string-frame"])
def test_malformed_frame_records_refuse(mod, identity, frames):
    meta, prov = identity
    ck = _ck(meta, prov)
    ck["frames"] = frames
    with pytest.raises(RuntimeError, match="refusing to resume"):
        mod._validate_resume(ck, meta, prov)


# ── refuse: payload schema (fields the resumed run consumes later) ───────────

def test_frame_record_missing_consumed_fields_refuses(mod, identity):
    meta, prov = identity
    ck = _ck(meta, prov)
    ck["frames"] = [{"frame": 0}]          # no sink sum / affected_fraction
    with pytest.raises(RuntimeError, match="refusing to resume"):
        mod._validate_resume(ck, meta, prov)


@pytest.mark.parametrize("mutate", [
    lambda ck: ck.pop("cum36_sink"),
    lambda ck: ck.__setitem__("cum36_sink", [0.0, 0.0]),                  # not a tensor
    lambda ck: ck.__setitem__("cum36_sink", torch.zeros((), dtype=torch.float64)),  # scalar broadcasts silently
    lambda ck: ck.__setitem__("cum36_sink", torch.zeros(4, dtype=torch.float32)),   # wrong dtype
    lambda ck: ck.pop("cum36_species"),
    lambda ck: ck.__setitem__("cum36_species", {"qr": 0.0}),              # species missing
    lambda ck: ck.__setitem__("cum36_species",
                              {sp: 0 for sp in ("qr", "qs", "qg", "qi")}),  # int, not float
    lambda ck: ck.pop("cum36_proj"),
    lambda ck: ck.__setitem__("cum36_proj", "0.0"),
], ids=["sink-missing", "sink-not-tensor", "sink-scalar", "sink-f32",
        "species-missing", "species-incomplete", "species-int", "proj-missing",
        "proj-string"])
def test_malformed_payload_refuses(mod, identity, mutate):
    meta, prov = identity
    ck = _ck(meta, prov)
    mutate(ck)
    with pytest.raises(RuntimeError, match="refusing to resume"):
        mod._validate_resume(ck, meta, prov)


@pytest.mark.parametrize("counter", ["2", True, -1, 2.0],
                         ids=["string", "bool", "negative", "float"])
def test_invalid_resume_counter_refuses(mod, identity, counter):
    meta, prov = identity
    with pytest.raises(RuntimeError, match="refusing to resume"):
        mod._validate_resume(_ck(meta, prov, resumes=counter), meta, prov)


# ── refuse: accumulator length vs the fingerprinted trajectory ───────────────

def test_wrong_length_cum36_sink_refuses(mod, identity):
    meta, prov = identity   # _ck builds cum36_sink with numel 4
    with pytest.raises(RuntimeError, match="refusing to resume"):
        mod._validate_resume(_ck(meta, prov), meta, prov, n_columns=8)


def test_matching_length_cum36_sink_resumes(mod, identity):
    meta, prov = identity
    assert mod._validate_resume(_ck(meta, prov), meta, prov, n_columns=4) == 1


# ── loud failure: corrupt checkpoint file ────────────────────────────────────

def test_truncated_checkpoint_fails_loud(mod, identity, tmp_path):
    meta, prov = identity
    bad = tmp_path / "ckpt.pt"
    bad.write_bytes(b"not a torch checkpoint")
    with pytest.raises(Exception):
        mod._load_and_validate_checkpoint(str(bad), meta, prov)


def test_load_and_validate_roundtrip(mod, identity, tmp_path):
    meta, prov = identity
    path = tmp_path / "ckpt.pt"
    torch.save(_ck(meta, prov, resumes=1), str(path))
    ck, resumes = mod._load_and_validate_checkpoint(str(path), meta, prov)
    assert resumes == 2 and len(ck["frames"]) == 3


# ── loud failure: positive-dt instrumentation gap (no zero-fill masking) ─────

def test_positive_dt_empty_ledger_fails_loud():
    from kdm6.water_budget import SedimentationLedger
    with pytest.raises(ValueError, match="no sedimentation substep recorded"):
        SedimentationLedger().finalize(like=None)
