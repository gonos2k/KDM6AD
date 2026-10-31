#!/usr/bin/env python3
"""Replay the pinned completed QNC-guard Control packet; makes no model calls."""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import tarfile
import tempfile

HERE = Path(__file__).resolve().parent
ARCHIVE_SHA = '568b09524f6ab5ca9eaade51cd77c45ebcbe2b17afe5bd0827ff0590717845c5'
VERIFIER_SHA = 'b4d8ae8f9a8473a523ff775a1754c31dbed45f571692d35f0fc1af7f358eddcd'
BINDING_SHA = '9380922ab5e7e30e26ea2602fcccd1c43ba170cfa60c014b7541d99d00fc0864'
SUMMARY_SHA = '7818fb559bd1358cd968a538b2ed1690bfe2622aefd2e43a3839bd84a6d455e7'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    archive = HERE / 'chunk_artifacts.tar.gz'
    source = HERE / 'verify_export.py'
    independent = HERE / 'executed_sources/verify_control_direct.py.txt'
    executed_export = HERE / 'executed_sources/verify_export_executed.py.txt'
    if (sha(executed_export) != '69739993c1ef54b0f78abe1dc49901bc2258d820b79dfff75a9b6be83a2fe9fc'
            or sha(archive) != ARCHIVE_SHA or sha(source) != VERIFIER_SHA
            or sha(independent) != '9605bb42872e8637f76461a9eaf5c89ccdfd75cf2cc4a91f9f43ebe248a974ab'):
        raise ValueError('archive or verifier source hash mismatch')
    manifest = json.loads((HERE / 'manifest.json').read_text())
    expected_files = {'chunk_artifacts.tar.gz', 'verify_export.py', 'packet_replay.py',
                      'test_packet_replay.py', 'analysis.json',
                      'executed_sources/run_control_direct.py.txt',
                      'executed_sources/verify_control_direct.py.txt',
                      'executed_sources/verify_export_executed.py.txt'}
    if (manifest['schema'] != 'kdm6.qnc_guard_control_direct_m0_packet.v1'
            or set(manifest['files_sha256']) != expected_files
            or any(sha(HERE / name) != expected for name, expected in manifest['files_sha256'].items())
            or manifest['producer_binding_sha256'] != BINDING_SHA
            or manifest['producer_summary_sha256'] != SUMMARY_SHA):
        raise ValueError('manifest or file hash mismatch')
    spec = importlib.util.spec_from_file_location('qnc_offline_verifier', source)
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    expected = {'binding.json', 'summary.json'} | {
        f'chunks/chunk_{i:03d}/{name}' for i in range(129)
        for name in ('attempt.json', 'result.json', 'result.npz')}
    with tempfile.TemporaryDirectory(prefix='qnc_control_replay_') as tmp:
        root = Path(tmp)
        with tarfile.open(archive, 'r:gz') as tar:
            entries = tar.getmembers()
            if len(entries) != len(expected) or {m.name for m in entries} != expected or any(not m.isfile() for m in entries):
                raise ValueError('archive member set/type differs')
            for member in entries:
                target = root / member.name
                target.parent.mkdir(parents=True, exist_ok=True)
                stream = tar.extractfile(member)
                if stream is None:
                    raise ValueError('unreadable archive member')
                with target.open('xb') as out:
                    while block := stream.read(8 << 20):
                        out.write(block)
        result = verifier.verify(root)
    if (result['binding_sha256'] != BINDING_SHA or result['summary_sha256'] != SUMMARY_SHA
            or result['control_huber_numerator'] != 4153768.353915674
            or result['control_cost'] != 11.007967186042567):
        raise ValueError('pinned output differs')
    result['archive_sha256'] = ARCHIVE_SHA
    result['verifier_sha256'] = VERIFIER_SHA
    print(json.dumps(result, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
