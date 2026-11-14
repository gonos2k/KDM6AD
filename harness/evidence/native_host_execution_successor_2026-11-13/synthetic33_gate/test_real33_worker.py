import os,struct,tempfile,unittest
from unittest.mock import patch
import real33_worker as w
from fixture_plan import FIELDS,K,CENTER

def bits(x):return struct.unpack('=Q',struct.pack('=d',x))[0]
class FakeRunner:
    FAKE_ONLY_NO_CDLL=True
    def __init__(self,path):pass
    def _call(self,case,mode,x,v,selected,seq):
        p=x[FIELDS.index('nc')*K+CENTER]/1e8+x[FIELDS.index('th')*K+CENTER]
        out={'out':bytes(468*8),'rain':0}
        if mode=='capture_off_value':return out
        out.update(selector=('same',),primal=bits(p))
        if mode=='center_joint_graph':out.update(graph_flag=1,jvps=[.01,1.],dots=[.01,1.],jvp_statuses=[0,0],vjp_status=0,mask=257,grad_words=['0000000000000000']*624)
        else:out.update(conditions={('gate',):1},operands={})
        return out
class WorkerTest(unittest.TestCase):
    def test_direct_runner_and_private_call_are_disabled(self):
        from graph_runner import Runner
        with patch('ctypes.CDLL',side_effect=AssertionError('no DSO load')):
            with self.assertRaisesRegex(RuntimeError,'hard-disabled'):Runner('/arbitrary')
            with self.assertRaisesRegex(RuntimeError,'hard-disabled'):object.__new__(Runner)._call('x','x',[],[],None,1)
    def test_direct_entry_is_disabled_without_loading(self):
        import real33_entry as e
        ready_r,ready_w=os.pipe();release_r,release_w=os.pipe()
        try:
            with tempfile.TemporaryDirectory() as t,patch.dict(os.environ,{'RESEARCH_READY_FD':str(ready_w),'RESEARCH_RELEASE_FD':str(release_r),'RESEARCH_OUTDIR':t},clear=True),patch('ctypes.CDLL',side_effect=AssertionError('no DSO load')):
                with self.assertRaisesRegex(RuntimeError,'hard-disabled'):e.main()
        finally:
            for fd in (ready_r,ready_w,release_r,release_w):
                try:os.close(fd)
                except OSError:pass
    def test_direct_worker_is_disabled_before_load_or_release(self):
        with patch('ctypes.CDLL',side_effect=AssertionError('no DSO load')):
            with self.assertRaisesRegex(RuntimeError,'hard-disabled'):w.run(-1,'/missing')
    def test_no_release_prevents_preflight_and_load(self):
        a,b=os.pipe();os.close(b)
        with tempfile.TemporaryDirectory() as t, patch.object(w,'Runner',FakeRunner),patch.object(w,'preflight',side_effect=AssertionError('must not load')):
            with self.assertRaisesRegex(RuntimeError,'release'):w.run(a,t)
        os.close(a)
    def test_unconnected_direction_continues_as_unresolved(self):
        class Unconnected(FakeRunner):
            def _call(self,case,mode,x,v,selected,seq):
                out=super()._call(case,mode,x,v,selected,seq)
                if case=='baseline' and mode=='center_joint_graph':out['jvp_statuses'][0]=2
                return out
        a,b=os.pipe();os.write(b,b'G');os.close(b)
        with tempfile.TemporaryDirectory() as t,patch.object(w,'preflight',return_value={'dso_path':'fake'}),patch.object(w,'Runner',Unconnected):
            result=w.run(a,t);self.assertEqual(result['calls'],33)
            self.assertEqual(result['results'][0]['derivatives'][0]['status'],'UNRESOLVED')
    def test_zero_signal_continues_as_unresolved(self):
        class Zero(FakeRunner):
            def _call(self,case,mode,x,v,selected,seq):
                out=super()._call(case,mode,x,v,selected,seq)
                if case=='baseline' and mode=='center_joint_graph':out['jvps'][0]=0.;out['dots'][0]=0.
                return out
        a,b=os.pipe();os.write(b,b'G');os.close(b)
        with tempfile.TemporaryDirectory() as t,patch.object(w,'preflight',return_value={'dso_path':'fake'}),patch.object(w,'Runner',Zero):
            result=w.run(a,t);self.assertEqual(result['calls'],33)
            self.assertEqual(result['results'][0]['derivatives'][0]['status'],'UNRESOLVED')
    def test_zero_and_crossing_do_not_abort_fixed_inventory(self):
        class ZeroCross(FakeRunner):
            def _call(self,case,mode,x,v,selected,seq):
                out=super()._call(case,mode,x,v,selected,seq)
                if case=='baseline' and mode=='center_joint_graph':out['jvps'][0]=0.;out['dots'][0]=0.
                if case=='baseline' and mode=='capture_on_value' and seq>3:out['conditions']={('changed',):1}
                return out
        a,b=os.pipe();os.write(b,b'G');os.close(b)
        with tempfile.TemporaryDirectory() as t,patch.object(w,'preflight',return_value={'dso_path':'fake'}),patch.object(w,'Runner',ZeroCross):
            result=w.run(a,t);self.assertEqual(result['calls'],33)
            statuses=[d['status'] for d in result['results'][0]['derivatives']]
            self.assertIn('BRANCH_CROSSING',statuses)
    def test_mock_full_33_slot_journal(self):
        a,b=os.pipe();os.write(b,b'G');os.close(b)
        with tempfile.TemporaryDirectory() as t, patch.object(w,'preflight',return_value={'dso_path':'fake'}),patch.object(w,'Runner',FakeRunner):
            result=w.run(a,t)
            self.assertEqual(result['status'],'INCONCLUSIVE');self.assertEqual(result['calls'],33)
            import pathlib,json
            rows=[json.loads(x) for x in (pathlib.Path(t)/'calls.jsonl').read_text().splitlines()]
            self.assertEqual(len(rows),66);self.assertEqual(rows[0]['state'],'STARTED');self.assertEqual(rows[-1]['state'],'COMPLETED')
if __name__=='__main__':unittest.main()
