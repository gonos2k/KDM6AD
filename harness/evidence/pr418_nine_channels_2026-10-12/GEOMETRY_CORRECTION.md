# Additive correction to the frozen PR417 geometry description

Applies to PR417 as merged in main `b07af3fe`. Original PLAN, hash registries,
BT, profiles, scripts and reports are preserved byte for byte. This correction
supersedes their descriptions of the **viewing calculation point** only.

The actual call to `ami_geometry` supplied the native column centre:
`(36.195343017578125 N, 122.0966796875 E)`, j103/i48. Both snapshots use
this same centre for viewing angles. Elevation is the native HGT in kilometres.
The saved geometry has zenith 42.4723210482 degrees and azimuth
169.7285056849 degrees. The function's old `ami_pixel_lat_lon` key actually
holds these native-centre coordinates for this caller; its text “computed at
AMI pixel center” is incorrect for this execution.

The original AMI pixel row289/column49 at
`(36.19700231203294 N, 122.09240151533507 E)` supplies a separate navigation
reference/distance donor. AMI GEOS satellite/ellipsoid constants were used
at the native centre. The pixel location was not the viewing-angle calculation
point. These two locations must remain separate in new metadata.

The shared native-centre rule leaves the recorded two-time comparison intact.
No H re-evaluation or angle perturbation was made for this correction; the BT
effect of choosing the pixel centre instead has not been measured. A new
observational matchup must declare pixel-centre geometry or a native-centre
approximation before inspecting residuals.

The added-channel execution retains exactly the original native-centre angles,
and records `viewing_geometry_calculation_point` independently of
`AMI_navigation_donor`. No observation fit or causal attribution is added.
