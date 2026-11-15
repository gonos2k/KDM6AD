"""Review-only single orchestrator. No live launch until separate Red clearance."""

import hashlib, json, math, os, pathlib, select, signal, sys, time, secrets
import freeze33, witness33
import fixture33
import replay33_assets
import selector_manifest_spec_v1 as selectors
from real33_supervisor_draft import CLEANUP_RESERVE_SECONDS, deadline_bounds

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
    dso_sha256 = obj.get("dso_sha256")
    if type(dso_sha256) is not str or len(dso_sha256) != 64 or any(c not in '0123456789abcdef' for c in dso_sha256):
        raise ValueError("missing or invalid DSO SHA256")
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
        or not CLEANUP_RESERVE_SECONDS < policy["wall_seconds"] <= 900
        or type(policy.get("cleanup_reserve_seconds")) is not int
        or policy["cleanup_reserve_seconds"] != CLEANUP_RESERVE_SECONDS
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
        "dso_sha256": dso_sha256,
    }


def validate_before_publication(
    out, result, started, deadline, manifest_path, approved_sha, trace_path
):
    """Reject cancellation or elapsed budget after the complete postcheck."""
    directory = pathlib.Path(out)
    paths = [directory / 'calls.jsonl', directory / 'worker_result.json', pathlib.Path(trace_path)] + [directory / f'call_{i:02}.json' for i in range(1, len(fixture33.plan()) + 1)]
    before = {str(path): witness33.sha(path) for path in paths}
    verified = witness33.validate_pinned(
        out, result, time.monotonic() - started, manifest_path, approved_sha, trace_path
    )
    if (
        _CANCELLED
        or signal.sigpending() & {signal.SIGTERM, signal.SIGINT}
        or time.monotonic() >= deadline
    ):
        raise RuntimeError("cancelled or expired during postcheck")
    # Snapshot exact assets around offline replay; no source/physical authenticity is
    # implied by these hashes. Same-UID concurrent mutation remains out of scope.
    replay = replay33_assets.replay(directory)
    if replay.get('status') != 'INCONCLUSIVE' or replay.get('calls') != len(fixture33.plan()):
        raise RuntimeError('invalid offline replay')
    after = {str(path): witness33.sha(path) for path in paths}
    if before != after:
        raise RuntimeError('asset changed during offline replay')
    if _CANCELLED or signal.sigpending() & {signal.SIGTERM, signal.SIGINT} or time.monotonic() >= deadline:
        raise RuntimeError('cancelled or expired during offline replay')
    return {**verified, 'offline_replay': replay, 'asset_sha256': before}



def validate_consumed_marker(path, armed, result):
    """Bind canonical one-shot marker to the actual watchdog and worker identities."""
    keys=('run_nonce','manifest_sha256','worker_pid','worker_start','watchdog_pid','watchdog_start','supervisor_pid','supervisor_start')
    marker_path=pathlib.Path(path)
    if marker_path.is_symlink() or not marker_path.is_file():raise RuntimeError('missing or unsafe consumed marker')
    raw=marker_path.read_bytes();marker=json.loads(raw)
    if type(marker) is not dict or set(marker)!=set(keys)|{'schema','output_dir'} or marker.get('schema')!='kdm6.synthetic33.authority_consumed.v1':raise RuntimeError('consumed marker schema')
    if type(marker['output_dir']) is not str or not marker_path.parent.is_absolute() or marker_path.parent.is_symlink() or str(marker_path.parent.resolve(strict=True))!=str(marker_path.parent) or marker['output_dir']!=str(marker_path.parent):raise RuntimeError('consumed marker output directory mismatch')
    if json.dumps(marker,sort_keys=True,separators=(',',':'),allow_nan=False).encode('ascii')!=raw:raise RuntimeError('consumed marker canonical bytes')
    for key in keys:
        value=marker[key]
        if key.endswith('_pid'):
            valid=type(value) is int and value>0
        elif key.endswith('_start'):
            valid=type(value) is list and len(value)==2 and all(type(x) is int and x>=0 for x in value)
        else:
            valid=type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value)
        if not valid or type(armed.get(key)) is not type(value) or type(result.get(key)) is not type(value) or armed[key]!=value or result[key]!=value or (key.endswith('_start') and any(type(x) is not int for row in (armed[key],result[key]) for x in row)):raise RuntimeError('consumed marker identity mismatch')
    return hashlib.sha256(raw).hexdigest()


def wait_for_watchdog(pid,total_deadline,*,clock=None,waitpid=None,sleep=None):
    """Bound parent wait by the original wall deadline, without assuming cleanup."""
    clock=time.monotonic if clock is None else clock
    waitpid=os.waitpid if waitpid is None else waitpid
    sleep=time.sleep if sleep is None else sleep
    while clock()<total_deadline:
        try:
            done,_=waitpid(pid,os.WNOHANG)
            if done:return True
        except ChildProcessError:return True
        remaining=total_deadline-clock()
        if remaining>0:sleep(min(.02,remaining))
    return False

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
    bounds = deadline_bounds(started, configuration["policy"]["wall_seconds"], configuration["policy"]["cleanup_reserve_seconds"])
    deadline = bounds["execution_deadline"]
    total_deadline = bounds["total_deadline"]
    if time.monotonic() >= deadline:
        raise RuntimeError("preflight wall limit")
    supervisor = os.getpid()
    identity = watchdog.process_start(supervisor)
    launch_capability = watchdog.issue_real_capability(
        manifest_path=manifest_path, approved_sha=approved_sha,
        dso_sha256=configuration["dso_sha256"], run_nonce=nonce,
        supervisor_pid=supervisor, supervisor_start=identity, output_dir=out,
        package=configuration["package"], inventory=configuration["inventory"], deadline=total_deadline,
        execution_deadline=deadline,
    )
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
                execution_deadline=deadline,
                total_deadline=total_deadline,
                max_rss_kib=configuration["policy"]["rss_bytes"] // 1024,
                mock_outdir=str(out),
                manifest_path=manifest_path,
                manifest_sha=approved_sha,
                run_nonce=nonce,
                use_native_census_helper=True,
                native_census_package=configuration["package"],
                native_census_manifest=configuration["inventory"],
                real_capability=launch_capability,
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
        armed = json.loads((out / "armed.json").read_text())
        identity_fields = ("manifest_sha256", "run_nonce", "supervisor_pid", "supervisor_start", "watchdog_pid", "watchdog_start", "worker_pid", "worker_start")
        if armed.get("status") != "ARMED_UNVERIFIED" or any(armed.get(k) != result.get(k) or type(armed.get(k)) is not type(result.get(k)) for k in identity_fields):
            raise RuntimeError("armed/final identity mismatch")
        if (result.get("supervisor_pid"), result.get("supervisor_start"), result.get("watchdog_pid"), result.get("watchdog_start")) != (supervisor, list(identity), pid, list(watchdog_start)):
            raise RuntimeError("supervisor/watchdog identity mismatch")
        worker_start = result.get("worker_start")
        if type(result.get("worker_pid")) is not int or result["worker_pid"] <= 0 or type(worker_start) is not list or len(worker_start) != 2 or any(type(x) is not int or x < 0 for x in worker_start):
            raise RuntimeError("worker start identity missing")
        marker_path=out / "authority_consumed.json"
        marker_sha=validate_consumed_marker(marker_path,armed,result)
        verified = validate_before_publication(out, result, started, deadline, manifest_path, approved_sha, trace["path"])
        receipts = {str(path): witness33.sha(path) for path in (out / "armed.json", out / "armed.json.result", marker_path)}
        if receipts[str(marker_path)]!=marker_sha:raise RuntimeError("consumed marker changed")
        payload = {"schema": "kdm6.synthetic33.completion_candidate.v1", "status": "CANDIDATE_UNVERIFIED", "validated_assets": verified, "manifest_sha256": approved_sha, "run_nonce": nonce, "worker_pid": result["worker_pid"], "worker_start": worker_start, "watchdog_pid": pid, "watchdog_start": list(watchdog_start), "receipt_sha256": receipts, "authority_scope": "candidate only; independent supervisor witness required"}
        def recheck():
            if _CANCELLED or signal.sigpending() & {signal.SIGINT, signal.SIGTERM} or time.monotonic() >= deadline:
                raise RuntimeError("cancelled or expired before completion")
            if reviewed_configuration(manifest_path, approved_sha) != configuration:
                raise RuntimeError("manifest changed before completion")
            if any(witness33.sha(path) != digest for path, digest in {**verified["asset_sha256"], **receipts}.items()):
                raise RuntimeError("completion input changed")
        witness33.publish_candidate(out / "completion_candidate.json", payload, deadline, recheck)
        return payload
    finally:
        # Closing liveness asks the independent watchdog to clean up.
        try:
            os.close(life_w)
        except OSError:
            pass
        reaped = wait_for_watchdog(pid,total_deadline)
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
