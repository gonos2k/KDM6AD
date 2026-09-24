# X4: physical population and validity-state declarations

The prior G3 `classify_volume_moments` checks a caller-declared C/N pair.
This pilot adds a narrow adapter that requires the two inputs to name the
**same population and phase**, distinguish mass from number, and declare
volume-basis units `kg/m3` and `#/m3`. It passes species-specific floors and
mean-particle-mass bounds to the existing classifier. For example, cloud-drop
mass paired with dry-aerosol number is rejected even if the arrays have the
same shape and finite values. No physical host number-basis conversion is
selected by this adapter.

Producer output and observation support are separate classifications:

| Producer state | Meaning |
| --- | --- |
| `valid_zero` | The active, defined physical output is exactly zero |
| `inactive` | This process did not produce an active value; its slot is not read |
| `undefined` | The process is active but the output is not defined; its slot is not read |
| `inadmissible` | The defined value is nonfinite or outside declared bounds |
| `conditional_valid` | Finite in range under an explicit unresolved assumption |

For an assumption-labeled sample, the conditional status takes precedence;
an exact numeric zero remains available as separate metadata and is not
silently promoted to unconditional `valid_zero`.

Observation `missing_observation`, `quality_rejected` and `accepted` are
classified independently. A missing or QC-rejected observation is not turned
into a zero-value observation, and its value field is not inspected. This
prevents the empty-mask/zero-cost confusion from becoming a generic validity
rule. The local sample helper is not a replacement for the project's RTTOV QC.

For a declared nonnegative-diameter population with volume moments M0/M1/M2,
the pilot additionally checks the **necessary** inequality `M0*M2 >= M1²`.
The synthetic positive triple `(1,2,1)` fails despite all components being
positive. Passing this one condition does not construct or certify a full
particle-size distribution. A distribution ID is required and tied to the
same population/phase; higher-moment checks are not applied to unrelated
quantities. The exact integer comparison is exact for the **stored binary64
inputs**, not a bound on measurement or model uncertainty.

Eight new tests and seven retained moment-validity tests passed locally
(`15/15`, Python 3.10.11) with warnings treated as errors. They include
unreadable inactive/undefined producer slots, missing/rejected observations,
mixed-population/phase/unit refusal, conditional number-basis labeling and
exact binary-rational M0/M1/M2 comparison, including underflow, overflow and
near-equal rounded products. Consumed boolean payloads cannot become numeric
1 or 0, and masked arrays cannot silently lose their missing-data mask during
`np.asarray` conversion. All examples are synthetic or public Python
contract checks. The native Fortran conditional `INTENT(OUT)` behavior,
physical number basis, operational accepted states and actual observation
support remain separate open items; no production physics or ABI changed.
