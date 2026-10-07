#!/usr/bin/env python3
"""Static nuisance snapshot comparison only; no KDM/RTTOV execution."""
import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path
import numpy as np
import torch
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "oracle"))
from kdm6.da_fulldomain import _freeze_fixed_obs_errors
BASELINE = "a4566024e25fe23d6e72fc73e14301cd0e5fbe7e"
source = subprocess.check_output(
    ["git", "show", BASELINE + ":oracle/kdm6/da_fulldomain.py"], cwd=ROOT, text=True)
function = next(n for n in ast.parse(source).body
                if isinstance(n, ast.FunctionDef) and n.name == "_freeze_fixed_obs_errors")
namespace = {"torch": torch}
exec(compile(ast.Module(body=[function], type_ignores=[]),
             "<original baseline function>", "exec"), namespace)
previous = namespace["_freeze_fixed_obs_errors"]
target = torch.zeros((2, 3), dtype=torch.float64)
scales = [None, 1., .1, [1., 2., 3.],
          np.array([.5, 1.5, 2.5], dtype=np.float32),
          torch.tensor([1., 2., 3.], dtype=torch.float64)]
biases = [None, 0., -.1, [.2, -.3, .4],
          np.array([[.1, -.2, .3], [.4, -.5, .6]], dtype=np.float32),
          torch.zeros((2, 3), dtype=torch.float64)]
checked = 0
for scale in scales:
    for bias in biases:
        old = previous(target, scale, bias)
        new = _freeze_fixed_obs_errors(target, scale, bias)
        for before, after in zip(old, new):
            if before is None:
                if after is not None:
                    raise RuntimeError("default snapshot changed")
            elif not torch.equal(before.view(torch.int64), after.view(torch.int64)):
                raise RuntimeError("numeric snapshot bits changed")
        checked += 1
print(json.dumps(dict(baseline=BASELINE,
    baseline_file_sha256=hashlib.sha256(source.encode()).hexdigest(),
    current_file_sha256=hashlib.sha256((ROOT / "oracle/kdm6/da_fulldomain.py").read_bytes()).hexdigest(),
    accepted_numeric_combinations=checked,
    result="raw binary64 sigma/bias snapshot bits identical; default None pair identical",
    scope="static nuisance input snapshots only; no KDM/RTTOV rerun"), indent=2))
