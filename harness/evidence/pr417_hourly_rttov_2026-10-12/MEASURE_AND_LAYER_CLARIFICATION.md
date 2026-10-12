# PR416 saved-column measure and layer clarification

This note corrects interpretation of the already saved PR416 `PROFILE.csv`; it does not reread forecast data or recompute a native column. The hourly states are three saved endpoints, not a continuous trajectory.

The PR416 hydrometeor column diagnostic is geometric EOS mass weighting:

`M_QCLOUD = Σ_k QCLOUD_k × rho_d,k × delz_k`.

Here `rho_d` is the selected-frame dry-air density and `delz` is the height thickness derived from saved geopotential interfaces. This is distinct from the WRF eta-layer host dry-air mass weight used in the older local-analysis path. These two weight definitions must not be conflated. The CSV-based QCLOUD column values are 0.007922 kg/m² at 05:00, 0.002475 kg/m² at 06:00, and zero at 07:00; QRAIN is `1.322×10⁻⁵ kg/m²` at 05:00 and zero later. They are snapshots, not fluxes or process rates.

QCLOUD is present only at model level `k=3`, spanning 204.61–312.19 m at 05:00 and 204.79–312.47 m at 06:00; no level has QCLOUD at 07:00. At `k=3`, temperature warms by 0.18098 K from 05:00 to 06:00 and 0.41317 K from 06:00 to 07:00. QVAPOR rises by `1.9824×10⁻⁴` and `2.7720×10⁻⁵ kg/kg`; total water mixing ratio `QVAPOR + QCLOUD + QRAIN + QICE + QSNOW + QGRAUP` rises by `1.5319×10⁻⁴` and `7.2698×10⁻⁶ kg/kg` at that level.

The largest profile cooling is outside this shallow liquid layer: the minimum temperature change from 05:00 to 06:00 is −2.52244 K at `k=37`, whose centers are 20,001.82 m and 19,995.98 m; from 06:00 to 07:00 it is −0.89066 K at `k=31`, whose centers are 16,229.68 m and 16,230.86 m. Thus the largest cooling is aloft, not within the QCLOUD-bearing level, which warms in both intervals. Do not describe the QCLOUD-layer change as cooling or treat the profile-wide cooling minimum as a cloud-layer response.

These values do not establish a closed water or energy budget, physical flux conservation, cloud truth, or process attribution. No layer flux terms are present in this CSV-only comparison. The raw number-concentration basis has not been independently revalidated here; this correction does not make a new claim about number-moment units or process behavior.
