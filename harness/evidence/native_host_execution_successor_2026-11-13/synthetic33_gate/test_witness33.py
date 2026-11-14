import copy,hashlib,json,os,pathlib,struct,sys,tempfile,unittest
from unittest.mock import patch
import fixture33,real33_worker as w,witness33 as z,real33_contract,freeze33
from test_real33_worker import FakeRunner
from real33_contract import sha
class WitnessTest(unittest.TestCase):
    def make(self,root):
        a,b=os.pipe();os.write(b,b'G');os.close(b)
        with patch.object(w,'preflight',return_value={'dso_path':'fake'}),patch.object(w,'Runner',FakeRunner):r=w.run(a,root)
        (root/'worker_result.json').write_text(json.dumps(r))
        images=[]
        for i in range(5):
            image=(root/f'fake{i}.dylib').resolve();image.write_bytes(f'fake{i}'.encode());images.append(image)
        log=root/'loader.log';log.write_text(''.join(f'dyld[1]: <A000-{i}> {image}\n' for i,image in enumerate(images)))
        status={'status':'INCOMPLETE','reason':'worker_exit','cleanup_errors':[],'signals':[],'worker_wait_status':0,'peak_group_rss_kib':1,'released':True,'worker_pid':1,'worker_reaped_pid':1}
        return status,{str(image):sha(image) for image in images},[str(image) for image in images],log
    def test_full_fake_only_and_partial_asset(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d);status,allowed,required,log=self.make(root)
            result=z.validate(root,status,10,fixture33.plan(),allowed,required,log,{})
            self.assertEqual(result['status'],'EXECUTION_COMPLETED_ASSETS_ONLY');self.assertEqual(result['forwards'],33)
            (root/'call_01.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'asset'):z.validate(root,status,10,fixture33.plan(),allowed,required,log,{})
    def test_three_selector_payloads_and_mutations(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d);self.make(root)
            _,assets=z.checked_journal(root,fixture33.plan())
            self.assertEqual(z.checked_results(assets),{'graph_primal':9,'jvp':18,'vjp':9})
            graph=next(x for x in assets if x['slot']['mode']=='center_joint_graph')
            self.assertNotIn('selector',graph['result']);self.assertNotIn('primal',graph['result'])
            name='a5_satadj.qc_final'
            missing=copy.deepcopy(assets);r=next(x['result'] for x in missing if x['slot']['mode']=='center_joint_graph')
            r['selectors'][name]={'status':'INCONCLUSIVE','reason':'missing or ambiguous full selector'}
            r['query_counts']={'graph_primal':2,'jvp':4,'vjp':2}
            self.assertEqual(z.checked_results(missing),{'graph_primal':8,'jvp':16,'vjp':8})
            unconnected=copy.deepcopy(assets);r=next(x['result'] for x in unconnected if x['slot']['mode']=='center_joint_graph')
            e=r['selectors'][name];e['graph_flag']=0;e['vjp_status']=1;e['mask']=0;e['jvp_statuses']=[1,1];e['jvps']=[0.,0.];e['dots']=[0.,0.]
            self.assertEqual(z.checked_results(unconnected),{'graph_primal':9,'jvp':18,'vjp':9})
            e['graph_flag']=1;e['vjp_status']=2;e['jvp_statuses']=[2,2]
            self.assertEqual(z.checked_results(unconnected),{'graph_primal':9,'jvp':18,'vjp':9})
            e['vjp_status']=0;e['mask']=256;e['jvp_statuses']=[0,2];e['jvps']=[.01,-0.];e['dots']=[.01,-0.]
            self.assertEqual(z.checked_results(unconnected),{'graph_primal':9,'jvp':18,'vjp':9})
            for key in ('jvps','dots'):
                bad=copy.deepcopy(unconnected);r=next(x['result'] for x in bad if x['slot']['mode']=='center_joint_graph')
                r['selectors'][name][key][1]=1.0
                with self.subTest(unconnected_value=key),self.assertRaisesRegex(ValueError,'nonzero unconnected direction'):z.checked_results(bad)
            for mutation in ('missing_selector','bad_identity','bad_query_count','bool_count','bad_status','bad_gradient','legacy_field','unexpected_field','bad_reason','disconnected_contradiction','connected_zero_mask','unconnected_nonzero_mask','unconnected_nonzero_jvp','wrong_direction_status','connected_no_graph_jvp','undefined_gradient','condition_garbage','condition_duplicate','condition_counter_overflow','absence_flag'):
                bad=copy.deepcopy(assets);r=next(x['result'] for x in bad if x['slot']['mode']=='center_joint_graph')
                if mutation=='missing_selector':del r['selectors'][name]
                if mutation=='bad_identity':r['selectors'][name]['identity']['outer_loop']+=1
                if mutation=='bad_query_count':r['query_counts']['jvp']-=1
                if mutation=='bool_count':r['query_counts']['jvp']=True
                if mutation=='bad_status':r['selectors'][name]['vjp_status']=True
                if mutation=='bad_gradient':r['selectors'][name]['grad_words'].pop()
                if mutation=='legacy_field':r['primal']=1
                if mutation=='unexpected_field':r['extra']='unknown'
                if mutation=='bad_reason':r['selectors'][name]={'status':'INCONCLUSIVE','reason':'invented'}
                if mutation=='disconnected_contradiction':r['selectors'][name]['graph_flag']=0
                if mutation=='connected_zero_mask':r['selectors'][name]['mask']=0
                if mutation=='unconnected_nonzero_mask':r['selectors'][name]['vjp_status']=2
                if mutation=='unconnected_nonzero_jvp':r['selectors'][name]['vjp_status']=2;r['selectors'][name]['mask']=0
                if mutation=='wrong_direction_status':r['selectors'][name]['jvp_statuses']=[2,2]
                if mutation=='connected_no_graph_jvp':r['selectors'][name]['jvp_statuses'][0]=1
                if mutation=='undefined_gradient':r['selectors'][name]['grad_words'][39]=struct.pack('=d',1.).hex()
                if mutation in ('condition_garbage','condition_duplicate','condition_counter_overflow','absence_flag'):
                    on=next(x['result'] for x in bad if x['slot']['mode']=='capture_on_value')
                    if mutation=='condition_garbage':on['conditions']=['garbage']
                    if mutation=='condition_duplicate':on['conditions'].append(copy.deepcopy(on['conditions'][0]))
                    if mutation=='condition_counter_overflow':on['conditions'][0]['identity'][4]=2**64
                    if mutation=='absence_flag':on['unverified_absence']=True
                with self.subTest(mutation=mutation),self.assertRaises(ValueError):z.checked_results(bad)
    def test_loader_rejects_short_wrong_pid_and_unclassified_lines(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d);image=(root/'fake').resolve();image.write_bytes(b'x');log=root/'trace'
            for data in (f'dyld[1]: <A-0> {image}\n',f'dyld[2]: <A-0> {image}\n','dyld[1]: unexpected something\n'):
                log.write_text(data)
                with self.assertRaises(ValueError):z.checked_loader(log,{str(image):sha(image)},[str(image)],1,{})
    def test_rehashed_nonfinite_and_bool_identity_rejected(self):
        for mutation in ('output_nan','rain_inf','gradient_nan','identity_bool'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as d:
                root=pathlib.Path(d);self.make(root)
                path=root/'call_03.json';obj=json.loads(path.read_bytes());r=obj['result']
                if mutation=='output_nan':r['out']=struct.pack('=d',float('nan')).hex()+r['out'][16:]
                if mutation=='rain_inf':r['rain']=struct.unpack('=Q',struct.pack('=d',float('inf')))[0]
                if mutation=='gradient_nan':r['selectors']['nc_snap1.nc_before']['grad_words'][0]=struct.pack('=d',float('nan')).hex()
                if mutation=='identity_bool':r['selectors']['nc_snap1.nc_before']['identity']['one_step_call']=True
                data=json.dumps(obj,sort_keys=True,separators=(',',':')).encode('ascii');path.write_bytes(data)
                journal=root/'calls.jsonl';events=[json.loads(x) for x in journal.read_text().splitlines()]
                events[5]['bytes']=len(data);events[5]['asset_sha256']=hashlib.sha256(data).hexdigest()
                journal.write_text(''.join(json.dumps(e)+'\n' for e in events))
                _,assets=z.checked_journal(root,fixture33.plan())
                with self.assertRaises(ValueError):z.checked_results(assets)
    def test_loader_mismatch_and_resource_fail(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d);status,allowed,required,log=self.make(root)
            with self.assertRaisesRegex(ValueError,'loaded image'):z.validate(root,status,10,fixture33.plan(),{},required,log,{})
            with self.assertRaisesRegex(ValueError,'resource'):z.validate(root,status,901,fixture33.plan(),allowed,required,log,{})
    def test_actual_preflight_freeze_and_witness_bind_dso_path(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d).resolve();status,allowed,required,log=self.make(root)
            dso=required[0];other=root/'other.dylib';other.write_bytes(pathlib.Path(dso).read_bytes())
            assets=dict(allowed);assets[str(other)]=sha(other)
            scripts=real33_contract.EXECUTION_SOURCE_FILES
            source=pathlib.Path(real33_contract.__file__).resolve().parent
            for name in scripts:
                path=(source/name).resolve(strict=True);assets[str(path)]=sha(path)
            interpreter=str(pathlib.Path(sys.executable).resolve(strict=True));assets[interpreter]=sha(interpreter)
            system={f'/usr/lib/fake_{i}':'ABCD-01' for i in range(596)}
            with open(log,'a') as stream:
                for path,uuid in system.items():stream.write(f'dyld[1]: <{uuid}> {path}\n')
                for _ in range(866):stream.write('dyld[1]: move loaded to delayed: fake\n')
            manifest={'schema':'kdm6.synthetic33.private.v1','status':'REVIEWED_PINNED','slots':fixture33.validate(),'assets':assets,'interpreter':interpreter,'dso_path':dso,'dso_sha256':allowed[dso],'approved_loaded_images':allowed,'required_loaded_images':required,'torch_prior_pins':{p:allowed[p] for p in required[1:]},'system_cache_baseline':system,'loader_status_line_count':866}
            path=root/'manifest.json'
            def check(m,success):
                path.write_text(json.dumps(m,sort_keys=True));digest=sha(path);status['manifest_sha256']=digest;status['dyld_trace_enabled']=True
                with patch.dict(os.environ,{'RESEARCH_PRIVATE_MANIFEST':str(path),'RESEARCH_MANIFEST_SHA256':digest}):
                    if success:
                        self.assertEqual(real33_contract.preflight()['dso_path'],dso)
                        freeze33.validate_frozen(path,digest)
                        self.assertEqual(z.validate_pinned(root,status,10,path,digest,log)['status'],'EXECUTION_COMPLETED_ASSETS_ONLY')
                    else:
                        for fn in (real33_contract.preflight,lambda:freeze33.validate_frozen(path,digest),lambda:z.validate_pinned(root,status,10,path,digest,log)):
                            with self.assertRaises(ValueError):fn()
            check(manifest,True)
            wrong=copy.deepcopy(manifest);wrong['dso_path']=str(other);check(wrong,False)
            wrong=copy.deepcopy(manifest);wrong['dso_sha256']=allowed[required[1]];check(wrong,False)
            wrong=copy.deepcopy(manifest);wrong['required_loaded_images']=required[1:];check(wrong,False)
            wrong=copy.deepcopy(manifest);wrong['approved_loaded_images'].pop(dso);check(wrong,False)
if __name__=='__main__':unittest.main()
