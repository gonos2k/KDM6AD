import json,pathlib,tempfile,unittest,os
from unittest.mock import patch
import sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
import real33_orchestrate as x
class TestOrchestrate(unittest.TestCase):
    def test_disabled_before_preflight_or_fork(self):
        with patch.object(x.freeze33,'validate_frozen',side_effect=AssertionError('preflight should not run')),patch.object(x.os,'fork',side_effect=AssertionError('fork should not run')):
            with self.assertRaisesRegex(RuntimeError,'disabled'):x.run('/missing','/missing','0'*64)
    def test_enabled_collision_fails_before_release(self):
        with tempfile.TemporaryDirectory() as d,patch.object(x,'REAL33_RELEASE_ENABLED',True),patch.object(x.os,'fork',side_effect=AssertionError('must not fork')):
            pathlib.Path(d,'stale').write_text('stale')
            with self.assertRaisesRegex(RuntimeError,'empty'):x.run(d,'/unused','0'*64)
    def test_enabled_fake_actual_worker_reaches_witness_gate(self):
        original=x.watchdog.supervise
        def fake_supervise(supervisor,identity,life,release,ready,receipt,scenario,**kwargs):
            nonce=kwargs.pop('run_nonce');manifest=kwargs.pop('manifest_sha');kwargs.pop('manifest_path')
            x.watchdog.group_rss_kib=lambda pid:1024
            kwargs['fake_ready_timeout']=15
            result=original(supervisor,identity,life,release,ready,receipt,'fixture33_exec_mock',**kwargs)
            result.update(run_nonce=nonce,manifest_sha256=manifest,watchdog_pid=os.getpid())
            path=pathlib.Path(receipt+'.result');path.write_text(json.dumps(result))
            return result
        with tempfile.TemporaryDirectory() as d,patch.object(x,'REAL33_RELEASE_ENABLED',True),patch.object(x.freeze33,'validate_frozen'),patch.object(x.watchdog,'supervise',side_effect=fake_supervise),patch.object(x.witness33,'validate_pinned',return_value={'status':'FAKE_ONLY'}):
            with self.assertRaisesRegex(RuntimeError,'publication disabled'):x.run(d,'/unused','a'*64)
            rows=pathlib.Path(d,'calls.jsonl').read_text().splitlines()
            self.assertEqual(len(rows),66);self.assertFalse(pathlib.Path(d,'witness.json').exists())
    def test_signal_at_readiness_prevents_release(self):
        owner=os.getpid();original_supervise=x.watchdog.supervise;original_select=x.select.select
        def fake_supervise(supervisor,identity,life,release,ready,receipt,scenario,**kwargs):
            kwargs.pop('run_nonce');kwargs.pop('manifest_sha');kwargs.pop('manifest_path')
            x.watchdog.group_rss_kib=lambda pid:1024
            kwargs['fake_ready_timeout']=15
            return original_supervise(supervisor,identity,life,release,ready,receipt,'fixture33_exec_mock',**kwargs)
        def readiness_signal(*args,**kwargs):
            value=original_select(*args,**kwargs)
            if os.getpid()==owner and value[0]:os.kill(owner,x.signal.SIGTERM)
            return value
        with tempfile.TemporaryDirectory() as d,patch.object(x,'REAL33_RELEASE_ENABLED',True),patch.object(x.freeze33,'validate_frozen'),patch.object(x.watchdog,'supervise',side_effect=fake_supervise),patch.object(x.select,'select',side_effect=readiness_signal):
            with self.assertRaisesRegex(RuntimeError,'before worker release'):x.run(d,'/unused','a'*64)
            self.assertFalse(pathlib.Path(d,'calls.jsonl').exists())
            self.assertFalse(pathlib.Path(d,'witness.json').exists())
    def test_supervise_exception_is_nonzero_and_durable(self):
        with tempfile.TemporaryDirectory() as d,patch.object(x,'REAL33_RELEASE_ENABLED',True),patch.object(x.freeze33,'validate_frozen'),patch.object(x.watchdog,'supervise',side_effect=RuntimeError('injected supervisor failure')):
            with self.assertRaisesRegex(RuntimeError,'not armed'):x.run(d,'/unused','0'*64)
            failure=json.loads(pathlib.Path(d,'watchdog_failure.json').read_text())
            self.assertEqual(failure['status'],'INCOMPLETE');self.assertIn('injected supervisor failure',failure['error'])
            self.assertFalse(pathlib.Path(d,'witness.json').exists())
if __name__=='__main__':unittest.main()
