"""Review-only single orchestrator. No live launch until separate Red clearance."""

import hashlib, json, math, os, pathlib, select, signal, sys, time, secrets
import freeze33, witness33
import fixture33
import selector_manifest_spec_v1 as selectors

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "fake_watchdog"))
import watchdog

REAL33_RELEASE_ENABLED = False
_CANCELLED = []


def _cancel(signum, frame):
    _CANCELLED.append(signum)


def reviewed_configuration(manifest_path, approved_sha):
    """Recheck the independent manifest and bind census/policy without loading a DSO."""
    freeze33.validate_frozen(manifest_path, approved_sha)
    path = pathlib.Path(manifest_path)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError("private manifest path")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != approved_sha:
        raise ValueError("private manifest SHA changed")
    obj = json.loads(raw)
    config = obj.get("census_provider")
    if type(config) is not dict or set(config) != {
        "package",
        "inventory",
        "inventory_sha256",
    }:
        raise ValueError("missing census provider pins")
    package = pathlib.Path(config["package"])
    verified = watchdog.validate_real_census_config(
        path, approved_sha, package, config["inventory"]
    )
    if verified.get("manifest_sha256") != approved_sha:
        raise ValueError("census verifier mismatch")
    policy = obj.get("budgets")
    if type(policy) is not dict:
        raise ValueError("missing manifest policy")
    slots = fixture33.plan()
    exact = {"forwards": len(slots), **selectors.query_budget(slots)["total"]}
    if any(type(policy.get(k)) is not int or policy[k] != v for k, v in exact.items()):
        raise ValueError("manifest call/query policy")
    if (
        type(policy.get("wall_seconds")) not in (int, float)
        or not math.isfinite(policy["wall_seconds"])
        or not 0 < policy["wall_seconds"] <= 900
        or type(policy.get("rss_bytes")) is not int
        or not 0 < policy["rss_bytes"] <= 4 * 1024**3
        or policy["rss_bytes"] % 1024
        or type(policy.get("serialized_call_bytes")) is not int
        or policy["serialized_call_bytes"] != 128 * 1024**2
        or type(policy.get("serialized_total_bytes")) is not int
        or policy["serialized_total_bytes"] != 4 * 1024**3
    ):
        raise ValueError("manifest resource policy")
    return {
        "package": verified["package"],
        "inventory": verified["inventory"],
        "inventory_sha256": config["inventory_sha256"],
        "policy": dict(policy),
    }


def validate_before_publication(
    out, result, started, deadline, manifest_path, approved_sha, trace_path
):
    """Reject cancellation or elapsed budget after the complete postcheck."""
    verified = witness33.validate_pinned(
        out, result, time.monotonic() - started, manifest_path, approved_sha, trace_path
    )
    if (
        _CANCELLED
        or signal.sigpending() & {signal.SIGTERM, signal.SIGINT}
        or time.monotonic() >= deadline
    ):
        raise RuntimeError("cancelled or expired during postcheck")
    return verified


def run(outdir, manifest_path, approved_sha):
    if not REAL33_RELEASE_ENABLED:
        raise RuntimeError("real33 execution disabled pending Red review")
    _CANCELLED.clear()
    started = time.monotonic()
    out = pathlib.Path(outdir).resolve(strict=True)
    if any(out.iterdir()):
        raise RuntimeError("output directory must be empty")
    nonce = secrets.token_hex(32)
    fd = os.open(out / "run_nonce", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, nonce.encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    # A nonce alone is not an execution or completion receipt; preflight failure
    # leaves no ARMED or completion witness.
    configuration = reviewed_configuration(manifest_path, approved_sha)
    deadline = started + configuration["policy"]["wall_seconds"]
    if time.monotonic() >= deadline:
        raise RuntimeError("preflight wall limit")
    supervisor = os.getpid()
    identity = watchdog.process_start(supervisor)
    opened = []
    old_handlers = {}
    try:
        life_r, life_w = os.pipe()
        opened.extend((life_r, life_w))
        release_r, release_w = os.pipe()
        opened.extend((release_r, release_w))
        ready_r, ready_w = os.pipe()
        opened.extend((ready_r, ready_w))
        for sig in (signal.SIGTERM, signal.SIGINT):
            old_handlers[sig] = signal.signal(sig, _cancel)
        pid = os.fork()
    except BaseException:
        for fd in opened:
            try:
                os.close(fd)
            except OSError:
                pass
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)
        raise
    if pid == 0:
        os.close(life_w)
        os.close(release_w)
        os.close(ready_r)
        rc = 1
        try:
            watchdog.supervise(
                supervisor,
                identity,
                life_r,
                release_r,
                ready_w,
                str(out / "armed.json"),
                "fixture33_real",
                timeout=max(0, deadline - time.monotonic()),
                max_rss_kib=configuration["policy"]["rss_bytes"] // 1024,
                mock_outdir=str(out),
                manifest_path=manifest_path,
                manifest_sha=approved_sha,
                run_nonce=nonce,
                use_native_census_helper=True,
                native_census_package=configuration["package"],
                native_census_manifest=configuration["inventory"],
            )
            rc = 0
        except BaseException as exc:
            try:
                watchdog.atomic(
                    out / "watchdog_failure.json",
                    {"status": "INCOMPLETE", "run_nonce": nonce, "error": repr(exc)},
                )
            except BaseException:
                pass
        os._exit(rc)
    os.close(life_r)
    os.close(release_r)
    os.close(ready_w)
    try:
        if (
            not select.select([ready_r], [], [], max(0, deadline - time.monotonic()))[0]
            or os.read(ready_r, 1) != b"R"
        ):
            raise RuntimeError("watchdog not armed")
        watchdog_start = watchdog.process_start(pid)
        oldmask = signal.pthread_sigmask(
            signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGINT}
        )
        try:
            if (
                _CANCELLED
                or signal.sigpending() & {signal.SIGTERM, signal.SIGINT}
                or time.monotonic() >= deadline
            ):
                raise RuntimeError("cancelled or expired before worker release")
            if watchdog.process_start(pid) != watchdog_start:
                raise RuntimeError("watchdog identity changed before worker release")
            if select.select([ready_r], [], [], 0)[0]:
                raise RuntimeError("watchdog unavailable before worker release")
            if reviewed_configuration(manifest_path, approved_sha) != configuration:
                raise RuntimeError(
                    "manifest configuration changed before worker release"
                )
            # Linearization point: cancellation, deadline and watchdog
            # liveness have been observed; later events are post-release.
            if (
                _CANCELLED
                or signal.sigpending() & {signal.SIGTERM, signal.SIGINT}
                or time.monotonic() >= deadline
            ):
                raise RuntimeError("cancelled or expired before worker release")
            os.write(release_w, b"G")
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, oldmask)
        # No automatic retry; a closed liveness FD causes watchdog cleanup.
        while time.monotonic() < deadline:
            waited, status = os.waitpid(pid, os.WNOHANG)
            if _CANCELLED:
                raise RuntimeError("supervisor cancelled")
            if waited:
                if status != 0:
                    raise RuntimeError("watchdog process failure")
                break
            time.sleep(0.05)
        else:
            raise RuntimeError("whole wall limit")
        result = json.loads((out / "armed.json.result").read_text())
        if (
            result.get("run_nonce") != nonce
            or result.get("manifest_sha256") != approved_sha
            or result.get("watchdog_pid") != pid
        ):
            raise RuntimeError("watchdog result identity")
        trace = result["exclusive_trace"]
        if not pathlib.Path(trace["path"]).is_file():
            raise RuntimeError("missing exclusive trace")
        if witness33.sha(trace["path"]) != trace["sha256"]:
            raise RuntimeError("trace digest changed")
        validate_before_publication(
            out, result, started, deadline, manifest_path, approved_sha, trace["path"]
        )
        # Real publication is deliberately disabled; fake-only link tests exist.
        raise RuntimeError("real witness publication disabled pending Red review")
    finally:
        # Closing liveness asks the independent watchdog to clean up.
        try:
            os.close(life_w)
        except OSError:
            pass
        until = time.monotonic() + 28
        reaped = False
        while time.monotonic() < until:
            try:
                done, _ = os.waitpid(pid, os.WNOHANG)
                if done:
                    reaped = True
                    break
            except ChildProcessError:
                reaped = True
                break
            time.sleep(0.02)
        if not reaped:
            try:
                watchdog.atomic(
                    out / "cleanup_unresolved.json",
                    {
                        "status": "INCOMPLETE",
                        "run_nonce": nonce,
                        "reason": "watchdog not reaped within cleanup bound",
                    },
                )
            except BaseException:
                pass
        for fd in (release_w, ready_r):
            try:
                os.close(fd)
            except OSError:
                pass
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)
