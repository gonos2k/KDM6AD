# Domain runner CLI output protection

The PR #438 review reproduced an input clobber: `--plan-json` could equal the
manifest or another existing file, and both dry-run and execution CLI branches
used `write_text`. The fix rejects unsafe paths before dispatch and reuses the
existing atomic `_publish_json_noclobber` publisher in both branches.

The report must be a fresh file outside the run output tree. Existing regular
files, directories, hardlinks and final symlinks (including dangling ones) are
refused. Parent symlinks are resolved, and the admitted canonical report path
is retained for publication. Case aliases are conservatively treated alike on
all platforms. The run directory and report must not overlap any manifest,
executable or source-chunk file path in either direction, including a currently
missing reserved source filename. A late destination creation fails without
modifying the new owner's bytes, and temporary publication files are removed.

Successful stdout behavior and new external report creation remain available.
Existing reports cannot be replaced, including on resume. No force-overwrite
option was introduced. A later parent-directory replacement is not a directory-FD
sandbox contract; the final exclusive publication still cannot replace an
existing destination. The tests distinguish canonical parent-alias resolution
from leaf-file creation races.

Validation uses temporary files, fake plan admission and a fake executor; no
KDM, native host, optimization or RTTOV call is necessary. Regression cases
cover dry/executed reports over manifest/tool/chunk/artifacts, hardlinks and
symlinks, future chunk-output names, output-tree aliases/ancestors, missing
source names/descendants, protected run directories, safe publication,
canonical parent retargeting, non-directory parents and a late leaf race.

The completed four-arm 516-call experiment and four pilot calls are preserved.
No scientific arrays, compiled physics, operational defaults or installed
libraries changed. The original reviewed helper hashes remain in the campaign
manifest's source history; its current reviewed-source pins advance to the
protected CLI and tests. The archived executed runner snapshot remains intact.
This is provenance maintenance, not a new experiment or derivative certificate.

Green/Red independently reviewed the path rules and counterexamples. Red's
missing-source-descendant counterexample was reproduced and closed. See
`validation.json` for checks and `manifest.json` for source/artifact hashes.
