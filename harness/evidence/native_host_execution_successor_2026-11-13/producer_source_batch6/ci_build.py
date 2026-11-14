#!/usr/bin/env python3
"""Build and test the reconstructed synthetic-only batch6 source in isolation."""
import argparse
import hashlib
import importlib.util
import json
import platform
import shlex
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

if __package__:
    from . import replay as a5_replay
else:
    import replay as a5_replay

_spec = importlib.util.spec_from_file_location('batch6_layers_replay', Path(__file__).resolve().parent.parent / 'producer_source_batch6_layers' / 'replay.py')
replay = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(replay)

BASE = set('''kdm6_step_c kdm6_step_ad_c kdm6_step_ad_variant_c kdm6_step_ad_number_c
kdm6_step_v2_c kdm6_get_abi_version_c kdm6_step_v2_args_size_c kdm6_handle_vjp_c
kdm6_handle_jvp_c kdm6_handle_close_c kdm6_handle_closep_c kdm6_step_ad_state_forcing_c
kdm6_handle_state_forcing_vjp_c kdm6_handle_state_forcing_jvp_c'''.split())
RESEARCH = {'kdm6_batch5_' + x + '_c' for x in
            ('begin', 'count', 'metadata', 'value_word', 'binding_token', 'graph_primal',
             'result_rain', 'intermediate_jvp', 'intermediate_vjp', 'clear')}
RESEARCH |= {'kdm6_batch5_condition_v2_' + x + '_c' for x in ('count', 'meta', 'raw', 'verify_absences')}
OFF_TESTS = set('smoke slope progb warm satadj aux_placeholder_gap cold melt_freeze sedimentation thermo coordinator cloud_dsd c_abi state_forcing_abi autograd_endtoend dry_number handle_vjp conservative_interface fortran_smoke fortran_normalized_ad fortran_state_forcing'.split())
TARGET_TESTS = {'batch5_intermediate_ad', 'batch5_sidecar', 'batch6_f32_context_rejection', 'batch5_conditions_v2', 'batch6_synthetic_capture_parity'}


def run(cmd, receipt, cwd=None):
    entry = {'argv': [str(x) for x in cmd], 'cwd': str(cwd) if cwd else None}
    receipt['commands'].append(entry)
    start = time.monotonic()
    try:
        result = subprocess.run(entry['argv'], cwd=cwd, text=True, capture_output=True, timeout=1800)
        entry.update(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
        print(result.stdout, end='', flush=True)
        print(result.stderr, end='', file=sys.stderr, flush=True)
        if result.returncode:
            raise RuntimeError(f"command failed ({result.returncode}): {entry['argv']}")
        return result.stdout
    except (OSError, subprocess.TimeoutExpired) as exc:
        entry['error'] = str(exc)
        raise RuntimeError(f'command could not complete: {entry["argv"]}: {exc}') from exc
    finally:
        entry['seconds'] = round(time.monotonic() - start, 3)


def check_flags(build):
    entries = json.loads((build / 'compile_commands.json').read_text())
    if not entries:
        raise ValueError('empty compile database')
    tests = set()
    for entry in entries:
        args = entry.get('arguments') or shlex.split(entry['command'])
        if '-ffp-contract=off' not in args or any(x.startswith('-ffp-contract=') and x != '-ffp-contract=off' for x in args):
            raise ValueError('missing or conflicting floating-point flag: ' + entry['file'])
        if any('CMakeFiles/test_' in arg for arg in args) and entry['file'].endswith(('.cpp', '.cc', '.cxx')):
            if '-UNDEBUG' not in args or ('-DNDEBUG' in args and args.index('-UNDEBUG') < args.index('-DNDEBUG')):
                raise ValueError('assertions disabled: ' + entry['file'])
            tests.add(Path(entry['file']).name)
    if not tests:
        raise ValueError('no C++ test compile commands')
    return sorted(tests)


def exports(build, expected, receipt):
    system = platform.system()
    if system == 'Darwin':
        lib, opts = build / 'libkdm6_c.dylib', ['-gU']
    elif system == 'Linux':
        lib, opts = build / 'libkdm6_c.so', ['-D', '--defined-only']
    else:
        raise ValueError('unsupported platform: ' + system)
    out = run(['nm', *opts, lib], receipt)
    names = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        name = parts[-1].split('@', 1)[0]
        if system == 'Darwin' and name.startswith('_'):
            name = name[1:]
        if name != 'KDM6_2':
            names.add(name)
    if names != expected:
        raise ValueError(f'export mismatch: missing={sorted(expected - names)}, extra={sorted(names - expected)}')
    return sorted(names)


def check_junit(path, expected, result=None):
    root = ET.parse(path).getroot()
    cases = root.findall('.//testcase')
    names = [case.get('name') for case in cases]
    counts = {'tests': len(cases), 'failures': 0, 'errors': 0, 'skipped': 0}
    for case in cases:
        for tag in ('failure', 'error', 'skipped'):
            if case.find(tag) is not None:
                counts[{'failure': 'failures', 'error': 'errors', 'skipped': 'skipped'}[tag]] += 1
    if result is not None:
        result['junit_counts'] = counts
    if len(names) != len(set(names)) or set(names) != expected:
        raise ValueError(f'JUnit test inventory mismatch: actual={sorted(names)}, expected={sorted(expected)}')
    if counts['failures'] or counts['errors'] or counts['skipped']:
        raise ValueError(f'JUnit contains unsuccessful tests: {counts}')
    return counts


def build_all(root, work, prefix, receipt):
    for mode in ('OFF', 'ON'):
        build = work / mode.lower()
        run(['cmake', '-S', root, '-B', build, '-DCMAKE_BUILD_TYPE=Release',
             '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON', '-DCMAKE_PREFIX_PATH=' + prefix,
             '-DKDM6_ENABLE_TEST_HOOKS=OFF', '-DKDM6_NATIVE_SCALAR_CAPTURE=OFF',
             '-DKDM6_BATCH5_RESEARCH_CAPTURE=' + mode], receipt)
        receipt['builds'][mode] = {'test_sources_with_assertions': check_flags(build)}
        cmd = ['cmake', '--build', build, '--parallel', '2']
        if mode == 'ON':
            cmd += ['--target', 'kdm6_c', 'test_batch5_intermediate_ad', 'test_batch5_sidecar', 'test_batch6_f32_context_rejection', 'test_batch5_conditions_v2', 'test_batch6_synthetic_capture_parity']
        run(cmd, receipt)
        receipt['builds'][mode]['exports'] = exports(build, BASE | (RESEARCH if mode == 'ON' else set()), receipt)
        listing = json.loads(run(['ctest', '--test-dir', build, '--show-only=json-v1'], receipt))
        names = {test['name'] for test in listing['tests']}
        if mode == 'ON' and not TARGET_TESTS <= names:
            raise ValueError('missing research CTests: ' + str(sorted(TARGET_TESTS - names)))
        if mode == 'OFF' and names != OFF_TESTS:
            raise ValueError('invalid shipped CTest inventory')
        junit = build / 'ctest-results.xml'
        cmd = ['ctest', '--test-dir', build, '--output-on-failure', '--no-tests=error', '--output-junit', junit]
        if mode == 'ON':
            cmd += ['-R', '^(' + '|'.join(sorted(TARGET_TESTS)) + ')$']
        expected = TARGET_TESTS if mode == 'ON' else names
        try:
            run(cmd, receipt)
        except RuntimeError:
            if junit.exists():
                check_junit(junit, expected, receipt['builds'][mode])
            raise
        receipt['builds'][mode]['junit_counts'] = check_junit(junit, expected, receipt['builds'][mode])
        receipt['builds'][mode]['passed_ctests'] = sorted(expected)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--receipt', required=True, type=Path)
    args = parser.parse_args()
    receipt = {'schema': 'kdm6.batch6.source_ci.v1', 'status': 'failed',
               'scope': 'Public C++ tests may run KDM on synthetic fixtures; no registered native host-column batch, WRF/RTTOV execution, scientific validation, or installed-build identity.',
               'commands': [], 'builds': {}, 'platform': platform.platform()}
    try:
        receipt['source_asset_sha256'] = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in {
            'a5_snapshot': a5_replay.HERE / 'source_snapshot.json',
            'a5_patch': a5_replay.HERE / 'rain_checkpoint.patch',
            **{name: replay.HERE / name for name in replay.ASSETS},
        }.items()}
        receipt['git_sha'] = run(['git', 'rev-parse', 'HEAD'], receipt).strip()
        prefix = run([sys.executable, '-c', 'import os,torch; print(os.path.dirname(torch.__file__))'], receipt).strip()
        with replay.reconstructed_tree() as (root, reconstruction), tempfile.TemporaryDirectory(prefix='batch6-ci-') as temp:
            receipt['reconstruction'] = reconstruction
            build_all(root, Path(temp), prefix, receipt)
        receipt['status'] = 'passed'
    except Exception as exc:
        receipt['error'] = f'{type(exc).__name__}: {exc}'
        print(receipt['error'], file=sys.stderr)
    finally:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    return 0 if receipt['status'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
