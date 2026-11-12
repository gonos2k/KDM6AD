#!/usr/bin/env python3
"""Parent-wait witness for synthetic budget runs; not an execution authorization.

Witnesses are caller-supplied, unsigned observations and cannot authenticate a
producer or scientific result. This supervisor invokes only the scheduler's
pinned-stub synthetic path; the production path remains blocked.
"""

import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import tempfile
import time

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "native_budget_scheduler", HERE / "execute_budget.py"
)
scheduler = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scheduler)
WITNESS_SCHEMA = "kdm6.native_host_preflight.supervisor_witness.v1"
CANDIDATE_SCHEMA = "kdm6.native_host_preflight.budget_completion_candidate.v1"


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _write_new(path, obj):
    data = (
        json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()
    fd, name = tempfile.mkstemp(prefix=".witness.", dir=path.parent)
    linked = False
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        # Hard-link is atomic and refuses to overwrite an existing witness.
        os.link(name, path)
        linked = True
        os.unlink(name)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        if linked:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        raise
    finally:
        if os.path.exists(name):
            os.unlink(name)


def supervise(plan, binding, commands, skipped, run_directory, *, root=scheduler.ROOT):
    """Run the fixed-stub scheduler in a child and witness its actual full wait.

    There is deliberately no file-only witness creation API. The child is forked
    here, and only a zero exit and observed parent wall within the plan budget
    permit a witness. This synchronous helper does not enforce a parent watchdog;
    an external watchdog must still handle a stuck child. No completion evidence
    is produced if this parent itself is killed or wait fails.
    """
    directory = Path(run_directory)
    budget = float(plan["limits"]["wall_seconds_max"])
    if not math.isfinite(budget) or budget <= 0 or budget > scheduler.MAX_SECONDS:
        raise scheduler.BudgetError("invalid supervisor budget")
    if directory.exists() or directory.is_symlink():
        raise scheduler.BudgetError("supervisor requires a new run directory")
    read_fd, write_fd = os.pipe()
    started = time.monotonic()
    try:
        pid = os.fork()
    except BaseException:
        os.close(read_fd)
        os.close(write_fd)
        raise
    if pid == 0:
        os.close(read_fd)
        try:
            result = scheduler.run(
                plan,
                binding,
                commands,
                skipped,
                directory,
                synthetic_test=True,
                root=root,
            )
            if result["status"] != "SYNTHETIC_CANDIDATE_UNVERIFIED":
                os._exit(1)
            token = {
                "schema": "kdm6.native_host_preflight.child_return.v1",
                "receipt_sha256": _sha((directory / "receipt.json").read_bytes()),
                "candidate_sha256": _sha((directory / "completion.json").read_bytes()),
            }
            os.write(
                write_fd,
                json.dumps(token, sort_keys=True, separators=(",", ":")).encode(),
            )
            os.close(write_fd)
            os._exit(0)
        except BaseException:
            os._exit(1)
    os.close(write_fd)
    try:
        observed, status = os.waitpid(pid, 0)
    except BaseException:
        # No witness is possible when the parent cannot complete its wait.
        try:
            os.kill(pid, 15)
        except ProcessLookupError:
            pass
        try:
            os.waitpid(pid, 0)
        except (ChildProcessError, InterruptedError):
            pass
        os.close(read_fd)
        raise
    wall = time.monotonic() - started
    os.set_blocking(read_fd, False)
    try:
        try:
            token_raw = os.read(read_fd, 2048)
        except BlockingIOError:
            token_raw = b""
    finally:
        os.close(read_fd)
    exit_code = os.waitstatus_to_exitcode(status)
    outcome = {
        "status": "UNWITNESSED",
        "child_exit_code": exit_code,
        "wall_seconds": wall,
        "budget_seconds": budget,
    }
    if observed != pid or exit_code != 0 or wall > budget:
        outcome["reason"] = "child did not exit normally within full parent wall budget"
        return outcome
    try:
        receipt_path = directory / "receipt.json"
        candidate_path = directory / "completion.json"
        if receipt_path.is_symlink() or candidate_path.is_symlink():
            raise ValueError("symlink receipt or candidate")
        receipt_raw = receipt_path.read_bytes()
        candidate_raw = candidate_path.read_bytes()
        receipt = json.loads(receipt_raw)
        candidate = json.loads(candidate_raw)
        token = json.loads(token_raw)
        if token != {
            "schema": "kdm6.native_host_preflight.child_return.v1",
            "receipt_sha256": _sha(receipt_raw),
            "candidate_sha256": _sha(candidate_raw),
        }:
            raise ValueError("missing or mismatched scheduler return token")
        plan_sha = _sha(
            json.dumps(
                plan, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
        )
        elapsed = receipt.get("elapsed_seconds")
        if (
            type(elapsed) not in (int, float)
            or not math.isfinite(elapsed)
            or elapsed < 0
            or elapsed > wall
        ):
            raise ValueError("receipt elapsed exceeds observed parent wall")
        if (
            receipt.get("status") != "SYNTHETIC_CANDIDATE_UNVERIFIED"
            or receipt.get("execution_scope") != "SYNTHETIC_TEST_ONLY"
            or receipt.get("plan_sha256") != plan_sha
            or candidate
            != {
                "schema": CANDIDATE_SCHEMA,
                "status": "CANDIDATE_NOT_SUFFICIENT",
                "execution_scope": "SYNTHETIC_TEST_ONLY",
                "plan_sha256": plan_sha,
                "receipt_sha256": _sha(receipt_raw),
            }
        ):
            raise ValueError("receipt or candidate binding mismatch")
        witness = {
            "schema": WITNESS_SCHEMA,
            "execution_scope": "SYNTHETIC_TEST_ONLY",
            "plan_sha256": plan_sha,
            "receipt_sha256": _sha(receipt_raw),
            "candidate_sha256": _sha(candidate_raw),
            "child_exit_code": exit_code,
            "child_return_confirmed": True,
            "child_return_token": token_raw.decode("utf-8"),
            "child_return_token_sha256": _sha(token_raw),
            "wall_seconds": wall,
            "budget_seconds": budget,
            "supervisor_source_sha256": _sha(Path(__file__).read_bytes()),
        }
        _write_new(directory / "supervisor_witness.json", witness)
        outcome.update(status="WITNESSED_SYNTHETIC_UNVERIFIED", witness=witness)
        return outcome
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        outcome["reason"] = "witness validation/write failed: " + str(exc)
        return outcome
