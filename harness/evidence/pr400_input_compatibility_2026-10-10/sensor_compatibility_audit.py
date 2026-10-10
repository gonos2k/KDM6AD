#!/usr/bin/env python3
"""Audit GK-2A AMI LA header calibration metadata against KMA and RTTOV references.

Only NetCDF dimensions and attributes are read. ``image_pixel_values`` data are
never indexed. No observation values, model data, or forward simulations are
produced.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET

import netCDF4


CHANNELS = {
    "sw038": {"sensor_channel": 7, "physical_name": "IR3.8"},
    "wv063": {"sensor_channel": 8, "physical_name": "WV063"},
    "wv069": {"sensor_channel": 9, "physical_name": "WV069"},
    "wv073": {"sensor_channel": 10, "physical_name": "WV073"},
    "ir087": {"sensor_channel": 11, "physical_name": "IR087"},
    "ir096": {"sensor_channel": 12, "physical_name": "IR096"},
    "ir105": {"sensor_channel": 13, "physical_name": "IR105"},
    "ir112": {"sensor_channel": 14, "physical_name": "IR112"},
    "ir123": {"sensor_channel": 15, "physical_name": "IR123"},
    "ir133": {"sensor_channel": 16, "physical_name": "IR133"},
}
SELECTED = ("wv073", "ir087", "ir096", "ir105", "ir112", "ir123", "ir133")
LA_CHANNELS = ("wv063", "wv069", *SELECTED)
CAL_FIELDS = (
    "DN_to_Radiance_Gain",
    "DN_to_Radiance_Offset",
    "Teff_to_Tbb_c0",
    "Teff_to_Tbb_c1",
    "Teff_to_Tbb_c2",
    "Plank_constant_h",
    "light_speed",
    "Boltzmann_constant_k",
)
GLOBAL_FIELDS = (
    "satellite_name",
    "instrument_name",
    "data_processing_center",
    "data_processing_mode",
    "file_name",
    "file_format_version",
    "calibration_table_version",
    "channel_center_wavelength",
    "channel_spatial_resolution",
    "scene_acquisition_time",
    "mission_reference_time",
    "file_generation_time",
    "projection_type",
)
NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "p": "http://schemas.openxmlformats.org/package/2006/relationships",
}
TABLE_CHANNELS = {
    "ir3.8": "sw038",
    "ir6.3": "wv063",
    "ir6.9": "wv069",
    "ir7.3": "wv073",
    "ir8.7": "ir087",
    "ir9.6": "ir096",
    "ir10.5": "ir105",
    "ir11.2": "ir112",
    "ir12.3": "ir123",
    "ir13.3": "ir133",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def scalar(value):
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def workbook_table(path: Path) -> dict[str, dict]:
    """Read the published KMA coefficient/wavenumber table cells without Excel."""
    with zipfile.ZipFile(path) as zf:
        wb = ET.fromstring(zf.read("xl/workbook.xml"))
        rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        rel_map = {el.attrib["Id"]: el.attrib["Target"] for el in rels}
        sheet = next(
            el
            for el in wb.find("m:sheets", NS)
            if el.attrib["name"] == "coeff.& equation_WN"
        )
        target = rel_map[sheet.attrib[f"{{{NS['r']}}}id"]]
        worksheet_path = str(PurePosixPath("xl") / target)
        strings = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            strings = [
                "".join(t.text or "" for t in si.findall(".//m:t", NS)) for si in root
            ]
        root = ET.fromstring(zf.read(worksheet_path))
        cells = {}
        for cell in root.findall(".//m:c", NS):
            value = cell.find("m:v", NS)
            if value is None:
                continue
            raw = value.text or ""
            if cell.attrib.get("t") == "s":
                raw = strings[int(raw)]
            cells[cell.attrib["r"]] = raw

    result = {}
    for row in range(13, 23):
        label = cells[f"B{row}"].strip().lower()
        channel = TABLE_CHANNELS.get(label)
        if channel is None:
            raise ValueError(f"unrecognized KMA table channel label {label!r}")
        result[channel] = {
            "table_label": cells[f"B{row}"],
            "center_wavenumber_cm1": float(cells[f"C{row}"]),
            "DN_to_Radiance_Gain": float(cells[f"D{row}"]),
            "DN_to_Radiance_Offset": float(cells[f"F{row}"]),
            "Teff_to_Tbb_c0": float(cells[f"I{row}"]),
            "Teff_to_Tbb_c1": float(cells[f"J{row}"]),
            "Teff_to_Tbb_c2": float(cells[f"K{row}"]),
        }
    constants = {
        "light_speed": float(cells["S18"]),
        "Plank_constant_h": float(cells["S19"]),
        "Boltzmann_constant_k": float(cells["S20"]),
    }
    for record in result.values():
        record.update(constants)
    if len(result) != 10:
        raise ValueError(f"expected 10 calibration rows, got {len(result)}")
    return result


def read_la_metadata(path: Path) -> dict:
    with netCDF4.Dataset(path, "r") as ds:
        global_names = set(ds.ncattrs())
        attrs = {
            name: scalar(ds.getncattr(name))
            for name in GLOBAL_FIELDS
            if name in global_names
        }
        attrs.update(
            {
                name: scalar(ds.getncattr(name))
                for name in CAL_FIELDS
                if name in global_names
            }
        )
        var = ds.variables["image_pixel_values"]
        return {
            "global_attributes": attrs,
            "global_srf_wavenumber_metadata_present": any(
                token in name.lower()
                for name in global_names
                for token in ("srf", "spectral_response", "wavenumber")
            ),
            "image_pixel_values_header": {
                "shape": list(var.shape),
                "dtype": str(var.dtype),
                "channel_name": scalar(var.getncattr("channel_name"))
                if "channel_name" in var.ncattrs()
                else None,
            },
        }


def parse_srf_member(data: bytes) -> list[tuple[float, float, float]]:
    rows = []
    for line in data.decode("utf-8", errors="replace").splitlines():
        try:
            cols = line.split()
            if len(cols) >= 3:
                wavelength, wn, response = map(float, cols[:3])
                rows.append((wavelength, wn, response))
        except ValueError:
            continue
    return rows


def parse_nwpsaf_srf(path: Path) -> dict[float, float]:
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            cols = line.split()
            if len(cols) >= 2:
                result[round(float(cols[0]), 8)] = float(cols[1])
        except ValueError:
            continue
    return result


def coefficient_info(
    executable: Path, coef: Path
) -> tuple[str, dict[int, dict], dict[str, float]]:
    run = subprocess.run(
        [str(executable), "--coef", str(coef), "--format", "FORMATTED", "--verbose"],
        check=True,
        capture_output=True,
        text=True,
    )
    # RTTOV's Fortran utility writes its report to stderr even on success.
    output = run.stdout + run.stderr
    channel_rows = {}
    pattern = re.compile(r"^\s*(\d+)\s+([0-9.]+)\s+cm-1\s+(.*)$")
    for line in output.splitlines():
        match = pattern.match(line)
        if match:
            channel_rows[int(match.group(1))] = {
                "utility_printed_center_wavenumber_cm1": float(match.group(2)),
                "flags": match.group(3).strip(),
            }
    readme_centers = {}
    for line in output.splitlines():
        match = re.match(r"^\s*(IR\d+\.\d+)\s+([0-9.]+)\s*$", line)
        if match:
            channel = TABLE_CHANNELS.get(match.group(1).lower())
            if channel:
                readme_centers[channel] = float(match.group(2))
    if len(channel_rows) != 16:
        raise ValueError(f"expected 16 RTTOV channel rows, got {len(channel_rows)}")
    if len(readme_centers) != 10:
        raise ValueError(
            f"expected 10 precise RTTOV README centers, got {len(readme_centers)}"
        )
    for key, info in channel_rows.items():
        channel = next(
            (name for name, meta in CHANNELS.items() if meta["sensor_channel"] == key),
            None,
        )
        if channel in readme_centers:
            info["center_wavenumber_cm1"] = readme_centers[channel]
        else:
            info["center_wavenumber_cm1"] = info[
                "utility_printed_center_wavenumber_cm1"
            ]
    return output, channel_rows, readme_centers


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--la-root",
        type=Path,
        default=Path(
            "/Users/yhlee/KDM6AD-k/host/research_evidence/pr400_sensor_compat_20261010/raw_la_202507190556"
        ),
    )
    parser.add_argument(
        "--receipt",
        type=Path,
        default=Path(
            "/Users/yhlee/KDM6AD-k/host/research_evidence/pr400_sensor_compat_20261010/raw_la_202507190556/slot_receipt.json"
        ),
    )
    parser.add_argument("--v30", type=Path, required=True)
    parser.add_argument("--v31", type=Path, required=True)
    parser.add_argument("--nmsc-srf-zip", type=Path, required=True)
    parser.add_argument("--nwpsaf-srf-ch16", type=Path, required=True)
    parser.add_argument("--rttov-coef", type=Path, required=True)
    parser.add_argument("--coef-info", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    receipt = json.loads(args.receipt.read_text())
    receipt_by_channel = {
        Path(record["local_file"]).name.split("_")[3]: record
        for record in receipt["file_records"]
    }
    if set(receipt_by_channel) != set(LA_CHANNELS):
        raise ValueError(
            "source receipt does not contain exactly the nine expected channels"
        )

    v30 = workbook_table(args.v30)
    v31 = workbook_table(args.v31)
    la_rows = {}
    for channel in LA_CHANNELS:
        path = args.la_root / f"gk2a_ami_le1b_{channel}_la020ge_202507190556.nc"
        meta = read_la_metadata(path)
        digest = sha256(path)
        receipt_record = receipt_by_channel[channel]
        ga = meta["global_attributes"]
        cal_actual = {field: float(ga[field]) for field in CAL_FIELDS if field in ga}
        if len(cal_actual) != len(CAL_FIELDS):
            raise ValueError(f"missing calibration metadata in {path.name}")
        exact_matches = {}
        for version, table in (("v3.0", v30), ("v3.1", v31)):
            exact_matches[version] = {
                field: (cal_actual[field] == table[channel][field])
                for field in CAL_FIELDS
                if field in table[channel]
            }
        la_rows[channel] = {
            "source_file": path.name,
            "size_bytes": path.stat().st_size,
            "sha256": digest,
            "matches_existing_slot_receipt_sha256": digest == receipt_record["sha256"],
            "matches_existing_slot_receipt_size": path.stat().st_size
            == receipt_record["bytes"],
            "metadata": meta,
            "calibration_exact_field_matches": exact_matches,
            "all_calibration_fields_match_v3_0": all(exact_matches["v3.0"].values())
            and len(exact_matches["v3.0"]) == len(CAL_FIELDS),
            "all_calibration_fields_match_v3_1": all(exact_matches["v3.1"].values())
            and len(exact_matches["v3.1"]) == len(CAL_FIELDS),
            "channel_identity_matches_filename_and_receipt": meta[
                "image_pixel_values_header"
            ]["channel_name"].lower()
            == channel
            and ga.get("calibration_table_version") == "v.3.0_20190415",
        }

    coef_text, rttov_channels, rttov_readme_centers = coefficient_info(
        args.coef_info, args.rttov_coef
    )
    coef_text_path = args.output.with_name("RTTOV_COEF_INFO.txt")
    coef_text_path.write_text(coef_text)
    with zipfile.ZipFile(args.nmsc_srf_zip) as zf:
        ir133_name = next(
            name
            for name in zf.namelist()
            if "IR133" in name.upper() and "SHIFT" in name.upper()
        )
        ir133_bytes = zf.read(ir133_name)
    nmsc_ir133 = parse_srf_member(ir133_bytes)
    nwpsaf_ir133 = parse_nwpsaf_srf(args.nwpsaf_srf_ch16)
    paired = [
        (round(wn, 8), response, nwpsaf_ir133[round(wn, 8)])
        for _, wn, response in nmsc_ir133
        if round(wn, 8) in nwpsaf_ir133
    ]
    if len(nmsc_ir133) != 581 or len(paired) != 581:
        raise ValueError(f"expected 581 matched IR133 SRF points, found {len(paired)}")
    srf_max_abs_difference = max(abs(local - remote) for _, local, remote in paired)

    nmsc_srf_catalog = {}
    with zipfile.ZipFile(args.nmsc_srf_zip) as zf:
        for channel in SELECTED:
            if channel == "ir133":
                member = ir133_name
            else:
                member = f"GK2A_ami_srf_{CHANNELS[channel]['physical_name']}.txt"
            data = zf.read(member)
            curve = parse_srf_member(data)
            positive = [
                (wl, wn, response) for wl, wn, response in curve if response > 0.0
            ]
            nmsc_srf_catalog[channel] = {
                "member": member,
                "sha256": hashlib.sha256(data).hexdigest(),
                "point_count": len(curve),
                "positive_response_wavelength_um_min_max": [
                    min(row[0] for row in positive),
                    max(row[0] for row in positive),
                ],
                "positive_response_wavenumber_cm1_min_max": [
                    min(row[1] for row in positive),
                    max(row[1] for row in positive),
                ],
            }

    versions = {}
    for channel in SELECTED:
        table0 = v30[channel]
        table1 = v31[channel]
        rttov_ch = CHANNELS[channel]["sensor_channel"]
        coeff_row = rttov_channels[rttov_ch]
        versions[channel] = {
            "physical_sensor_channel": rttov_ch,
            "physical_name": CHANNELS[channel]["physical_name"],
            "la_declared_calibration_table_version": la_rows[channel]["metadata"][
                "global_attributes"
            ].get("calibration_table_version"),
            "la_channel_center_wavelength_um": la_rows[channel]["metadata"][
                "global_attributes"
            ].get("channel_center_wavelength"),
            "v3_0_table_center_wavenumber_cm1": table0["center_wavenumber_cm1"],
            "v3_1_table_center_wavenumber_cm1": table1["center_wavenumber_cm1"],
            "rttov_coefficient_center_wavenumber_cm1": coeff_row[
                "center_wavenumber_cm1"
            ],
            "rttov_utility_rounded_center_wavenumber_cm1": coeff_row[
                "utility_printed_center_wavenumber_cm1"
            ],
            "rttov_channel_flags": coeff_row["flags"],
            "nmsc_official_srf_curve": nmsc_srf_catalog[channel],
            "rttov_matches_v3_0_center_wavenumber": coeff_row["center_wavenumber_cm1"]
            == table0["center_wavenumber_cm1"],
            "rttov_matches_v3_1_center_wavenumber": coeff_row["center_wavenumber_cm1"]
            == table1["center_wavenumber_cm1"],
            "la_calibration_values_match_v3_0": la_rows[channel][
                "all_calibration_fields_match_v3_0"
            ],
            "la_calibration_values_match_v3_1": la_rows[channel][
                "all_calibration_fields_match_v3_1"
            ],
        }
    v30_v31_changed = {
        channel: [
            field
            for field in ("center_wavenumber_cm1", *CAL_FIELDS)
            if v30[channel].get(field) != v31[channel].get(field)
        ]
        for channel in CHANNELS
    }

    calibration_assets = []
    for label, path in (
        ("NMSC v3.0 workbook", args.v30),
        ("NMSC v3.1 workbook", args.v31),
        ("NMSC 16-band SRF ZIP", args.nmsc_srf_zip),
        ("NWP SAF published channel-16 SRF", args.nwpsaf_srf_ch16),
        ("installed RTTOV coefficient", args.rttov_coef),
        ("rttov_coef_info utility", args.coef_info),
    ):
        calibration_assets.append(
            {
                "label": label,
                "path": str(path),
                "size_bytes": path.stat().st_size,
                "sha256": sha256(path),
                "mode_octal": oct(path.stat().st_mode & 0o777),
            }
        )

    result = {
        "schema": "pr400_gk2a_ami_la_sensor_compatibility_v1",
        "scope": {
            "actual_inputs": "Nine existing 2025-07-19 05:56 LA020GE AMI NetCDF files, 500x500 each; metadata/header only.",
            "pixels_read": False,
            "dn_bt_arithmetic_recomputed": False,
            "native_or_external_model_data": False,
            "rttov_forward_or_h_call": False,
            "coefficient_or_default_modified": False,
            "rttov_coef_info_is_forward_model": False,
            "rttov_coef_info_note": "This is the RTTOV metadata utility; it inspects coefficient headers and does not run RTTOV forward/H.",
        },
        "provenance": {
            "la_input_root": str(args.la_root),
            "la_slot_receipt_path": str(args.receipt),
            "la_slot_receipt_sha256": sha256(args.receipt),
            "la_slot_receipt_source_prefix": receipt["source_prefix"],
            "la_slot_receipt_listing_sha256": receipt["source_listing_sha256"],
            "audit_source_path": str(Path(__file__).resolve()),
            "audit_source_sha256": sha256(Path(__file__).resolve()),
            "official_reference_assets": calibration_assets,
            "rttov_coef_info_output_path": str(coef_text_path),
            "rttov_coef_info_output_sha256": sha256(coef_text_path),
        },
        "actual_la_files": la_rows,
        "selected_physical_channels_10_to_16": versions,
        "kma_table_differences_v3_0_to_v3_1": v30_v31_changed,
        "ir133_srf_curve_comparison": {
            "nmsc_entry_name": ir133_name,
            "nmsc_entry_sha256": hashlib.sha256(ir133_bytes).hexdigest(),
            "nmsc_point_count": len(nmsc_ir133),
            "nwp_saf_file_sha256": sha256(args.nwpsaf_srf_ch16),
            "nwp_saf_point_count": len(nwpsaf_ir133),
            "matched_wavenumber_points": len(paired),
            "max_abs_response_difference": srf_max_abs_difference,
            "comparison_precision_note": "NWP SAF text prints the response to six decimal places; NMSC ZIP stores more digits.",
            "interpretation": "The two official published shifted channel-16 curves agree on all 581 common 0.1 cm-1 samples to NWP SAF's printed precision. The installed coefficient header separately names the same shifted KMA input and center wavenumber; the coefficient file does not carry a hash of an input SRF payload.",
        },
        "rttov_coefficient_metadata": {
            "path": str(args.rttov_coef),
            "sha256": sha256(args.rttov_coef),
            "utility_sha256": sha256(args.coef_info),
            "channel_rows_10_to_16": {
                str(ch): rttov_channels[ch] for ch in range(10, 17)
            },
            "precise_center_wavenumbers_from_embedded_readme": rttov_readme_centers,
            "full_verbose_output_path": str(coef_text_path),
            "number_of_channels": len(rttov_channels),
        },
        "compatibility_conclusion": {
            "actual_la_product_declared_calibration": "v.3.0_20190415 on all nine inspected LA files; all eight stored calibration fields match the v3.0 workbook exactly.",
            "rttov_reference": "Installed RTTOV 14.1 coefficient file was created 2021-05-03; its README identifies KMA's 2021 updated AMI SRFs, the v3.1 shifted IR133 center, and channel-16 New_AMI_SRF_IR133_-0.80wn.txt. The IR133 Teff-to-BT polynomial comparison comes from the two NMSC workbooks, not from RTTOV metadata.",
            "channel_scope": "Of channels 10-16, the NMSC calibration rows and RTTOV center wavenumbers align for channels 10-15. Channel 16 IR133 is the sole v3.0/v3.1 row change and sole center-wavenumber mismatch: LA metadata/calibration tuple is v3.0, while RTTOV uses the v3.1 shifted center and its shifted KMA SRF metadata. The three Teff-to-BT coefficient differences are from the official NMSC workbook comparison.",
            "status": "IR133_COMPATIBILITY_MISMATCH_IN_DECLARED_CALIBRATION_TUPLE; UPSTREAM_LA_SRF_PAYLOAD_UNVERIFIED",
            "limits": [
                "The LA files identify the declared calibration table and expose its conversion coefficients, but no explicit SRF identifier or wavenumber attribute was present.",
                "The product header does not establish which SRF response curve the upstream production processor used outside the stated calibration tuple.",
                "No actual pixel values or conversion were examined, so this audit makes no numeric BT residual or error estimate.",
                "The changed compatibility evidence is isolated to IR133; it does not imply all channels or the full observed/model discrepancy are caused by this mismatch.",
            ],
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "sha256": sha256(args.output),
                "status": result["compatibility_conclusion"]["status"],
                "la_file_count": len(la_rows),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
