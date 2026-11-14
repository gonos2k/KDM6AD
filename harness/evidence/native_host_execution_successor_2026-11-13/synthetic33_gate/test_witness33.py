import copy,json,os,pathlib,sys,tempfile,unittest
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
    def test_loader_rejects_short_wrong_pid_and_unclassified_lines(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d);image=(root/'fake').resolve();image.write_bytes(b'x');log=root/'trace'
            for data in (f'dyld[1]: <A-0> {image}\n',f'dyld[2]: <A-0> {image}\n','dyld[1]: unexpected something\n'):
                log.write_text(data)
                with self.assertRaises(ValueError):z.checked_loader(log,{str(image):sha(image)},[str(image)],1,{})
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
            scripts=('fixture_plan.py','fixture33.py','graph_runner.py','real33_worker.py','real33_entry.py','real33_contract.py','real33_supervisor_draft.py','real33_orchestrate.py','witness33.py','trace33.py','freeze33.py','fake_watchdog/watchdog.py')
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
