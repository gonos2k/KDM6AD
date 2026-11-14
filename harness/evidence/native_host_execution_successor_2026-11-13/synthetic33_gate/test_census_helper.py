import os,signal,time,unittest
from unittest.mock import patch
from census_helper import CensusHelper,HelperError,start_float

def sample(request,deadline):
    return {'request':request,'policy':'SAMPLED_STOP_THRESHOLD','members':[request['leader_pid']],'rss_bytes':64}
def denied(request,deadline):raise PermissionError('fake denied')
def stalled(request,deadline):time.sleep(20)
def churn(request,deadline):return {'request':{**request,'nonce':'wrong'},'policy':'SAMPLED_STOP_THRESHOLD','members':[request['leader_pid']],'rss_bytes':1}
class HelperTests(unittest.TestCase):
    def test_success_and_rate_limit(self):
        h=CensusHelper(sample);aborts=[]
        try:
            x=h.sample(101,lambda:('alive',(1000,123456)),lambda:aborts.append('worker'),time.monotonic()+10)
            self.assertEqual(x['rss_bytes'],64);self.assertEqual(aborts,[])
            with self.assertRaisesRegex(HelperError,'rate'):h.sample(101,lambda:('alive',(1000,123456)),lambda:aborts.append('worker'),time.monotonic()+10)
            self.assertEqual(aborts,['worker'])
        finally:h.close()
    def test_stall_aborts_worker_before_reap(self):
        h=CensusHelper(stalled);events=[];old=h.close
        def close():events.append('helper');old()
        h.close=close
        with self.assertRaisesRegex(HelperError,'timeout'):h.sample(101,lambda:('alive',(1000,123456)),lambda:events.append('worker'),time.monotonic()+4)
        self.assertEqual(events,['worker','helper'])
    def test_denied_churn_and_changed_parent_reservation(self):
        for fn in (denied,churn):
            with self.subTest(fn=fn.__name__):
                h=CensusHelper(fn);calls=[]
                with self.assertRaises(HelperError):h.sample(101,lambda:('alive',(1000,123456)),lambda:calls.append(1),time.monotonic()+4)
                self.assertEqual(calls,[1])
        h=CensusHelper(sample);calls=[];state=iter([('alive',(1000,123456)),('exited_reserved',(1000,123456))])
        with self.assertRaisesRegex(HelperError,'reservation'):h.sample(101,lambda:next(state),lambda:calls.append(1),time.monotonic()+4)
        self.assertEqual(calls,[1])
    def test_start_float_and_ambiguous_values(self):
        self.assertEqual(start_float((1000,123456)),1000.123456)
        for value in ((0,0),(1,1000000),(1,-1),(1.0,1)):
            with self.assertRaises(HelperError):start_float(value)
    def test_startup_before_setsid_timeout_kills_direct_child(self):
        calls=[];original=os.kill
        def tracked(pid,sig):calls.append((pid,sig));return original(pid,sig)
        with patch('census_helper.os.kill',side_effect=tracked):
            with self.assertRaises(HelperError):CensusHelper(sample,startup_timeout=.15,fake_startup_stall=True)
        self.assertTrue(any(sig==signal.SIGKILL for _,sig in calls))
    def test_helper_group_eperm_remains_failure_after_direct_reap(self):
        h=CensusHelper(sample);pid=h.pid
        with patch('census_helper.os.killpg',side_effect=PermissionError('injected')):
            with self.assertRaisesRegex(HelperError,'group signal'):h.close()
        waited,_=os.waitpid(pid,0);self.assertEqual(waited,pid)
    def test_helper_fork_attempt_fails_closed(self):
        def fork_attempt(request,deadline):os.fork()
        h=CensusHelper(fork_attempt);aborted=[]
        with self.assertRaises(HelperError):h.sample(101,lambda:('alive',(1000,123456)),lambda:aborted.append(True),time.monotonic()+4)
        self.assertEqual(aborted,[True])
    def test_abort_failure_still_reaps_helper(self):
        h=CensusHelper(denied)
        def abort():raise RuntimeError('signal failed')
        with self.assertRaises(RuntimeError):h.sample(101,lambda:('alive',(1000,123456)),abort,time.monotonic()+4)
        self.assertTrue(h.closed)
if __name__=='__main__':unittest.main()

class FramingTests(unittest.TestCase):
    def test_oversized_and_duplicate_frames_fail(self):
        import socket,struct
        from census_helper import _recv,MAX_FRAME
        a,b=socket.socketpair()
        try:
            b.sendall(struct.pack('!I',MAX_FRAME+1))
            with self.assertRaises(HelperError):_recv(a,time.monotonic()+1)
        finally:a.close();b.close()
        a,b=socket.socketpair()
        try:
            raw=b'{"x":1,"x":2}';b.sendall(struct.pack('!I',len(raw))+raw)
            with self.assertRaisesRegex(HelperError,'duplicate'):_recv(a,time.monotonic()+1)
        finally:a.close();b.close()
    def test_partial_frame_and_blocked_writer_time_out(self):
        import socket,struct
        from census_helper import _recv,_send
        a,b=socket.socketpair();a.setblocking(False);b.setblocking(False)
        try:
            b.send(struct.pack('!I',20)+b'{')
            with self.assertRaisesRegex(HelperError,'timeout'):_recv(a,time.monotonic()+.1)
            while True:
                try:a.send(b'x'*65536)
                except BlockingIOError:break
            with self.assertRaisesRegex(HelperError,'timeout'):_send(a,{'x':'y'},time.monotonic()+.1)
        finally:a.close();b.close()
    def test_truncated_frame_eof(self):
        import socket,struct
        from census_helper import _recv
        a,b=socket.socketpair()
        try:
            b.sendall(struct.pack('!I',10)+b'{');b.close()
            with self.assertRaisesRegex(HelperError,'EOF'):_recv(a,time.monotonic()+1)
        finally:a.close()
