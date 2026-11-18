import importlib.util
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("ci_timing", HERE / "ci_timing.py")
timing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(timing)


class CITimingTest(unittest.TestCase):
    def test_archived_run_summary(self):
        saved = json.loads((HERE / "ci_timing.json").read_text())
        self.assertEqual(timing.analyze(), saved)
        self.assertEqual(saved["evidence_modes"]["normal"]["suite_count"], 49)
        self.assertEqual(saved["evidence_modes"]["optimized"]["suite_count"], 49)

    def test_missing_or_duplicate_suite_fails(self):
        log, _, _ = timing.load_run("oracle")
        lines = log.splitlines()
        command_lines = [i for i, line in enumerate(lines)
                         if "unittest (QNICE evidence, normal)" in line
                         and timing.COMMAND.search(timing.ANSI.sub("", line))
                         and "##[group]Run" not in line]
        self.assertEqual(len(command_lines), 49)
        missing = lines.copy()
        del missing[command_lines[-1]]
        with self.assertRaisesRegex(ValueError, "suite inventory"):
            timing.evidence_mode("\n".join(missing), "normal")
        duplicate = lines.copy()
        duplicate[command_lines[1]] = duplicate[command_lines[0]]
        with self.assertRaisesRegex(ValueError, "duplicate suite"):
            timing.evidence_mode("\n".join(duplicate), "normal")


if __name__ == "__main__":
    unittest.main()
