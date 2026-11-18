"""Candidate-only publication cannot be used as a completion witness."""
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import witness33
import real33_orchestrate as orchestrator


class CompletionTest(unittest.TestCase):
    def test_direct_publication_rejected_even_with_noop_callback(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'completion_witness.json'
            with self.assertRaisesRegex(RuntimeError,'independent supervisor'):
                witness33.publish_verified(path,{'status':'EXECUTION_COMPLETED_ASSETS_ONLY'},time.monotonic()+5,object(),(),lambda:None)
            self.assertFalse(path.exists())

    def test_consumed_marker_exact_identity_and_bytes(self):
        identity={'run_nonce':'a'*64,'manifest_sha256':'b'*64,'worker_pid':23,'worker_start':[1,2],'watchdog_pid':24,'watchdog_start':[3,4],'supervisor_pid':25,'supervisor_start':[5,6]}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory).resolve()/'authority_consumed.json';marker={'schema':'kdm6.synthetic33.authority_consumed.v1','output_dir':str(path.parent),**identity}
            path.write_bytes(json.dumps(marker,sort_keys=True,separators=(',',':')).encode('ascii'))
            self.assertEqual(len(orchestrator.validate_consumed_marker(path,identity,identity)),64)
            for name,value in (('worker_pid',True),('worker_start',[True,2]),('run_nonce','c'*64),('output_dir',str(path.parent/'wrong')),('output_dir',False)):
                altered=dict(marker);altered[name]=value;path.write_bytes(json.dumps(altered,sort_keys=True,separators=(',',':')).encode('ascii'))
                with self.assertRaises(RuntimeError):orchestrator.validate_consumed_marker(path,identity,identity)
            path.write_bytes(json.dumps(marker,sort_keys=True,separators=(',',':')).encode('ascii'))
            bad_armed={**identity,'worker_start':[True,2]}
            with self.assertRaises(RuntimeError):orchestrator.validate_consumed_marker(path,bad_armed,identity)
            path.write_text(json.dumps(marker,sort_keys=True))
            with self.assertRaisesRegex(RuntimeError,'canonical'):orchestrator.validate_consumed_marker(path,identity,identity)
            path.unlink()
            with self.assertRaises(RuntimeError):orchestrator.validate_consumed_marker(path,identity,identity)

    def test_candidate_only_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'completion_candidate.json'
            payload={'schema':'kdm6.synthetic33.completion_candidate.v1','status':'CANDIDATE_UNVERIFIED'}
            witness33.publish_candidate(path,payload,time.monotonic()+5,lambda:None)
            self.assertEqual(json.loads(path.read_text()),payload)
            with self.assertRaises(FileExistsError):witness33.publish_candidate(path,payload,time.monotonic()+5,lambda:None)
            with self.assertRaisesRegex(RuntimeError,'candidate-only'):
                witness33.publish_candidate(Path(directory)/'completion_witness.json',payload,time.monotonic()+5,lambda:None)
            with self.assertRaisesRegex(RuntimeError,'candidate-only'):
                witness33.publish_candidate(Path(directory)/'other',{'status':'EXECUTION_COMPLETED_ASSETS_ONLY'},time.monotonic()+5,lambda:None)

    def test_candidate_precommit_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'completion_candidate.json';payload={'schema':'kdm6.synthetic33.completion_candidate.v1','status':'CANDIDATE_UNVERIFIED'}
            def reject():raise RuntimeError('changed input')
            with self.assertRaisesRegex(RuntimeError,'changed input'):witness33.publish_candidate(path,payload,time.monotonic()+5,reject)
            with self.assertRaisesRegex(RuntimeError,'expired'):witness33.publish_candidate(path,payload,time.monotonic()-1,lambda:None)
            self.assertFalse(path.exists())

    def test_after_link_fsync_failure_leaves_candidate_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'completion_candidate.json';payload={'schema':'kdm6.synthetic33.completion_candidate.v1','status':'CANDIDATE_UNVERIFIED'};original=witness33.os.fsync;calls=[]
            def fsync(fd):
                calls.append(fd)
                if len(calls)==2:raise OSError('directory fsync failure')
                return original(fd)
            with patch.object(witness33.os,'fsync',side_effect=fsync):
                with self.assertRaises(OSError):witness33.publish_candidate(path,payload,time.monotonic()+5,lambda:None)
            self.assertEqual(json.loads(path.read_text())['status'],'CANDIDATE_UNVERIFIED')


if __name__=='__main__':unittest.main()
