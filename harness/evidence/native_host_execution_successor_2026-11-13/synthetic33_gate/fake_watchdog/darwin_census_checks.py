"""Explicit Darwin census checks, using injected process providers only."""

import importlib.util
import os
import py_compile
import struct
import hashlib
import tempfile
from unittest.mock import patch
import unittest
from types import SimpleNamespace
from pathlib import Path

PATH = Path(__file__).resolve().parent.parent / "darwin_census_provider.py"
spec = importlib.util.spec_from_file_location("darwin_census_provider", PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Fake:
    def __init__(self):
        self.pids = [100, 101]
        self.state = "alive"
        self.rows = {100: (10, 100, 1024), 101: (11, 100, 2048)}

    def list_group(self, pgid, capacity):
        return len(self.pids) * 4, list(self.pids)

    def inspect(self, pid):
        return self.rows[pid]


def request(fake):
    return {
        "leader_pid": 100,
        "leader_start": 10,
        "leader_state": fake.state,
        "request_id": "sample-1",
    }


class CensusChecks(unittest.TestCase):
    def test_stable_and_reserved_leader(self):
        f = Fake()
        self.assertEqual(
            m.sample_group(f, request(f), 10, clock=lambda: 1)["rss_bytes"], 3072
        )
        f.state = "exited_reserved"
        del f.rows[100]
        result = m.sample_group(f, request(f), 10, clock=lambda: 1)
        self.assertEqual(result["rss_bytes"], 2048)
        self.assertEqual(result["policy"], "SAMPLED_STOP_THRESHOLD")

    def test_buffer_failures_and_growth(self):
        def good(group, cap):
            return (min(cap, 3) * 4, [100, 101, 102][:cap])

        self.assertEqual(
            m.read_group(good, 100, 10, clock=lambda: 1, initial=2, maximum=8),
            (100, 101, 102),
        )
        bad = [(3, [100]), (8, [100]), (8, [100, 100]), (4, [101]), (4, [0]), (-1, [])]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(m.CensusError):
                m.read_group(lambda group, cap: value, 100, 10, clock=lambda: 1)
        with self.assertRaises(m.CensusError):
            m.read_group(
                lambda group, cap: (cap * 4, list(range(100, 100 + cap))),
                100,
                10,
                clock=lambda: 1,
                initial=2,
                maximum=2,
            )

    def test_churn_identity_and_permission_failures(self):
        f = Fake()
        original = f.list_group
        calls = [0]

        def changed(group, capacity):
            calls[0] += 1
            return original(group, capacity) if calls[0] == 1 else (4, [100])

        f.list_group = changed
        with self.assertRaises(m.CensusError):
            m.sample_group(f, request(f), 10, clock=lambda: 1)
        for row in ((11, 999, 2048), (11, 100, -1), (12, 100, 2048)):
            f = Fake()
            if row[0] == 12:
                calls = [0]

                def inspect(pid):
                    calls[0] += 1
                    return row if pid == 101 and calls[0] > 2 else f.rows[pid]

                f.inspect = inspect
            else:
                f.rows[101] = row
            with self.assertRaises(m.CensusError):
                m.sample_group(f, request(f), 10, clock=lambda: 1)
        f = Fake()

        def denied(pid):
            raise PermissionError("denied")

        f.inspect = denied
        with self.assertRaises(PermissionError):
            m.sample_group(f, request(f), 10, clock=lambda: 1)

    def test_same_pid_and_group_reuse_during_inspect_is_rejected(self):
        current = {100: 10.0, 101: 11.0}
        reuse = [True]

        class CachedProcess:
            def __init__(self, pid):
                self.pid = pid
                # Simulate psutil 5.9.4's per-Process cached create_time.
                self.cached_start = current[pid]

            def status(self):
                return 'running'

            def create_time(self):
                return self.cached_start

            def memory_info(self):
                if self.pid == 101 and reuse[0]:
                    current[101] = 12.0
                    reuse[0] = False
                return SimpleNamespace(rss=1024 if self.pid == 100 else 2048)

        provider = m.DarwinProvider.__new__(m.DarwinProvider)
        provider.psutil = SimpleNamespace(Process=CachedProcess, STATUS_ZOMBIE='zombie')
        provider.list_group = lambda group, capacity: (8, [100, 101])
        with patch.object(m.os, 'getpgid', return_value=100):
            with self.assertRaisesRegex(m.CensusError, 'inspect race'):
                m.sample_group(provider, request(Fake()), 10, clock=lambda: 1)
            # On stable identities both observations still use sampled RSS.
            self.assertEqual(m.sample_group(provider, request(Fake()), 10, clock=lambda: 1)['rss_bytes'], 3072)

    def test_package_inventory_precheck(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp).resolve() / "psutil"
            package.mkdir()
            (package / "__init__.py").write_text("harmless")
            manifest = {
                "__init__.py": hashlib.sha256(
                    (package / "__init__.py").read_bytes()
                ).hexdigest()
            }
            with patch.object(m, "PSUTIL_SHA256", manifest):
                self.assertEqual(m.verify_package(package, manifest), manifest)
                (package / "extra.py").write_text("untrusted")
                with self.assertRaises(m.CensusError):
                    m.verify_package(package, manifest)

    def test_cached_bytecode_and_symlinks_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp).resolve() / "psutil"
            package.mkdir()
            source = package / "__init__.py"
            source.write_text("safe = 1\n")
            original_stat = source.stat()
            manifest = {"__init__.py": hashlib.sha256(source.read_bytes()).hexdigest()}
            with patch.object(m, "PSUTIL_SHA256", manifest):
                # Compile different code with the same size and timestamp as the
                # pinned source, then restore the source while retaining its mtime.
                source.write_text("evil = 1\n")
                os.utime(
                    source, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns)
                )
                pyc = Path(py_compile.compile(str(source), doraise=True))
                source.write_text("safe = 1\n")
                os.utime(
                    source, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns)
                )
                header = pyc.read_bytes()
                self.assertEqual(
                    struct.unpack_from("<I", header, 8)[0], int(source.stat().st_mtime)
                )
                self.assertEqual(
                    struct.unpack_from("<I", header, 12)[0], source.stat().st_size
                )
                with self.assertRaises(m.CensusError):
                    m.verify_package(package, manifest)
                pyc.unlink()
                pyc.parent.rmdir()
                (package / "linked_dir").symlink_to(package, target_is_directory=True)
                with self.assertRaises(m.CensusError):
                    m.verify_package(package, manifest)
                (package / "linked_dir").unlink()
                (package / "linked_file").symlink_to(source)
                with self.assertRaises(m.CensusError):
                    m.verify_package(package, manifest)

    def test_deadline_and_lost_reservation(self):
        f = Fake()
        with self.assertRaises(m.CensusError):
            m.sample_group(f, request(f), 1, clock=lambda: 1)
        f.state = "unknown"
        with self.assertRaises(m.CensusError):
            m.sample_group(f, request(f), 10, clock=lambda: 1)
        f = Fake()
        f.pids = [101]
        with self.assertRaises(m.CensusError):
            m.sample_group(f, request(f), 10, clock=lambda: 1)


if __name__ == "__main__":
    unittest.main()
