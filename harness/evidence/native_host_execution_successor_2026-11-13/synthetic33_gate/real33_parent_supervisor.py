"""Success-only parent observation; real execution remains disabled.

The model wall ends before the separate atomic publication step. A timeout or
lost child has no completion witness and cannot establish watchdog cleanup.
Same-UID tampering and escaped process groups are outside this contract.
Atomic link is the commit point: abrupt process death after link may leave a
witness. Synchronous post-link failures attempt durable removal; failed removal
is explicitly reported as uncertain and must not be treated as success.
"""
import hashlib
import json
import os
import re
from pathlib import Path
import signal
import tempfile
import time

import real33_orchestrate as child
import replay33_assets
import witness33

REAL_PARENT_ENABLED = False
_CANCELLED = []


def _cancel(signum, _frame):
    _CANCELLED.append(signum)


def _sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _canonical(value):
    return (json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode('ascii')


def _claim_attempt(manifest_path,approved_sha,out,started):
    """Permanently claim one attempt; incomplete writes still block retries.

    This is a trusted-code workflow guard, not security authentication or a
    defense against deliberate modification by the same OS user.
    """
    manifest=Path(manifest_path)
    if type(approved_sha) is not str or re.fullmatch('[0-9a-f]{64}',approved_sha) is None:
        raise ValueError('invalid approved manifest SHA')
    if not manifest.is_absolute() or manifest.is_symlink() or str(manifest.resolve(strict=True))!=str(manifest) or not manifest.is_file():
        raise ValueError('manifest canonical path or SHA mismatch')
    raw=manifest.read_bytes()
    if _sha_bytes(raw)!=approved_sha:raise ValueError('manifest canonical path or SHA mismatch')
    document=json.loads(raw)
    if type(document) is not dict or document.get('schema')!='kdm6.synthetic33.private.v1' or document.get('status')!='REVIEWED_PINNED':raise ValueError('unreviewed manifest')
    root_name=document.get('attempt_registry_root')
    if type(root_name) is not str:raise ValueError('missing pinned attempt registry root')
    root=Path(root_name)
    if not root.is_absolute() or root.is_symlink() or str(root.resolve(strict=True))!=str(root) or not root.is_dir():raise ValueError('invalid canonical attempt registry root')
    if not out.is_absolute() or out.is_symlink() or str(out.resolve(strict=True))!=str(out) or not out.is_dir() or manifest.parent==out or root==out:
        raise ValueError('invalid canonical output directory')
    registry=root / ('.synthetic33-attempt-'+approved_sha+'.json')
    record={'schema':'kdm6.synthetic33.attempt.v1','status':'ATTEMPT_CLAIMED_UNVERIFIED','manifest_path':str(manifest),'manifest_sha256':approved_sha,'registry_root':str(root),'output_dir':str(out),'started_monotonic':started,'parent_source_sha256':witness33.sha(__file__)}
    data=_canonical(record)
    fd=os.open(registry,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
    try:
        with os.fdopen(fd,'wb') as stream:
            fd=-1;stream.write(data);stream.flush();os.fsync(stream.fileno())
    finally:
        if fd>=0:os.close(fd)
    directory_fd=os.open(root,os.O_RDONLY)
    try:os.fsync(directory_fd)
    finally:os.close(directory_fd)
    return registry


def _stop_child(pid):
    """Signal only our unreaped direct child; never target a numeric worker PGID."""
    try:os.kill(pid,signal.SIGTERM)
    except ProcessLookupError:pass
    end=time.monotonic()+2
    while time.monotonic()<end:
        try:
            done,_=os.waitpid(pid,os.WNOHANG)
            if done==pid:return True
        except ChildProcessError:return False
        time.sleep(.02)
    try:os.kill(pid,signal.SIGKILL)
    except ProcessLookupError:pass
    end=time.monotonic()+1
    while time.monotonic()<end:
        try:
            if os.waitpid(pid,os.WNOHANG)[0]==pid:return True
        except ChildProcessError:return False
        time.sleep(.02)
    return False


def run(outdir,manifest_path,approved_sha):
    if not REAL_PARENT_ENABLED:raise RuntimeError('parent real execution disabled pending containment review')
    started=time.monotonic();_CANCELLED.clear()
    out=Path(outdir)
    if not out.is_absolute() or out.is_symlink() or str(out.resolve(strict=True))!=str(out) or not out.is_dir() or any(out.iterdir()):raise ValueError('fresh canonical empty output directory required')
    config=child.reviewed_configuration(manifest_path,approved_sha)
    total_deadline=started+config['policy']['wall_seconds']
    execution_deadline=total_deadline-config['policy']['cleanup_reserve_seconds']
    if time.monotonic()>=execution_deadline:raise RuntimeError('parent preflight deadline')
    attempt_path=_claim_attempt(manifest_path,approved_sha,out,started)
    attempt_sha=witness33.sha(attempt_path)
    if time.monotonic()>=execution_deadline:raise RuntimeError('parent attempt registration deadline')
    readfd,writefd=os.pipe();pid=None;reaped=False
    handlers={sig:signal.signal(sig,_cancel) for sig in (signal.SIGTERM,signal.SIGINT)}
    try:
        pid=os.fork()
        if pid==0:
            os.close(readfd)
            try:
                result=child.run(out,manifest_path,approved_sha)
                if result.get('schema')!='kdm6.synthetic33.completion_candidate.v1' or result.get('status')!='CANDIDATE_UNVERIFIED':raise RuntimeError('invalid child return')
                data=(out/'completion_candidate.json').read_bytes()
                if json.loads(data)!=result:raise RuntimeError('candidate differs from returned object')
                token={'schema':'kdm6.synthetic33.parent_child_return.v1','child_pid':os.getpid(),'manifest_sha256':approved_sha,'run_nonce':result['run_nonce'],'candidate_sha256':_sha_bytes(data)}
                raw=_canonical(token)
                if os.write(writefd,raw)!=len(raw):raise RuntimeError('short return token')
                os.close(writefd);os._exit(0)
            except BaseException:os._exit(1)
        os.close(writefd);writefd=None
        child_start=child.watchdog.process_start(pid)
        status=None
        while time.monotonic()<execution_deadline:
            if _CANCELLED:break
            try:done,status=os.waitpid(pid,os.WNOHANG)
            except ChildProcessError:
                reaped=True
                raise RuntimeError('unexpected child ownership loss')
            if done==pid:reaped=True;break
            time.sleep(min(.05,max(0,execution_deadline-time.monotonic())))
        if not reaped:
            child_reaped=_stop_child(pid);reaped=True
            return {'status':'UNWITNESSED','reason':'cancelled or parent execution deadline','child_reaped':child_reaped,'cleanup':'UNVERIFIED'}
        if status!=0 or _CANCELLED:
            return {'status':'UNWITNESSED','reason':'child nonzero exit or cancellation','cleanup':'UNVERIFIED'}
        os.set_blocking(readfd,False)
        try:token_raw=os.read(readfd,4097)
        except BlockingIOError:token_raw=b''
        if not token_raw or len(token_raw)>4096:raise RuntimeError('missing or oversized child return token')
        try:tail=os.read(readfd,1)
        except BlockingIOError:raise RuntimeError('child return token missing EOF')
        if tail:raise RuntimeError('child return token trailing bytes')
        token=json.loads(token_raw)
        if _canonical(token)!=token_raw or set(token)!={'schema','child_pid','manifest_sha256','run_nonce','candidate_sha256'} or token['schema']!='kdm6.synthetic33.parent_child_return.v1' or type(token['child_pid']) is not int or token['child_pid']!=pid or token['manifest_sha256']!=approved_sha:raise RuntimeError('child return token identity')
        if (out/'cleanup_unresolved.json').exists():raise RuntimeError('cleanup unresolved')
        candidate_bytes=(out/'completion_candidate.json').read_bytes();candidate=json.loads(candidate_bytes)
        if _sha_bytes(candidate_bytes)!=token['candidate_sha256'] or candidate.get('schema')!='kdm6.synthetic33.completion_candidate.v1' or candidate.get('status')!='CANDIDATE_UNVERIFIED' or candidate.get('manifest_sha256')!=approved_sha or candidate.get('run_nonce')!=token['run_nonce'] or (out/'run_nonce').read_text()!=token['run_nonce']:raise RuntimeError('candidate identity')
        armed=json.loads((out/'armed.json').read_text());result=json.loads((out/'armed.json.result').read_text())
        if armed.get('status')!='ARMED_UNVERIFIED':raise RuntimeError('armed status')
        marker_sha=child.validate_consumed_marker(out/'authority_consumed.json',armed,result)
        fields=('worker_pid','worker_start','watchdog_pid','watchdog_start')
        if any(type(candidate.get(k)) is not type(result.get(k)) or candidate.get(k)!=result.get(k) or (k.endswith('_start') and any(type(x) is not int for x in candidate[k])) for k in fields):raise RuntimeError('worker/watchdog identity')
        if result.get('supervisor_pid')!=pid or type(result.get('supervisor_pid')) is not int or result.get('supervisor_start')!=list(child_start):raise RuntimeError('child supervisor identity')
        receipts={str(p):witness33.sha(p) for p in (out/'armed.json',out/'armed.json.result',out/'authority_consumed.json')}
        if candidate.get('receipt_sha256')!=receipts or receipts[str(out/'authority_consumed.json')]!=marker_sha:raise RuntimeError('receipt digest mismatch')
        trace=result['exclusive_trace']
        if witness33.sha(trace['path'])!=trace['sha256']:raise RuntimeError('trace digest mismatch')
        before=child.validate_before_publication(out,result,started,execution_deadline,manifest_path,approved_sha,trace['path'])
        if before.get('status')!='EXECUTION_COMPLETED_ASSETS_ONLY' or before!=candidate.get('validated_assets'):raise RuntimeError('independent postcheck differs')
        replay=replay33_assets.replay(out)
        if replay!=before['offline_replay']:raise RuntimeError('independent replay differs')
        if child.reviewed_configuration(manifest_path,approved_sha)!=config:raise RuntimeError('manifest configuration changed')
        if any(witness33.sha(path)!=digest for path,digest in {**before['asset_sha256'],**receipts}.items()):raise RuntimeError('asset changed after validation')
        if _CANCELLED or (out/'cleanup_unresolved.json').exists() or time.monotonic()>=total_deadline:raise RuntimeError('cancelled or parent wall exceeded')
        payload={'schema':'kdm6.synthetic33.parent_witness.v1','status':'PARENT_OBSERVED_ASSETS_ONLY','scientific_status':'INCONCLUSIVE','manifest_sha256':approved_sha,'run_nonce':token['run_nonce'],'child_pid':pid,'child_exit_code':0,'candidate_sha256':token['candidate_sha256'],'attempt_registry_path':str(attempt_path),'attempt_registry_sha256':attempt_sha,'receipt_sha256':receipts,'asset_sha256':before['asset_sha256'],'worker_pid':candidate['worker_pid'],'worker_start':candidate['worker_start'],'watchdog_pid':candidate['watchdog_pid'],'watchdog_start':candidate['watchdog_start'],'parent_source_sha256':witness33.sha(__file__),'postcheck_elapsed_seconds':time.monotonic()-started,'observed_wall_limit_seconds':config['policy']['wall_seconds'],'publication_scope':'publication is separate from observed model wall; same-UID trust and escaped groups remain limitations'}
        raw=_canonical(payload)
        fd,tmp=tempfile.mkstemp(prefix='.parent-witness.',dir=out)
        temp_removed=False
        try:
            with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
            old=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
            try:
                if _CANCELLED or signal.sigpending() & {signal.SIGINT,signal.SIGTERM} or time.monotonic()>=total_deadline:raise RuntimeError('cancelled or parent wall exceeded')
                if child.reviewed_configuration(manifest_path,approved_sha)!=config or any(witness33.sha(path)!=digest for path,digest in {**before['asset_sha256'],**receipts}.items()) or witness33.sha(out/'completion_candidate.json')!=token['candidate_sha256'] or witness33.sha(attempt_path)!=attempt_sha:raise RuntimeError('publication inputs changed')
                if _CANCELLED or signal.sigpending() & {signal.SIGINT,signal.SIGTERM} or time.monotonic()>=total_deadline:raise RuntimeError('cancelled or parent wall exceeded')
                publication_started=time.monotonic();linked=False;target=out/'parent_witness.json'
                try:
                    os.link(tmp,target);linked=True
                    directory_fd=os.open(out,os.O_RDONLY)
                    try:os.fsync(directory_fd)
                    finally:os.close(directory_fd)
                    # A synchronous failure here must retract the final link.
                    os.unlink(tmp);temp_removed=True
                except BaseException as publication_error:
                    if linked:
                        try:
                            os.unlink(target)
                            directory_fd=os.open(out,os.O_RDONLY)
                            try:os.fsync(directory_fd)
                            finally:os.close(directory_fd)
                        except BaseException as cleanup_error:
                            raise RuntimeError('publication durability/cleanup uncertain: '+repr(cleanup_error)) from publication_error
                    raise
            finally:signal.pthread_sigmask(signal.SIG_SETMASK,old)
        finally:
            if not temp_removed:
                try:os.unlink(tmp)
                except OSError:pass  # The final link is already retracted or uncertain.
        return {'status':'PARENT_OBSERVED_ASSETS_ONLY','witness_sha256':_sha_bytes(raw),'publication_seconds':time.monotonic()-publication_started}
    except Exception as exc:
        return {'status':'UNWITNESSED','reason':repr(exc),'cleanup':'UNVERIFIED'}
    finally:
        if writefd is not None:os.close(writefd)
        os.close(readfd)
        if pid is not None and not reaped:_stop_child(pid)
        for sig,handler in handlers.items():signal.signal(sig,handler)
