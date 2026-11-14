import json, os, pathlib, signal, tempfile, time, unittest, subprocess
import watchdog
import sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
import witness33,fixture33
from real33_contract import sha
from unittest.mock import patch

class WatchdogTest(unittest.TestCase):
    def harness(self,scenario,action,final_signal=False,timeout=20,max_rss_kib=8*1024*1024,fake_ready_timeout=15.0,fake_post_release_timeout=None):
        with tempfile.TemporaryDirectory() as t:
            life_r,life_w=os.pipe(); ready_r,ready_w=os.pipe(); rel_r,rel_w=os.pipe()
            sup=os.fork()
            if sup==0:
                os.close(life_r);os.close(ready_r);os.close(ready_w);os.close(rel_r);os.close(rel_w)
                while True:time.sleep(1)
            os.close(life_w)
            dog=os.fork()
            if dog==0:
                # Deterministic fake RSS; timeout/error path has its own test.
                watchdog.group_rss_kib=lambda pid:1024
                os.close(ready_r);os.close(rel_w)
                if final_signal:
                    old=watchdog.atomic
                    def injected(path,value):
                        if str(path).endswith('.result'):
                            os.kill(os.getpid(),signal.SIGTERM);os.kill(os.getpid(),signal.SIGTERM)
                        old(path,value)
                    watchdog.atomic=injected
                try: watchdog.supervise(sup,watchdog.process_start(sup),life_r,rel_r,ready_w,str(pathlib.Path(t)/'armed.json'),scenario,timeout=timeout,max_rss_kib=max_rss_kib,mock_outdir=t,fake_ready_timeout=fake_ready_timeout,fake_post_release_timeout=fake_post_release_timeout)
                except BaseException:
                    import traceback;traceback.print_exc();os._exit(1)
                os._exit(0)
            os.close(life_r);os.close(ready_w);os.close(rel_r)
            try:
                self.assertEqual(os.read(ready_r,1),b'R')
                action(sup,dog,rel_w,ready_r)
                deadline=time.monotonic()+8;status=None
                while time.monotonic()<deadline:
                    p,s=os.waitpid(dog,os.WNOHANG)
                    if p:status=s;break
                    time.sleep(.03)
                self.assertIsNotNone(status,'watchdog hung')
                result=json.loads((pathlib.Path(t)/'armed.json.result').read_text())
                self.assertEqual(result['status'],'INCOMPLETE');self.assertEqual(result['cleanup_errors'],[])
                if scenario=='fixture33_exec_mock':
                    self.assertGreater(result['exclusive_trace']['bytes'],0)
                    self.assertEqual(result['exclusive_trace']['sha256'],sha(result['exclusive_trace']['path']))
                if scenario in ('fixture33_mock','fixture33_exec_mock'):
                    value=json.loads((pathlib.Path(t)/'worker_result.json').read_text())
                    self.assertEqual(value['calls'],33);self.assertEqual(value['status'],'INCONCLUSIVE')
                    events=[json.loads(line) for line in (pathlib.Path(t)/'calls.jsonl').read_text().splitlines()]
                    self.assertEqual(len(events),66)
                    images=[]
                    for i in range(5):
                        image=(pathlib.Path(t)/f'fake{i}.dylib').resolve();image.write_bytes(f'fake{i}'.encode());images.append(image)
                    log=pathlib.Path(t)/'loader.log';log.write_text(''.join(f'dyld[{result["worker_pid"]}]: <A000-{i}> {image}\n' for i,image in enumerate(images)))
                    allowed={str(image):sha(image) for image in images};required=[str(image) for image in images]
                    verified=witness33.validate(t,result,1.,fixture33.plan(),allowed,required,log,{})
                    self.assertEqual(verified['status'],'EXECUTION_COMPLETED_ASSETS_ONLY')
                    with self.assertRaisesRegex(ValueError,'loaded image'):
                        witness33.validate(t,result,1.,fixture33.plan(),{},required,log,{})
                    asset=pathlib.Path(t)/'call_01.json';original=asset.read_bytes();asset.write_text('{}')
                    with self.assertRaisesRegex(ValueError,'asset'):
                        witness33.validate(t,result,1.,fixture33.plan(),allowed,required,log,{})
                    asset.write_bytes(original)
                    verified=witness33.validate(t,result,1.,fixture33.plan(),allowed,required,log,{})
                    verified['test_only']=True
                    witness33.publish_fake_only(pathlib.Path(t)/'fake_witness.json',verified,time.monotonic()+3)
                    self.assertEqual(json.loads((pathlib.Path(t)/'fake_witness.json').read_text())['status'],'EXECUTION_COMPLETED_ASSETS_ONLY')
                return result
            finally:
                for fd in (ready_r,rel_w):
                    try:os.close(fd)
                    except OSError:pass
                for p in (sup,dog):
                    try:os.kill(p,signal.SIGKILL)
                    except ProcessLookupError:pass
                    try:os.waitpid(p,0)
                    except ChildProcessError:pass
    def test_supervisor_sigkill_released_descendant(self):
        def action(s,d,r,ack):os.write(r,b'G');self.assertEqual(os.read(ack,1),b'G');os.kill(s,signal.SIGKILL)
        a=self.harness('term_ignore_descendant',action);self.assertTrue(a['released']);self.assertIn(a['reason'],('supervisor_exit','supervisor_pipe_eof'))
    def test_supervisor_death_before_release(self):
        a=self.harness('term_ignore_descendant',lambda s,d,r,ack:os.kill(s,signal.SIGKILL));self.assertFalse(a['released'])
    def test_leader_exits_first(self):
        a=self.harness('leader_exits_first',lambda s,d,r,ack:os.write(r,b'G'));self.assertEqual(a['reason'],'worker_exit')
    def test_repeated_term(self):
        def action(s,d,r,ack):os.write(r,b'G');self.assertEqual(os.read(ack,1),b'G');os.kill(d,signal.SIGTERM);os.kill(d,signal.SIGTERM)
        a=self.harness('term_ignore_descendant',action);self.assertEqual(a['reason'],'cancelled')
    def test_signal_during_finalization_never_publishes_witness(self):
        def action(s,d,r,ack):os.write(r,b'G');self.assertEqual(os.read(ack,1),b'G');os.kill(s,signal.SIGKILL)
        a=self.harness('term_ignore_descendant',action,final_signal=True)
        self.assertEqual(a['status'],'INCOMPLETE')
    def test_live_unrelated_pid_cannot_override_closed_liveness_pipe(self):
        with tempfile.TemporaryDirectory() as t:
            lr,lw=os.pipe();rr,rw=os.pipe();pr,pw=os.pipe();os.close(lw);os.write(rw,b'G')
            try:
                result=watchdog.supervise(os.getppid(),watchdog.process_start(os.getppid()),lr,rr,pw,str(pathlib.Path(t)/'armed'),'term_ignore_descendant',timeout=2)
                self.assertFalse(result['released']);self.assertEqual(result['reason'],'supervisor_pipe_eof')
                self.assertEqual(result['cleanup_errors'],[])
            finally:
                for fd in (lr,rr,rw,pr,pw):
                    try:os.close(fd)
                    except OSError:pass
    def test_wrong_start_identity_refused(self):
        with tempfile.TemporaryDirectory() as t:
            lr,lw=os.pipe();rr,rw=os.pipe();pr,pw=os.pipe()
            try:
                result=watchdog.supervise(os.getppid(),(1,1),lr,rr,pw,str(pathlib.Path(t)/'armed'),'term_ignore_descendant',timeout=.1)
                self.assertIsNone(result['worker_pid']);self.assertIn('stale supervisor identity',result['reason'])
            finally:
                for fd in (lr,lw,rr,rw,pr,pw):
                    try:os.close(fd)
                    except OSError:pass
    def test_33_slot_journal_rejects_forgery(self):
        plan=watchdog.fake_plan();self.assertEqual(len(plan),33)
        events=[]
        for row in plan: events.extend([{**row,'state':'STARTED'},{**row,'state':'COMPLETED'}])
        self.assertTrue(all(x['state']=='COMPLETED' for x in watchdog.validate_fake_journal(plan,events)))
        events[0]['fixture']='wrong'
        with self.assertRaisesRegex(ValueError,'identity'):watchdog.validate_fake_journal(plan,events)
    def test_fake_witness_delayed_or_signalled_is_removed(self):
        with tempfile.TemporaryDirectory() as t:
            candidate=pathlib.Path(t)/'candidate';witness=pathlib.Path(t)/'witness'
            plan=watchdog.fake_plan();events=[]
            for row in plan:events.extend([{**row,'state':'STARTED'},{**row,'state':'COMPLETED'}])
            watchdog.atomic(candidate,{'schema':'FAKE_ONLY_NO_EXECUTION_AUTHORITY','events':events})
            watchdog._CANCEL.clear()
            with self.assertRaisesRegex(RuntimeError,'late'):watchdog.publish_fake_witness(candidate,witness,time.monotonic()-1)
            self.assertFalse(witness.exists())
            original=os.link
            def signalled(a,b):
                original(a,b);os.kill(os.getpid(),signal.SIGTERM)
            old=signal.signal(signal.SIGTERM,watchdog._cancel)
            try:
                with patch.object(os,'link',signalled):
                    with self.assertRaisesRegex(RuntimeError,'cancelled'):watchdog.publish_fake_witness(candidate,witness,time.monotonic()+2)
                self.assertFalse(witness.exists())
            finally:signal.signal(signal.SIGTERM,old);watchdog._CANCEL.clear()
    def test_rss_cap(self):
        a=self.harness('term_ignore_descendant',lambda s,d,r,ack:None,max_rss_kib=1)
        self.assertEqual(a['reason'],'rss_limit')
    def test_wall_timeout(self):
        def release(s,d,r,ack):os.write(r,b'G');self.assertEqual(os.read(ack,1),b'G')
        a=self.harness('term_ignore_descendant',release,timeout=20,fake_post_release_timeout=.3)
        self.assertTrue(a['released']);self.assertEqual(a['reason'],'timeout')
    def test_setsid_escape_is_explicitly_not_contained(self):
        r,w=os.pipe(); leader=os.fork()
        if leader==0:
            os.close(r);os.setsid();kid=os.fork()
            if kid==0:
                os.setsid();os.write(w,str(os.getpid()).encode());os.close(w)
                while True:time.sleep(1)
            os.close(w)
            while True:time.sleep(1)
        os.close(w);escaped=None
        try:
            escaped=int(os.read(r,64));self.assertNotEqual(os.getpgid(escaped),leader)
            os.killpg(leader,signal.SIGKILL);os.waitpid(leader,0);leader=None
            os.kill(escaped,0)  # An escaped live process remains outside the group.
        finally:
            os.close(r)
            if escaped is not None:
                try:os.kill(escaped,signal.SIGKILL)
                except ProcessLookupError:pass
            if leader is not None:
                try:os.killpg(leader,signal.SIGKILL)
                except ProcessLookupError:pass
                try:os.waitpid(leader,0)
                except ChildProcessError:pass
    def test_denied_kill_does_not_block_cleanup(self):
        ready_r,ready_w=os.pipe();p=os.fork()
        if p==0:
            os.close(ready_r);os.setsid();signal.signal(signal.SIGTERM,signal.SIG_IGN);os.write(ready_w,b'R');os.close(ready_w)
            while True:time.sleep(1)
        os.close(ready_w);os.read(ready_r,1);os.close(ready_r);start=time.monotonic()
        try:
            with patch.object(watchdog.os,'killpg',side_effect=PermissionError('injected')):
                errors=watchdog.cleanup(p)
            self.assertTrue(errors);self.assertLess(time.monotonic()-start,5)
        finally:
            os.killpg(p,signal.SIGKILL);os.waitpid(p,0)
    def test_ps_timeout_fails_closed(self):
        with patch.object(watchdog.subprocess,'run',side_effect=subprocess.TimeoutExpired('ps',1)):
            with self.assertRaises(subprocess.TimeoutExpired):watchdog.group_rss_kib(os.getpid())
    def test_mock_33_worker_timeout_after_release(self):
        def release(s,d,r,ack):os.write(r,b'G');self.assertEqual(os.read(ack,1),b'G')
        result=self.harness('fixture33_stall',release,timeout=20,fake_ready_timeout=15,fake_post_release_timeout=.3)
        self.assertTrue(result['released']);self.assertEqual(result['reason'],'timeout')
    def test_mock_33_worker_supervisor_sigkill_after_release(self):
        def release(s,d,r,ack):os.write(r,b'G');self.assertEqual(os.read(ack,1),b'G');os.kill(s,signal.SIGKILL)
        result=self.harness('fixture33_stall',release,timeout=5)
        self.assertIn(result['reason'],('supervisor_exit','supervisor_pipe_eof'))
    def test_mock_33_worker_rss_cap(self):
        result=self.harness('fixture33_stall',lambda s,d,r,ack:None,max_rss_kib=1)
        self.assertEqual(result['reason'],'rss_limit')
    def test_mock_33_exec_worker_after_watchdog_release(self):
        result=self.harness('fixture33_exec_mock',lambda s,d,r,ack:os.write(r,b'G'),timeout=12)
        self.assertEqual(result['reason'],'worker_exit');self.assertTrue(result['released'])
    def test_mock_33_worker_after_watchdog_release(self):
        result=self.harness('fixture33_mock',lambda s,d,r,ack:os.write(r,b'G'),timeout=12)
        self.assertEqual(result['reason'],'worker_exit')
        self.assertTrue(result['released'])
    def test_failed_presignal_census_still_attempts_termination(self):
        calls=[]
        def record(pid,sig):calls.append(sig);raise ProcessLookupError()
        with patch.object(watchdog,'leader_exited',return_value=True), patch.object(watchdog,'other_members',side_effect=ValueError('bad census')),patch.object(watchdog.os,'killpg',side_effect=record),patch.object(watchdog,'reapable',side_effect=TimeoutError('not reaped')):
            errors=watchdog.cleanup(123)
        self.assertTrue(errors);self.assertIn(signal.SIGTERM,calls);self.assertIn(signal.SIGKILL,calls)
    def test_census_failure_still_kills_real_fake_descendant(self):
        r,w=os.pipe();leader=os.fork()
        if leader==0:
            os.close(r);os.setsid();kid=os.fork()
            if kid==0:
                signal.signal(signal.SIGTERM,signal.SIG_IGN);os.close(w)
                while True:time.sleep(1)
            os.write(w,str(kid).encode());os.close(w);os._exit(0)
        os.close(w);kid=int(os.read(r,64));os.close(r);watchdog.reapable(leader)
        original=watchdog.other_members;counter=[0]
        def fail_once(pid):
            counter[0]+=1
            if counter[0]==1:raise ValueError('injected census failure')
            return original(pid)
        try:
            with patch.object(watchdog,'other_members',side_effect=fail_once):errors=watchdog.cleanup(leader)
            self.assertTrue(any('injected census failure' in e for e in errors))
            time.sleep(.1)
            with self.assertRaises(ProcessLookupError):os.kill(kid,0)
        finally:
            try:os.kill(kid,signal.SIGKILL)
            except ProcessLookupError:pass
            try:os.waitpid(leader,0)
            except ChildProcessError:pass
    def test_rss_census_rejects_empty_truncated_and_missing_leader(self):
        class R:
            def __init__(self,text):self.stdout=text
        for text in ('','123 123 42\ntruncated\n','987 987 42\n'):
            with patch.object(watchdog.subprocess,'run',return_value=R(text)):
                with self.assertRaises(ValueError):watchdog.group_rss_kib(123)
    def test_residual_or_census_error_keeps_leader_unreaped(self):
        with patch.object(watchdog,'leader_exited',return_value=True),patch.object(watchdog,'other_members',side_effect=ValueError('census incomplete')),patch.object(watchdog.os,'killpg',side_effect=PermissionError('denied')),patch.object(watchdog,'reapable',return_value=None),patch.object(watchdog.os,'waitpid') as wait:
            errors=watchdog.cleanup(123)
            self.assertTrue(errors);wait.assert_not_called()
    def test_incomplete_census_rejected(self):
        class R:
            def __init__(self,text):self.stdout=text
        for text in ('','123 123 Z\ntruncated\n','987 987 Z\n'):
            with patch.object(watchdog.subprocess,'run',return_value=R(text)):
                with self.assertRaises(ValueError):watchdog.other_members(123)
    def test_real_ps_smoke_with_test_only_relaxed_deadline(self):
        r,w=os.pipe();leader=os.fork()
        if leader==0:
            os.close(r);os.setsid();os.write(w,b'R');os.close(w)
            while True:time.sleep(1)
        os.close(w);self.assertEqual(os.read(r,1),b'R');os.close(r)
        original=watchdog.subprocess.run
        def run(*args,**kwargs):
            kwargs['timeout']=15.0  # Smoke only; production retains ten seconds.
            return original(*args,**kwargs)
        try:
            with patch.object(watchdog.subprocess,'run',side_effect=run):
                self.assertGreater(watchdog.group_rss_kib(leader),0)
        finally:
            os.killpg(leader,signal.SIGKILL);os.waitpid(leader,0)
    def test_real_default_readiness_bound_is_ten_seconds(self):
        import inspect
        self.assertEqual(inspect.signature(watchdog.supervise).parameters['fake_ready_timeout'].default,10.0)
    def test_pre_ready_timeout_fails_closed(self):
        lr,lw=os.pipe();rr,rw=os.pipe();pr,pw=os.pipe()
        try:
            with tempfile.TemporaryDirectory() as t,patch.object(watchdog,'child',side_effect=lambda *args:time.sleep(2)):
                result=watchdog.supervise(os.getppid(),watchdog.process_start(os.getppid()),lr,rr,pw,str(pathlib.Path(t)/'armed'),'term_ignore_descendant',timeout=1,fake_ready_timeout=.1)
            self.assertIn('ready timeout',result['reason']);self.assertFalse(result['released'])
        finally:
            for fd in (lr,lw,rr,rw,pr,pw):
                try:os.close(fd)
                except OSError:pass
    def test_real_mode_rejects_fake_timing_overrides(self):
        with self.assertRaisesRegex(ValueError,'fake-only timing'):
            watchdog.supervise(0,(0,0),-1,-1,-1,'/unused','fixture33_real',fake_ready_timeout=15)
        with self.assertRaisesRegex(ValueError,'fake-only timing'):
            watchdog.supervise(0,(0,0),-1,-1,-1,'/unused','fixture33_real',fake_post_release_timeout=.3)
    def test_stale_supervisor_refused(self):
        with tempfile.TemporaryDirectory() as t:
            lr,lw=os.pipe();rr,rw=os.pipe();pr,pw=os.pipe()
            try:
                result=watchdog.supervise(99999999,(0,0),lr,rr,pw,str(pathlib.Path(t)/'armed'),'term_ignore_descendant',timeout=.1)
                self.assertIsNone(result['worker_pid']);self.assertTrue(result['reason'].startswith('error:'))
            finally:
                for fd in (lr,lw,rr,rw,pr,pw):
                    try:os.close(fd)
                    except OSError:pass
if __name__=='__main__':unittest.main()
