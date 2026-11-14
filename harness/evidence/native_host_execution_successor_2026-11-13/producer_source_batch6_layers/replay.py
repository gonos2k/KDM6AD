#!/usr/bin/env python3
"""Offline A5 -> v2 schema -> A-2 named hooks -> A-3 diagnostics -> A-4 synthetic test reconstruction."""
import hashlib
import importlib.util
import json
import re
import subprocess
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
A5 = HERE.parent / 'producer_source_batch6' / 'replay.py'
A5_SHA = '6eec3ace4df9befb5ef95c103c0203c7c657225ea73ebdef33bab47c2675f261'
ASSETS = {
    'v2.patch': 'ed80e058528bdaac8a7a84f75d5aef4e0abb394cc1df9414f0f4a9d66caf14dd',
    'v2_snapshot.json': '1fe83aa8628982a03a86c2359fa029dcf88087a40efaccda0163ad4fe42a6ee8',
    'a2.patch': 'c47c54bb2be4e448e2609c7012dc522bf4735f9e9d08c707d7c58756353d528e',
    'a2_snapshot.json': '2ee85ddeaa142cc7704d67164e05bdce45833cedb59be88537b3319fd200bf31',
    'a3.patch': 'ecaeb8d93b5be1b0e76ea3e791d6d1a3f195111b62f5d894ac4dd62b78404331',
    'a3_snapshot.json': '3d947134a061c992f3cabc1b1309497f3b5cfc18c2a14cb657b23b40f058d01a',
    'a4.patch': '665e70a8d1d204c696f7b2fe861a57bd2fa4ed932984106ae763580e128d7362',
    'a4_snapshot.json': 'fe2d660baf7bb88d8ba9e4ff9afe6692873a197cadb05fb35f21cbf12199dc48',
    'a5_graph.patch': 'c8f770a2b29b90b041908d8b2148740161e80a206f1d2f7e302a2f496a95536a',
    'a5_graph_snapshot.json': 'b4ff2a9e2bb95ab19333ea73bbcce030d82f6165b94ab26a85841d489782ee3a',
    'a7_ledger.patch': '97f17b411075989feac89639f76ccf6f2c7f7eb9966a19936fa4da4865bdd3bd',
    'a7_ledger_snapshot.json': '033558eb6f771beb76d6ba8ebbc1aa126c4abafd4eb6d53dcabd3361cb8a1038',
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def need(ok, message):
    if not ok:
        raise ValueError(message)


def load_a5():
    need(sha(A5.read_bytes()) == A5_SHA, 'A5 replay SHA')
    spec = importlib.util.spec_from_file_location('batch6_a5_replay', A5)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snapshot(raw, size, validator):
    obj = json.loads(raw, object_pairs_hook=unique_keys)
    need(isinstance(obj, dict) and len(obj) == size, 'snapshot inventory size')
    output = {}
    for name, digest in obj.items():
        path = 'libtorch/' + name
        validator.safe_file(path)
        need(isinstance(digest, str) and re.fullmatch('[0-9a-f]{64}', digest) is not None, 'invalid digest')
        output[path] = digest
    return output


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, 'duplicate snapshot key')
        result[key] = value
    return result


def verify_tree(root, inventory, validator):
    found = set()
    for path in root.rglob('*'):
        need(not path.is_symlink(), 'source symlink')
        if path.is_file():
            name = str(path.relative_to(root.parent))
            validator.safe_file(name)
            need(name in inventory and sha(path.read_bytes()) == inventory[name], 'source SHA: ' + name)
            found.add(name)
        else:
            need(path.is_dir(), 'nonregular source entry')
    need(found == set(inventory), 'source inventory')


def apply_layer(root, patch, base, target, validator):
    verify_tree(root, base, validator)
    changes = validator.validate_patch(patch, base, target)
    for command in (['git', 'apply', '--no-index', '--check', '-'], ['git', 'apply', '--no-index', '-']):
        result = subprocess.run(command, input=patch, cwd=root.parent, capture_output=True, timeout=30, check=False)
        need(result.returncode == 0, 'patch application: ' + result.stderr.decode(errors='replace')[-1000:])
    verify_tree(root, target, validator)
    return {'base_files': len(base), 'changed_files': len(changes), 'reconstructed_files': len(target)}


@contextmanager
def reconstructed_tree(layer='a7_ledger'):
    need(layer in ('a4', 'a5_graph', 'a7_ledger'), 'unknown final layer')
    a5 = load_a5()
    assets = {name: (HERE / name).read_bytes() for name in ASSETS}
    for name, data in assets.items():
        need(sha(data) == ASSETS[name], 'asset SHA: ' + name)
    validator = a5.parent_module()
    base = snapshot((a5.HERE / 'source_snapshot.json').read_bytes(), 77, validator)
    v2 = snapshot(assets['v2_snapshot.json'], 82, validator)
    a2 = snapshot(assets['a2_snapshot.json'], 83, validator)
    a3 = snapshot(assets['a3_snapshot.json'], 83, validator)
    a4 = snapshot(assets['a4_snapshot.json'], 84, validator)
    a5_graph = snapshot(assets['a5_graph_snapshot.json'], 84, validator)
    a7_ledger = snapshot(assets['a7_ledger_snapshot.json'], 84, validator)
    with a5.reconstructed_tree() as (root, a5_result):
        v2_result = apply_layer(root, assets['v2.patch'], base, v2, validator)
        a2_result = apply_layer(root, assets['a2.patch'], v2, a2, validator)
        a3_result = apply_layer(root, assets['a3.patch'], a2, a3, validator)
        a4_result = apply_layer(root, assets['a4.patch'], a3, a4, validator)
        result = {'a5': a5_result, 'v2': v2_result, 'a2': a2_result, 'a3': a3_result, 'a4': a4_result}
        if layer in ('a5_graph', 'a7_ledger'):
            result['a5_graph'] = apply_layer(root, assets['a5_graph.patch'], a4, a5_graph, validator)
        if layer == 'a7_ledger':
            result['a7_ledger'] = apply_layer(root, assets['a7_ledger.patch'], a5_graph, a7_ledger, validator)
        yield root, result


def replay():
    with reconstructed_tree() as (_, result):
        return {'schema': 'kdm6.batch6.layered_source_replay.v1', **result,
                'scope': 'offline source reconstruction only; no compiler, model, DSO or host execution',
                'installed_build_identity': 'NOT_ESTABLISHED', 'scientific_status': 'INCONCLUSIVE',
                'physical_unit_status': 'INCONCLUSIVE'}


if __name__ == '__main__':
    print(json.dumps(replay(), indent=2, sort_keys=True))
