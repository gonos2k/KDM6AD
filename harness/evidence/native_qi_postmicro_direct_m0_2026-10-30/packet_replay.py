#!/usr/bin/env python3
"""Verify the public direct-M0 artifact chain and replay its arithmetic offline."""

import hashlib
import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
N, Z = 65988, 377342
ARTIFACTS = {
    "README.md",
    "SOURCE_RESOLUTION.md",
    "analysis.json",
    "replay.py",
    "observation_diagnostics.py",
    "observation_diagnostics.json",
    "packet_replay.py",
    "data/control.npz",
    "data/alpha025.npz",
    "data/producer_receipts.json",
    "data/chunk_artifacts.tar.gz",
    "executed_sources/run_full_m0_direct.py.txt",
    "executed_sources/pack_full_m0_direct.py.txt",
    "executed_sources/export_chunk_artifacts.py.txt",
}
PARENT = (
    HERE.parent / "native_qi_postmicro_boundary_2026-10-30" / "execution_summary.json"
)


def check(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load_checked(path, expected):
    raw = path.read_bytes()
    check(sha(raw) == expected, f"hash mismatch: {path.name}")
    return raw


def main():
    manifest = json.loads((HERE / "manifest.json").read_text())
    check(
        manifest["schema"] == "kdm6.qi_postmicro_direct_m0_packet.v1", "manifest schema"
    )
    check(
        set(manifest["artifacts"]) == ARTIFACTS
        and manifest.get("offline_model_calls")
        == {"host": 0, "KDM6": 0, "RTTOV": 0, "optimizer": 0}
        and manifest.get("source_tree_sha256")
        == "1ef3cc94d90465cea370c0974445f1d54b8de3192d33d2f5438464de41c0609f"
        and manifest.get("parent_execution_summary_sha256") == sha(PARENT.read_bytes()),
        "manifest inventory or summary mismatch",
    )
    raw = {
        name: load_checked(HERE / name, h) for name, h in manifest["artifacts"].items()
    }
    producer = json.loads(raw["data/producer_receipts.json"])
    analysis = json.loads(raw["analysis.json"])
    check(
        producer["schema"] == "kdm6.qi_postmicro_direct_m0_producer_receipts.v1",
        "producer schema",
    )
    check(
        producer["packer_sha256"]
        == sha(raw["executed_sources/pack_full_m0_direct.py.txt"])
        and producer["replay_source_sha256"] == sha(raw["replay.py"])
        and manifest["exporter_source_sha256"]
        == sha(raw["executed_sources/export_chunk_artifacts.py.txt"])
        and manifest["analysis_sha256"] == sha(raw["analysis.json"]),
        "source snapshot or analysis pin mismatch",
    )
    parent = json.loads(PARENT.read_text())
    check(
        parent["schema"] == "kdm6.native_qi_postmicro_execution_summary.v1",
        "host parent schema mismatch",
    )
    expected = set()
    reference_binding = None
    for case in ("control", "alpha025"):
        expected.update(f"{case}/{name}" for name in ("binding.json", "summary.json"))
        expected.update(
            f"{case}/chunks/chunk_{i:03d}/{name}"
            for i in range(129)
            for name in ("attempt.json", "result.json", "result.npz")
        )
    archive = {}
    with tarfile.open(
        fileobj=io.BytesIO(raw["data/chunk_artifacts.tar.gz"]), mode="r:gz"
    ) as tar:
        members = tar.getmembers()
        check(
            len(members) == 778
            and len({m.name for m in members}) == 778
            and {m.name for m in members} == expected,
            "archive inventory mismatch",
        )
        check(
            all(m.isfile() and 0 <= m.size <= 2_000_000 for m in members)
            and sum(m.size for m in members) <= 100_000_000,
            "archive bounds/type mismatch",
        )
        for member in members:
            archive[member.name] = tar.extractfile(member).read()
    for case in ("control", "alpha025"):
        meta = producer["cases"][case]
        bh = meta["binding_sha256"]

        def get(name, h):
            b = archive[f"{case}/{name}"]
            check(sha(b) == h, f"{case}/{name}: hash mismatch")
            return b

        binding = json.loads(get("binding.json", bh))
        summary = json.loads(get("summary.json", meta["summary_sha256"]))
        check(
            binding["schema"] == "kdm6.qi_postmicro_full_m0_direct.v1"
            and binding["case"] == case
            and binding["checkpoint_sha256"] == meta["checkpoint_sha256"]
            and binding["source_tree_sha256"]
            == meta["source_tree_sha256"]
            == manifest["source_tree_sha256"]
            and binding["source_tree_files"] == meta["source_tree_files"] == 517
            and binding["runner_sha256"] == meta["runner_sha256"]
            and binding["runner_sha256"]
            == sha(raw["executed_sources/run_full_m0_direct.py.txt"])
            and sorted(binding["source_pins"].values()) == meta["source_pin_hashes"]
            and binding["chunks"] == 129
            and binding["support_cells"] == Z
            and binding["with_k"] is False
            and binding["KDM_calls"] == binding["host_steps"] == 0,
            f"{case}: binding mismatch",
        )
        host = parent["cases"][case]
        check(
            binding["checkpoint_sha256"] == host["candidate_checkpoint_sha256"]
            and binding["host_trace_on_result_sha256"]
            == host["runs"]["pilot_on_trace_on"]["run_result_sha256"]
            and binding["host_trace_off_result_sha256"]
            == host["runs"]["pilot_on_trace_off"]["run_result_sha256"],
            f"{case}: host endpoint/receipt binding mismatch",
        )
        common_binding = (
            binding["source_pins"],
            binding["rt_assets"],
            binding["runtime"],
        )
        if reference_binding is None:
            reference_binding = common_binding
        else:
            check(
                common_binding == reference_binding,
                "control/alpha operator or asset binding differs",
            )
        check(
            summary["binding_sha256"] == bh
            and summary["status"] == "DIRECT_FIXED_M0_COMPLETE"
            and summary["completed_chunk_receipts"]
            == summary["direct_calls_recorded_in_completed_receipts"]
            == 129
            and summary["K_calls"] == 0
            and summary["support_cells"] == Z,
            f"{case}: summary mismatch",
        )
        rows = meta["chunks"]
        check(
            len(rows) == 129 and [r["chunk"] for r in rows] == list(range(129)),
            "receipt index mismatch",
        )
        check(
            all(row["worker_source_sha256"] is None for row in rows),
            "unexpected worker-produced chunk",
        )
        with np.load(io.BytesIO(raw[f"data/{case}.npz"]), allow_pickle=False) as z:
            packed = {k: np.array(z[k], copy=True) for k in z.files}
        for row in rows:
            i = row["chunk"]
            start = i * 512
            stop = min(start + 512, N)
            prefix = f"chunks/chunk_{i:03d}"
            a = json.loads(get(f"{prefix}/attempt.json", row["attempt_sha256"]))
            r = json.loads(get(f"{prefix}/result.json", row["result_sha256"]))
            capture = get(f"{prefix}/result.npz", row["capture_sha256"])
            check(
                row["flat_range"] == a["flat_range"] == [start, stop]
                and a["chunk"] == r["chunk"] == i
                and a["binding_sha256"]
                == r["binding_sha256"]
                == row["binding_sha256"]
                == bh
                and a["with_k"] is False
                and r["capture_sha256"] == row["capture_sha256"]
                and r["direct_calls"] == row["direct_calls"] == 1
                and r["K_calls"] == row["K_calls"] == 0
                and r["rttov_receipt"]["direct_calls"] == 1
                and r["rttov_receipt"]["K_calls"] == 0
                and r["rttov_receipt"]["mode"] == "direct"
                and a.get("worker_source_sha256")
                == r.get("worker_source_sha256")
                == row["worker_source_sha256"],
                f"{case}/{i}: receipt mismatch",
            )
            with np.load(io.BytesIO(capture), allow_pickle=False) as z:
                check(
                    z["flat_indices"].dtype == np.int32
                    and np.array_equal(
                        z["flat_indices"], np.arange(start, stop, dtype=np.int32)
                    ),
                    "capture flat mismatch",
                )
                for src, dst in [
                    ("bt", "bt_k"),
                    ("quality", "model_quality"),
                    ("valid", "actual_valid_mask"),
                    ("profile_valid", "profile_valid"),
                ]:
                    x = z[src]
                    y = packed[dst][start:stop]
                    check(
                        x.dtype == y.dtype
                        and x.shape == y.shape
                        and x.tobytes() == y.tobytes(),
                        f"{case}/{i}: {src} differs from packed",
                    )
        check(
            summary["cost"] == analysis["cases"][case]["cost"]
            and summary["numerator"] == analysis["cases"][case]["huber_numerator"],
            "summary cost mismatch",
        )
        check(
            sha(raw[f"data/{case}.npz"]) == producer["packed_sha256"][case],
            "packed provenance mismatch",
        )
    baseline = (
        HERE.parent
        / "native_full_physics_observation_2026-10-25/native_full_physics_observation_baseline.npz"
    )
    cmd = [
        sys.executable,
        str(HERE / "replay.py"),
        "--baseline",
        str(baseline),
        "--control",
        str(HERE / "data/control.npz"),
        "--control-sha256",
        producer["packed_sha256"]["control"],
        "--alpha025",
        str(HERE / "data/alpha025.npz"),
        "--alpha025-sha256",
        producer["packed_sha256"]["alpha025"],
    ]
    result = json.loads(
        subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    )
    check(
        result == analysis == producer["replay"],
        "replayed arithmetic differs from published analysis",
    )
    diagnostic = subprocess.run(
        [sys.executable, str(HERE / "observation_diagnostics.py")],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.encode()
    check(
        diagnostic == raw["observation_diagnostics.json"],
        "observation diagnostics differ from published bytes",
    )
    details = json.loads(diagnostic)
    check(
        details["packed_sha256"] == producer["packed_sha256"]
        and details["original_M0_channel_cells"] == Z
        and details["model_calls"]
        == {"host": 0, "KDM6": 0, "RTTOV": 0, "optimizer": 0},
        "observation diagnostic binding differs",
    )
    print(
        json.dumps(
            {
                "status": "PACKET_REPLAY_PASSED",
                "chunk_artifacts": 778,
                "cases": 2,
                "support_cells": Z,
                "model_calls_in_replay": 0,
                "costs": {k: v["cost"] for k, v in result["cases"].items()},
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
