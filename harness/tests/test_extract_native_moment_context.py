import numpy as np
import pytest

from harness.extract_native_moment_context import TARGETS, extract_context, sha256_file


@pytest.mark.parametrize("existing", ["output", "receipt", "dangling_link"])
def test_context_refuses_outputs_before_reading_checkpoints(tmp_path, existing):
    output, receipt = tmp_path / "context.npz", tmp_path / "receipt.json"
    target = receipt if existing == "receipt" else output
    if existing == "dangling_link":
        target.symlink_to(tmp_path / "absent")
    else:
        target.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        extract_context(tmp_path / "missing-ready", tmp_path / "missing-final",
                        output, receipt, ready_sha256="0" * 64, final_sha256="1" * 64)
    if existing == "dangling_link":
        assert target.is_symlink()
    else:
        assert target.read_bytes() == b"keep"
    other = output if target == receipt else receipt
    assert not other.exists()


def test_context_preserves_selected_float32_bits(tmp_path):
    netcdf = pytest.importorskip("netCDF4")
    expected = {}
    for label in ("ready", "final"):
        path = tmp_path / f"{label}.nc"
        with netcdf.Dataset(path, "w") as data:
            for name, count in (("Time", 1), ("bottom_top", 39), ("south_north", 282), ("west_east", 234)):
                data.createDimension(name, count)
            for field, native in (("qc", "QCLOUD"), ("nc", "QNCLOUD")):
                variable = data.createVariable(native, "f4", tuple(data.dimensions), zlib=True)
                variable[:] = 0.0
                profiles = []
                for index, (i, j) in enumerate(TARGETS):
                    profile = np.arange(39, dtype=np.float32) + index
                    profile[0] = np.float32(-0.0)
                    profile[1] = np.nextafter(np.float32(0), np.float32(1))
                    if label == "final":
                        profile[2:] += np.float32(0.5)
                    variable[0, :, j - 1, i - 1] = profile
                    profiles.append(profile)
                expected[f"{label}_{field}"] = np.stack(profiles)
    output, receipt = tmp_path / "context.npz", tmp_path / "receipt.json"
    result = extract_context(tmp_path / "ready.nc", tmp_path / "final.nc", output, receipt,
                             ready_sha256=sha256_file(tmp_path / "ready.nc"),
                             final_sha256=sha256_file(tmp_path / "final.nc"))
    assert result["context"]["sha256"] == sha256_file(output)
    with np.load(output, allow_pickle=False) as arrays:
        assert arrays.files == ["ready_qc", "ready_nc", "final_qc", "final_nc"]
        for key, values in expected.items():
            assert arrays[key].dtype == np.float32
            assert arrays[key].tobytes() == values.tobytes()
