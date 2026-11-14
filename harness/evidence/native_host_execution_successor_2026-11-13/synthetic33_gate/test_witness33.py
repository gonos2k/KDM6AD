import json,os,pathlib,tempfile,unittest
from unittest.mock import patch
import fixture33,real33_worker as w,witness33 as z
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
if __name__=='__main__':unittest.main()
