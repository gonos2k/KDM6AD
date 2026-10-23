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
