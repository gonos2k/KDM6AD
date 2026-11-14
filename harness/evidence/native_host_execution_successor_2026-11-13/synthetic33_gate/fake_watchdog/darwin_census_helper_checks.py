"""Fake process topology checks; no KDM/DSO use."""
import ctypes,errno,os,pathlib,signal,sys,time,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
import watchdog
from census_helper import CensusHelper

def sibling_waitid_probe(request,deadline):
    libc=ctypes.CDLL(None,use_errno=True);libc.waitid.argtypes=[ctypes.c_int,ctypes.c_uint,ctypes.c_void_p,ctypes.c_int]
    b=ctypes.create_string_buffer(512);ctypes.set_errno(0)
    rc=libc.waitid(os.P_PID,request['leader_pid'],b,os.WEXITED|os.WNOHANG|os.WNOWAIT)
    if rc!=-1 or ctypes.get_errno()!=errno.ECHILD:raise RuntimeError('sibling unexpectedly owns leader')
    return {'request':request,'policy':'SAMPLED_STOP_THRESHOLD','members':[request['leader_pid']],'rss_bytes':1}
class TopologyTests(unittest.TestCase):
    def test_helper_is_sibling_parent_alone_retains_waitid(self):
        p=os.fork()
        if p==0:
            os.setsid()
            while True:time.sleep(1)
        try:
            deadline=time.monotonic()+2
            while time.monotonic()<deadline:
                try:
                    if os.getpgid(p)==p:break
                except ProcessLookupError:pass
                time.sleep(.01)
            identity=watchdog.process_start(p)
            def reservation():
                if watchdog.leader_exited(p):return ('exited_reserved',identity)
                current=watchdog.process_start(p)
                if current!=identity:raise RuntimeError('leader replaced')
                return ('alive',identity)
            h=CensusHelper(sibling_waitid_probe)
            try:
                sample=h.sample(p,reservation,lambda:os.killpg(p,signal.SIGKILL),time.monotonic()+5)
                self.assertEqual(sample['policy'],'SAMPLED_STOP_THRESHOLD')
                self.assertNotEqual(os.getpgid(h.pid),os.getpgid(p))
            finally:h.close()
        finally:
            try:os.killpg(p,signal.SIGKILL)
            except ProcessLookupError:pass
            os.waitpid(p,0)
if __name__=='__main__':unittest.main()

def watchdog_stall_sampler(request,deadline):
    time.sleep(20)

class WatchdogTopologyTest(unittest.TestCase):
    def test_helper_stall_gives_incomplete_and_attempts_worker_cleanup(self):
        import json,tempfile
        with tempfile.TemporaryDirectory() as d:
            life_r,life_w=os.pipe();ready_r,ready_w=os.pipe();release_r,release_w=os.pipe()
            sup=os.fork()
            if sup==0:
                os.close(life_r);os.close(ready_r);os.close(ready_w);os.close(release_r);os.close(release_w)
                while True:time.sleep(1)
            os.close(life_w);dog=os.fork()
            if dog==0:
                os.close(ready_r);os.close(release_w)
                try:watchdog.supervise(sup,watchdog.process_start(sup),life_r,release_r,ready_w,str(pathlib.Path(d)/'armed'),'term_ignore_descendant',timeout=12,fake_ready_timeout=10,use_fake_census_helper=True,fake_census_sampler=watchdog_stall_sampler)
                except BaseException:
                    import traceback;traceback.print_exc();os._exit(1)
                os._exit(0)
            os.close(life_r);os.close(ready_w);os.close(release_r)
            try:
                self.assertEqual(os.read(ready_r,1),b'R');os.write(release_w,b'G')
                end=time.monotonic()+12
                while time.monotonic()<end:
                    done,_=os.waitpid(dog,os.WNOHANG)
                    if done:dog=None;break
                    time.sleep(.03)
                self.assertIsNone(dog,'watchdog stalled')
                result=json.loads((pathlib.Path(d)/'armed.result').read_text())
                self.assertEqual(result['status'],'INCOMPLETE');self.assertIn('helper',result['reason'].lower())
                self.assertNotEqual(result['census_helper_pid'],result['worker_pid'])
            finally:
                os.close(ready_r);os.close(release_w)
                if dog is not None:
                    try:os.kill(dog,signal.SIGKILL)
                    except ProcessLookupError:pass
                    os.waitpid(dog,0)
                try:os.kill(sup,signal.SIGKILL)
                except ProcessLookupError:pass
                os.waitpid(sup,0)

def sampler_exit(request,deadline):os._exit(17)
def sampler_denied(request,deadline):raise PermissionError('synthetic AccessDenied')
def sampler_gone(request,deadline):raise ProcessLookupError('synthetic NoSuchProcess')
def sampler_churn(request,deadline):return {'request':{**request,'request_id':'bad'},'policy':'SAMPLED_STOP_THRESHOLD','members':[request['leader_pid']],'rss_bytes':1}
def sampler_missing(request,deadline):return {'request':request,'policy':'SAMPLED_STOP_THRESHOLD','members':[],'rss_bytes':1}
class FailureMatrix(unittest.TestCase):
    def test_helper_failures_abort_and_leave_incomplete(self):
        import json,tempfile
        for sampler in (sampler_exit,sampler_denied,sampler_gone,sampler_churn,sampler_missing):
            with self.subTest(sampler=sampler.__name__),tempfile.TemporaryDirectory() as d:
                lr,lw=os.pipe();rr,rw=os.pipe();pr,pw=os.pipe();sup=os.fork()
                if sup==0:
                    os.close(lr);os.close(rr);os.close(rw);os.close(pr);os.close(pw)
                    while True:time.sleep(1)
                os.close(lw);dog=os.fork()
                if dog==0:
                    os.close(rr);os.close(pw)
                    try:watchdog.supervise(sup,watchdog.process_start(sup),lr,pr,rw,str(pathlib.Path(d)/'armed'),'term_ignore_descendant',timeout=12,fake_ready_timeout=10,use_fake_census_helper=True,fake_census_sampler=sampler)
                    finally:os._exit(0)
                os.close(lr);os.close(rw);os.close(pr)
                try:
                    self.assertEqual(os.read(rr,1),b'R');os.write(pw,b'G');end=time.monotonic()+12
                    while time.monotonic()<end:
                        done,_=os.waitpid(dog,os.WNOHANG)
                        if done:dog=None;break
                        time.sleep(.03)
                    self.assertIsNone(dog,'watchdog timed out')
                    result=json.loads((pathlib.Path(d)/'armed.result').read_text())
                    self.assertEqual(result['status'],'INCOMPLETE');self.assertIn('helper',result['reason'].lower())
                    self.assertTrue(result['cleanup_errors'])
                finally:
                    os.close(rr);os.close(pw)
                    if dog is not None:
                        try:os.kill(dog,signal.SIGKILL)
                        except ProcessLookupError:pass
                        os.waitpid(dog,0)
                    try:os.kill(sup,signal.SIGKILL)
                    except ProcessLookupError:pass
                    os.waitpid(sup,0)
