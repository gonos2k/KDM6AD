# Native model levels with scene-anchor GK2A viewing geometry

## Scope and provenance

Column 45577 and its 39 native layers / 40 interfaces are unchanged. This run uses the existing local same-slot FD file spacecraft **centre-pixel ECEF anchor** to derive the target model-column view. It does not claim exact KO pixel acquisition timing or per-pixel measured viewing angles. No external model or reanalysis inputs are used. The earlier explicit-pressure experiment remains separate evidence.

FD input SHA256: `40cb7ace877a65661be317476ce09589fe7597a1903c8ff51ae93ca4e7079de4`. Local retained Satpy `get_orbital_parameters()` interprets this centre anchor as Earth-centred Earth-fixed metres. Ellipsoid axes come from the FD file. The observer is the same model latitude/longitude/height, not a replacement observation location.

ECEF target position computed analytically agrees exactly with pyproj for this input. Satellite-minus-observer vector is projected onto ellipsoidal local east/north/up; zenith is atan2(horizontal, up), and azimuth is atan2(east, north), clockwise from north. This matches the local RTTOV satellite-angle utility convention. No interpolation between spacecraft anchors is used.

| Anchor | Zenith (degrees) | Azimuth (degrees) |
| --- | ---: | ---: |
| first | 46.727255588833 | 182.615592888228 |
| center | 46.726926305122 | 182.615009780825 |
| last | 46.726582754176 | 182.614396557966 |

The centre anchor is used in all ten evaluations, serialized as 46.726926 / 182.615010 degrees by the existing six-decimal geometry writer. The first/last spread is descriptive, **not an uncertainty bound** or an exact target-pixel navigation solution. FD scene acquisition begins at 00:00:33; nominal slot UTC and the previous solar calculation remain fixed. KO is regridded and lacks an individual navigation vector. Those timing/representativeness limitations remain open.

## Executed first-order results

Same initial state, 20 s KDM integration, controls, epsilon=.03/.1, observations, sigma=1 K, Huber delta=1, bias=0, pressure files, surface fields and background-gas assumptions are retained. Only satellite zenith/azimuth differ from the earlier experiment. Seven usable IR channels remain; WV063/WV069 quality32768 are still excluded. Masks, quality arrays and tapped branches match within all pairs, with no QC relaxation.

| Control | Cost VJP | Cost JVP | Maximum cost FD relative difference |
| --- | ---: | ---: | ---: |
| deposition | -0.013383672296319385 | -0.013383672296319402 | 0.527615% |
| riming | -1.320111241504018e-05 | -1.3201112415040182e-05 | 0.126333% |

The unchanged 5% rule passes at both widths. Channel-wise reverse gradients are obtained from each BT output separately; genuine forward AD is contracted with the baseline K. Direct finite differences rerun RTTOV. All 16 channels are retained in the artifact, including excluded/unused channels; the following table covers the seven jointly usable channels.

| Channel | Deposition VJP (K/control) | Max FD difference | Riming VJP (K/control) | Max FD difference |
| --- | ---: | ---: | ---: | ---: |
| WV073 | -0.00245640739274 | 0.038297% | -2.98073750958e-07 | 0.646217% |
| IR087 | -0.00279352834192 | 0.553005% | -3.12252646762e-06 | 0.187656% |
| IR096 | -0.0020099654514 | 0.512220% | -2.11987242181e-06 | 0.634995% |
| IR105 | -0.00345225033039 | 0.510546% | -3.58905206528e-06 | 0.305032% |
| IR112 | -0.0036638754582 | 0.521864% | -3.53344175547e-06 | 0.185607% |
| IR123 | -0.00413193348651 | 0.439588% | -3.29408195695e-06 | 0.326291% |
| IR133 | -0.00401363804623 | 0.268785% | -2.19201392146e-06 | 0.364345% |

Every listed channel exceeds its BT-text spacing threshold at both widths and meets the same 5% relative criterion. Maximum absolute channel JVP–VJP differences are 1.39e-17 and 8.48e-22 respectively. Small observed errors remain subject to the retained text-output spacing and truncation limits; they are not total radiative accuracy guarantees.

## Reproduction and remaining scope

Local artifacts are `graphify-out/pr221-view/derive_view.py`, `view_geometry.json`, `run_native_view_aux.py`, `native_view_aux.json`, and the ten raw case directories named in the JSON. The wrapper reuses the retained actual-column runner; all applied auxiliary and pressure files have identical hashes across paired evaluations. Model-top extrapolation, coefficient background gases and the P8W bottom are unchanged. This is one column, two controls, and two widths, not ten independent atmospheric cases.

Live JSON SHA256: `2974a251dd2ce295e578f01323e730323fdf37536b0ad946a1157f02caf8cdc5`.

Exact pixel-time navigation, upper/bottom-boundary sensitivity, representative processes/columns, particle-number unit reconciliation, nonzero applied transport and timestep convergence remain open. This experiment reduces the arbitrary 45/0 view assumption using recorded spacecraft metadata, but does not close those broader items.
