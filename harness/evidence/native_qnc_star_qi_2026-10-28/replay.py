#!/usr/bin/env python3
"""Replay accepted QNC-star/QI-donor traces and frozen paired-face arithmetic."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


PACKET = Path(__file__).resolve().parent
REPO = PACKET.parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from harness.analyze_qnc_star_qi_trace import analyze  # noqa: E402
from harness.native_qnc_advect_qi_trace_records import (  # noqa: E402
    read_qi_writer_trace,
    read_qnc_producer_trace,
)
from harness.native_qnc_star_qi_records import (  # noqa: E402
    read_qnc_star_trace,
    read_star_qi_writer_trace,
)


EXPECTED_MANIFEST_SHA = "2e1584cdf1ee3d48247ef2d923d4071de40f395644920e4157456f36a5e03a64"
PARENTS = {
    "pr469": ("native_qnc_advect_qi_2026-10-28",
              "6a13f766cb802ae7bdd26b5f6ee1b32d0e40168f7d43c1116e98e84bdfdfd4e2"),
    "pr470": ("native_qnc_saved_face_probe_2026-10-28",
              "a718b443a242bfda4192d0769a4e1dced98e013ab4ac3e3cf2b8bf1f9cd0da83"),
}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _inventory(root: Path, files: list[dict]) -> None:
    seen = set()
    for item in files:
        rel = item["path"]
        if (not isinstance(rel, str) or rel in seen or Path(rel).is_absolute() or
                ".." in Path(rel).parts or "__pycache__" in Path(rel).parts or
                Path(rel).suffix == ".pyc"):
            raise ValueError(f"unsafe/repeated packet path: {rel}")
        seen.add(rel)
        path = root / rel
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"packet path escapes root: {rel}")
        raw = path.read_bytes()
        if len(raw) != item["bytes"] or sha(raw) != item["sha256"]:
            raise ValueError(f"packet asset differs: {rel}")


def _parents(manifest: dict) -> tuple[Path, dict]:
    if manifest["parent_manifest_pins"] != {name: digest for name, (_, digest) in PARENTS.items()}:
        raise ValueError("historical manifest pins differ")
    roots = {}
    for name, (directory, digest) in PARENTS.items():
        root = REPO / "harness/evidence" / directory
        raw = (root / "manifest.json").read_bytes()
        if sha(raw) != digest:
            raise ValueError(f"{name} historical manifest changed")
        parent = json.loads(raw)
        _inventory(root, parent["files"])
        for rel, source_sha in parent["external_source_pins"].items():
            if sha((REPO / rel).read_bytes()) != source_sha:
                raise ValueError(f"{name} historical source changed: {rel}")
        roots[name] = root
    pr469 = roots["pr469"]
    inputs = {name: pr469 / rel for name, rel in (
        ("control_producer", "data/control/qnc_producer.tsv"),
        ("alpha025_producer", "data/alpha025/qnc_producer.tsv"),
        ("control_writer", "data/control/qi_writer_moments.tsv"),
        ("alpha025_writer", "data/alpha025/qi_writer_moments.tsv"),
        ("execution", "execution_summary.json"),
    )}
    inputs["pr470_analysis"] = roots["pr470"] / "analysis.json"
    if manifest["parent_input_pins"] != {name: sha(path.read_bytes()) for name, path in inputs.items()}:
        raise ValueError("historical producer/writer/analysis input differs")
    return pr469, json.loads(inputs["pr470_analysis"].read_text())


def build_analysis(manifest: dict) -> dict:
    pr469, pr470 = _parents(manifest)
    execution = json.loads((PACKET / "execution_summary.json").read_text())
    prior = json.loads((pr469 / "execution_summary.json").read_text())
    if (execution["status"] != "FOUR_ACCEPTED_FULL_HOST_STEPS_TRACE_NONINTERFERING" or
            execution["base_main_commit"] != "e13da888ea540b22146ab391c12a79d6e9aec023" or
            execution["build"]["base_receipt_sha256"] != prior["private_build_receipt_sha256"] or
            execution["build"]["changed_archive_members"] != ["module_advect_em.o", "solve_em.o"] or
            not execution["build"]["module_interface_byte_identical"] or
            execution["build"]["dso_sha256"] != prior["build"]["dso_sha256"] or
            execution["build"]["public_overlay_sha256"] != sha((
                REPO / "harness/native_qnc_star_qi_overlay.py").read_bytes()) or
            execution["observed_accepted_model_calls"] != {
                "host_steps": 4, "KDM_wrapper_entries": 8, "RTTOV": 0, "optimizer": 0}):
        raise ValueError("native QNC-star/QI-donor build or execution receipt differs")
    runtime = execution["runtime"]
    if (runtime["native_shape_i_j_k"] != [234, 282, 39] or runtime["ranks"] != 1 or
            runtime["threads"] != 1 or runtime["dt_seconds"] != 20 or
            not runtime["radiation_every_step"] or
            runtime["native_runtime_parameters"]["mp_physics"] != "137" or
            runtime["checked_namelist_values"] != {
                "scalar_adv_opt": "1", "moist_adv_opt": "1", "specified": ".true.",
                "spec_zone": "1", "diff_opt": "1", "no_mp_heating": "0",
                "use_q_diabatic": "0"}):
        raise ValueError("native QNC-star/QI-donor runtime differs")
    rejected = execution["rejected_attempts"]
    if (set(rejected) != {"control_trace_on_mpi_exit_one", "alpha025_trace_off_enospc"} or
            any(item["counted_as_accepted"] for item in rejected.values())):
        raise ValueError("rejected native attempts were not kept separate")
    shared, writer, prior_writer, prior_producer = {}, {}, {}, {}
    for case in ("control", "alpha025"):
        runs = execution["runs"][case]
        old = prior["runs"][case]
        if (runs["off"]["checkpoint_sha256"] != runs["on"]["checkpoint_sha256"] or
                runs["off"]["ack_sha256"] != runs["on"]["ack_sha256"] or
                runs["off"]["applied_control"] != runs["on"]["applied_control"] or
                runs["off"]["checkpoint_sha256"] != old["off"]["checkpoint_sha256"] or
                runs["on"]["checkpoint_sha256"] != old["on"]["checkpoint_sha256"] or
                runs["off"]["traces"] or
                any(runs[mode]["host_steps"] != 1 or
                    runs[mode]["observed_kdm_wrapper_entries"] != 2
                    for mode in ("off", "on"))):
            raise ValueError(f"{case} off/on or PR469 endpoint differs")
        descriptors = runs["on"]["traces"]
        paths = {"qnc_star": f"data/{case}/qnc_star.tsv",
                 "star_qi": f"data/{case}/qnc_star_qi_moments.tsv"}
        for name, rel in paths.items():
            raw = (PACKET / rel).read_bytes()
            expected = 147 if name == "qnc_star" else 1550
            if descriptors[name] != {"path": rel, "sha256": sha(raw),
                                     "bytes": len(raw), "typed_records": expected}:
                raise ValueError(f"{case} trace receipt differs from public bytes")
        shared[case] = read_qnc_star_trace(PACKET / paths["qnc_star"])
        writer[case] = read_star_qi_writer_trace(PACKET / paths["star_qi"])
        prior_writer[case] = read_qi_writer_trace(pr469 / f"data/{case}/qi_writer_moments.tsv")
        prior_producer[case] = read_qnc_producer_trace(pr469 / f"data/{case}/qnc_producer.tsv")
    result = analyze(shared["control"], shared["alpha025"],
                     writer["control"], writer["alpha025"],
                     prior_writer["control"], prior_writer["alpha025"],
                     prior_producer["control"], prior_producer["alpha025"])
    target = result["alpha025_frozen_paired_one_ulp_probe"]["cells"]["i113_j70_k12"]
    if (target["candidate_exact_saved_face"]["residual"]["exact"] !=
            pr470["alpha025"]["one_ulp_exact_saved_face"]["residual"]["exact"] or
            target["candidate_source_compatible_f32_qnc"] !=
            pr470["alpha025"]["one_ulp_compatible_f32_qnc"]):
        raise ValueError("new paired target counterfactual differs from PR470")
    return result


def main() -> int:
    manifest_raw = (PACKET / "manifest.json").read_bytes()
    if sha(manifest_raw) != EXPECTED_MANIFEST_SHA:
        raise ValueError("QNC-star/QI-donor packet manifest changed")
    manifest = json.loads(manifest_raw)
    if manifest["schema"] != "kdm6.native_qnc_star_qi_public_packet.v1":
        raise ValueError("QNC-star/QI-donor packet schema differs")
    source = Path(__file__).read_bytes()
    if (source.count(EXPECTED_MANIFEST_SHA.encode()) != 1 or
            sha(source.replace(EXPECTED_MANIFEST_SHA.encode(), b"PENDING")) !=
                manifest["normalized_replay_sha256"]):
        raise ValueError("QNC-star/QI-donor replay source changed")
    _inventory(PACKET, manifest["files"])
    for rel, digest in manifest["external_source_pins"].items():
        if sha((REPO / rel).read_bytes()) != digest:
            raise ValueError(f"QNC-star/QI-donor source changed: {rel}")
    result = build_analysis(manifest)
    actual = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    if actual != (PACKET / "analysis.json").read_bytes():
        raise ValueError("QNC-star/QI-donor analysis differs from published bytes")
    print(json.dumps({"status": "REPLAY_PASSED", "analysis_sha256": sha(actual),
                      "offline_model_calls": result["offline_model_calls"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
