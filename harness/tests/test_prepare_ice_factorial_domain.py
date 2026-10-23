import numpy as np
import pytest

from harness import prepare_ice_factorial_domain as prep


class FakeVariable:
    name = "synthetic"
    dimensions = ("Time", "bottom_top", "south_north", "west_east")

    def __init__(self, value):
        self.value = value

    def __getitem__(self, key):
        return self.value[key]


def test_chunk_bounds_cover_tail_without_overlap():
    bounds = list(prep.chunk_bounds(65988, 512))
    assert bounds[0] == (0, 512)
    assert bounds[-1] == (65536, 65988)
    assert sum(stop - start for start, stop in bounds) == 65988
    assert all(a[1] == b[0] for a, b in zip(bounds, bounds[1:]))


def test_flat_reader_preserves_bottom_first_and_row_edges():
    values = np.arange(1 * 3 * 2 * 4, dtype=np.float32).reshape(1, 3, 2, 4)
    got = prep._read_flat(FakeVariable(values), 3, 6, ny=2, nx=4, levels=3)
    expected = np.array([[3, 11, 19], [4, 12, 20], [5, 13, 21]], dtype=np.float32)
    np.testing.assert_array_equal(got, expected)


def test_batched_binary64_packet_readback_matches_f64_prep_and_public_1d(tmp_path):
    pytest.importorskip("torch", reason="native prep execution needs Torch; packet/source guards remain NumPy-only")
    levels, columns = 39, 3
    config = {"ptop": 5000.0, "rd": 287.0, "p0": 100000.0, "t0": 300.0,
              "alpha": 1.6083624362945557, "gamma": 1.399999976158142,
              "kappa": 0.2857142984867096, "g": 9.8100004196167}
    thm = np.full((columns, levels), 280.0, dtype=np.float64)
    qv = np.full_like(thm, 0.01)
    mu = np.full(columns, 90000.0, dtype=np.float64)
    ph = np.broadcast_to(np.arange(levels + 1, dtype=np.float64) * 10000.0,
                         (columns, levels + 1)).copy()
    phb = np.zeros_like(ph)
    c3h = np.full(levels, 0.5, dtype=np.float64)
    c4h = np.zeros(levels, dtype=np.float64)
    c3f = np.linspace(1.0, 0.1, levels + 1, dtype=np.float64)
    c4f = np.zeros(levels + 1, dtype=np.float64)
    got = prep._native_prep_batch(thm, qv, mu, ph, phb, c3h, c4h, c3f, c4f, config)
    assert got.shape == (5, columns, levels)
    raw_fields = [np.full((columns, levels), idx + 0.25, dtype=np.float32)
                  for idx in range(11)]
    xland = np.array([1.0, 2.0, 1.0], dtype=np.float32)
    state, forcing, xland64 = prep._packet_arrays(got, raw_fields, xland)
    packet_path = tmp_path / "chunk.npz"
    flat = np.arange(columns, dtype=np.int32)
    np.savez(packet_path, state=state, forcing=forcing, xland=xland64, flat_indices=flat)
    with np.load(packet_path, allow_pickle=False) as packet:
        stored_state, stored_forcing, stored_xland = packet["state"], packet["forcing"], packet["xland"]
        assert stored_state.dtype == stored_forcing.dtype == stored_xland.dtype == np.float64
        np.testing.assert_array_equal(stored_state.view(np.uint64), state.view(np.uint64))
        np.testing.assert_array_equal(stored_forcing.view(np.uint64), got[1:].view(np.uint64))
        np.testing.assert_array_equal(stored_xland.view(np.uint64), xland.astype(np.float64).view(np.uint64))
        for row, raw in enumerate(raw_fields, start=1):
            np.testing.assert_array_equal(stored_state[row].view(np.uint64),
                                          raw.astype(np.float64).view(np.uint64))
    for index in range(columns):
        prep._sample_check(stored_state, stored_forcing, index, thm, qv, mu, ph, phb,
                           c3h, c4h, c3f, c4f, config)


def test_source_contract_checks_namelist_flags_checkpoint_attrs_time_and_grid():
    valid = """&DOMAINS
 HYPSOMETRIC_OPT=2,
 /
&PHYSICS
 MP_PHYSICS=137, 10*-1,
 USE_THETA_M=1,
 NON_HYDROSTATIC=11*T,
 /
"""
    attrs = {"MP_PHYSICS": np.int32(137), "USE_THETA_M": np.int32(1)}
    dimensions = {"west_east": 234, "south_north": 282,
                  "bottom_top": 39, "bottom_top_stag": 40}
    receipt = prep.verify_prep_source_contract(valid, attrs, dimensions, "2025-07-19_00:00:40")
    assert receipt["status"] == "passed"

    for before, after in (("MP_PHYSICS=137", "MP_PHYSICS=37"),
                          ("USE_THETA_M=1", "USE_THETA_M=0"),
                          ("HYPSOMETRIC_OPT=2", "HYPSOMETRIC_OPT=1"),
                          ("NON_HYDROSTATIC=11*T", "NON_HYDROSTATIC=11*F")):
        with pytest.raises(ValueError):
            prep.verify_prep_source_contract(valid.replace(before, after), attrs, dimensions,
                                             "2025-07-19_00:00:40")
    with pytest.raises(ValueError, match="MP_PHYSICS"):
        prep.verify_prep_source_contract(valid, {**attrs, "MP_PHYSICS": 37}, dimensions,
                                         "2025-07-19_00:00:40")
    with pytest.raises(ValueError, match="Times"):
        prep.verify_prep_source_contract(valid, attrs, dimensions, "2025-07-19_00:00:20")
    with pytest.raises(ValueError, match="dimensions"):
        prep.verify_prep_source_contract(valid, attrs, {**dimensions, "west_east": 233},
                                         "2025-07-19_00:00:40")


def test_final_packet_inventory_uses_final_producer_and_retains_history():
    import hashlib
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    evidence = root / "harness/evidence/ice_factorial_2026-10-23"
    inventory_path = evidence / "full_domain_preparation.json"
    inventory = json.loads(inventory_path.read_text())
    generation = inventory["final_packet_generation"]
    final_sha = generation["producer_sha256"]

    def sha(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    # The packet's two current producer identities and the pre-generation source
    # gate must all name the frozen producer used to regenerate the final chunks.
    assert inventory["producer_sha256"] == final_sha
    assert inventory["packet_producer_sha256_executed"] == final_sha
    producer_path = root / "harness/prepare_ice_factorial_domain.py"
    assert sha(producer_path) == final_sha
    gate_path = evidence / "final_packet_source_preflight.json"
    gate = json.loads(gate_path.read_text())
    assert generation["source_gate_checked_before_generation"] is True
    assert gate["producer_sha256"] == final_sha
    assert gate["packet_manifest_sha256"] == inventory["private_packet"]["manifest_sha256"]
    assert inventory["current_source_preflight"]["sha256"] == sha(gate_path)

    # Keep both earlier fingerprints explicitly historical, with a phase and
    # source receipt field for each; neither may masquerade as the final producer.
    prior_receipt_path = evidence / "post_preparation_source_preflight.json"
    prior_receipt = json.loads(prior_receipt_path.read_text())
    prior_provenance = {
        prior_receipt["producer_sha256_prior_inventory"]: (
            "producer_sha256_prior_inventory", "prior_inventory_fingerprint_before_frozen_source_gate"),
        prior_receipt["producer_sha256_executed"]: (
            "producer_sha256_executed", "earlier_fp64_packet_preparation_before_frozen_source_gate"),
    }
    history = inventory["producer_history"]
    by_sha = {entry["sha256"]: entry for entry in history}
    assert set(prior_provenance) <= set(by_sha)
    assert inventory["producer_sha256_recorded_prior_to_source_gate"] == prior_receipt[
        "producer_sha256_prior_inventory"]
    assert final_sha not in prior_provenance
    for digest, (source_field, expected_phase) in prior_provenance.items():
        entry = by_sha[digest]
        assert entry["phase"] == expected_phase and entry["origin"]
        reference = entry["reference"]
        assert reference["file"] == "post_preparation_source_preflight.json"
        assert reference["field"] == source_field
        assert reference["receipt_sha256"] == sha(prior_receipt_path)

    study_manifest = json.loads((evidence / "manifest.json").read_text())
    assert study_manifest["artifact_sha256"][
        "harness/evidence/ice_factorial_2026-10-23/full_domain_preparation.json"
    ] == sha(inventory_path)
    assert study_manifest["source_sha256"]["harness/prepare_ice_factorial_domain.py"] == sha(producer_path)
    assert study_manifest["source_sha256"]["harness/tests/test_prepare_ice_factorial_domain.py"] == sha(__file__)
