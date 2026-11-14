"""Fake-only bounded census-helper protocol; no DSO/model integration.

The caller is the worker's direct parent and must provide a non-reaping
reservation check. Helper is a separately supervised child/process group.
RSS is a sampled stop threshold, never a hard memory cap.
"""
import json,os,secrets,select,signal,socket,struct,time,subprocess
MAX_FRAME=16384
class HelperError(RuntimeError):pass

def start_float(identity):
    if not isinstance(identity,tuple) or len(identity)!=2 or any(type(x) is not int for x in identity):raise HelperError('invalid start identity')
    sec,usec=identity
    if sec<=0 or not 0<=usec<1000000:raise HelperError('invalid start time')
    value=sec+usec/1000000.
    # Reject an ambiguous float conversion, rather than silently widening it.
    if round(value*1000000)!=sec*1000000+usec:raise HelperError('ambiguous start conversion')
    return value

def _send(sock,obj,deadline):
    data=json.dumps(obj,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    if len(data)>MAX_FRAME:raise HelperError('frame too large')
    data=struct.pack('!I',len(data))+data
    while data:
        left=deadline-time.monotonic()
        if left<=0 or not select.select([],[sock],[],left)[1]:raise HelperError('helper write timeout')
        try:n=sock.send(data)
        except (BlockingIOError,InterruptedError):continue
        if n<=0:raise HelperError('helper closed')
        data=data[n:]

def _recv(sock,deadline):
    def exact(n):
        b=b''
        while len(b)<n:
            left=deadline-time.monotonic()
            if left<=0 or not select.select([sock],[],[],left)[0]:raise HelperError('helper read timeout')
            try:x=sock.recv(n-len(b))
            except (BlockingIOError,InterruptedError):continue
            if not x:raise HelperError('helper EOF')
            b+=x
        return b
    n=struct.unpack('!I',exact(4))[0]
    if not 0<n<=MAX_FRAME:raise HelperError('bad frame length')
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise HelperError('duplicate JSON key')
            result[key]=value
        return result
    value=json.loads(exact(n),object_pairs_hook=unique)
    if type(value) is not dict:raise HelperError('invalid frame')
    return value

class CensusHelper:
    def __init__(self,sampler,*,startup_timeout=2.,clock=time.monotonic,fake_startup_stall=False):
        """sampler is injected fake; native provider wiring is intentionally blocked."""
        self.clock=clock;self.nonce=secrets.token_hex(32);self.seq=0;self.next_sample=0.;self.closed=False
        parent,child=socket.socketpair();parent.setblocking(False);child.setblocking(False);self.sock=parent;self.group_ready=False;pid=os.fork()
        if pid==0:
            parent.close()
            keep=child.fileno()
            for name in os.listdir('/dev/fd'):
                try:fd=int(name)
                except ValueError:continue
                if fd>2 and fd!=keep:
                    try:os.close(fd)
                    except OSError:pass
            try:
                # Trusted helper contract: no descendant creation. This guards
                # Python APIs; it is not an OS sandbox against native code.
                def forbidden(*args,**kwargs):raise HelperError('helper process creation forbidden')
                os.fork=forbidden
                if hasattr(os,'posix_spawn'):os.posix_spawn=forbidden
                if hasattr(os,'posix_spawnp'):os.posix_spawnp=forbidden
                subprocess.Popen=forbidden
                if fake_startup_stall:time.sleep(20)
                os.setsid();_send(child,{'ready':'FAKE_HELPER_ONLY'},time.monotonic()+startup_timeout)
                while True:
                    request=_recv(child,time.monotonic()+900.)
                    try:
                        sample=sampler(request,request['deadline'])
                        _send(child,{'request':request,'sample':sample},request['deadline'])
                    except BaseException as exc:
                        _send(child,{'request':request,'error':type(exc).__name__},time.monotonic()+1.)
            except BaseException:pass
            finally:child.close();os._exit(0)
        child.close();self.pid=pid
        try:
            reply=_recv(self.sock,time.monotonic()+startup_timeout)
            if reply!={'ready':'FAKE_HELPER_ONLY'} or os.getpgid(pid)!=pid:raise HelperError('helper identity')
            self.group_ready=True
        except BaseException:
            self.close();raise
    def sample(self,leader,reservation,abort_worker,whole_deadline):
        """Parent reservation() -> (alive|exited_reserved, (sec,usec))."""
        try:
            now=self.clock()
            if self.closed or self.seq>=903 or now<self.next_sample:raise HelperError('sample budget/rate')
            state,identity=reservation();start=start_float(identity)
            if state not in ('alive','exited_reserved') or whole_deadline<=time.monotonic():raise HelperError('invalid parent reservation/deadline')
            self.seq+=1;self.next_sample=now+1.
            deadline=min(whole_deadline,time.monotonic()+2.)
            request={'request_id':str(self.seq),'nonce':self.nonce,'leader_pid':leader,'leader_start':start,'leader_state':state,'parent_start':list(identity),'deadline':deadline}
            _send(self.sock,request,deadline);reply=_recv(self.sock,deadline)
            if reply.get('request')!=request or 'error' in reply:raise HelperError('helper response identity/error')
            sample=reply.get('sample')
            if type(sample) is not dict or sample.get('request')!=request or sample.get('policy')!='SAMPLED_STOP_THRESHOLD' or type(sample.get('rss_bytes')) is not int or sample['rss_bytes']<0:raise HelperError('invalid sample')
            members=sample.get('members')
            if not isinstance(members,(list,tuple)) or leader not in members or len(set(members))!=len(members) or any(type(p) is not int or p<=0 for p in members):raise HelperError('invalid group inventory')
            if reservation()!=(state,identity):raise HelperError('parent reservation changed')
            return sample
        except BaseException:
            # Signal worker before waiting for a stuck helper.
            try:abort_worker()
            finally:self.close()
            raise
    def close(self):
        if self.closed:return
        self.closed=True;errors=[]
        try:
            if self.group_ready:os.killpg(self.pid,signal.SIGKILL)
            else:os.kill(self.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        except OSError as exc:
            errors.append('group signal: '+repr(exc))
            # The direct child PID remains reserved; kill it conservatively.
            try:os.kill(self.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            except OSError as child_exc:errors.append('child signal: '+repr(child_exc))
        finally:self.sock.close()
        if errors:raise HelperError('; '.join(errors)+'; helper remains unreaped')
        end=time.monotonic()+2.;reaped=False
        while time.monotonic()<end:
            try:
                p,_=os.waitpid(self.pid,os.WNOHANG)
                if p:reaped=True;break
            except ChildProcessError:reaped=True;break
            time.sleep(.02)
        if not reaped:errors.append('helper not reaped')
        if errors:raise HelperError('; '.join(errors))

def native_sampler(package,manifest):
    """Lazy provider construction executes only inside the guarded helper."""
    provider=None
    def sample(request,deadline):
        nonlocal provider
        from darwin_census_provider import DarwinProvider,sample_group
        if provider is None:provider=DarwinProvider(package,manifest)
        return sample_group(provider,request,deadline)
    return sample
