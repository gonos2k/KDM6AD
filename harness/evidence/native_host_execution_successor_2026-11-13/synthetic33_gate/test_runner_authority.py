"""Fake-only authority and ABI wiring checks; never load a DSO."""
import os
import json
import pathlib
import tempfile
import threading
import unittest
from unittest.mock import patch
import fixture33
import graph_runner as gr
import real33_orchestrate as orchestrate

def arm(root,manifest_sha):
    receipt={'status':'ARMED_UNVERIFIED','run_nonce':'a'*64,'manifest_sha256':manifest_sha,
        'worker_pid':os.getpid(),'worker_start':[1,2],'watchdog_pid':os.getppid(),'watchdog_start':[1,2],
        'supervisor_pid':max(os.getpid(),os.getppid())+100000,'supervisor_start':[1,2]}
    (root/'armed.json').write_text(json.dumps(receipt));return receipt

class Function:
    def __init__(self,name,events):self.name=name;self.events=events
    def __call__(self,*args):
        self.events.append(self.name)
        return 1 if self.name=='kdm6_batch5_begin_c' else 0
class FakeCDLL:
    def __init__(self):self.events=[];self.functions={}
    def __getattr__(self,name):
        if name not in self.functions:self.functions[name]=Function(name,self.events)
        return self.functions[name]

class AuthorityTests(unittest.TestCase):
    def setUp(self):
        self.enabled=patch.object(orchestrate,'REAL33_RELEASE_ENABLED',True)
        self.enabled.start();self.addCleanup(self.enabled.stop)
    def test_default_off_rejects_fake_release_before_marker(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(orchestrate,'REAL33_RELEASE_ENABLED',False),patch.object(gr.C,'CDLL') as loader:
            a,b=os.pipe();os.write(b,b'G');os.close(b)
            with self.assertRaisesRegex(RuntimeError,'hard-disabled'):gr.issue_authority(a,tmp)
            self.assertFalse((pathlib.Path(tmp)/gr.MARKER_NAME).exists());loader.assert_not_called()
    def test_armed_binding_and_exclusive_replay(self):
        for mutation in ('missing','nonce','manifest','worker','parent','start','replay'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                root=pathlib.Path(tmp);manifest=root/'manifest';manifest.write_text('pinned');dso=root/'fake';dso.write_bytes(b'x');(root/'run_nonce').write_text('a'*64)
                contract={'dso_path':str(dso),'dso_sha256':gr.sha(dso),'calls':fixture33.plan()}
                env={'RESEARCH_PRIVATE_MANIFEST':str(manifest),'RESEARCH_MANIFEST_SHA256':gr.sha(manifest)}
                receipt=arm(root,env['RESEARCH_MANIFEST_SHA256'])
                if mutation=='missing':(root/'armed.json').unlink()
                elif mutation!='replay':
                    if mutation=='nonce':receipt['run_nonce']='b'*64
                    if mutation=='manifest':receipt['manifest_sha256']='b'*64
                    if mutation=='worker':receipt['worker_pid']+=1
                    if mutation=='parent':receipt['watchdog_pid']+=1
                    if mutation=='start':receipt['worker_start']=[1,3]
                    (root/'armed.json').write_text(json.dumps(receipt))
                with patch.dict(os.environ,env),patch.object(gr,'preflight',return_value=contract),patch.object(gr,'process_start',return_value=(1,2)),patch.object(gr.C,'CDLL') as loader:
                    if mutation=='replay':
                        a,b=os.pipe();os.write(b,b'G');os.close(b);gr.issue_authority(a,root)
                    a,b=os.pipe();os.write(b,b'G');os.close(b)
                    with self.assertRaises((RuntimeError,OSError)):gr.issue_authority(a,root)
                    loader.assert_not_called()
    def test_release_preflight_load_order_and_begin_failure_clear(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);manifest=root/'manifest';manifest.write_text('pinned');dso=root/'fake.dylib';dso.write_bytes(b'not-a-library');(root/'run_nonce').write_text('a'*64)
            manifest_sha=gr.sha(manifest);contract={'dso_path':str(dso),'dso_sha256':gr.sha(dso),'calls':fixture33.plan()}
            arm(root,manifest_sha)
            env={'RESEARCH_PRIVATE_MANIFEST':str(manifest),'RESEARCH_MANIFEST_SHA256':manifest_sha}
            fake=FakeCDLL();a,b=os.pipe();os.write(b,b'G');os.close(b)
            with patch.dict(os.environ,env),patch.object(gr,'preflight',return_value=contract),patch.object(gr,'process_start',return_value=(1,2)),patch.object(gr.C,'CDLL',return_value=fake) as loader:
                authority=gr.issue_authority(a,root);loader.assert_not_called()
                marker=json.loads((root/gr.MARKER_NAME).read_text())
                self.assertEqual(marker['schema'],gr.MARKER_SCHEMA)
                self.assertEqual(marker['worker_pid'],os.getpid())
                runner=gr.Runner(authority);loader.assert_called_once_with(str(dso))
                with self.assertRaisesRegex(RuntimeError,'begin'):
                    runner._call('baseline','capture_off_value',fixture33.center('baseline'),fixture33.direction('nc'),None,1)
                self.assertEqual(fake.events,['kdm6_batch5_begin_c','kdm6_batch5_clear_c'])
                with self.assertRaisesRegex(RuntimeError,'hard-disabled'):gr.Runner(authority)
    def test_no_release_or_changed_nonce_cannot_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);manifest=root/'manifest';manifest.write_text('pinned');dso=root/'fake';dso.write_bytes(b'x');nonce=root/'run_nonce';nonce.write_text('a'*64)
            contract={'dso_path':str(dso),'dso_sha256':gr.sha(dso),'calls':fixture33.plan()}
            env={'RESEARCH_PRIVATE_MANIFEST':str(manifest),'RESEARCH_MANIFEST_SHA256':gr.sha(manifest)}
            arm(root,env['RESEARCH_MANIFEST_SHA256'])
            with patch.dict(os.environ,env),patch.object(gr,'preflight',return_value=contract),patch.object(gr,'process_start',return_value=(1,2)),patch.object(gr.C,'CDLL') as loader:
                a,b=os.pipe();os.close(b)
                with self.assertRaisesRegex(RuntimeError,'release'):gr.issue_authority(a,root)
                a,b=os.pipe();os.write(b,b'G');os.close(b);authority=gr.issue_authority(a,root)
                nonce.write_text('b'*64)
                with self.assertRaisesRegex(RuntimeError,'pin changed'):gr.Runner(authority)
                loader.assert_not_called()
    def test_manifest_dso_and_thread_pins_fail_before_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);manifest=root/'manifest';manifest.write_text('pinned');dso=root/'fake';dso.write_bytes(b'x');(root/'run_nonce').write_text('a'*64)
            contract={'dso_path':str(dso),'dso_sha256':gr.sha(dso),'calls':fixture33.plan()}
            env={'RESEARCH_PRIVATE_MANIFEST':str(manifest),'RESEARCH_MANIFEST_SHA256':gr.sha(manifest)}
            arm(root,env['RESEARCH_MANIFEST_SHA256'])
            with patch.dict(os.environ,env),patch.object(gr,'process_start',return_value=(1,2)),patch.object(gr.C,'CDLL') as loader:
                a,b=os.pipe();os.write(b,b'G');os.close(b)
                with patch.object(gr,'preflight',side_effect=ValueError('unreviewed manifest')):
                    with self.assertRaisesRegex(ValueError,'unreviewed'):gr.issue_authority(a,root)
                with patch.object(gr,'preflight',return_value=contract):
                    a,b=os.pipe();os.write(b,b'G');os.close(b);authority=gr.issue_authority(a,root)
                    errors=[]
                    def wrong_thread():
                        try:gr.Runner(authority)
                        except RuntimeError as exc:errors.append(str(exc))
                    t=threading.Thread(target=wrong_thread);t.start();t.join()
                    self.assertEqual(errors,['authority process/thread'])
                    with patch.object(gr.os,'getpid',return_value=authority.pid+1):
                        with self.assertRaisesRegex(RuntimeError,'process/thread'):gr.Runner(authority)
                    dso.write_bytes(b'changed')
                    with self.assertRaisesRegex(RuntimeError,'pin changed'):gr.Runner(authority)
                loader.assert_not_called()
if __name__=='__main__':unittest.main()
