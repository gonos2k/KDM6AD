import numpy as np
import pytest

from harness.native_replay_compare import compare_frames


def _times(*stamps):
    width = max(len(stamp) for stamp in stamps)
    return np.stack([
        np.frombuffer(stamp.encode("ascii").ljust(width, b" "), dtype="S1")
        for stamp in stamps
    ])


class FakeDimension:
    def __init__(self, size):
        self.size = size

    def __len__(self):
        return self.size


class FakeVariable:
    def __init__(self, values, dimensions, attrs=None):
        self.values = np.asanyarray(values)
        self.dimensions = tuple(dimensions)
        self.shape = self.values.shape
        self.dtype = self.values.dtype
        self.attrs = dict(attrs or {})

    def ncattrs(self):
        return list(self.attrs)

    def getncattr(self, name):
        return self.attrs[name]

    def __getitem__(self, index):
        return self.values[index]


class FakeDataset:
    def __init__(self, variables, dimensions):
        self.variables = variables
        self.dimensions = {name: FakeDimension(size) for name, size in dimensions.items()}


def _dataset(stamps, *, t_values=None, h_values=None, extra=None, dims=None):
    n = len(stamps)
    if t_values is None:
        t_values = np.asarray([[250.0], [251.0]][:n], dtype=np.float32)
    if h_values is None:
        h_values = np.asarray([[0.1], [0.2]][:n], dtype=np.float32)
    t_array = np.asarray(t_values, dtype=None if isinstance(t_values, np.ndarray) else np.float32)
    h_array = np.asarray(h_values, dtype=None if isinstance(h_values, np.ndarray) else np.float32)
    variables = {
        "Times": FakeVariable(_times(*stamps), ("Time", "DateStrLen")),
        "T": FakeVariable(t_array, ("Time", "bottom_top")),
        "H_DIABATIC": FakeVariable(h_array, ("Time", "bottom_top")),
    }
    if extra:
        variables.update(extra)
    dimension_sizes = {"Time": n, "DateStrLen": variables["Times"].shape[1], "bottom_top": 1}
    if dims:
        dimension_sizes.update(dims)
    return FakeDataset(variables, dimension_sizes)


T0 = "2025-07-19_00:02:00"
T1 = "2025-07-19_00:04:00"


def test_pairs_different_frame_indices_by_exact_timestamp():
    reference = _dataset(
        ["2025-07-19_00:00:00", T1, T0],
        t_values=np.asarray([[250.0], [251.0], [252.0]], dtype=np.float32),
        h_values=np.asarray([[0.1], [0.2], [0.3]], dtype=np.float32),
    )
    candidate = _dataset(
        ["2025-07-19_00:00:40", T0],
        t_values=np.asarray([[251.0], [252.0]], dtype=np.float32),
        h_values=np.asarray([[0.2], [0.3]], dtype=np.float32),
    )
    report = compare_frames(reference, candidate, 2, 1, T0)
    assert report["passed"]
    assert report["reference_frame"] == 2
    assert report["candidate_frame"] == 1
    assert report["times_values"] == {"reference": T0, "candidate": T0}


def test_rejects_wrong_selected_timestamp():
    reference = _dataset([T0])
    candidate = _dataset([T1])
    report = compare_frames(reference, candidate, 0, 0, T0)
    assert not report["passed"]
    assert "Times mismatch" in " ".join(report["errors"])


def test_missing_h_diabatic_is_not_hidden():
    reference = _dataset([T0])
    candidate = _dataset([T0])
    del candidate.variables["H_DIABATIC"]
    report = compare_frames(reference, candidate, 0, 0, T0)
    assert not report["passed"]
    assert report["missing_variables"] == ["H_DIABATIC"]


def test_reports_single_raw_bit_change_and_first_index():
    reference = _dataset([T0], t_values=[[1.0]], h_values=[[2.0]])
    changed = np.nextafter(np.float32(1.0), np.float32(2.0))
    candidate = _dataset([T0], t_values=[[changed]], h_values=[[2.0]])
    report = compare_frames(reference, candidate, 0, 0, T0)
    assert not report["passed"]
    assert report["numeric_element_mismatches"] == 1
    assert report["variables"]["T"]["mismatch_count"] == 1
    assert report["variables"]["T"]["first_mismatch_index"] == [0]
    assert report["variables"]["T"]["max_abs_difference"] > 0.0


def test_signed_zero_difference_is_not_tolerance_collapsed():
    reference = _dataset([T0], t_values=[[-0.0]], h_values=[[0.0]])
    candidate = _dataset([T0], t_values=[[0.0]], h_values=[[0.0]])
    report = compare_frames(reference, candidate, 0, 0, T0)
    assert not report["passed"]
    assert report["variables"]["T"]["mismatch_count"] == 1
    assert report["variables"]["T"]["max_abs_difference"] == 0.0


def test_rejects_non_time_shape_and_dtype_mismatches():
    reference = _dataset([T0], t_values=[[1.0]], h_values=[[2.0]])
    shape_candidate = _dataset(
        [T0], t_values=[[1.0, 1.0]], h_values=[[2.0, 2.0]],
        dims={"bottom_top": 2},
    )
    shape_candidate.variables["T"] = FakeVariable([[1.0, 1.0]], ("Time", "bottom_top"))
    shape_candidate.variables["H_DIABATIC"] = FakeVariable([[2.0, 2.0]], ("Time", "bottom_top"))
    shape_report = compare_frames(reference, shape_candidate, 0, 0, T0)
    assert not shape_report["passed"]
    assert any("dimension bottom_top size differs" in e for e in shape_report["errors"])

    dtype_candidate = _dataset([T0], t_values=np.asarray([[1.0]], dtype=np.float64), h_values=[[2.0]])
    dtype_report = compare_frames(reference, dtype_candidate, 0, 0, T0)
    assert not dtype_report["passed"]
    assert any("dtype mismatch" in e for e in dtype_report["errors"])


def test_matching_nan_payload_is_raw_match_but_not_finite_pass():
    nan = np.asarray([[np.float32(np.nan)]], dtype=np.float32)
    reference = _dataset([T0], t_values=nan, h_values=[[2.0]])
    candidate = _dataset([T0], t_values=nan.copy(), h_values=[[2.0]])
    report = compare_frames(reference, candidate, 0, 0, T0)
    assert report["variables"]["T"]["raw_bitwise_equal"]
    assert report["raw_bitwise_equal"]
    assert report["finite"] is False
    assert report["variables"]["T"]["reference_nonfinite"]["nan"] == 1
    assert not report["passed"]


def test_identical_finite_fill_sentinels_are_not_complete_values():
    reference = _dataset([T0])
    candidate = _dataset([T0])
    for dataset in (reference, candidate):
        dataset.variables["T"] = FakeVariable(
            np.asarray([[-9999.0]], dtype=np.float32),
            ("Time", "bottom_top"),
            attrs={"_FillValue": np.float32(-9999.0)},
        )
    report = compare_frames(reference, candidate, 0, 0, T0)
    assert report["raw_bitwise_equal"]
    assert report["finite"]
    assert report["complete_values"] is False
    assert report["variables"]["T"]["declared_missing_count"] == {
        "reference": 1,
        "candidate": 1,
    }
    assert not report["passed"]


def test_nonempty_masked_selected_values_are_rejected():
    reference = _dataset([T0])
    candidate = _dataset([T0])
    reference.variables["T"] = FakeVariable(
        np.ma.array([[250.0]], mask=[[True]], dtype=np.float32),
        ("Time", "bottom_top"),
    )
    with pytest.raises(ValueError, match="masked values"):
        compare_frames(reference, candidate, 0, 0, T0)


def test_compares_non_times_character_fields_exactly():
    reference = _dataset([T0], extra={"LABEL": FakeVariable(np.asarray([[b"A"]]), ("Time", "one"))}, dims={"one": 1})
    candidate = _dataset([T0], extra={"LABEL": FakeVariable(np.asarray([[b"B"]]), ("Time", "one"))}, dims={"one": 1})
    report = compare_frames(reference, candidate, 0, 0, T0)
    assert not report["passed"]
    assert "LABEL: character data differ" in report["errors"]


def test_unsupported_dtypes_are_rejected():
    reference = _dataset([T0], extra={"OBJECT": FakeVariable(np.asarray([[object()]], dtype=object), ("Time", "bottom_top"))})
    candidate = _dataset([T0], extra={"OBJECT": FakeVariable(np.asarray([[object()]], dtype=object), ("Time", "bottom_top"))})
    with pytest.raises(TypeError, match="unsupported dtype"):
        compare_frames(reference, candidate, 0, 0, T0)
