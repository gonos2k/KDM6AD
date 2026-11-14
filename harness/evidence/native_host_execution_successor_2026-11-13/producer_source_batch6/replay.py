#!/usr/bin/env python3
"""Reconstruct the batch6 research source offline; never build or run the model."""
import hashlib
import importlib.util
import json
import re
import subprocess
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / 'producer_source' / 'replay.py'
PARENT_SHA = 'bb621554daab87441d39bea7a430c595c3b2939e40dc783f283c980d89ba9190'
PATCH_SHA = '65524b6fce5c6f57cd8c063cbd6b360710c0b3019780d3f4854001fab088a657'
SNAPSHOT_SHA = '3d06cc352895de7719a2fb3710cb12e949dbd56e98554009c9c5ce2e85aed9b2'
PRIVATE_RECEIPT_SHA = 'c0294dbfc28ba3e3b4aea0dac815df58df7b0ff203202da4e2ba9d4e9f6d1274'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def need(condition, message):
    if not condition:
        raise ValueError(message)

def parent_module():
    need(sha(PARENT.read_bytes()) == PARENT_SHA, 'parent replay SHA')
    spec = importlib.util.spec_from_file_location('batch5_source_replay', PARENT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def validate_patch(module, patch, base, target):
    # The archived patch has eight-digit Git object IDs. Expand only those IDs
    # for the parent's strict structural parser; apply the original bytes.
    text = patch.decode('utf-8')
    def expand(match):
        return 'index ' + match[1].ljust(40, '0') + '..' + match[2].ljust(40, '0') + match[3]
    text = re.sub(r'^index ([0-9a-f]{8})\.\.([0-9a-f]{8})( 100644)?$',
                  lambda m: expand((m[0], m[1], m[2], m[3] or '')), text, flags=re.MULTILINE)
    return module.validate_patch(text.encode(), base, target)

def apply_and_validate(module, root, patch, target):
    base = json.loads((PARENT.parent / 'source_manifest.json').read_bytes())['target_file_sha256']
    need(len(base) == 76 and len(target) == 77, 'source inventory size')
    for name, digest in target.items():
        module.safe_file(name)
        need(re.fullmatch('[0-9a-f]{64}', digest) is not None, 'source digest')
    changes = validate_patch(module, patch, base, target)
    for args in (['git', 'apply', '--no-index', '--check', '-'], ['git', 'apply', '--no-index', '-']):
        result = subprocess.run(args, cwd=root.parent, input=patch, capture_output=True, timeout=30, check=False)
        need(result.returncode == 0, 'patch application: ' + result.stderr.decode(errors='replace')[-1000:])
    found = set()
    for path in root.rglob('*'):
        need(not path.is_symlink(), 'source symlink')
        if path.is_file():
            name = str(path.relative_to(root.parent))
            module.safe_file(name)
            need(name in target and sha(path.read_bytes()) == target[name], 'target source SHA: ' + name)
            found.add(name)
        else:
            need(path.is_dir(), 'nonregular source entry')
    need(found == set(target), 'target inventory')
    return {'base_files': len(base), 'changed_files': len(changes), 'reconstructed_files': len(found)}

@contextmanager
def reconstructed_tree():
    module = parent_module()
    patch = (HERE / 'rain_checkpoint.patch').read_bytes()
    snapshot = (HERE / 'source_snapshot.json').read_bytes()
    need(sha(patch) == PATCH_SHA and sha(snapshot) == SNAPSHOT_SHA, 'asset SHA')
    target = {'libtorch/' + k: v for k, v in json.loads(snapshot).items()}
    with module.reconstructed_tree() as (root, _):
        result = apply_and_validate(module, root, patch, target)
        yield root, result

def replay():
    with reconstructed_tree() as (_, result):
        return {'schema': 'kdm6.batch6.isolated_source_replay.v1', **result,
                'scope': 'offline source reconstruction only; no compiler, model, DSO or host execution',
                'installed_build_identity': 'NOT_ESTABLISHED', 'scientific_status': 'INCONCLUSIVE',
                'physical_unit_status': 'INCONCLUSIVE'}

if __name__ == '__main__':
    print(json.dumps(replay(), indent=2, sort_keys=True))
