#!/usr/bin/env python3
"""Hash and report AMI NetCDF metadata without indexing pixel arrays."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import netCDF4


FD_TIME = "202507190000"
KO_TIMES = ("202507190000", "202507190002")
ALL_AMI = ("sw038", "wv063", "wv069", "wv073", "ir087", "ir096",
           "ir105", "ir112", "ir123", "ir133")
SELECTED_KO = ("wv073", "ir087", "ir096", "ir105", "ir112", "ir123", "ir133")
CAL_FIELDS = ("DN_to_Radiance_Gain", "DN_to_Radiance_Offset", "Teff_to_Tbb_c0",
              "Teff_to_Tbb_c1", "Teff_to_Tbb_c2", "Plank_constant_h",
              "light_speed", "Boltzmann_constant_k")
FD_META = ("satellite_name", "instrument_name", "data_processing_center",
           "data_processing_mode", "channel_center_wavelength",
           "scene_acquisition_time", "mission_reference_time", "file_generation_time",
           "file_name", "file_format_version", "calibration_table_version",
           "observation_start_time", "observation_end_time", "time_synchro_obt",
           "time_synchro_utc", "observation_mode")
KO_META = ("satellite_name", "instrument_name", "data_processing_center",
           "data_processing_mode", "channel_center_wavelength",
           "channel_spatial_resolution", "file_name", "origianl_sourece_file",
           "file_format_version")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def json_value(value):
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def header(path: Path, global_names: tuple[str, ...]) -> dict:
    with netCDF4.Dataset(path, "r") as ds:
        attrs = {name: json_value(ds.getncattr(name)) for name in global_names
                 if name in ds.ncattrs()}
        global_set = set(ds.ncattrs())
        spectral_names = [name for name in ds.ncattrs() if name not in attrs
                          and any(tag in name.lower() for tag in
                                  ("srf", "spectral_response", "wavenumber", "wavelength"))]
        attrs["spectral_metadata_attributes"] = {
            name: json_value(ds.getncattr(name)) for name in spectral_names
            if name not in attrs
        }
        var = ds.variables["image_pixel_values"]
        var_attrs = {name: json_value(var.getncattr(name)) for name in var.ncattrs()
                     if name in ("channel_name", "number_of_valid_bits_per_pixel",
                                 "number_of_total_bits_per_pixel",
                                 "number_of_data_quality_flag_bits_per_pixel")}
        return {"global_attributes": attrs,
                "metadata_presence": {
                    "calibration_table_version": "calibration_table_version" in global_set,
                    "scene_acquisition_time": "scene_acquisition_time" in global_set,
                    "mission_reference_time": "mission_reference_time" in global_set,
                    "observation_start_time": "observation_start_time" in global_set,
                    "observation_end_time": "observation_end_time" in global_set,
                    "explicit_bt_wavenumber": "bt_wavenumber_cm1" in global_set,
                    "srf_or_spectral_response_metadata": bool(spectral_names),
                },
                "image_pixel_values_header": {"shape": list(var.shape),
                                              "dtype": str(var.dtype),
                                              "attributes": var_attrs}}


def channel_files(root: Path, product: str, stamp: str, channels: tuple[str, ...]) -> dict[str, Path]:
    found = {}
    for channel in channels:
        path = root / f"gk2a_ami_le1b_{channel}_{product}_{stamp}.nc"
        if not path.is_file():
            raise FileNotFoundError(path)
        found[channel] = path
    return found


def validate_fd_identity(path: Path, channel: str, header_data: dict, manifest_item: dict,
                         expected_prefix: str) -> None:
    if manifest_item is None or manifest_item.get("key") != expected_prefix + path.name:
        raise ValueError("FD manifest key does not identify the expected object")
    if Path(manifest_item.get("path", "")).name != path.name:
        raise ValueError("FD manifest path does not identify the expected filename")
    label = header_data["image_pixel_values_header"]["attributes"].get("channel_name")
    if not isinstance(label, str) or label.lower() != channel:
        raise ValueError("FD variable channel_name differs from filename channel")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fd-root", type=Path, required=True)
    parser.add_argument("--ko-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, default=Path(__file__).resolve().parents[2]
                        / "oracle/kdm6/obs/data/gk2a_ami_cal_202507190000.json")
    args = parser.parse_args()

    calibration = json.loads(args.calibration.read_text())["channels"]
    manifest_path = args.fd_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    expected_prefix = "AMI/L1B/FD/202507/19/00/"
    if manifest.get("source") != "noaa-gk2a-pds" or manifest.get("prefix") != expected_prefix:
        raise ValueError("FD manifest is not the pinned NOAA-GK2A-PDS 2025-07-19 00Z prefix")
    manifest_files = {Path(item["path"]).name: item for item in manifest["files"]}
    if len(manifest_files) != len(manifest["files"]):
        raise ValueError("FD manifest contains duplicate filenames")

    records = {"fd_202507190000": {}, "ko_202507190000": {}, "ko_202507190002": {}}
    fd_paths = channel_files(args.fd_root, "fd020ge", FD_TIME, ALL_AMI)
    for channel, path in fd_paths.items():
        meta = header(path, FD_META + CAL_FIELDS)
        global_attrs = meta["global_attributes"]
        matches = {name: float(global_attrs[name]) == float(calibration[channel][name])
                   for name in CAL_FIELDS if name in global_attrs}
        record = {"path": str(path.resolve()), "size_bytes": path.stat().st_size,
                  "sha256": sha256(path), "header": meta,
                  "calibration_json_exact_matches": matches,
                  "all_calibration_fields_match": len(matches) == len(CAL_FIELDS)
                  and all(matches.values())}
        manifest_item = manifest_files.get(path.name)
        validate_fd_identity(path, channel, meta, manifest_item, expected_prefix)
        record["manifest_size_matches"] = (manifest_item is not None and
                                            int(manifest_item["size"]) == path.stat().st_size)
        record["manifest_key"] = manifest_item["key"] if manifest_item else None
        records["fd_202507190000"][channel] = record

    for stamp in KO_TIMES:
        key = f"ko_{stamp}"
        for channel, path in channel_files(args.ko_root, "ko020lc", stamp, SELECTED_KO).items():
            records[key][channel] = {"path": str(path.resolve()),
                                     "size_bytes": path.stat().st_size,
                                     "sha256": sha256(path),
                                     "header": header(path, KO_META)}

    result = {
        "scope": "Header metadata and raw-file hashes only; image_pixel_values was never indexed.",
        "time_interpretation": {
            "fd": "Report source strings and numeric time fields as stored. Do not infer SRF epoch from table version.",
            "ko": "KO filename timestamps and origianl_sourece_file identify remapped ELA products; they do not establish source FD lineage or transfer the FD full-disk observation interval.",
        },
        "roots": {"fd": str(args.fd_root.resolve()), "ko": str(args.ko_root.resolve())},
        "manifest": {"path": str(manifest_path.resolve()), "sha256": sha256(manifest_path),
                     "source": manifest["source"], "prefix": manifest["prefix"],
                     "expected_ami_files_present": all(c in records["fd_202507190000"] for c in ALL_AMI),
                     "sizes_match": all(r["manifest_size_matches"] for r in records["fd_202507190000"].values())},
        "fd_ami_spectral_files": records["fd_202507190000"],
        "ko_selected_channel_headers": {k: v for k, v in records.items() if k.startswith("ko_")},
        "summary": {
            "fd_channel_count": len(records["fd_202507190000"]),
            "fd_all_report_v3_0_and_match_calibration_json": all(
                r["header"]["global_attributes"].get("calibration_table_version") == "v.3.0_20190415"
                and r["all_calibration_fields_match"] for r in records["fd_202507190000"].values()),
            "fd_any_explicit_srf_metadata": any(
                bool(r["header"]["global_attributes"]["spectral_metadata_attributes"])
                for r in records["fd_202507190000"].values()),
            "ko_original_ela_filename_present": all(
                bool(r["header"]["global_attributes"].get("origianl_sourece_file"))
                for group in (records["ko_202507190000"], records["ko_202507190002"])
                for r in group.values()),
            "ko_fd_source_lineage_established": False,
            "ko_calibration_version_attribute_present": any(
                r["header"]["metadata_presence"]["calibration_table_version"]
                for group in (records["ko_202507190000"], records["ko_202507190002"])
                for r in group.values()),
            "ko_explicit_acquisition_time_attribute_present": any(
                r["header"]["metadata_presence"]["scene_acquisition_time"]
                or r["header"]["metadata_presence"]["observation_start_time"]
                or r["header"]["metadata_presence"]["observation_end_time"]
                for group in (records["ko_202507190000"], records["ko_202507190002"])
                for r in group.values()),
        },
    }
    result["provenance"] = {"script_path": str(Path(__file__).resolve()),
                            "script_sha256": sha256(Path(__file__).resolve()),
                            "cli_argv": sys.argv,
                            "calibration_path": str(args.calibration.resolve()),
                            "calibration_sha256": sha256(args.calibration)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(args.output), "sha256": sha256(args.output),
                      "summary": result["summary"]}, sort_keys=True))


if __name__ == "__main__":
    main()
