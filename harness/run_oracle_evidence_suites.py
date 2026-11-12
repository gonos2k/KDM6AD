#!/usr/bin/env python3
"""Run a fixed registry of isolated unittest discovery processes, fail closed."""
import argparse
import ast
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / 'harness/oracle_evidence_suites.json'
RAN = re.compile(r'^Ran (\d+) tests? in [\d.]+s$', re.MULTILINE)


def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('duplicate JSON key: ' + key)
        obj[key] = value
    return obj


def read_registry(path=REGISTRY, root=ROOT):
    data = json.loads(path.read_text(), object_pairs_hook=unique_object)
    if data.get('schema') != 'kdm6.oracle_evidence_suites.v1':
        raise ValueError('invalid registry schema')
    suites = data.get('suites')
    if not isinstance(suites, list) or not suites or type(data.get('expected_count')) is not int or len(suites) != data['expected_count']:
        raise ValueError('missing suites or count mismatch')
    if any(not isinstance(p, str) for p in suites):
        raise ValueError('invalid suite')
    if root == ROOT and hashlib.sha256(('\n'.join(suites[:49])+'\n').encode()).hexdigest() != '350c3e2e53683c61f73a871848a9ef127d2d13bd774189e6c0cc0889c0705540':
        raise ValueError('baseline suite coverage changed')
    if root == ROOT and 'harness/evidence/native_host_analysis_batch_2026-11-12' not in suites:
        raise ValueError('missing analysis suite')
    if any(not isinstance(p, str) for p in suites) or len(set(suites)) != len(suites):
        raise ValueError('invalid or duplicate suite')
    excluded = data.get('excluded_test_directories')
    if not isinstance(excluded, dict) or any(not isinstance(k, str) or not isinstance(v, str) or not v.strip() for k, v in excluded.items()):
        raise ValueError('invalid excluded test directory inventory')
    if set(suites) & set(excluded):
        raise ValueError('active/excluded suite overlap')
    base = (root / 'harness/evidence').resolve()
    resolved = set()
    for name in [*suites, *excluded]:
        p = Path(name)
        if p.is_absolute() or '..' in p.parts or p.parts[:2] != ('harness', 'evidence') or len(p.parts) != 3:
            raise ValueError('invalid suite path: ' + name)
        dest = (root / p).resolve()
        if dest in resolved or dest != root.resolve() / p or dest.parent != base or not dest.is_dir() or not any(dest.glob('test*.py')):
            raise ValueError('missing or invalid suite: ' + name)
        resolved.add(dest)
    discovered = {str(Path('harness/evidence') / child.name) for child in base.iterdir() if child.is_dir() and any(child.glob('test*.py'))}
    classified = set(suites) | set(excluded)
    if discovered != classified:
        raise ValueError(f'test directory inventory mismatch: unclassified={sorted(discovered - classified)} missing={sorted(classified - discovered)}')
    approved = data.get('allowed_skips')
    if not isinstance(approved, dict) or set(approved) - set(suites):
        raise ValueError('invalid allowed skips')
    for suite, entries in approved.items():
        if not isinstance(entries, dict) or not entries or any(not isinstance(k, str) or not k or not isinstance(v, str) or not v for k, v in entries.items()):
            raise ValueError('invalid allowed skips: ' + suite)
    hints = data.get('timing_hints_seconds', {})
    if not isinstance(hints, dict) or set(hints) - {'normal', 'optimized'}:
        raise ValueError('invalid timing hints')
    for mode_hints in hints.values():
        if not isinstance(mode_hints, dict) or set(mode_hints) - set(suites) or any(type(x) not in (int, float) or not math.isfinite(x) or x < 0 for x in mode_hints.values()):
            raise ValueError('invalid timing hints')
    return suites


def schedule(suites, hints):
    return sorted(enumerate(suites), key=lambda item: (-hints.get(item[1], 0), item[0]))



def provenance(root, registry, mode, workers, timeout):
    ci = os.environ.get('GITHUB_ACTIONS') == 'true' and root.resolve() == ROOT.resolve()
    def git(arg):
        try:
            value = subprocess.check_output(['git', 'rev-parse', '--verify', arg], cwd=root, stderr=subprocess.DEVNULL, text=True).strip()
            return value if re.fullmatch(r'[0-9a-f]{40}', value) else None
        except (OSError, subprocess.CalledProcessError):
            return None
    commit, tree = git('HEAD'), git('HEAD^{tree}')
    try: registry_hash = hashlib.sha256(registry.read_bytes()).hexdigest()
    except OSError: registry_hash = None
    run_id, attempt = os.environ.get('GITHUB_RUN_ID'), os.environ.get('GITHUB_RUN_ATTEMPT')
    if ci and (not commit or not tree or not registry_hash or not run_id or not run_id.isdecimal() or not attempt or not attempt.isdecimal() or os.environ.get('GITHUB_SHA') != commit):
        raise ValueError('missing or mismatched CI provenance')
    return {'head_commit':commit, 'head_tree':tree, 'registry_sha256':registry_hash,
            'python_version':sys.version, 'python_executable':sys.executable,
            'workers':workers, 'timeout_seconds':timeout, 'mode':mode,
            'github_run_id':run_id, 'github_run_attempt':attempt}


def skip_details(text, approved, suite):
    lines = re.findall(r'^.*\.\.\. skipped .+$', text, re.MULTILINE)
    parsed = []
    for line in lines:
        match = re.fullmatch(r'(\S+) \(([^()]+)\) \.\.\. skipped (.+)', line)
        if not match:
            return lines, False
        try: reason = ast.literal_eval(match.group(3))
        except (ValueError, SyntaxError): return lines, False
        method, ident = match.group(1), match.group(2)
        if not ident.endswith('.' + method): ident += '.' + method
        if not isinstance(reason, str) or approved.get(suite, {}).get(ident) != reason:
            return lines, False
        parsed.append(ident)
    return lines, len(set(parsed)) == len(parsed)

def run(suites, mode, output, root=ROOT, python=sys.executable, timeout=300, workers=2, hints=None, allowed_skips=None, registry=REGISTRY, expected_registry_sha=None):
    if mode not in ('normal', 'optimized') or workers < 1 or timeout <= 0:
        raise ValueError('invalid execution options')
    details = provenance(root, registry, mode, workers, timeout)
    if expected_registry_sha is not None and details['registry_sha256'] != expected_registry_sha:
        raise ValueError('registry changed before execution')
    allowed_skips = allowed_skips or {}
    wall_start = time.monotonic()
    hints = hints or {}
    pending = schedule(suites, hints)
    active = {}
    results = {}
    interrupted = False
    env = os.environ.copy()
    if mode == 'optimized': env['PYTHONOPTIMIZE'] = '1'
    else: env.pop('PYTHONOPTIMIZE', None)
    def stop(process):
        # A group may outlive its leader. An inaccessible group is unverified,
        # so it must fail closed even if the direct child can be reaped.
        errors = []
        def group_signal(sig):
            try:
                os.killpg(process.pid, sig)
                return True
            except ProcessLookupError:
                return False
            except OSError as exc:
                errors.append(f'killpg({sig}): {exc}')
                return None
        exists = group_signal(0)
        observed_remaining = exists is not False
        if exists is not False:
            group_signal(signal.SIGTERM)
            if exists is True:
                deadline = time.monotonic() + 0.5
                state = exists
                try:
                    while time.monotonic() < deadline:
                        process.poll()
                        state = group_signal(0)
                        if state is not True: break
                        time.sleep(0.02)
                except BaseException as exc:
                    # A second interrupt during cleanup must still reach the
                    # bounded SIGKILL and emit a failed run report.
                    errors.append(f'cleanup interrupted: {type(exc).__name__}')
                    state = group_signal(0)
                exists = state
            if exists is not False:
                group_signal(signal.SIGKILL)
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            except OSError as exc:
                errors.append(f'leader kill: {exc}')
            try:
                process.wait(timeout=1)
            except (OSError, subprocess.TimeoutExpired) as exc:
                errors.append(f'leader wait: {exc}')
        except OSError as exc:
            errors.append(f'leader wait: {exc}')
        return observed_remaining, '; '.join(errors) or None
    with tempfile.TemporaryDirectory(prefix='kdm6-evidence-') as temp:
        try:
            while pending or active:
                while pending and len(active) < workers:
                    index, suite = pending.pop(0)
                    log = open(Path(temp) / str(index), 'w+b')
                    command = [python] + (['-O'] if mode == 'optimized' else []) + ['-m', 'unittest', 'discover', '-s', suite, '-v']
                    start = time.monotonic()
                    try:
                        process = subprocess.Popen(command, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                    except OSError as exc:
                        log.close()
                        results[index] = {'suite':suite, 'status':'spawn_error', 'detail':str(exc), 'elapsed_seconds':round(time.monotonic()-start, 3)}
                        continue
                    active[index] = (suite, process, log, start)
                for index, (suite, process, log, start) in list(active.items()):
                    elapsed = time.monotonic() - start
                    timed_out = elapsed > timeout and process.poll() is None
                    if timed_out:
                        leaked, cleanup_error = stop(process)
                    rc = process.poll()
                    if rc is None and not timed_out: continue
                    if not timed_out:
                        leaked, cleanup_error = stop(process)
                    log.flush(); log.seek(0)
                    text = log.read().decode('utf-8', errors='replace'); log.close()
                    matches = RAN.findall(text)
                    count = int(matches[-1]) if len(matches) == 1 else 0
                    ok = re.search(r'^OK(?: \(skipped=(\d+)\))?$', text, re.MULTILINE)
                    skipped = int(ok.group(1) or 0) if ok else 0
                    skip_lines, approved = skip_details(text, allowed_skips, suite)
                    skip_consistent = skipped <= count and len(skip_lines) == skipped and approved
                    status = 'timeout' if timed_out else ('pass' if rc == 0 and count > 0 and ok and skip_consistent and not leaked and not cleanup_error else 'fail')
                    results[index] = {'suite':suite, 'status':status, 'returncode':rc, 'tests':count, 'skipped':skipped, 'skip_reasons':skip_lines, 'cleanup_error':cleanup_error, 'leaked_or_unverified_group':leaked, 'elapsed_seconds':round(time.monotonic()-start, 3)}
                    print(f'[{mode}] {suite}: {status} ({results[index]["elapsed_seconds"]:.3f}s, tests={count}, skipped={skipped})', flush=True)
                    # Keep the old verbose test names and skip reasons visible in
                    # the CI log, grouped by suite despite concurrent execution.
                    print(f'[{mode}] BEGIN {suite}\n{text}\n[{mode}] END {suite}', flush=True)
                    del active[index]
                if active: time.sleep(0.05)
        except (KeyboardInterrupt, SystemExit):
            interrupted = True
        finally:
            for index, (suite, process, log, start) in active.items():
                try:
                    leaked, cleanup_error = stop(process)
                except BaseException as exc:
                    leaked, cleanup_error = True, f'cleanup exception: {exc}'
                    try:
                        if process.poll() is None: process.kill()
                        process.wait(timeout=1)
                    except BaseException as fallback:
                        cleanup_error += f'; leader fallback: {fallback}'
                try:
                    log.close()
                except OSError as exc:
                    cleanup_error = f'{cleanup_error or ""}; log close: {exc}'
                results[index] = {'suite':suite, 'status':'cancelled', 'returncode':process.returncode, 'cleanup_error':cleanup_error, 'leaked_or_unverified_group':leaked, 'elapsed_seconds':round(time.monotonic()-start, 3)}
            for index, suite in pending:
                results[index] = {'suite':suite, 'status':'not_run', 'elapsed_seconds':0}
            ordered = [results[i] for i in sorted(results)]
            success = not interrupted and len(ordered) == len(suites) and all(r['status'] == 'pass' for r in ordered)
            total_tests = sum(r.get('tests', 0) for r in ordered)
            total_skipped = sum(r.get('skipped', 0) for r in ordered)
            failed = sum(r['status'] != 'pass' for r in ordered)
            passed_tests = sum(r.get('tests', 0)-r.get('skipped', 0) for r in ordered if r['status'] == 'pass')
            print(f'[{mode}] summary expected={len(suites)} completed={sum(r["status"] not in ("not_run", "cancelled") for r in ordered)} tests={total_tests} passed={passed_tests} skipped={total_skipped} failed_suites={failed}', flush=True)
            report = {'schema':'kdm6.oracle_evidence_results.v1', 'provenance':details, 'mode':mode, 'expected':len(suites), 'success':success, 'wall_seconds':round(time.monotonic()-wall_start, 3), 'totals':{'completed':sum(r['status'] not in ('not_run','cancelled') for r in ordered), 'tests':total_tests, 'passed_in_successful_suites':passed_tests, 'skipped':total_skipped, 'nonpassing_suites':failed}, 'suites':ordered}
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, indent=2) + '\n')
    return success


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', required=True, choices=('normal', 'optimized'))
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--timeout', type=float, default=300)
    args = parser.parse_args()
    def terminate(_signum, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, terminate)
    try:
        registry_bytes = REGISTRY.read_bytes()
        suites = read_registry()
        if REGISTRY.read_bytes() != registry_bytes:
            raise ValueError('registry changed during validation')
        config = json.loads(registry_bytes)
        registry_sha = hashlib.sha256(registry_bytes).hexdigest()
        hints = config.get('timing_hints_seconds', {}).get(args.mode, {})
        return 0 if run(suites, args.mode, args.output, timeout=args.timeout, hints=hints, allowed_skips=config['allowed_skips'], expected_registry_sha=registry_sha) else 1
    except KeyboardInterrupt:
        print('evidence runner interrupted', file=sys.stderr)
        return 1
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f'evidence runner: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
