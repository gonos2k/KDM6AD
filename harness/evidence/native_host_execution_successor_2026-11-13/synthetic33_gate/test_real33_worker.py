import os,struct,tempfile,unittest
import ctypes as C
import threading
from unittest.mock import patch
import real33_worker as w
from fixture_plan import FIELDS,K,CENTER
from selector_manifest_spec_v1 import SELECTORS

def bits(x):return struct.unpack('=Q',struct.pack('=d',x))[0]
class FakeRunner:
    FAKE_ONLY_NO_CDLL=True
    graph_queries={'primal':0,'jvp':0,'vjp':0}
    def __init__(self,path):pass
    def _call(self,case,mode,x,v,selected,seq):
        p=x[FIELDS.index('nc')*K+CENTER]/1e8+x[FIELDS.index('th')*K+CENTER]
        out={'out':bytes(468*8),'rain':0}
        if mode=='capture_off_value':return out
        out.update(selector=('same',),primal=bits(p))
        if mode=='center_joint_graph':out.update(graph_flag=1,jvps=[.01,1.],dots=[.01,1.],jvp_statuses=[0,0],vjp_status=0,mask=257,grad_words=['0000000000000000']*624)
        else:out.update(conditions={('gate',):1},operands={})
        out['selectors']={name:{'status':'SPEC_ONLY','identity':dict(spec),'primal':bits(p),**({'graph_flag':out['graph_flag'],'jvps':out['jvps'],'dots':out['dots'],'jvp_statuses':out['jvp_statuses'],'vjp_status':out['vjp_status']} if mode=='center_joint_graph' else {})} for name,spec in SELECTORS.items()}
        if mode=='center_joint_graph':
            FakeRunner.graph_queries['primal']+=len(out['selectors']);FakeRunner.graph_queries['jvp']+=len(out['selectors'])*2;FakeRunner.graph_queries['vjp']+=len(out['selectors'])
        return out
class WorkerTest(unittest.TestCase):
    def test_fake_abi_graph_queries_and_cleanup(self):
        import graph_runner as gr
        class FakeABI:
            FAKE_ONLY_NO_CDLL=True
            def __init__(self,fail=False):self.events=[];self.closed=False;self.fail=fail;self.thread=threading.get_ident()
            def check(self,h,t,kind):
                self.assert_live(h,t);self.events.append(kind)
            def assert_live(self,h,t):
                if self.closed or h.value!=123 or t.value!=456 or threading.get_ident()!=self.thread:raise AssertionError('wrong handle/token/lifetime/thread')
            def kdm6_batch5_graph_primal_c(self,h,t,n,out,flag):
                self.check(h,t,'primal');C.cast(out,C.POINTER(C.c_uint64))[0]=bits(1.);C.cast(flag,C.POINTER(C.c_int))[0]=1;return 0
            def kdm6_batch5_intermediate_vjp_c(self,h,t,n,cot,grad,size,mask,status):
                self.check(h,t,'vjp');C.cast(mask,C.POINTER(C.c_uint16))[0]=65535;C.cast(status,C.POINTER(C.c_int))[0]=0
                for i in range(size):grad[i]=0.
                return 1 if self.fail else 0
            def kdm6_batch5_intermediate_jvp_c(self,h,t,n,seed,size,out,status):
                self.check(h,t,'jvp');C.cast(out,C.POINTER(C.c_double))[0]=0.;C.cast(status,C.POINTER(C.c_int))[0]=0;return 0
            def kdm6_handle_closep_c(self,p):
                self.events.append('close');self.closed=True;C.cast(p,C.POINTER(C.c_void_p))[0]=None;return 0
            def kdm6_batch5_clear_c(self):self.events.append('clear')
        for fail in (False,True):
            d=FakeABI(fail);h=C.c_void_p(123);token=C.c_uint64(456);vec=[[0.]*624,[0.]*624]
            try:
                if fail:
                    with self.assertRaisesRegex(RuntimeError,'VJP ABI'):gr.query_graph_set(d,h,token,[(str(i),{},i) for i in range(3)],vec)
                else:
                    self.assertEqual(len(gr.query_graph_set(d,h,token,[(str(i),{},i) for i in range(3)],vec)),3)
            finally:gr.release_capture(d,h)
            self.assertEqual(d.events[-2:],['close','clear'])
            if not fail:self.assertEqual({x:d.events.count(x) for x in ('primal','jvp','vjp')},{'primal':3,'jvp':6,'vjp':3})
            with self.assertRaises(AssertionError):d.assert_live(C.c_void_p(123),token)
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
    def test_missing_selector_continues_all_calls(self):
        class Missing(FakeRunner):
            def _call(self,case,mode,x,v,selected,seq):
                out=super()._call(case,mode,x,v,selected,seq)
                if mode!='capture_off_value':out['selectors']['a5_satadj.qc_final']={'status':'INCONCLUSIVE','reason':'missing or ambiguous full selector'}
                return out
        a,b=os.pipe();os.write(b,b'G');os.close(b)
        with tempfile.TemporaryDirectory() as t,patch.object(w,'preflight',return_value={'dso_path':'fake'}),patch.object(w,'Runner',Missing):
            result=w.run(a,t);self.assertEqual(result['calls'],33)
            rows=result['results'][0]['derivatives']
            self.assertEqual(len(rows),12)
            self.assertTrue(all(x['selector_status']=='INCONCLUSIVE' and x['fd_signal']=='UNAVAILABLE' for x in rows if x['selector']=='a5_satadj.qc_final'))
            self.assertTrue(any(x['selector_status']=='SPEC_ONLY' for x in rows if x['selector']=='nc_snap1.nc_before'))
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
    def test_duality_mismatch_survives_zero_fd(self):
        class Mismatch(FakeRunner):
            def _call(self,case,mode,x,v,selected,seq):
                out=super()._call(case,mode,x,v,selected,seq)
                if case=='baseline' and mode!='capture_off_value':
                    for entry in out['selectors'].values():entry['primal']=bits(1.)
                if case=='baseline' and mode=='center_joint_graph':out['jvps'][0]=.01;out['dots'][0]=3.
                return out
        a,b=os.pipe();os.write(b,b'G');os.close(b)
        with tempfile.TemporaryDirectory() as t,patch.object(w,'preflight',return_value={'dso_path':'fake'}),patch.object(w,'Runner',Mismatch):
            result=w.run(a,t);self.assertEqual(result['calls'],33)
            row=result['results'][0]['derivatives'][0]
            self.assertEqual((row['fd'],row['ad_duality'],row['fd_signal'],row['status']),(0.,'MISMATCH','UNDER_RESOLUTION','NUMERIC_MISMATCH'))
            self.assertEqual(row['two_step_stability'],'UNKNOWN')
    def test_two_step_fd_instability_reported(self):
        class Unstable(FakeRunner):
            def _call(self,case,mode,x,v,selected,seq):
                out=super()._call(case,mode,x,v,selected,seq)
                if case=='baseline' and mode!='capture_off_value':
                    for entry in out['selectors'].values():entry['primal']=bits({5:1.001,7:1.02}.get(seq,1.))
                return out
        a,b=os.pipe();os.write(b,b'G');os.close(b)
        with tempfile.TemporaryDirectory() as t,patch.object(w,'preflight',return_value={'dso_path':'fake'}),patch.object(w,'Runner',Unstable):
            result=w.run(a,t);self.assertEqual(result['calls'],33)
            self.assertEqual([row['two_step_stability'] for row in result['results'][0]['derivatives'] if row['selector']=='nc_snap1.nc_before' and row['direction']=='nc'],['UNSTABLE','UNSTABLE'])
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
        FakeRunner.graph_queries={'primal':0,'jvp':0,'vjp':0}
        a,b=os.pipe();os.write(b,b'G');os.close(b)
        with tempfile.TemporaryDirectory() as t, patch.object(w,'preflight',return_value={'dso_path':'fake'}),patch.object(w,'Runner',FakeRunner):
            result=w.run(a,t)
            self.assertEqual(result['status'],'INCONCLUSIVE');self.assertEqual(result['calls'],33)
            self.assertEqual(FakeRunner.graph_queries,{'primal':9,'jvp':18,'vjp':9})
            row=result['results'][0]['derivatives'][0]
            self.assertEqual((row['ad_duality'],row['recorded_branch_schedule']),('CONSISTENT','STABLE'))
            import pathlib,json
            rows=[json.loads(x) for x in (pathlib.Path(t)/'calls.jsonl').read_text().splitlines()]
            self.assertEqual(len(rows),66);self.assertEqual(rows[0]['state'],'STARTED');self.assertEqual(rows[-1]['state'],'COMPLETED')
if __name__=='__main__':unittest.main()
