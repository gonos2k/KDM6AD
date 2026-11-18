"""Join pilot block captures and selected profile ordinals to this witness."""

import hashlib
import io
import json
import tarfile
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "native_qi_postmicro_direct_m0_2026-10-30/data"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def check(witness):
    archive = (DATA / "chunk_artifacts.tar.gz").read_bytes()
    if (
        digest(archive)
        != "736779e7084bccc0a4348eb62cbd0eacf753173a48146a37657e92e65f88df77"
    ):
        raise ValueError("pilot archive hash differs")
    if (
        digest((DATA / "control.npz").read_bytes())
        != "055e0222eda193bb8942f3890684d5f2389ec578eb0450330e05adce38ad074e"
    ):
        raise ValueError("pilot packed control hash differs")
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as t:
        if (
            digest(t.extractfile("control/binding.json").read())
            != witness["pilot_binding_sha256"]
        ):
            raise ValueError("pilot binding differs")
        for p in witness["profiles"]:
            prefix = f"control/chunks/chunk_{p['chunk']:03d}"
            raw = t.extractfile(prefix + "/result.json").read()
            r = json.loads(raw)
            if (
                digest(raw)
                != witness["chunk_receipts"][str(p["chunk"])][
                    "pilot_result_receipt_sha256"
                ]
            ):
                raise ValueError("pilot receipt differs")
            idx = r["rttov_receipt"]["source_flat_indices"]
            if (
                idx.count(p["flat"]) != 1
                or f"{idx.index(p['flat']) + 1:03d}" != p["case_profiles_1based"][2]
            ):
                raise ValueError("pilot case profile ordinal differs")
            raw = t.extractfile(prefix + "/result.npz").read()
            if (
                digest(raw) != r["capture_sha256"]
                or r["binding_sha256"] != witness["pilot_binding_sha256"]
                or r["direct_calls"] != 1
                or r["K_calls"] != 0
            ):
                raise ValueError("pilot capture or metadata differs")
            with np.load(io.BytesIO(raw), allow_pickle=False) as z:
                row = p["flat"] % 512
                if (
                    int(z["flat_indices"][row]) != p["flat"]
                    or not z["valid"][row].all()
                    or not (z["quality"][row] == 0).all()
                    or z["bt"][row].tolist() != p["bt"][2]
                ):
                    raise ValueError("pilot captured row differs")
    return {"profiles": 10, "model_calls": 0}


if __name__ == "__main__":
    print(
        json.dumps(
            check(json.loads((HERE / "witness.json").read_bytes())), sort_keys=True
        )
    )
