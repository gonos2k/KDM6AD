# Three ways to stop the division, and only two leave the rest of the model alone

The owner review asked for G1, G2 and G3 to be compared rather than for the
submitted patch to be assumed correct. Built as diagnostic arms by
`make_graupel_melt_arms.py` and run on the column that fails at the
OPERATIONAL step, `(100,142)`.

## All three remove the non-finite value

Records whose decoded payload is not finite, by call step:

| arm | 5 s | 10 s | 20 s | 30 s |
|---|---|---|---|---|
| `legacy` | 0 | 0 | **4** | **8** |
| `melt_g1` | 0 | 0 | **0** | **0** |
| `melt_g2` | 0 | 0 | **0** | **0** |
| `melt_g3` | 0 | 0 | **0** | **0** |

So the choice is not about whether the overflow goes.

## Only two leave the non-firing cells untouched

The same column at 5 s, where `0 < qg <= qcrmin` never occurs, digested over
every stage record:

| arm | digest | |
|---|---|---|
| `legacy` | `fee1d4187dba6f7c` | baseline |
| **`melt_g1`** | `fee1d4187dba6f7c` | **bitwise identical** |
| `melt_g2` | `27a8f80ca1576564` | **differs** |
| **`melt_g3`** | `fee1d4187dba6f7c` | **bitwise identical** |

**G2 changes cells the defect never reached.** It recomputes `rhox` wherever
`qg > 0 .and. brs > 0`, which overwrites the value `ProgB_param` already
produced -- so it is not a repair of the division, it is a change of density
policy. That fails the review's own criterion: cells where the threshold window
does not fire must be bitwise unchanged.

G1 and G3 both act only inside the window.

## What still separates G1 from G3

Both pass the containment test, and they do different physics in the window:

    G1  skips the melt entirely. Trace graupel stays as graupel; the latent
        heat and the rain-mass transfer are skipped with it.
    G3  lets the melt run and sets the volume to zero when the mass reaches
        zero. `pgmlt` is already capped at `-qg`, so in this window the melt is
        always complete: mass and latent heat move to rain, and no division
        happens because none is needed.

**G3 is the one that conserves what the melt was for.** G1 leaves `qg` and its
enthalpy where they were; G3 moves both, as the unguarded code intended, and
avoids the division by recognising that a complete melt has no partial volume to
compute.

That is an argument and not a measurement. This finding does not choose: it
establishes that G2 is out on containment, and that G1 and G3 differ in what
happens to trace graupel and its latent heat rather than in whether the crash
goes.

## Not measured here

Mass and enthalpy closure across the arms. The stage digest shows containment,
not conservation; the review asks for `Delta(qr+qg) = 0`,
`Delta H_latent = 0` and `qg = rho_g * b_g` on the failing columns, and those
are not computed in this finding.

Whether G3's zeroing is right when `pgmlt` does NOT take its cap. In the
measured window it always does -- post-melt `qg` is exactly `0.0` -- but the
branch is written for the general case and that case is untested here.

One column, one host, f32, the deployed revision. The arms are diagnostic and
none is proposed as the release fix; the freeze-lift request says the same.
