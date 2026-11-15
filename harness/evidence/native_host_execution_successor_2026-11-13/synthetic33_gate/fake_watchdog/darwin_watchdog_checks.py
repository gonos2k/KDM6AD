import copy, json, os, pathlib, signal, tempfile, time, unittest, subprocess, hashlib
import watchdog
import sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
import witness33,fixture33
from real33_contract import sha
from unittest.mock import patch

class WatchdogTest(unittest.TestCase):
    def harness(self,scenario,action,final_signal=False,timeout=20,max_rss_kib=8*1024*1024,fake_ready_timeout=15.0,fake_post_release_timeout=None,release_injection=None,initial_mode=None,prearm_failure=False,use_helper=False):
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
                def initial_sample(pid):
                    if initial_mode=='zero':return 0
                    if initial_mode=='failure':raise RuntimeError('injected RSS failure')
                    if initial_mode=='cancel':watchdog._cancel(signal.SIGTERM,None)
                    if initial_mode=='late':
                        original=watchdog.time.monotonic
                        watchdog.time.monotonic=lambda:original()+60
                    return 1024
                watchdog.group_rss_kib=initial_sample
                def helper_sampler(request,deadline):
                    if initial_mode=='failure':raise PermissionError('injected helper failure')
                    if initial_mode=='cancel':os.kill(os.getppid(),signal.SIGTERM)
                    if initial_mode=='late':time.sleep(3)
                    value=0 if initial_mode=='zero' else 1024*1024
                    return {'request':request,'policy':'SAMPLED_STOP_THRESHOLD','members':[request['leader_pid']],'rss_bytes':value}

                if release_injection:
                    original_kqueue=watchdog.select.kqueue
                    class InjectQueue:
                        def __init__(self):self.inner=original_kqueue();self.done=False
                        def control(self,changes,max_events,timeout=None):
                            events=self.inner.control(changes,max_events,timeout)
                            if not self.done and any(e.filter==watchdog.select.KQ_FILTER_READ and e.ident==rel_r for e in events):
                                self.done=True
                                if release_injection=='cancel':watchdog._cancel(signal.SIGTERM,None)
                                elif release_injection=='deadline':
                                    original=watchdog.time.monotonic
                                    watchdog.time.monotonic=lambda:original()+60
                                elif release_injection=='supervisor_death':
                                    os.kill(sup,signal.SIGKILL)
                                    watchdog.select.select([life_r],[],[],2)
                            return events
                        def close(self):self.inner.close()
                    watchdog.select.kqueue=InjectQueue
                os.close(ready_r);os.close(rel_w)
                if final_signal:
                    old=watchdog.atomic
                    def injected(path,value):
                        if str(path).endswith('.result'):
                            os.kill(os.getpid(),signal.SIGTERM);os.kill(os.getpid(),signal.SIGTERM)
                        old(path,value)
                    watchdog.atomic=injected
                try: watchdog.supervise(sup,watchdog.process_start(sup),life_r,rel_r,ready_w,str(pathlib.Path(t)/'armed.json'),scenario,timeout=timeout,max_rss_kib=max_rss_kib,mock_outdir=t,fake_ready_timeout=fake_ready_timeout,fake_post_release_timeout=fake_post_release_timeout,use_fake_census_helper=use_helper,fake_census_sampler=helper_sampler if use_helper else None)
                except BaseException:
                    import traceback;traceback.print_exc();os._exit(1)
                os._exit(0)
            os.close(life_r);os.close(ready_w);os.close(rel_r)
            try:
                initial=os.read(ready_r,1)
                if prearm_failure:self.assertEqual(initial,b'')
                else:
                    self.assertEqual(initial,b'R')
                    action(sup,dog,rel_w,ready_r)
                deadline=time.monotonic()+8;status=None
                while time.monotonic()<deadline:
                    p,s=os.waitpid(dog,os.WNOHANG)
                    if p:status=s;break
                    time.sleep(.03)
                self.assertIsNotNone(status,'watchdog hung')
                result=json.loads((pathlib.Path(t)/'armed.json.result').read_text())
                self.assertEqual(result['status'],'INCOMPLETE')
                if not (prearm_failure and use_helper):self.assertEqual(result['cleanup_errors'],[])
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
                    try:verified=witness33.validate(t,result,1.,fixture33.plan(),allowed,required,log,{})
                    except ValueError as exc:self.fail('fake witness failed: '+str(exc)+' watchdog result='+repr(result))
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
    def test_cancel_arriving_during_kqueue_release_is_not_forwarded(self):
        a=self.harness('term_ignore_descendant',lambda s,d,r,ack:os.write(r,b'G'),release_injection='cancel')
        self.assertFalse(a['released']);self.assertEqual(a['reason'],'cancelled')
    def test_deadline_expiring_during_kqueue_release_is_not_forwarded(self):
        a=self.harness('term_ignore_descendant',lambda s,d,r,ack:os.write(r,b'G'),release_injection='deadline')
        self.assertFalse(a['released']);self.assertEqual(a['reason'],'timeout')
    def test_supervisor_death_coincident_with_release_is_not_forwarded(self):
        a=self.harness('term_ignore_descendant',lambda s,d,r,ack:os.write(r,b'G'),release_injection='supervisor_death')
        self.assertFalse(a['released']);self.assertIn(a['reason'],('supervisor_pipe_eof','supervisor_unavailable','supervisor_exit'))
    def test_later_sample_verified_exit_is_distinct_from_sampling_failure(self):
        watchdog._CANCEL.clear();identity=(123,456);states=iter([('alive',identity),('exited_reserved',identity)])
        with self.assertRaises(watchdog.WorkerExitedDuringSample):
            watchdog.checked_rss_sample(lambda:next(states),lambda:1024,time.monotonic()+2)
        with self.assertRaisesRegex(RuntimeError,'missing leader'):
            watchdog.checked_rss_sample(lambda:('alive',identity),lambda:(_ for _ in ()).throw(RuntimeError('missing leader')),time.monotonic()+2)
        with self.assertRaisesRegex(RuntimeError,'nonpositive'):
            watchdog.checked_rss_sample(lambda:('alive',identity),lambda:0,time.monotonic()+2)
    def test_fast_exit_has_initial_positive_rss_before_release(self):
        def release(s,d,r,ack):os.write(r,b'G');self.assertEqual(os.read(ack,1),b'G')
        result=self.harness('fast_exit',release)
        self.assertEqual(result['reason'],'worker_exit');self.assertTrue(result['released'])
        self.assertGreater(result['initial_rss_kib'],0);self.assertGreater(result['peak_group_rss_kib'],0)
    def test_initial_rss_failure_never_arms_or_releases(self):
        for use_helper in (False,True):
            for mode in ('zero','failure'):
                with self.subTest(use_helper=use_helper,mode=mode):
                    result=self.harness('fast_exit',lambda *args:self.fail('must not release'),initial_mode=mode,prearm_failure=True,use_helper=use_helper)
                    self.assertFalse(result['released']);self.assertEqual(result['peak_group_rss_kib'],0)
                    self.assertIn('error_detail',result)
    def test_initial_rss_late_or_cancel_never_arms_or_releases(self):
        for use_helper in (False,True):
            for mode in ('late','cancel'):
                with self.subTest(use_helper=use_helper,mode=mode):
                    result=self.harness('fast_exit',lambda *args:self.fail('must not release'),initial_mode=mode,prearm_failure=True,use_helper=use_helper)
                    self.assertFalse(result['released'])
                    if mode=='cancel':self.assertEqual(result['reason'],'cancelled')
                    else:self.assertIn('timeout',result['reason'].lower())
    def test_fast_exit_with_helper_has_initial_sample(self):
        def release(s,d,r,ack):os.write(r,b'G');self.assertEqual(os.read(ack,1),b'G')
        result=self.harness('fast_exit',release,use_helper=True)
        self.assertTrue(result['released']);self.assertGreater(result['initial_rss_kib'],0)
        self.assertEqual(result['rss_policy'],'SAMPLED_STOP_THRESHOLD')
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
        a=self.harness('term_ignore_descendant',lambda *args:self.fail('must not release'),max_rss_kib=1,prearm_failure=True)
        self.assertFalse(a['released']);self.assertIn('initial RSS stop threshold',a['error_detail'])
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
    def test_worker_exit_during_start_lookup_rechecks_reservation(self):
        identity=(1000,12)
        with patch.object(watchdog,'leader_exited',side_effect=[False,True]) as exited, \
             patch.object(watchdog,'process_start',side_effect=RuntimeError('identity unavailable')):
            self.assertEqual(watchdog.worker_reservation(123,identity),('exited_reserved',identity))
            self.assertEqual(exited.call_count,2)
        with patch.object(watchdog,'leader_exited',side_effect=[False,False,True]), \
             patch.object(watchdog,'process_start',side_effect=RuntimeError('identity unavailable')), \
             patch.object(watchdog.time,'sleep'):
            self.assertEqual(watchdog.worker_reservation(123,identity),('exited_reserved',identity))
        with patch.object(watchdog,'leader_exited',side_effect=[False,False]), \
             patch.object(watchdog,'process_start',side_effect=RuntimeError('identity unavailable')):
            with self.assertRaisesRegex(RuntimeError,'identity unavailable'):
                watchdog.worker_reservation(123,identity,deadline=0)
        with patch.object(watchdog,'leader_exited',side_effect=[False,OSError('waitid unavailable')]), \
             patch.object(watchdog,'process_start',side_effect=RuntimeError('identity unavailable')):
            with self.assertRaisesRegex(OSError,'waitid unavailable'):
                watchdog.worker_reservation(123,identity)
        with patch.object(watchdog,'leader_exited',return_value=False), \
             patch.object(watchdog,'process_start',return_value=(1000,13)):
            with self.assertRaisesRegex(RuntimeError,'worker start changed'):
                watchdog.worker_reservation(123,identity)

    @patch.object(watchdog,'EPERM_RECHECK_SECONDS',0)
    def test_eperm_transition_requires_reserved_exited_empty_group(self):
        for stage in ('term','probe','kill'):
            with self.subTest(stage=stage):
                signals = ([PermissionError('denied')] if stage == 'term' else
                           [None] if stage == 'probe' else [None, PermissionError('denied')])
                probe = PermissionError('denied') if stage == 'probe' else False
                with patch.object(watchdog,'leader_exited',side_effect=[False, True, True]) as reserved, \
                     patch.object(watchdog,'other_members',return_value=[]) as census, \
                     patch.object(watchdog.os,'killpg',side_effect=signals), \
                     patch.object(watchdog,'alive',side_effect=probe if isinstance(probe,Exception) else None,return_value=False), \
                     patch.object(watchdog.os,'waitpid',return_value=(123,0)) as reap:
                    self.assertEqual(watchdog.cleanup(123),[])
                    self.assertEqual(reserved.call_count,3)
                    self.assertEqual(census.call_count,1)
                    self.assertEqual(census.call_args.args,(123,))
                    reap.assert_called_once_with(123,0)
        for kind in ('live_leader','live_member','reservation_lost','census_error','unknown_inventory'):
            with self.subTest(kind=kind):
                states={'live_leader':[False,False,False], 'live_member':[False,True,True],
                        'reservation_lost':[False,True,False], 'census_error':[False,True,True],
                        'unknown_inventory':[False,True,True]}[kind]
                members=ValueError('truncated census') if kind=='census_error' else (None if kind=='unknown_inventory' else ([(456,123,'R')] if kind=='live_member' else []))
                with patch.object(watchdog,'leader_exited',side_effect=states), \
                     patch.object(watchdog,'other_members',side_effect=members if isinstance(members,Exception) else None,return_value=members), \
                     patch.object(watchdog.os,'killpg',side_effect=[PermissionError('denied'),None]), \
                     patch.object(watchdog,'alive',return_value=False), \
                     patch.object(watchdog,'reapable',return_value=None), \
                     patch.object(watchdog.os,'waitpid') as reap:
                    self.assertTrue(watchdog.cleanup(123))
                    reap.assert_not_called()

    def test_eperm_reobserves_exit_and_records_diagnostics(self):
        record={}
        with patch.object(watchdog,'leader_exited',side_effect=[False,False,False,True,True]), \
             patch.object(watchdog,'other_members',return_value=[]), \
             patch.object(watchdog.os,'killpg',side_effect=PermissionError('denied')), \
             patch.object(watchdog.time,'sleep'), \
             patch.object(watchdog.os,'waitpid',return_value=(123,0)) as reap:
            self.assertEqual(watchdog.cleanup(123,record),[])
        attempts=record['eperm_observations'][0]['attempts']
        self.assertEqual([(a['leader_before'],a['leader_after'],a['members']) for a in attempts],
                         [(False,False,[]),(True,True,[])])
        reap.assert_called_once_with(123,0)

    @patch.object(watchdog,'EPERM_RECHECK_SECONDS',0)
    def test_eperm_reconciled_waitpid_failure_is_recorded(self):
        for stage in ('term','probe','kill'):
            with self.subTest(stage=stage):
                signals=([PermissionError('denied')] if stage=='term' else
                         [None] if stage=='probe' else [None,PermissionError('denied')])
                probe=PermissionError('denied') if stage=='probe' else False
                record={}
                with patch.object(watchdog,'leader_exited',side_effect=[False,True,True]), \
                     patch.object(watchdog,'other_members',return_value=[]), \
                     patch.object(watchdog.os,'killpg',side_effect=signals), \
                     patch.object(watchdog,'alive',side_effect=probe if isinstance(probe,Exception) else None,return_value=False), \
                     patch.object(watchdog.os,'waitpid',side_effect=OSError('injected wait failure')) as reap:
                    errors=watchdog.cleanup(123,record)
                    self.assertEqual(len(errors),1)
                    self.assertIn('reconciled reap',errors[0])
                    self.assertIn('injected wait failure',errors[0])
                    self.assertNotIn('worker_reaped_pid',record)
                    reap.assert_called_once_with(123,0)

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
        result=self.harness('fixture33_stall',lambda *args:self.fail('must not release'),max_rss_kib=1,prearm_failure=True)
        self.assertFalse(result['released']);self.assertIn('initial RSS stop threshold',result['error_detail'])
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
        def fail_once(pid,**kwargs):
            counter[0]+=1
            if counter[0]==1:raise ValueError('injected census failure')
            return original(pid,**kwargs)
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
    def test_pre_ready_cleanup_freezes_before_group_or_pid_signal(self):
        import ctypes
        from types import SimpleNamespace
        from unittest.mock import MagicMock
        pid=12345
        waitid=MagicMock(side_effect=lambda kind,child,buf,opts:(setattr(ctypes.c_int.from_buffer(buf,12),'value',pid) or 0))
        libc=SimpleNamespace(waitid=waitid)
        with patch.object(watchdog.ctypes,'CDLL',return_value=libc),patch.object(watchdog.os,'kill') as kill,patch.object(watchdog.os,'getpgid',return_value=pid),patch.object(watchdog,'cleanup',return_value=[]) as clean:
            self.assertEqual(watchdog.pre_ready_cleanup(pid),[])
            kill.assert_called_once_with(pid,signal.SIGSTOP)
            clean.assert_called_once_with(pid,None)
            self.assertTrue(waitid.call_args.args[3]&os.WNOWAIT)
        with patch.object(watchdog.ctypes,'CDLL',return_value=libc),patch.object(watchdog.os,'kill') as kill,patch.object(watchdog.os,'getpgid',return_value=888),patch.object(watchdog,'reapable'),patch.object(watchdog.os,'waitpid',return_value=(pid,9)) as reap,patch.object(watchdog,'cleanup') as clean:
            self.assertEqual(watchdog.pre_ready_cleanup(pid),[])
            self.assertEqual(kill.call_args_list,[unittest.mock.call(pid,signal.SIGSTOP),unittest.mock.call(pid,signal.SIGKILL)])
            clean.assert_not_called();reap.assert_called_once_with(pid,0)
        with patch.object(watchdog.ctypes,'CDLL',return_value=libc),patch.object(watchdog.os,'kill'),patch.object(watchdog.os,'getpgid',side_effect=PermissionError('unknown group')),patch.object(watchdog.os,'waitpid') as reap:
            self.assertIn('pre-ready cleanup unresolved',watchdog.pre_ready_cleanup(pid)[0])
            reap.assert_not_called()

    def test_real_capability_binds_nonce_manifest_worker_and_is_one_shot(self):
        with tempfile.TemporaryDirectory() as t:
            root=pathlib.Path(t).resolve();package=root/'psutil';package.mkdir();nonce='b'*64
            (root/'run_nonce').write_text(nonce)
            inventory={'__init__.py':'a'*64}
            inventory_raw=json.dumps(inventory,sort_keys=True,separators=(',',':')).encode('ascii')
            value={'schema':'kdm6.synthetic33.private.v1','status':'REVIEWED_PINNED','dso_sha256':'c'*64,
                   'census_provider':{'package':str(package),'inventory':inventory,'inventory_sha256':hashlib.sha256(inventory_raw).hexdigest()}}
            path=root/'manifest.json';path.write_text(json.dumps(value));digest=hashlib.sha256(path.read_bytes()).hexdigest()
            args={'manifest_path':path,'approved_sha':digest,'dso_sha256':'c'*64,'run_nonce':nonce,
                  'supervisor_pid':111,'supervisor_start':(100,1),'output_dir':root,'package':package,
                  'inventory':inventory,'deadline':time.monotonic()+60}
            with patch.object(watchdog.os,'getpid',return_value=111),patch.object(watchdog,'process_start',return_value=(100,1)):
                capability=watchdog.issue_real_capability(**args)
                rejected=watchdog.issue_real_capability(**args)
            binding={k:args[k] for k in ('supervisor_pid','supervisor_start','manifest_path','approved_sha','run_nonce','output_dir','package','inventory','deadline')}
            with patch.object(watchdog.os,'getpid',return_value=222),patch.object(watchdog.os,'getppid',return_value=111),patch.object(watchdog,'process_start',return_value=(100,1)),patch.object(watchdog,'worker_reservation',return_value=('alive',(200,2))):
                wrong=dict(binding);wrong['run_nonce']='d'*64
                with self.assertRaisesRegex(ValueError,'binding'):rejected.consume_pre_fork(**wrong)
                with self.assertRaisesRegex(RuntimeError,'already consumed'):rejected.consume_pre_fork(**binding)
                capability.consume_pre_fork(**binding)
                with self.assertRaisesRegex(RuntimeError,'already consumed'):capability.consume_pre_fork(**binding)
                child=copy.deepcopy(capability)
                bad_release=copy.deepcopy(capability)
                tampered=copy.deepcopy(capability)
                stale_worker=copy.deepcopy(capability)
                with patch.object(watchdog,'worker_reservation',return_value=('exited_reserved',(200,2))):
                    with self.assertRaisesRegex(RuntimeError,'worker reservation changed'):
                        stale_worker.arm(333,(200,2))
                with self.assertRaisesRegex(RuntimeError,'arm state'):stale_worker.arm(333,(200,2))
                capability.arm(333,(200,2))
                bad_release.arm(333,(200,2))
                tampered.arm(333,(200,2))
                (root/'run_nonce').write_text('d'*64)
                with self.assertRaisesRegex(ValueError,'nonce file'):tampered.consume_release(333,(200,2))
                (root/'run_nonce').write_text(nonce)
                with self.assertRaisesRegex(RuntimeError,'release state'):tampered.consume_release(333,(200,2))
                with self.assertRaisesRegex(RuntimeError,'worker identity'):bad_release.consume_release(333,(200,3))
                with self.assertRaisesRegex(RuntimeError,'release state'):bad_release.consume_release(333,(200,2))
                capability.consume_release(333,(200,2))
                with self.assertRaisesRegex(RuntimeError,'release state'):capability.consume_release(333,(200,2))
            with patch.object(watchdog.os,'getppid',return_value=222),patch.object(watchdog,'process_start',return_value=(100,1)):
                child.verify_child(manifest_path=path,approved_sha=digest,run_nonce=nonce,output_dir=root)
                with self.assertRaisesRegex(RuntimeError,'child capability identity'):
                    child.verify_child(manifest_path=path,approved_sha=digest,run_nonce=nonce,output_dir=root)
            with patch.object(watchdog.os,'getpid',return_value=111),patch.object(watchdog,'process_start',return_value=(100,1)):
                (root/'run_nonce').write_text('d'*64)
                with self.assertRaisesRegex(ValueError,'nonce file'):watchdog.issue_real_capability(**args)

    def test_real_pre_fork_orders_pinned_helper_and_closes_pipes_on_failure(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as t:
            root=pathlib.Path(t).resolve();package=root/'psutil';package.mkdir();nonce='b'*64
            (root/'run_nonce').write_text(nonce)
            inventory={'__init__.py':'a'*64}
            inventory_raw=json.dumps(inventory,sort_keys=True,separators=(',',':')).encode('ascii')
            value={'schema':'kdm6.synthetic33.private.v1','status':'REVIEWED_PINNED','dso_sha256':'c'*64,
                   'census_provider':{'package':str(package),'inventory':inventory,'inventory_sha256':hashlib.sha256(inventory_raw).hexdigest()}}
            path=root/'manifest.json';path.write_text(json.dumps(value));digest=hashlib.sha256(path.read_bytes()).hexdigest()
            args={'manifest_path':path,'approved_sha':digest,'dso_sha256':'c'*64,'run_nonce':nonce,
                  'supervisor_pid':111,'supervisor_start':(100,1),'output_dir':root,'package':package,
                  'inventory':inventory,'deadline':time.monotonic()+60}
            with patch.object(watchdog.os,'getpid',return_value=111),patch.object(watchdog,'process_start',return_value=(100,1)):
                capability=watchdog.issue_real_capability(**args)
            events=[];fds=[];original_pipe=os.pipe
            def pipe():
                pair=original_pipe();fds.extend(pair);return pair
            class Helper:
                pid=444;closed=False
                def __init__(self,*a,**kw):events.append('helper_ready')
                def close(self):events.append('helper_close');self.closed=True
            class Queue:
                def control(self,*a,**kw):return []
                def close(self):pass
            class Trace:
                def __init__(self,*a):pass
                def snapshot(self):return {}
                def close(self):pass
            def stop_before_fork():
                events.append('worker_fork');raise RuntimeError('fake fork refusal')
            fake_modules={'freeze33':SimpleNamespace(validate_frozen=lambda *a:None),
                          'fixture33':SimpleNamespace(plan=lambda:[]),
                          'trace33':SimpleNamespace(Trace=Trace),
                          'census_helper':SimpleNamespace(CensusHelper=Helper,native_sampler=lambda *a:None)}
            with patch.object(watchdog,'ENABLE_REAL33',True),patch.object(watchdog.os,'getpid',return_value=222), \
                 patch.object(watchdog.os,'getppid',return_value=111),patch.object(watchdog,'process_start',return_value=(100,1)), \
                 patch.object(watchdog.select,'kqueue',return_value=Queue()),patch.object(watchdog.select,'kevent',return_value=None),patch.object(watchdog.signal,'signal'), \
                 patch.object(watchdog.signal,'pthread_sigmask',return_value=set()),patch.object(watchdog.signal,'sigpending',return_value=set()), \
                 patch.object(watchdog,'release_refusal',return_value=None),patch.object(watchdog,'leader_exited',return_value=False), \
                 patch.object(watchdog.os,'pipe',side_effect=pipe),patch.object(watchdog.os,'fork',side_effect=stop_before_fork), \
                 patch.object(watchdog,'atomic') as atomic,patch.dict(sys.modules,fake_modules):
                result=watchdog.supervise(111,(100,1),-1,-1,-1,str(root/'armed'),'fixture33_real',timeout=10,
                    mock_outdir=str(root),manifest_path=path,manifest_sha=digest,run_nonce=nonce,
                    use_native_census_helper=True,native_census_package=package,native_census_manifest=inventory,
                    real_capability=capability)
            self.assertEqual(events,['helper_ready','worker_fork','helper_close'],result)
            self.assertEqual(result['status'],'INCOMPLETE');self.assertFalse(result['released'])
            self.assertIn('fake fork refusal',result['error_detail'])
            self.assertEqual(atomic.call_count,1)
            self.assertTrue(str(atomic.call_args.args[0]).endswith('.result'))
            for fd in fds:
                with self.assertRaises(OSError):os.fstat(fd)

    def test_real_path_stays_disabled_and_requires_native_helper_before_fork(self):
        args=(1,(1,1),-1,-1,-1,'unused','fixture33_real')
        with patch.object(watchdog.os,'fork') as fork:
            with self.assertRaisesRegex(RuntimeError,'real33 disabled'):
                watchdog.supervise(*args)
            fork.assert_not_called()
        with patch.object(watchdog,'ENABLE_REAL33',True),patch.object(watchdog.os,'fork') as fork:
            with self.assertRaisesRegex(RuntimeError,'pinned native census helper'):
                watchdog.supervise(*args)
            fork.assert_not_called()

    def test_real_census_config_is_bound_to_private_manifest(self):
        with tempfile.TemporaryDirectory() as t:
            package=pathlib.Path(t).resolve()/'psutil';package.mkdir()
            inventory={'__init__.py':'a'*64}
            encoded=json.dumps(inventory,sort_keys=True,separators=(',',':')).encode('ascii')
            value={'schema':'kdm6.synthetic33.private.v1','status':'REVIEWED_PINNED',
                   'census_provider':{'package':str(package),'inventory':inventory,'inventory_sha256':hashlib.sha256(encoded).hexdigest()}}
            manifest=pathlib.Path(t)/'manifest.json';manifest.write_text(json.dumps(value))
            digest=hashlib.sha256(manifest.read_bytes()).hexdigest()
            self.assertEqual(watchdog.validate_real_census_config(manifest,digest,package,inventory)['package'],package)
            with self.assertRaises(ValueError):watchdog.validate_real_census_config(manifest,'0'*64,package,inventory)
            with self.assertRaises(ValueError):watchdog.validate_real_census_config(manifest,digest,package,{'__init__.py':'b'*64})
            value.pop('census_provider');manifest.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError,'missing census provider pins'):
                watchdog.validate_real_census_config(manifest,hashlib.sha256(manifest.read_bytes()).hexdigest(),package,inventory)

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
