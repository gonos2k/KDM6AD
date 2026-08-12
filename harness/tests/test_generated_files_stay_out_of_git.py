"""A test that renders into the repo must not be able to leave a trace in git.

`_run` in test_g33_column_separability renders a fixture INTO the working tree
-- the build selects a module by NAME from its own directory, so it has to sit
beside the committed ones -- and unlinks it in a `finally`. A KILLED run never
reaches that finally.

The orphan then makes the tree dirty, and every producer that refuses to build
a bundle from a dirty tree errors. It cost a full gate as 309 errors that
reproduced in no single file, because in isolation the orphan was not there.
Then `git add -A`, run while a suite was mid-render, committed it -- and once
TRACKED, the test's own cleanup read as a deletion, so the tree was dirty
whether the test had run or not (Codex).

These checks live HERE, not beside the test that renders the file, because that
module is `skipif`-ed on gfortran and the gitignored host reference -- so in CI,
the one place where committing a stray file matters most, it never runs.
"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: (directory, glob) for every file a test renders into the repo.
GENERATED = (
    ("harness/g33_fortran", "g33_fixture_permtest_*.f90"),
    ("harness/g33_overlay", "g33_fixture_permtest_*.h"),
)


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                          text=True).stdout


def test_no_generated_fixture_is_TRACKED():
    """Nothing rendered per-run belongs in the index."""
    tracked = _git("ls-files", *(f"{d}/{g}" for d, g in GENERATED)).split()
    assert not tracked, (
        f"generated fixtures are in the index: {tracked}. They are rendered per "
        f"run and unlinked in a `finally`, so tracking one turns its own "
        f"cleanup into a deletion that the dirty-tree guards then refuse")


def test_an_ORPHANED_generated_file_leaves_the_tree_CLEAN():
    """The actual prevention, and the failure this reproduces.

    Checking only that nothing is TRACKED would not have stopped any of it: the
    309 errors came from an UNTRACKED orphan. What makes an orphan inert is the
    ignore rule, so that is what gets asserted -- by leaving one behind exactly
    as a killed run does, and reading `git status` the way the producers do.
    """
    made = []
    try:
        for d, glob in GENERATED:
            p = ROOT / d / glob.replace("*", "orphanprobe")
            p.write_text("! left behind by a killed run\n")
            made.append(p)
            assert _git("check-ignore", str(p)).strip(), \
                f"{p.relative_to(ROOT)} is not ignored -- an orphan here " \
                f"dirties the tree for every bundle producer"
        # The ORPHAN must not appear -- not "the tree is clean", which would
        # only pass on a tree with no work in progress and so would fail for a
        # reason having nothing to do with what this guards.
        status = _git("status", "--porcelain")
        seen = [ln for ln in status.splitlines()
                if any(p.name in ln for p in made)]
        assert not seen, (
            f"an orphaned generated file made the working tree dirty: {seen}")
    finally:
        for p in made:
            p.unlink(missing_ok=True)
