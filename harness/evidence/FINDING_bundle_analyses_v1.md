# The bundle now produces the analyses, and the first thing they did was correct a published number

<!-- claim-status: generated from CLAIMS.yaml, do not edit -->

| claim | status | grade | scope |
|---|---|---|---|
| `G33-CHAIN-002` | **active** | confirmed | g33_fixture_multisubcycle_v1, legacy, h = 25 s for the numbers. The bundle change applies to future --nflux bundles and does not retrofit the ones already published. |

Statuses above are the authority; prose below may predate them.
<!-- /claim-status -->

Owner §14 priority-4. A bundle pinned its raw streams and its build; the tables a
claim quotes came from analyses that ran somewhere else and left nothing behind.
So "the run is pinned" stopped one step short of the number being cited.

## What the bundle carries now

Every `--nflux` member gets three analyses, written into the bundle and digested
into its manifest:

| analysis | what it records |
|---|---|
| `matched_closure` | the mass/number closure, per row, with the per-call control |
| `cap_interface` | departure vs arrival per interface, and the cap's share |
| `extension_protocol` | what the stream actually carried, as the strict parser saw it |

Each entry pins **two** digests — the output and its **analyzer**:

```json
{"file": "n12.rezero.cap_interface.json", "analysis": "cap_interface",
 "sha256": "015b3f36289c1d02…", "analyzer": "harness/g33_cap_interface.py",
 "analyzer_sha256": "794375906007…"}
```

With only the first, a reader can check the table has not changed but cannot
re-derive it. `g33_evidence_chain.py` follows a pinned manifest through to these,
so a claim pinning one manifest now reaches the raw streams *and* the analyses.

`extension_protocol` is deliberately not a restatement of the header: the header
**declares** features, this records how many records of each family **survived
validation**, so a reader can tell a complete extension stream from a header that
merely claimed one.

## The correction

`cap_interface` reproduces every published figure — 100.00% of the ice mass
residual explained, ratios −28.58 / −28.90 on ice and **1.0000** on all three
main columns, 255 interfaces — which is the test that its interface pairing is
the one the finding describes. It disagreed on exactly one:

> ~~It binds at 39 of 255 interfaces, all of them in the ice chain~~

| chain | mass departure ≠ arrival | **number** departure ≠ arrival | total \|interface term\| |
|---|---|---|---|
| ice | **39 of 108** | **39 of 108** | 8.63e−03 |
| main | **23 of 147** | **0 of 147** | **2.70e−11** |

**A second correction (owner §10):** `cap_bound` compared only `dq`, so a figure
quoted as "cap-bound interfaces" silently meant the **mass** cap. The two are not
the same set, and the difference matters: on the main chain the **number**
departure and arrival never differ, which is exactly why its number result is a
clean measure-mismatch measurement rather than a cap measurement. A single count
could not say that. The fields are now `mass_departure_arrival_differ`,
`number_departure_arrival_differ` and `either_differ` — named for what is
compared, since "cap-bound" also overstates an exact inequality that a
roundoff-scale difference satisfies.

The ice count of 39 is right. **"All of them in the ice chain" is not** — the
main chain's departure and arrival differ at 23 interfaces too. The error came
from counting without magnitude: a bare count makes a roundoff-scale difference
and a residual-dominating one the same event.

The conclusion is unchanged and better supported. The main chain's interface term
is **eight orders of magnitude** below ice's, and that is *why* its mass residual
sits at 1e-10–1e-12 — not because nothing happens there. The tool now reports the
count beside the magnitude, and a test requires the main-chain count to be
non-zero, so the withdrawn phrasing cannot come back.

## Limits

- **Three analyses, not all of them.** The water budget, the enthalpy ledger and
  the refinement orders still run outside any bundle. These three were chosen
  because they read the extension records the `--nflux` arm exists to produce.
- **Only `--nflux` bundles.** The analyses all read extension records, so running
  them on a plain bundle would put empty tables in the manifest and make an
  uninstrumented bundle look analysed.
- **A digest is an identity, not a validation.** It says the table is the one the
  claim was written against, and that the code named is the code that produced
  it. It does not say the analysis is correct — that is what the tests against
  the published figures are for.
- **The already-published bundles have no analyses.** This changes what future
  bundles carry; it does not retrofit the ones already in
  `~/kdm6ad-g33m-refine`, and `g33_evidence_chain.py` reports them as carrying
  none rather than pretending otherwise.
