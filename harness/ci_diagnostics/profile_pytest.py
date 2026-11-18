#!/usr/bin/env python3
"""Profile an explicitly supplied pytest command, without changing its selection."""
import argparse
import json
import os
from pathlib import Path
import re
import resource
import signal
import subprocess
import sys
import tempfile
import threading
import time

DURATION = re.compile(r'^\s*([0-9]+(?:\.[0-9]+)?)s\s+(setup|call|teardown)\s+(.+?)\s*$')


def slow_tests(lines):
    rows=[]
    for line in lines:
        match=DURATION.match(line)
        if match: rows.append({'seconds':float(match.group(1)),'phase':match.group(2),'nodeid':match.group(3)})
    return sorted(rows,key=lambda row:-row['seconds'])


def profile(command, output, durations=10):
    if not command or durations < 1: raise ValueError('command and positive durations required')
    cmd=[*command,f'--durations={durations}']; started=time.monotonic(); lines=[]; signalled=[]
    child=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
    old={}; grace_timer=None; cleanup_errors=[]
    def kill_group():
        try: os.killpg(child.pid,signal.SIGKILL)
        except ProcessLookupError: pass
        except OSError as exc: cleanup_errors.append(str(exc))
    def group_exists():
        try: os.killpg(child.pid,0); return True
        except ProcessLookupError: return False
        except OSError as exc:
            cleanup_errors.append(str(exc)); return True
    def forward(sig, _frame):
        nonlocal grace_timer
        signalled.append(sig)
        try: os.killpg(child.pid,sig)
        except ProcessLookupError: pass
        except OSError as exc: cleanup_errors.append(str(exc))
        if grace_timer is None:
            grace_timer=threading.Timer(3.0,kill_group);grace_timer.daemon=True;grace_timer.start()
    for sig in (signal.SIGINT,signal.SIGTERM): old[sig]=signal.signal(sig,forward)
    def stream():
        try:
            for raw in iter(child.stdout.readline,b''):
                sys.stdout.buffer.write(raw);sys.stdout.buffer.flush();lines.append(raw.decode('utf-8',errors='replace').rstrip('\r\n'))
        except (OSError, ValueError):
            pass
    thread=threading.Thread(target=stream,daemon=True);thread.start()
    try:
        _,status,usage=os.wait4(child.pid,0);child.returncode=os.waitstatus_to_exitcode(status)
        if grace_timer is not None: grace_timer.cancel()
        # The leader can exit while descendants remain in its process group,
        # including descendants that closed stdout and cannot delay draining.
        residual_group_detected=group_exists()
        if signalled or residual_group_detected: kill_group()
        thread.join(timeout=3)
        drain_timed_out=thread.is_alive()
        if drain_timed_out:
            kill_group();thread.join(timeout=3)
        drain_complete=not thread.is_alive()
        if not drain_complete:
            try: os.close(child.stdout.fileno())
            except OSError: pass
    finally:
        for sig, handler in old.items(): signal.signal(sig,handler)
    profile_success=child.returncode == 0 and not signalled and not residual_group_detected and not drain_timed_out and drain_complete and not cleanup_errors
    wrapper_rc=child.returncode if child.returncode != 0 else (0 if profile_success else 1)
    report={'schema':'kdm6.pytest_resource_profile.v1','command':cmd,'cwd':os.getcwd(),'returncode':child.returncode,'profile_success':profile_success,'wrapper_exit_code':wrapper_rc,'forwarded_signals':signalled,'residual_group_detected':residual_group_detected,'signal_grace_seconds':3,'cleanup_errors':cleanup_errors,'output_drain_complete':drain_complete,'wall_seconds':time.monotonic()-started,'user_seconds':usage.ru_utime,'system_seconds':usage.ru_stime,'max_rss':usage.ru_maxrss,'max_rss_unit':'bytes' if sys.platform=='darwin' else ('KiB' if sys.platform.startswith('linux') else 'platform-dependent'),'resource_scope':'wait4 child process resource usage; descendant accounting follows OS semantics, not aggregate concurrent peak RSS','slow_tests':slow_tests(lines),'duration_note':'pytest --durations output, subject to pytest display precision and captured phases'}
    destination=Path(output)
    fd,temp=tempfile.mkstemp(prefix='.'+destination.name+'.',dir=destination.parent)
    try:
        with os.fdopen(fd,'w') as f:
            json.dump(report,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(temp,destination)
        dirfd=os.open(destination.parent,os.O_RDONLY)
        try: os.fsync(dirfd)
        finally: os.close(dirfd)
    finally:
        if os.path.exists(temp): os.unlink(temp)
    return wrapper_rc


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--durations',type=int,default=10);parser.add_argument('command',nargs=argparse.REMAINDER);args=parser.parse_args();command=args.command
    if command and command[0]=='--':command=command[1:]
    if not command:parser.error('supply the pytest command after --')
    rc=profile(command,args.output,args.durations)
    if rc < 0:
        sig=-rc
        if sig != signal.SIGKILL: signal.signal(sig,signal.SIG_DFL)
        os.kill(os.getpid(),sig)
        return 128+sig
    return rc

if __name__=='__main__':sys.exit(main())
