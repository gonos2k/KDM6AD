"""Join public QNC-only direct captures to this witness without model calls."""

import hashlib
import io
import json
import sys
import tarfile
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
EXPECTED = "568b09524f6ab5ca9eaade51cd77c45ebcbe2b17afe5bd0827ff0590717845c5"


def check_source_manifest():
    """Validate the fixed source inventory before reading numeric evidence."""
    manifest = json.loads((HERE / "source_manifest.json").read_bytes())
    names = {
        "analyze.py",
        "crosscheck_pilot.py",
        "crosscheck_qnc.py",
        "extract.py",
        "replay.py",
        "test_witness.py",
    }
    if manifest.get("schema") != "east-optical-source-manifest-v1":
        raise ValueError("source manifest schema differs")
    hashes = manifest.get("sha256")
    if not isinstance(hashes, dict) or set(hashes) != names:
        raise ValueError("source manifest inventory differs")
    for name in sorted(names):
        if hashlib.sha256((HERE / name).read_bytes()).hexdigest() != hashes[name]:
            raise ValueError(f"packet source SHA differs: {name}")


def check(path):
    check_source_manifest()
    raw = Path(path).read_bytes()
    if not hashlib.sha256(raw).hexdigest() == EXPECTED:
        raise ValueError("guard archive SHA differs")
    witness = json.loads((HERE / "witness.json").read_bytes())
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as t:
        binding = t.extractfile("binding.json").read()
        if not hashlib.sha256(binding).hexdigest() == witness["qnc_binding_sha256"]:
            raise ValueError("guard binding SHA differs")
        for p in witness["profiles"]:
            prefix = f"chunks/chunk_{p['chunk']:03d}"
            receipt_raw = t.extractfile(prefix + "/result.json").read()
            if (
                hashlib.sha256(receipt_raw).hexdigest()
                != witness["chunk_receipts"][str(p["chunk"])][
                    "qnc_result_receipt_sha256"
                ]
            ):
                raise ValueError("QNC result receipt hash differs")
            receipt = json.loads(receipt_raw)
            indices = receipt["rttov_receipt"]["source_flat_indices"]
            if (
                indices.count(p["flat"]) != 1
                or f"{indices.index(p['flat']) + 1:03d}" != p["case_profiles_1based"][1]
            ):
                raise ValueError("QNC case profile ordinal differs")
            capture = t.extractfile(prefix + "/result.npz").read()
            if not hashlib.sha256(capture).hexdigest() == receipt["capture_sha256"]:
                raise ValueError("guard capture SHA differs")
            if not (
                receipt["binding_sha256"] == witness["qnc_binding_sha256"]
                and receipt["direct_calls"] == 1
                and (receipt["K_calls"] == 0)
            ):
                raise ValueError("guard direct call metadata differs")
            with np.load(io.BytesIO(capture), allow_pickle=False) as z:
                row = p["flat"] % 512
                if not (
                    z["flat_indices"][row] == p["flat"]
                    and z["valid"][row].all()
                    and (z["quality"][row] == 0).all()
                ):
                    raise ValueError("guard flat row, validity or quality differs")
                if not z["bt"][row].tolist() == p["bt"][1]:
                    raise ValueError("guard BT differs from witness")
    return {
        "profiles": 10,
        "channels": 7,
        "model_calls": 0,
        "qnc_archive_sha256": EXPECTED,
    }


if __name__ == "__main__":
    print(json.dumps(check(sys.argv[1]), sort_keys=True))
