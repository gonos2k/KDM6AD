"""Direct-parent loss after release, using a stalled fake worker only."""
import json
import os
from pathlib import Path
import select
import signal
import tempfile
import time
import unittest

import watchdog


class ParentLossChecks(unittest.TestCase):
    def test_orchestrator_exit_after_release_preserves_watchdog_cleanup(self):
        started = time.monotonic()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            notify_r, notify_w = os.pipe()
            trigger_r, trigger_w = os.pipe()
            orchestrator = os.fork()
            if orchestrator == 0:
                try:
                    os.close(notify_r)
                    os.close(trigger_w)
                    life_r, life_w = os.pipe()
                    release_r, release_w = os.pipe()
                    ready_r, ready_w = os.pipe()
                    identity = watchdog.process_start(os.getpid())
                    dog = os.fork()
                    if dog == 0:
                        try:
                            os.close(life_w)
                            os.close(release_w)
                            os.close(ready_r)
                            os.close(notify_w)
                            os.close(trigger_r)
                            # CPU-free fake sampling; actual cleanup still uses
                            # the real parent waitid and process-group census.
                            watchdog.group_rss_kib = lambda pid: 1024
                            original_waitpid = watchdog.os.waitpid
                            def audited_waitpid(pid, options):
                                if options == 0:
                                    if not watchdog.leader_exited(pid):
                                        raise RuntimeError('worker not WNOWAIT-reserved')
                                    if watchdog.other_members(pid):
                                        raise RuntimeError('worker group not empty before reap')
                                    (root / 'wnowait_before_reap').write_text('reserved and empty')
                                return original_waitpid(pid, options)
                            watchdog.os.waitpid = audited_waitpid
                            watchdog.supervise(os.getppid(), identity, life_r, release_r,
                                               ready_w, str(root / 'armed'), 'term_ignore_descendant',
                                               timeout=12, mock_outdir=str(root), fake_ready_timeout=10)
                        except BaseException:
                            import traceback
                            (root / 'watchdog_exception').write_text(traceback.format_exc())
                            os._exit(91)
                        os._exit(0)
                    os.close(life_r)
                    os.close(release_r)
                    os.close(ready_w)
                    if not select.select([ready_r], [], [], 10)[0] or os.read(ready_r, 1) != b'R':
                        os._exit(92)
                    os.write(release_w, b'G')
                    if not select.select([ready_r], [], [], 10)[0] or os.read(ready_r, 1) != b'G':
                        os._exit(93)
                    worker_pid = json.loads((root / 'armed').read_text())['worker_pid']
                    until = time.monotonic() + 5
                    while time.monotonic() < until:
                        if watchdog.other_members(worker_pid):
                            break
                        time.sleep(.02)
                    else:
                        os._exit(96)
                    os.write(notify_w, b'R')
                    os.close(notify_w)
                    if os.read(trigger_r, 1) != b'X':
                        os._exit(94)
                    # Abrupt nonzero orchestrator failure: closes liveness pipe.
                    os._exit(37)
                except BaseException:
                    os._exit(95)
            os.close(notify_w)
            os.close(trigger_r)
            try:
                self.assertTrue(select.select([notify_r], [], [], 15)[0], 'release notification timeout')
                self.assertEqual(os.read(notify_r, 1), b'R')
                os.write(trigger_w, b'X')
                deadline = started + 20
                child, status = 0, None
                while not child and time.monotonic() < deadline:
                    child, status = os.waitpid(orchestrator, os.WNOHANG)
                    if not child:
                        time.sleep(.02)
                self.assertNotEqual(child, 0, 'orchestrator did not exit within bound')
                orchestrator = None
                self.assertTrue(os.WIFEXITED(status))
                self.assertEqual((child > 0, os.WEXITSTATUS(status)), (True, 37))
                result_path = root / 'armed.result'
                while not result_path.is_file() and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertTrue(result_path.is_file(), 'surviving watchdog did not finish')
                result = json.loads(result_path.read_text())
                self.assertEqual(result['status'], 'INCOMPLETE')
                self.assertTrue(result['released'])
                self.assertIn(result['reason'], ('supervisor_exit', 'supervisor_pipe_eof'))
                self.assertEqual(result['cleanup_errors'], [])
                self.assertEqual(result['worker_reaped_pid'], result['worker_pid'])
                self.assertEqual((root / 'wnowait_before_reap').read_text(), 'reserved and empty')
                for name in ('witness.json', 'completion_candidate.json', 'parent_witness.json', 'final_witness.json'):
                    self.assertFalse((root / name).exists(), name)
                self.assertLess(time.monotonic() - started, 20)
            finally:
                os.close(notify_r)
                os.close(trigger_w)
                if orchestrator is not None:
                    try:
                        os.kill(orchestrator, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    try:
                        os.waitpid(orchestrator, 0)
                    except ChildProcessError:
                        pass


if __name__ == '__main__':
    unittest.main()
