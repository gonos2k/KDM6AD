#!/usr/bin/env python3
"""Recompute #583 CI timing from archived public GitHub Actions logs."""
from __future__ import annotations

from datetime import datetime
import gzip
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw/ci_runs"
RUNS = {"oracle": 43148213993, "g33": 43148214005, "port": 43148214063}
ANSI = re.compile(r"\x1b\[[0-9;]*m")
COMMAND = re.compile(r"python(?: -O)? -m unittest discover -s (harness/evidence/[A-Za-z0-9_-]+) -v")
SUMMARY = re.compile(r"Ran (\d+) tests? in ([0-9.]+)s")
SKIPPED = re.compile(r"OK \(skipped=(\d+)\)")


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def seconds(start: str, end: str) -> float:
    a = datetime.fromisoformat(start.replace("Z", "+00:00"))
    b = datetime.fromisoformat(end.replace("Z", "+00:00"))
    result = (b - a).total_seconds()
    require(result >= 0, "negative CI duration")
    return result


def load_run(name: str) -> tuple[str, dict, dict]:
    raw = gzip.decompress((RAW / f"{name}.log.gz").read_bytes())
    info_raw = (RAW / f"{name}.json").read_bytes()
    info = json.loads(info_raw)
    require(info["headSha"] == "4f46938f942e438d2bf3d867bf644b624874c6c4", "#583 head")
    require(all(j["conclusion"] == "success" for j in info["jobs"]), "CI job status")
    source = {
        "run_id": RUNS[name],
        "head_sha": info["headSha"],
        "log_sha256": hashlib.sha256(raw).hexdigest(),
        "metadata_sha256": hashlib.sha256(info_raw).hexdigest(),
    }
    return raw.decode("utf-8"), info, source


def job_summary(job: dict) -> dict:
    return {
        "name": job["name"],
        "wall_seconds": seconds(job["startedAt"], job["completedAt"]),
        "steps": {
            step["name"]: seconds(step["startedAt"], step["completedAt"])
            for step in job["steps"]
            if step["status"] == "completed" and step["startedAt"] != "0001-01-01T00:00:00Z"
        },
    }


def evidence_mode(log: str, mode: str) -> dict:
    label = f"unittest (QNICE evidence, {mode})"
    lines = [ANSI.sub("", line) for line in log.splitlines() if f"\t{label}\t" in line]
    commands = [COMMAND.search(line).group(1) for line in lines
                if COMMAND.search(line) and "##[group]Run" not in line]
    summaries = [SUMMARY.search(line) for line in lines if SUMMARY.search(line)]
    require(len(commands) == len(summaries) == 49, f"{mode} suite inventory")
    skips = []
    for index, line in enumerate(lines):
        if not SUMMARY.search(line):
            continue
        following = lines[index + 1:index + 6]
        matches = [SKIPPED.search(next_line) for next_line in following if SKIPPED.search(next_line)]
        skips.append(int(matches[0].group(1)) if matches else 0)
    require(len(skips) == 49, f"{mode} skip inventory")
    suites = [
        {"path": path, "tests": int(match.group(1)),
         "reported_seconds": float(match.group(2)), "skipped": skip}
        for path, match, skip in zip(commands, summaries, skips)
    ]
    require(len({x["path"] for x in suites}) == 49, f"{mode} duplicate suite")
    return {
        "suites": suites,
        "suite_count": 49,
        "tests": sum(x["tests"] for x in suites),
        "skipped": sum(x["skipped"] for x in suites),
        "reported_suite_seconds": round(sum(x["reported_seconds"] for x in suites), 3),
    }


def analyze() -> dict:
    loaded = {name: load_run(name) for name in RUNS}
    oracle_log, oracle_info, _ = loaded["oracle"]
    modes = {mode: evidence_mode(oracle_log, mode) for mode in ("normal", "optimized")}
    require([x["path"] for x in modes["normal"]["suites"]]
            == [x["path"] for x in modes["optimized"]["suites"]], "normal/optimized suite mismatch")
    jobs = {name: [job_summary(j) for j in info["jobs"]]
            for name, (_, info, _) in loaded.items()}
    step = jobs["oracle"][0]["steps"]
    for mode in modes:
        modes[mode]["wall_seconds"] = step[f"unittest (QNICE evidence, {mode})"]
    require(modes["normal"]["tests"] == modes["optimized"]["tests"] == 400,
            "#583 evidence test count")
    require(modes["normal"]["skipped"] == modes["optimized"]["skipped"] == 3,
            "#583 evidence skip count")
    ranking = sorted(
        ({"path": a["path"], "normal_seconds": a["reported_seconds"],
          "optimized_seconds": b["reported_seconds"]}
         for a, b in zip(modes["normal"]["suites"], modes["optimized"]["suites"])),
        key=lambda row: row["normal_seconds"], reverse=True,
    )
    return {
        "schema": "kdm6.native_host_analysis_ci_timing.v1",
        "scope": "#583 completed public CI logs; job wall time and per-suite reported time are distinct",
        "sources": {name: source for name, (_, _, source) in loaded.items()},
        "jobs": jobs,
        "evidence_modes": modes,
        "top_ten_normal": ranking[:10],
        "critical_path_job": "oracle pytest (f64 reference)",
        "critical_path_seconds": jobs["oracle"][0]["wall_seconds"],
        "interpretation": "Concurrent job wall times are not summed; parallel suites may reduce wait while increasing simultaneous CPU/memory use.",
    }


if __name__ == "__main__":
    (HERE / "ci_timing.json").write_text(json.dumps(analyze(), indent=2, sort_keys=True) + "\n")
