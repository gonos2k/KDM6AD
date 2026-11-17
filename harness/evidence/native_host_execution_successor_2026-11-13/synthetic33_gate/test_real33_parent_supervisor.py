"""Fake-only parent observation; no DSO, watchdog or physics execution."""
import hashlib
import json
import os
import stat
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import real33_parent_supervisor as parent


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ParentTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.out=self.root/'out';self.out.mkdir()
        self.registry_root=self.root/'registry';self.registry_root.mkdir()
        self.manifest=self.root/'manifest';self.manifest.write_text(json.dumps({'schema':'kdm6.synthetic33.private.v1','status':'REVIEWED_PINNED','attempt_registry_root':str(self.registry_root)}));self.digest=sha(self.manifest)
        self.config={'policy':{'wall_seconds':60,'cleanup_reserve_seconds':28}}

    def fake_run(self,out,manifest,digest):
        root=Path(out);nonce='a'*64;worker=23;watchdog=24
        identity={'run_nonce':nonce,'manifest_sha256':digest,'worker_pid':worker,'worker_start':[1,2],'watchdog_pid':watchdog,'watchdog_start':[3,4],'supervisor_pid':os.getpid(),'supervisor_start':list(parent.child.watchdog.process_start(os.getpid()))}
        armed={'status':'ARMED_UNVERIFIED',**identity};result={**identity,'exclusive_trace':{'path':str(root/'trace'),'sha256':hashlib.sha256(b'trace').hexdigest()}}
        for name,data in (('run_nonce',nonce),('trace','trace'),('armed.json',json.dumps(armed)),('armed.json.result',json.dumps(result)),('authority_consumed.json','marker'),('asset','asset')):(root/name).write_text(data)
        receipts={str(root/n):sha(root/n) for n in ('armed.json','armed.json.result','authority_consumed.json')}
        verified={'status':'EXECUTION_COMPLETED_ASSETS_ONLY','offline_replay':{'status':'INCONCLUSIVE','calls':33},'asset_sha256':{str(root/'asset'):sha(root/'asset')}}
        candidate={'schema':'kdm6.synthetic33.completion_candidate.v1','status':'CANDIDATE_UNVERIFIED','validated_assets':verified,'manifest_sha256':digest,'run_nonce':nonce,'worker_pid':worker,'worker_start':[1,2],'watchdog_pid':watchdog,'watchdog_start':[3,4],'receipt_sha256':receipts}
        (root/'completion_candidate.json').write_text(json.dumps(candidate));return candidate

    def patches(self,run=None):
        return (patch.object(parent,'REAL_PARENT_ENABLED',True),patch.object(parent.child.watchdog,'process_start',side_effect=lambda pid:(pid,1)),patch.object(parent.child,'reviewed_configuration',return_value=self.config),patch.object(parent.child,'run',side_effect=run or self.fake_run),patch.object(parent.child,'validate_consumed_marker',side_effect=lambda path,a,b:sha(path)),patch.object(parent.child,'validate_before_publication',side_effect=lambda out,*args:json.loads((Path(out)/'completion_candidate.json').read_text())['validated_assets']),patch.object(parent.replay33_assets,'replay',return_value={'status':'INCONCLUSIVE','calls':33}))

    def execute(self,run=None):
        from contextlib import ExitStack
        with ExitStack() as stack:
            for item in self.patches(run):stack.enter_context(item)
            return parent.run(self.out,self.manifest,self.digest)

    def test_default_blocked(self):
        with self.assertRaisesRegex(RuntimeError,'disabled'):parent.run(self.out,self.manifest,self.digest)

    def test_success_and_zero_exit_child_return(self):
        result=self.execute();self.assertEqual(result['status'],'PARENT_OBSERVED_ASSETS_ONLY')
        witness=json.loads((self.out/'parent_witness.json').read_text())
        self.assertEqual(witness['scientific_status'],'INCONCLUSIVE');self.assertEqual(witness['child_exit_code'],0)

    def test_directory_fsync_failure_retracts_published_witness(self):
        original=parent.os.fsync;failed=[False]
        def fail_once(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode) and (self.out/'parent_witness.json').exists() and not failed[0]:
                failed[0]=True;raise OSError('injected directory fsync failure')
            return original(fd)
        with patch.object(parent.os,'fsync',side_effect=fail_once):result=self.execute()
        self.assertTrue(failed[0]);self.assertEqual(result['status'],'UNWITNESSED')
        self.assertFalse((self.out/'parent_witness.json').exists())

    def test_temporary_unlink_failure_retracts_published_witness(self):
        original=parent.os.unlink;failed=[False]
        def fail_once(path,*args,**kwargs):
            if Path(path).name.startswith('.parent-witness.') and not failed[0]:
                failed[0]=True;raise OSError('injected temporary unlink failure')
            return original(path,*args,**kwargs)
        with patch.object(parent.os,'unlink',side_effect=fail_once):result=self.execute()
        self.assertTrue(failed[0]);self.assertEqual(result['status'],'UNWITNESSED')
        self.assertFalse((self.out/'parent_witness.json').exists())

    def test_failed_retraction_reports_uncertainty(self):
        original_unlink=parent.os.unlink
        def unlink(path,*args,**kwargs):
            if str(path).endswith('parent_witness.json'):raise OSError('injected unlink failure')
            return original_unlink(path,*args,**kwargs)
        original_fsync=parent.os.fsync;failed=[False]
        def fail_once(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode) and (self.out/'parent_witness.json').exists() and not failed[0]:
                failed[0]=True;raise OSError('injected directory fsync failure')
            return original_fsync(fd)
        with patch.object(parent.os,'fsync',side_effect=fail_once),patch.object(parent.os,'unlink',side_effect=unlink):result=self.execute()
        self.assertEqual(result['status'],'UNWITNESSED');self.assertIn('durability/cleanup uncertain',result['reason'])
        self.assertTrue((self.out/'parent_witness.json').exists())

    def test_attempt_registry_rejects_second_fresh_directory_before_fork(self):
        first=self.execute();self.assertEqual(first['status'],'PARENT_OBSERVED_ASSETS_ONLY')
        registry=self.registry_root/('.synthetic33-attempt-'+self.digest+'.json')
        record=json.loads(registry.read_text());self.assertEqual(record['manifest_sha256'],self.digest);self.assertEqual(record['output_dir'],str(self.out))
        self.assertEqual(stat.S_IMODE(registry.stat().st_mode),0o600)
        second=self.root/'second';second.mkdir()
        with patch.object(parent,'REAL_PARENT_ENABLED',True),patch.object(parent.child,'reviewed_configuration',return_value=self.config),patch.object(parent.os,'fork',side_effect=AssertionError('fork forbidden')):
            with self.assertRaises(FileExistsError):parent.run(second,self.manifest,self.digest)

    def test_identical_manifest_copy_shares_registry(self):
        self.assertEqual(self.execute()['status'],'PARENT_OBSERVED_ASSETS_ONLY')
        sibling=self.root/'sibling';sibling.mkdir();copy_path=sibling/'copy.json';copy_path.write_bytes(self.manifest.read_bytes())
        self.assertEqual(sha(copy_path),self.digest)
        second=self.root/'fresh';second.mkdir()
        with patch.object(parent,'REAL_PARENT_ENABLED',True),patch.object(parent.child,'reviewed_configuration',return_value=self.config),patch.object(parent.os,'fork',side_effect=AssertionError('fork forbidden')):
            with self.assertRaises(FileExistsError):parent.run(second,copy_path,self.digest)

    def test_unpinned_or_noncanonical_registry_root_rejected(self):
        for bad in (None,str(self.root/'missing'),'relative'):
            data={'schema':'kdm6.synthetic33.private.v1','status':'REVIEWED_PINNED','attempt_registry_root':bad}
            self.manifest.write_text(json.dumps(data));digest=sha(self.manifest)
            with patch.object(parent,'REAL_PARENT_ENABLED',True),patch.object(parent.child,'reviewed_configuration',return_value=self.config),patch.object(parent.os,'fork',side_effect=AssertionError('fork forbidden')):
                with self.assertRaises((ValueError,FileNotFoundError)):parent.run(self.out,self.manifest,digest)

    def test_interrupted_registration_permanently_blocks_retry(self):
        original=parent.os.fsync;failed=[False]
        def fail_file(fd):
            if stat.S_ISREG(os.fstat(fd).st_mode) and not failed[0]:failed[0]=True;raise OSError('interrupted attempt fsync')
            return original(fd)
        with patch.object(parent.os,'fsync',side_effect=fail_file):
            with self.assertRaisesRegex(OSError,'interrupted attempt'):self.execute()
        registry=self.registry_root/('.synthetic33-attempt-'+self.digest+'.json');self.assertTrue(registry.exists())
        other=self.root/'other';other.mkdir()
        with patch.object(parent,'REAL_PARENT_ENABLED',True),patch.object(parent.child,'reviewed_configuration',return_value=self.config),patch.object(parent.os,'fork',side_effect=AssertionError('fork forbidden')):
            with self.assertRaises(FileExistsError):parent.run(other,self.manifest,self.digest)

    def test_wrong_manifest_or_noncanonical_output_does_not_claim(self):
        with patch.object(parent,'REAL_PARENT_ENABLED',True),patch.object(parent.child,'reviewed_configuration',return_value=self.config),patch.object(parent.os,'fork',side_effect=AssertionError('fork forbidden')):
            with self.assertRaisesRegex(ValueError,'manifest'):parent.run(self.out,self.manifest,'f'*64)
            alias=self.root/'alias';alias.symlink_to(self.out,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'canonical'):parent.run(alias,self.manifest,self.digest)
        self.assertFalse((self.registry_root/('.synthetic33-attempt-'+self.digest+'.json')).exists())

    def test_nonzero_and_early_return_unwitnessed(self):
        def early(*_):return {'schema':'wrong','status':'CANDIDATE_UNVERIFIED'}
        self.assertEqual(self.execute(early)['status'],'UNWITNESSED')
        self.assertFalse((self.out/'parent_witness.json').exists())

    def test_candidate_nonce_tamper_fails_closed(self):
        def bad(*args):
            result=self.fake_run(*args);result['run_nonce']='b'*64
            (self.out/'completion_candidate.json').write_text(json.dumps(result));return result
        self.assertEqual(self.execute(bad)['status'],'UNWITNESSED')
        self.assertFalse((self.out/'parent_witness.json').exists())

    def test_candidate_bool_start_fails_closed(self):
        def bad(*args):
            result=self.fake_run(*args);result['worker_start']=[True,2]
            (self.out/'completion_candidate.json').write_text(json.dumps(result));return result
        self.assertEqual(self.execute(bad)['status'],'UNWITNESSED')
        self.assertFalse((self.out/'parent_witness.json').exists())

    def test_cleanup_unresolved_blocks_witness(self):
        def bad(*args):
            result=self.fake_run(*args);(self.out/'cleanup_unresolved.json').write_text('{}');return result
        self.assertEqual(self.execute(bad)['status'],'UNWITNESSED')
        self.assertFalse((self.out/'parent_witness.json').exists())

    def test_timeout_unwitnessed_without_worker_group_signal(self):
        self.config={'policy':{'wall_seconds':28.05,'cleanup_reserve_seconds':28}}
        def slow(*_):time.sleep(5)
        result=self.execute(slow)
        self.assertEqual(result['status'],'UNWITNESSED');self.assertEqual(result['cleanup'],'UNVERIFIED')
        self.assertFalse((self.out/'parent_witness.json').exists())


if __name__=='__main__':unittest.main()
