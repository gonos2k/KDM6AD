#!/usr/bin/env python3
"""Fail-closed scheduling envelope; no KDM producer or scientific verification.

The checked-in SPEC_ONLY plan has no new DSO pin and cannot be launched.
"""

import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
HEX = re.compile(r"^[0-9a-f]{64}$")
PLAN_GZ_SHA = "4d6a935c9d83d987a8a2149d58699b2812af565785d20c599cf9f49f05846b8a"
STUB = HERE / "budget_test_stub.py"
STUB_SHA = "c282d35b37335b8af0f3933e1205ace7b6c2ed81c35da3a2f79f7038108259f7"
SCENARIOS = {"success", "sleep", "fail", "term_ignoring_child", "residual_child"}
MAX_CALLS = 100
MAX_SECONDS = 900.0


class BudgetError(RuntimeError):
    pass


class Cancelled(BudgetError):
    pass


class FinalReceiptError(BudgetError):
    """A durable final receipt could not be written; execution is not successful."""

    def __init__(self, message, receipt):
        super().__init__(message)
        self.receipt = receipt


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_plan():
    raw = (HERE / "plan.json.gz").read_bytes()
    if hashlib.sha256(raw).hexdigest() != PLAN_GZ_SHA:
        raise BudgetError("canonical plan hash mismatch")
    return json.loads(gzip.decompress(raw))


def validate(plan, binding, commands, skipped, root=ROOT):
    """Validate all inputs before launch; current checked-in plan stays blocked."""
    expected = canonical_plan()
    if (
        plan.get("schema") != "kdm6.native_host_capture_preflight.v1"
        or plan.get("status") != "SPEC_ONLY"
        or plan.get("execution_receipt") is not None
    ):
        raise BudgetError("SPEC_ONLY plan required")
    candidate = plan.get("build_requirements", {}).get("instrumented_dso_sha256")
    if (
        not isinstance(candidate, str)
        or not HEX.fullmatch(candidate)
        or candidate == plan["build_requirements"].get("installed_dso_sha256")
    ):
        raise BudgetError(
            "execution blocked: distinct new instrumented DSO SHA256 required"
        )
    # Only the predeclared new-DSO slot may differ; every call/input/control is fixed.
    normalized = json.loads(json.dumps(plan))
    normalized["build_requirements"]["instrumented_dso_sha256"] = None
    if normalized != expected:
        raise BudgetError("plan differs from canonical SPEC_ONLY plan")
    limits = plan["limits"]
    calls = plan["calls"]
    if (
        limits["calls_max"] > MAX_CALLS
        or limits["wall_seconds_max"] > MAX_SECONDS
        or len(calls) != limits["calls_max"]
        or len(calls) > MAX_CALLS
    ):
        raise BudgetError("plan exceeds budget")
    if [x["sequence"] for x in calls] != list(range(1, len(calls) + 1)) or any(
        x["status"] not in ("PLANNED", "PLANNED_OPTIONAL") for x in calls
    ):
        raise BudgetError("invalid planned call sequence")
    if (
        not isinstance(binding, dict)
        or set(binding)
        != {"dso", "dependencies", "sources", "producer_files", "controls", "compiler"}
        or binding["controls"] != plan["controls"]
    ):
        raise BudgetError("incomplete build/controls binding")

    def checked(item, expected_hash=None):
        if (
            not isinstance(item, dict)
            or set(item) != {"path", "sha256"}
            or not isinstance(item["sha256"], str)
            or not HEX.fullmatch(item["sha256"])
        ):
            raise BudgetError("invalid bound asset")
        path = Path(item["path"])
        if (
            not path.is_absolute()
            or path.is_symlink()
            or not path.is_file()
            or digest(path) != item["sha256"]
            or (expected_hash is not None and item["sha256"] != expected_hash)
        ):
            raise BudgetError("bound asset missing or changed")

    checked(binding["dso"], candidate)
    for field in ("dependencies", "sources", "producer_files"):
        if not isinstance(binding[field], dict) or not binding[field]:
            raise BudgetError(field + " required")
        for value in binding[field].values():
            checked(value)
    pins = plan["build_requirements"]["source_pins"]
    if set(binding["sources"]) != set(pins):
        raise BudgetError("source pin inventory mismatch")
    for name, sha in pins.items():
        if (
            Path(binding["sources"][name]["path"]).resolve()
            != (Path(root) / name).resolve()
            or binding["sources"][name]["sha256"] != sha
        ):
            raise BudgetError("source path/pin mismatch")
    compiler = binding["compiler"]
    if (
        not isinstance(compiler, dict)
        or not compiler.get("identity")
        or "-ffp-contract=off" not in compiler.get("flags", [])
        or compiler.get("test_assertions") != "enabled"
    ):
        raise BudgetError("compiler/FP/assertion controls required")
    skipped = set(skipped)
    optional = {x["sequence"] for x in calls if x["status"] == "PLANNED_OPTIONAL"}
    if not skipped <= optional:
        raise BudgetError("only explicitly optional calls can be skipped")
    if set(commands) != {x["sequence"] for x in calls} - skipped:
        raise BudgetError("command inventory mismatch")
    for seq, cmd in commands.items():
        if not isinstance(cmd, dict) or set(cmd) != {"argv", "env", "artifact"}:
            raise BudgetError("invalid command binding")
        argv, env, artifact = cmd["argv"], cmd["env"], cmd["artifact"]
        if STUB.is_symlink() or not STUB.is_file() or digest(STUB) != STUB_SHA:
            raise BudgetError("synthetic stub missing or changed")
        expected = [str(Path(sys.executable).resolve()), "-I", "-S", str(STUB)]
        if (
            not isinstance(argv, list)
            or len(argv) != 5
            or argv[:4] != expected
            or argv[4] not in SCENARIOS
        ):
            raise BudgetError("only pinned synthetic stub scenarios are allowed")
        if not any(
            Path(a["path"]).resolve() == Path(argv[0]).resolve()
            for a in binding["producer_files"].values()
        ):
            raise BudgetError("synthetic interpreter must be pinned")
        if env != {
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "OMP_THREAD_LIMIT": "1",
        }:
            raise BudgetError("synthetic environment must be exact and isolated")
        if artifact != "out.bin":
            raise BudgetError("synthetic artifact must be out.bin")
    return calls


def _alive(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError as exc:
        raise BudgetError("process group probe denied") from exc


def _terminate(proc, deadline):
    """Try TERM then KILL, never assert that a denied group vanished."""
    errors = []
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except OSError as e:
        errors.append(str(e))
    until = min(deadline, time.monotonic() + 0.5)
    while time.monotonic() < until:
        try:
            if not _alive(proc.pid):
                break
        except BudgetError as e:
            errors.append(str(e))
            break
        time.sleep(0.02)
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError as e:
        errors.append(str(e))
    try:
        proc.wait(timeout=max(0.01, min(1.0, deadline - time.monotonic())))
    except subprocess.TimeoutExpired:
        errors.append("leader not reaped before deadline")
    try:
        if _alive(proc.pid):
            errors.append("residual process group remains")
    except BudgetError as e:
        errors.append(str(e))
    return errors


def _write_receipt(path, receipt):
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w") as f:
        json.dump(receipt, f, indent=2, allow_nan=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def run(
    plan,
    binding,
    commands,
    skipped,
    run_directory,
    *,
    synthetic_test=False,
    root=ROOT,
    clock=time.monotonic,
):
    """Execute an independently checked future plan; output is a scheduling envelope.

    Production execution is always blocked. Explicit synthetic_test mode exercises
    scheduling only and its receipts cannot represent real scientific execution.
    """
    if synthetic_test is not True:
        raise BudgetError(
            "production execution blocked: a separately registered EXECUTION_READY successor and adapter are required"
        )
    if binding.get("compiler", {}).get("identity") != "SYNTHETIC_TEST_ONLY":
        raise BudgetError("synthetic test binding required")
    begin = clock()
    calls = validate(plan, binding, commands, skipped, root=root)
    directory = Path(run_directory)
    directory.mkdir(parents=True, exist_ok=False)
    deadline = begin + min(float(plan["limits"]["wall_seconds_max"]), MAX_SECONDS)
    records = []
    cancelled = []
    old_handlers = {}
    receipt = {
        "schema": "kdm6.native_host_preflight.execution_budget.v1",
        "status": "RUNNING",
        "execution_scope": "SYNTHETIC_TEST_ONLY",
        "scientific_status": "INCONCLUSIVE",
        "physical_unit_status": "INCONCLUSIVE",
        "plan_gzip_sha256": PLAN_GZ_SHA,
        "plan_sha256": hashlib.sha256(
            json.dumps(
                plan, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
        ).hexdigest(),
        "dso_sha256": binding["dso"]["sha256"],
        "controls": plan["controls"],
        "limits": plan["limits"],
        "calls": records,
        "scope": "scheduler envelope only; output semantics and scientific claims require independent verification",
    }

    cleanup_active = False

    def cancel(sig, _frame):
        first = not cancelled
        cancelled.append(sig)
        if first and not cleanup_active:
            raise Cancelled("received signal " + str(sig))

    def terminate(proc):
        nonlocal cleanup_active
        cleanup_active = True
        try:
            return _terminate(proc, deadline)
        finally:
            cleanup_active = False

    for sig in (signal.SIGTERM, signal.SIGINT):
        old_handlers[sig] = signal.signal(sig, cancel)
    failed = False
    reason = None
    try:
        for c in calls:
            seq = c["sequence"]
            record = {
                "sequence": seq,
                "input_id": c["input_id"],
                "mode": c["mode"],
                "required": c["status"] == "PLANNED",
            }
            records.append(record)
            if seq in skipped:
                record.update(status="skipped", reason="explicit_optional_skip")
                continue
            if failed or clock() >= deadline:
                record.update(
                    status="skipped", reason="not_started_after_failure_or_budget"
                )
                failed = True
                continue
            call_dir = directory / f"{seq:03d}"
            call_dir.mkdir()
            cmd = commands[seq]
            start = clock()
            proc = None
            cleanup = []
            try:
                # Check all byte pins again before every launch, including sources/deps.
                validate(plan, binding, commands, skipped, root=root)
                remaining = deadline - clock()
                if remaining <= 0:
                    raise BudgetError("wall budget exhausted before launch")
                with (
                    (call_dir / "stdout.bin").open("xb") as stdout,
                    (call_dir / "stderr.bin").open("xb") as stderr,
                ):
                    proc = subprocess.Popen(
                        cmd["argv"],
                        cwd=call_dir,
                        env=cmd["env"],
                        stdout=stdout,
                        stderr=stderr,
                        start_new_session=True,
                    )
                    try:
                        rc = proc.wait(timeout=remaining)
                    except subprocess.TimeoutExpired:
                        cleanup = terminate(proc)
                        raise BudgetError("call timed out")
                try:
                    residual = _alive(proc.pid)
                except BudgetError:
                    cleanup = terminate(proc)
                    raise
                if residual:
                    cleanup = terminate(proc)
                    raise BudgetError("residual process group after leader exit")
                if rc != 0:
                    raise BudgetError("producer returned " + str(rc))
                artifact = call_dir / cmd["artifact"]
                if artifact.is_symlink() or not artifact.is_file():
                    raise BudgetError("missing or invalid artifact")
                if clock() > deadline:
                    raise BudgetError("wall budget exceeded during output validation")
                record.update(
                    status="completed",
                    returncode=rc,
                    output_path=str(artifact.relative_to(directory)),
                    output_sha256=digest(artifact),
                )
            except (Exception, KeyboardInterrupt) as exc:
                if proc is not None and proc.poll() is None:
                    cleanup += terminate(proc)
                failed = True
                reason = str(exc)
                record.update(
                    status="failed",
                    reason=reason,
                    returncode=proc.returncode if proc else None,
                    cleanup_errors=cleanup,
                )
            finally:
                for file in ("stdout.bin", "stderr.bin"):
                    p = call_dir / file
                    if p.exists():
                        record[file.replace(".bin", "_sha256")] = digest(p)
                record["elapsed_seconds"] = clock() - start
                try:
                    _write_receipt(directory / "receipt.json", receipt)
                except Exception as exc:
                    failed = True
                    reason = "intermediate receipt write failed: " + str(exc)
            if clock() > deadline:
                failed = True
                reason = "wall budget exceeded during record write"
    finally:
        # Record signals during finalization without interrupting the durable writes.
        cleanup_active = True
        recorded = {x["sequence"] for x in records}
        for c in calls:
            if c["sequence"] not in recorded:
                records.append(
                    {
                        "sequence": c["sequence"],
                        "input_id": c["input_id"],
                        "mode": c["mode"],
                        "required": c["status"] == "PLANNED",
                        "status": "skipped",
                        "reason": "not_started_after_cancel",
                    }
                )
        records.sort(key=lambda x: x["sequence"])
        receipt["elapsed_seconds"] = clock() - begin
        receipt["status"] = "INCOMPLETE"
        receipt["reason"] = reason or "finalization pending"
        receipt["signals"] = cancelled
        receipt_path = directory / "receipt.json"
        marker_path = directory / "completion.json"
        try:
            # A provisional receipt is durable before any completion candidate.
            _write_receipt(receipt_path, receipt)
            receipt["elapsed_seconds"] = clock() - begin
            over = clock() > deadline
            if over:
                reason = "wall budget exceeded during final receipt write"
            receipt["status"] = (
                "INCOMPLETE"
                if failed
                or cancelled
                or over
                or any(x["required"] and x["status"] != "completed" for x in records)
                else "SYNTHETIC_COMPLETED_UNVERIFIED"
            )
            receipt["reason"] = reason
            _write_receipt(receipt_path, receipt)
            # Include the candidate receipt serialization/fsync in elapsed time.
            receipt["elapsed_seconds"] = clock() - begin
            if clock() > deadline or cancelled:
                receipt["status"] = "INCOMPLETE"
                receipt["reason"] = (
                    "wall budget exceeded during final receipt write"
                    if clock() > deadline
                    else "cancelled during finalization"
                )
            _write_receipt(receipt_path, receipt)
            if receipt["status"] != "INCOMPLETE" and (clock() > deadline or cancelled):
                receipt["status"] = "INCOMPLETE"
                receipt["reason"] = (
                    "wall budget exceeded during final receipt write"
                    if clock() > deadline
                    else "cancelled during finalization"
                )
                receipt["elapsed_seconds"] = clock() - begin
                _write_receipt(receipt_path, receipt)
            if receipt["status"] == "SYNTHETIC_COMPLETED_UNVERIFIED":
                # Readers must require this marker and independently hash receipt.
                marker = {
                    "schema": "kdm6.native_host_preflight.budget_completion.v1",
                    "execution_scope": "SYNTHETIC_TEST_ONLY",
                    "plan_sha256": receipt["plan_sha256"],
                    "receipt_sha256": digest(receipt_path),
                }
                _write_receipt(marker_path, marker)
                if clock() > deadline or cancelled:
                    marker_path.unlink(missing_ok=True)
                    receipt["status"] = "INCOMPLETE"
                    receipt["reason"] = (
                        "wall budget exceeded during completion marker write"
                        if clock() > deadline
                        else "cancelled during finalization"
                    )
                    receipt["elapsed_seconds"] = clock() - begin
                    _write_receipt(receipt_path, receipt)
        except Exception as exc:
            receipt["status"] = "INCOMPLETE"
            receipt["reason"] = "final receipt write failed: " + str(exc)
            receipt["elapsed_seconds"] = clock() - begin
            try:
                marker_path.unlink(missing_ok=True)
            except OSError:
                pass
            try:
                _write_receipt(receipt_path, receipt)
            except Exception:
                try:
                    receipt_path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise FinalReceiptError(receipt["reason"], receipt) from exc
        finally:
            for sig, handler in old_handlers.items():
                signal.signal(sig, handler)

    return receipt


if __name__ == "__main__":
    raise SystemExit(
        "SPEC_ONLY: no instrumented DSO or producer adapter is authorized by this command"
    )
