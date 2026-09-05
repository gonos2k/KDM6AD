"""Run the driver's density-arm matrix. RUN role, on purpose (owner review §8).

The arm streams are raw run content: they are published into the bundle,
digested, and carried by `run_content_id`. The code that produced them lived
inside `g33_metric_trajectory` -- an analysis seed, cut from the producer's
dispatch edges -- so the run RECIPE did not pin the module whose logic decided
what those streams were. A recipe that does not cover the code that made its
own content answers "was this the same experiment" with only part of the
experiment.

So the orchestration lives here, imported by the producer DIRECTLY rather
than through the analysis dispatch, which puts this module in the run role of
the derived graph. `g33_metric_trajectory` keeps the analysis: it reads the
streams this module collected and never runs the driver itself.
"""
from __future__ import annotations

import subprocess

#: `offset+/-` shifts every level by the same constant, preserving each density
#: gap while moving the absolute density. In the metric counterfactual the
#: offset changes the residual by c*sum(dz_lo*dn_in - dz_up*dn_out), so it
#: cancels only when the paired transfers balance in that measure. This
#: separates gradient sensitivity from absolute-density sensitivity on the
#: captured fixture without asserting that an offset always cancels (owner §7).
ARMS = ("as-is", "uniform", "inverted", "x2", "offset+", "offset-")


def declared_arm(stream: str) -> str:
    """The arm the STREAM says it is, read back from its own header."""
    for ln in stream.splitlines():
        if ln.startswith("G33N STREAM_BEGIN"):
            return ln.split()[-1]
    return "?"


def collect(driver: str, nsplit: int, *, mode: str = "rezero", width: int = 3,
            baseline_stream: str | None = None) -> dict:
    """{arm: stdout} for every arm, refusing any stream that is not the run
    it was asked for.

    `baseline_stream` lets the caller supply the bundle's OWN stored as-is
    member instead of a fresh run of it (owner §4): re-running the baseline
    meant the decomposition compared against a stream nobody kept, so the
    published member and the analysis baseline were only *probably* identical.
    Validated FIRST -- it costs nothing and a wrong one would otherwise be
    discovered after five driver runs.
    """
    if baseline_stream is not None:
        got = declared_arm(baseline_stream)
        if got != "as-is":
            raise SystemExit(
                f"the supplied baseline stream declares arm {got!r}, not 'as-is'")

    def run(arm):
        argv = [driver, str(nsplit), mode, str(width), arm]
        r = subprocess.run(argv, capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(f"{arm}: driver exited {r.returncode}\n{r.stderr[-2000:]}")
        got = declared_arm(r.stdout)
        # REQUESTED must equal DECLARED (owner §13.1). Recording both and
        # leaving a reviewer to notice the mismatch in the JSON is not a
        # check: a stream that ran the wrong forcing would still be published,
        # and every number derived from it would be attributed to an arm it
        # is not.
        if got != arm:
            raise SystemExit(
                f"asked the driver for arm {arm!r} and its stream declares "
                f"{got!r} — refusing to attribute this run to {arm!r}")
        return r.stdout

    raw = {a: run(a) for a in ARMS if a != "as-is" or baseline_stream is None}
    if baseline_stream is not None:
        raw["as-is"] = baseline_stream
    return raw
