"""Read-only consistency validation; no DSO loading or execution authorization.

Expected values must come from an independent policy/source. A self-consistent
manifest cannot authenticate its producer or prove that the reported commands ran.
"""
import hashlib
import json
import shlex
import stat
from pathlib import Path

if __package__:
    from . import ci_build as ci
else:
    import ci_build as ci


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def unique(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def read_regular(path, root, limit):
    need(not path.is_symlink() and path.exists() and stat.S_ISREG(path.stat().st_mode), 'missing or unsafe file')
    need(path.resolve(strict=True).parent == root, 'path escape')
    need(path.stat().st_size <= limit, 'file size bound')
    return path.read_bytes()


def parse(raw):
    return json.loads(raw, object_pairs_hook=unique)


def validate(directory, expected):
    """Compare an extracted bundle with independently supplied exact expectations."""
    directory = Path(directory)
    need(directory.is_absolute() and '..' not in directory.parts and not directory.is_symlink() and directory.is_dir(), 'artifact directory')
    root = directory.resolve(strict=True)
    required = {'system', 'architecture', 'python_abi', 'torch', 'compiler_version', 'cmake_version',
                'snapshot_sha256', 'source_assets_sha256', 'required_compile_flags', 'exports', 'binary_sha256'}
    need(type(expected) is dict and set(expected) == required, 'expectations')
    system = expected['system']
    need(system in ('Linux', 'Darwin'), 'platform')
    library = 'libkdm6_c.so.2.0.0' if system == 'Linux' else 'libkdm6_c.2.0.0.dylib'
    files = {library, 'test_batch6_synthetic_capture_parity', 'compile_commands.json', 'ctest-results.xml',
             'a7_ledger_snapshot.json', 'source_assets.json', 'ci_receipt.json'}
    need({p.name for p in directory.iterdir()} == files | {'manifest.json'}, 'artifact inventory')
    manifest_raw = read_regular(directory / 'manifest.json', root, ci.FILE_LIMITS['manifest.json'])
    manifest = parse(manifest_raw)
    need(manifest.get('schema') == 'kdm6.batch6.artifacts.v1' and manifest.get('parity_status') == 'CONTAINMENT_PENDING'
         and manifest.get('build_type') == 'Release' and manifest.get('capture_macro') == 'ON', 'manifest status')
    environment = manifest['environment']
    for field in ('system', 'architecture', 'python_abi', 'torch', 'compiler_version', 'cmake_version'):
        need(type(expected[field]) is str and expected[field] and environment.get(field) == expected[field], 'environment mismatch: ' + field)
    need(type(manifest['files']) is dict and set(manifest['files']) == files, 'manifest inventory')
    contents = {}
    total = len(manifest_raw)
    for name in sorted(files):
        entry = manifest['files'][name]
        need(type(entry) is dict and set(entry) == {'sha256', 'size_bytes'} and type(entry['size_bytes']) is int and entry['size_bytes'] >= 0, 'file metadata')
        raw = read_regular(directory / name, root, ci.FILE_LIMITS[name])
        total += len(raw)
        need(total <= ci.MAX_ARTIFACT_BYTES and len(raw) == entry['size_bytes']
             and hashlib.sha256(raw).hexdigest() == entry['sha256'], 'file hash/size: ' + name)
        contents[name] = raw
    binary_names = {library, 'test_batch6_synthetic_capture_parity'}
    need(type(expected['binary_sha256']) is dict and set(expected['binary_sha256']) == binary_names
         and all(expected['binary_sha256'][name] == manifest['files'][name]['sha256'] for name in binary_names),
         'independent binary pins')
    need(expected['snapshot_sha256'] == ci.replay.ASSETS['a7_ledger_snapshot.json']
         and hashlib.sha256(contents['a7_ledger_snapshot.json']).hexdigest() == expected['snapshot_sha256'], 'A7 snapshot pin')
    assets = parse(contents['source_assets.json'])
    need(type(expected['source_assets_sha256']) is dict and assets == expected['source_assets_sha256']
         and assets.get('a7_ledger_snapshot.json') == expected['snapshot_sha256'], 'source asset pins')
    receipt = parse(contents['ci_receipt.json'])
    need(receipt['status'] == 'passed' and receipt['source_asset_sha256'] == assets
         and receipt['unrun_tests'] == ci.UNRUN_TESTS, 'receipt status')
    on = receipt['builds']['ON']
    need(type(expected['exports']) is list and len(expected['exports']) == len(set(expected['exports']))
         and set(expected['exports']) == ci.BASE | ci.RESEARCH and set(on['exports']) == set(expected['exports'])
         and len(on['exports']) == len(expected['exports']), 'export surface')
    need(on['passed_ctests'] == sorted(ci.RUN_TESTS)
         and on['junit_counts'] == {'tests': 4, 'failures': 0, 'errors': 0, 'skipped': 0}, 'CTest receipt')
    ci.check_junit(directory / 'ctest-results.xml', ci.RUN_TESTS)
    tests = ci.check_flags(directory)
    need(tests == on['test_sources_with_assertions'], 'test compile inventory')
    commands = parse(contents['compile_commands.json'])
    required_flags = expected['required_compile_flags']
    need(type(required_flags) is list and required_flags and all(type(x) is str and x for x in required_flags)
         and '-ffp-contract=off' in required_flags, 'required flags')
    runtime = []
    for entry in commands:
        args = entry.get('arguments') or shlex.split(entry['command'])
        need(all(flag in args for flag in required_flags), 'required compile flags absent')
        if entry['file'].endswith('/src/runtime.cpp'):
            runtime.append(args)
    need(len(runtime) == 1 and '-DKDM6_BATCH5_RESEARCH_CAPTURE' in runtime[0]
         and '-UKDM6_BATCH5_RESEARCH_CAPTURE' not in runtime[0] and '-DNDEBUG' in runtime[0],
         'research capture macro or Release flag')
    return {'status': 'VERIFIED_BUILD_ASSET_ONLY', 'eligibility': 'NOT_ELIGIBLE',
            'parity_status': 'CONTAINMENT_PENDING',
            'scope': 'Bundle consistency against supplied expectations only; no authenticated producer, execution, reuse authorization, or scientific claim.'}
