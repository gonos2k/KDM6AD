# RTTOV actual extinction diagnostic

The saved profile reproduces the Delta Eddington warning in RTTOV channel IDs 8 and 9. The new isolated instrumented build identifies the exact internal layers and confirms that this case’s hydrometeor contribution is zero. It also shows why the earlier hydrostatic proxy was only suggestive: RTTOV’s measured triggering layers are the bottom three thin layers in its 66-layer profile.

| RTTOV channel | RTTOV layer (1-based) | Pressure interfaces (hPa) | `ltick` (km) | Total extinction before clip (km⁻¹) | After clip (km⁻¹) |
|---|---:|---:|---:|---:|---:|
| 8 | 65 | 992.796875–1000.438047 | 0.067785523 | 32.839162969 | 20 |
| 8 | 66 | 1000.438047–1006.420469 | 0.052836564 | 38.407032752 | 20 |
| 9 | 64 | 983.138281–992.796875 | 0.086209425 | 20.147651516 | 20 |
| 9 | 65 | 992.796875–1000.438047 | 0.067785523 | 21.684010584 | 20 |
| 9 | 66 | 1000.438047–1006.420469 | 0.052836564 | 22.595689756 | 20 |

The source captures `ltick`, the clear-sky base extinction, and each hydrometeor-category total immediately before and after the RTTOV clip. Category 0 and category 1 match exactly for every channel and layer; the saved profile’s hydrometeor contents and fractions are zero. The values therefore show that gas optical depth accounts for these warnings in this profile. “Gas” here means the aggregate clear-sky gas path; the data do not separate individual gases.

Two calls were captured. Call 1 is the test driver's explicit forward call; call 2 is the forward pass invoked from the K calculation. Both call traces have identical extinction values. The instrumented log reports warning slots 1 and 2; the saved `channels.txt` order maps those slots to requested RTTOV channel IDs 8 and 9. The retained quality values are `[32768,32768,0,0,0,0,0,0,0]`, consistent with bit 15. The clipped threshold is 20 km⁻¹.

The recorded clear-sky base is after the source's minimum extinction floor
`MAX(base,min_ext_delta_edd)` (1e-10 km⁻¹), while PRECLIP refers to the later
maximum cap of 20 km⁻¹. Some non-triggering rows equal the floor; their unfloored
bases and sub-floor components were not recorded. Every reported trigger value
is above 20 km⁻¹ and is unaffected by the minimum floor. The diagnostic does
not claim a raw unfloored clear-sky base for every layer.

The untouched original executable was run first on the same saved profile. Its direct and K numerical outputs match the retained case byte-for-byte. The instrumented build also matches those direct and K outputs byte-for-byte, including radiance, transmission, and K profiles. Only the runtime log text differs. This demonstrates numerical noninterference for this one saved profile and these outputs.

The repository’s RTTOV ASCII parser was also applied to the original and instrumented direct/K products. Parsed brightness temperatures, quality flags, reflectance, and all `profiles_k` fields compare exactly.

The private source copy, small rebuilt object/library, instrumented executable, build logs, and full layer dump are held under the ignored `graphify-out/pr390-local/rttov/` path. The tracked evidence contains the original-run receipt and derived numerical summary only. The build recompiled only `rttov_eddington_setup.o`, re-archived its RTTOV main static library, and relinked the test executable. All other object files are hash-identical to the installed build. The original source, executable, coefficients, hydrotable, and saved case were left unchanged.

The official [NWP SAF licence agreement](https://nwp-saf.eumetsat.int/site/software/licence-agreement/) grants use within the licensee’s organisation, limits further rights to use, prohibits redistribution, and retains EUMETSAT’s IP. The agreement does not expressly prohibit private source modifications; the user authorized this local diagnostic. No RTTOV source, patch, object, executable, coefficient, or hydrotable is included in tracked evidence or published. See `license_assessment.json` and `actual_extinction_profile_summary.json`.

The parent native forecast packet remains invalid (`experiment_valid=false`, runner exit code 1). This one-profile RTTOV rerun does not change native-run validity, attribution for other profiles, or physics approval. The diagnostic applies only to this profile with aerosols disabled and zero hydrometeor content.
