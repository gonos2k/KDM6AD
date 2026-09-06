"""Real POSIX process lifecycle tests; no RTTOV/WRF assets or parser doubles."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

from kdm6.obs.rttov_runner import (
    DEFAULT_RTTOV_TIMEOUT, _run_case_fresh, exclusive_rttov_case,
    run_rttov_direct, run_rttov_k, validate_rttov_timeout,
)
from kdm6.obs.rttov_case_writer import make_live_run_k

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX execution contract")


def _running(pid):
    result = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)],
                            capture_output=True, text=True, timeout=2)
    state = result.stdout.strip()
    return bool(state) and not state.startswith("Z")


def _assert_stopped(pid):
    deadline = time.monotonic() + 2
    while _running(pid) and time.monotonic() < deadline:
        time.sleep(.01)
    assert not _running(pid), f"child {pid} survived the execution boundary"


@pytest.mark.parametrize("ending,error", [
    ("wait", subprocess.TimeoutExpired),
    ("exit 0", RuntimeError),
    ("exit 7", RuntimeError),
])
def test_wrapper_descendants_are_stopped_on_every_exit(tmp_path, ending, error):
    script = tmp_path / "run.sh"
    script.write_text(
        "echo $$ > leader.pid\nsleep 30 &\necho $! > worker.pid\n"
        "echo ready\necho diagnostic >&2\necho fresh > result\n" + ending + "\n")
    start = time.monotonic()
    try:
        with pytest.raises(error) as raised:
            _run_case_fresh(script, [tmp_path / "result"], .3)
        assert time.monotonic() - start < 3
        if ending == "exit 0":
            assert "unfinished children" in str(raised.value)
        if ending == "exit 7":
            assert "rc=7" in str(raised.value)
        for name in ("leader.pid", "worker.pid"):
            _assert_stopped(int((tmp_path / name).read_text()))
        assert "diagnostic" in (tmp_path / "run.stderr.log").read_text()
        assert "diagnostic" in (tmp_path / "run.failure.txt").read_text()
    finally:
        # Also clean up if this test is deliberately run against the old code.
        for name in ("worker.pid", "leader.pid"):
            if (tmp_path / name).exists():
                try:
                    os.kill(int((tmp_path / name).read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass


def test_freshness_failure_then_success_clear_failure_record(tmp_path):
    script, target = tmp_path / "run.sh", tmp_path / "result"
    target.write_text("stale")
    script.write_text("exit 0\n")
    with pytest.raises(RuntimeError, match="did not write"):
        _run_case_fresh(script, [target], 2)
    assert not target.exists()
    script.write_text("echo fresh > result\necho done\n")
    _run_case_fresh(script, [target], 2)
    assert target.read_text() == "fresh\n"
    assert (tmp_path / "run.stdout.log").read_text() == "done\n"
    assert not (tmp_path / "run.failure.txt").exists()


@pytest.mark.parametrize("bad", [None, True, 0, -1, float("nan"), float("inf"), "1"])
def test_timeout_rejected_before_case_mutation(tmp_path, bad):
    target = tmp_path / "result"
    target.write_text("keep")
    with pytest.raises(ValueError, match="positive finite"):
        _run_case_fresh(tmp_path / "run.sh", [target], bad)
    with pytest.raises(ValueError, match="positive finite"):
        make_live_run_k(tmp_path, timeout=bad)
    for run in (run_rttov_k, run_rttov_direct):
        with pytest.raises(ValueError, match="positive finite"):
            run(tmp_path, nchannels=1, expected_nprofiles=1, timeout=bad)
    assert target.read_text() == "keep"


def test_live_case_lock_covers_separate_closures_and_aliases(tmp_path, monkeypatch):
    import kdm6.obs.rttov_case_writer as writer
    case = tmp_path / "case"
    alias = tmp_path / "alias"
    case.mkdir()
    alias.symlink_to(case, target_is_directory=True)
    first = make_live_run_k(case)
    second = make_live_run_k(alias)
    writes = []

    class FinishedProbe(Exception):
        pass

    def write(*args, **kwargs):
        writes.append(args[1])
        with pytest.raises(RuntimeError, match="already in use"):
            second(None)
        raise FinishedProbe

    monkeypatch.setattr(writer, "write_rttov_case", write)
    with pytest.raises(FinishedProbe):
        first(None)
    assert writes == [case]
    # Exceptions release ownership; the persistent inode is reusable.
    with exclusive_rttov_case(case):
        pass
    assert first.timeout == DEFAULT_RTTOV_TIMEOUT == 300.0
    assert validate_rttov_timeout(1) == 1.0


def test_case_lock_is_cross_process(tmp_path):
    case = tmp_path / "case"
    code = """
import sys
from kdm6.obs.rttov_runner import exclusive_rttov_case
try:
    with exclusive_rttov_case(sys.argv[1]):
        sys.exit(2)
except RuntimeError as exc:
    assert 'already in use' in str(exc)
"""
    with exclusive_rttov_case(case):
        result = subprocess.run([sys.executable, "-c", code, str(case)],
                                cwd=Path(__file__).parents[1], timeout=10)
        assert result.returncode == 0


def test_interruption_cleans_up_child_before_propagating(tmp_path, monkeypatch):
    original_wait = subprocess.Popen.wait
    injected = []

    def interrupt_once(proc, timeout=None):
        if not injected:
            injected.append(proc.pid)
            raise KeyboardInterrupt
        return original_wait(proc, timeout=timeout)

    script = tmp_path / "run.sh"
    script.write_text("sleep 30\n")
    monkeypatch.setattr(subprocess.Popen, "wait", interrupt_once)
    with pytest.raises(KeyboardInterrupt):
        _run_case_fresh(script, [], 1)
    _assert_stopped(injected[0])
    assert "KeyboardInterrupt" in (tmp_path / "run.failure.txt").read_text()


@pytest.mark.parametrize("failure", [None, RuntimeError, KeyboardInterrupt])
def test_default_run_k_disposes_case_and_sibling_lock(monkeypatch, failure):
    import kdm6.obs.rttov_case_writer as writer
    from kdm6.obs.rttov_obs_operator import default_run_k

    seen = []

    def fake_live(case):
        def run(value):
            with exclusive_rttov_case(case):
                case.mkdir()
                (case / "run.failure.txt").write_text("ephemeral diagnostic")
                seen.append(case.parent)
                if failure:
                    raise failure("unchanged exception")
                return value
        return run

    monkeypatch.setattr(writer, "make_live_run_k", fake_live)
    if failure:
        with pytest.raises(failure, match="unchanged exception"):
            default_run_k("result")
    else:
        assert default_run_k("result") == "result"
    assert len(seen) == 1
    assert not seen[0].exists()  # includes the persistent sibling lock inode
