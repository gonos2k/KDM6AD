"""Fail-closed identity checks for the retained AMI FD metadata receipt."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


_ROOT = Path(__file__).resolve().parents[2]
_SOURCE = _ROOT / "harness/evidence/AMI_epoch_metadata_source_2026-10-04.py"
_RECEIPT = _ROOT / "harness/evidence/AMI_epoch_metadata_result_2026-10-04.json"
_SPEC = importlib.util.spec_from_file_location("ami_epoch_metadata_source", _SOURCE)
assert _SPEC is not None and _SPEC.loader is not None
_EPOCH = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_EPOCH)

_PREFIX = "AMI/L1B/FD/202507/19/00/"


def _actual_ir105_identity():
    receipt = json.loads(_RECEIPT.read_text())
    item = receipt["fd_ami_spectral_files"]["ir105"]
    path = Path(item["path"])
    manifest_item = {"key": item["manifest_key"], "path": item["manifest_key"]}
    return path, item["header"], manifest_item


def test_retained_ir105_header_and_manifest_identity_pass():
    path, header, item = _actual_ir105_identity()
    _EPOCH.validate_fd_identity(path, "ir105", header, item, _PREFIX)


@pytest.mark.parametrize("field,bad_value,message", [
    ("key", "OTHER/PREFIX/file.nc", "manifest key"),
    ("path", "other_channel.nc", "manifest path"),
])
def test_manifest_must_identify_the_expected_fd_object(field, bad_value, message):
    path, header, item = _actual_ir105_identity()
    item[field] = bad_value
    with pytest.raises(ValueError, match=message):
        _EPOCH.validate_fd_identity(path, "ir105", header, item, _PREFIX)


def test_missing_manifest_item_is_rejected():
    path, header, _ = _actual_ir105_identity()
    with pytest.raises(ValueError, match="manifest key"):
        _EPOCH.validate_fd_identity(path, "ir105", header, None, _PREFIX)


def test_header_channel_label_must_match_filename_channel():
    path, header, item = _actual_ir105_identity()
    header = json.loads(json.dumps(header))
    header["image_pixel_values_header"]["attributes"]["channel_name"] = "IR112"
    with pytest.raises(ValueError, match="channel_name"):
        _EPOCH.validate_fd_identity(path, "ir105", header, item, _PREFIX)
