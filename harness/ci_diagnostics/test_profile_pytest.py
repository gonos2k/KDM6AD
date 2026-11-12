import importlib.util
import json
import os
import signal
import time
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT=Path(__file__).with_name('profile_pytest.py')
spec=importlib.util.spec_from_file_location('profile_pytest',SCRIPT);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class ProfileTest(unittest.TestCase):
    def test_duration_parse(self):
        lines=['0.12s call test_one.py::test_a','0.03s setup test_one.py::test_a','irrelevant']
        self.assertEqual([x['phase'] for x in m.slow_tests(lines)],['call','setup'])
    def test_exit_and_profile(self):
        with tempfile.TemporaryDirectory() as td:
            report=Path(td)/'r.json'; code='import sys;print("0.12s call x::test_y");sys.exit(7)'
            proc=subprocess.run([sys.executable,str(SCRIPT),'--output',str(report),'--',sys.executable,'-c',code],capture_output=True,text=True)
            self.assertEqual(proc.returncode,7);r=json.loads(report.read_text());self.assertEqual(r['returncode'],7);self.assertEqual(r['slow_tests'][0]['nodeid'],'x::test_y');self.assertEqual(r['command'][-1],'--durations=10');self.assertGreaterEqual(r['wall_seconds'],0)

    def test_sigterm_forwarded_and_reported(self):
        with tempfile.TemporaryDirectory() as td:
            report=Path(td)/'r.json'
            proc=subprocess.Popen([sys.executable,str(SCRIPT),'--output',str(report),'--',sys.executable,'-c','import time;time.sleep(30)'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                time.sleep(0.5);proc.send_signal(signal.SIGTERM);proc.communicate(timeout=5)
                self.assertEqual(proc.returncode,-signal.SIGTERM)
                data=json.loads(report.read_text());self.assertEqual(data['returncode'],-signal.SIGTERM);self.assertIn(signal.SIGTERM,data['forwarded_signals'])
            finally:
                if proc.poll() is None: proc.kill();proc.wait()

    def test_term_ignoring_grandchild_does_not_hang(self):
        with tempfile.TemporaryDirectory() as td:
            report=Path(td)/'r.json'
            grandchild='import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);print("ready",flush=True);time.sleep(30)'
            child='import subprocess,sys,time;subprocess.Popen([sys.executable,"-c",'+repr(grandchild)+']);time.sleep(30)'
            proc=subprocess.Popen([sys.executable,str(SCRIPT),'--output',str(report),'--',sys.executable,'-c',child],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                self.assertEqual(proc.stdout.readline().strip(),b'ready')
                proc.send_signal(signal.SIGTERM);proc.communicate(timeout=6)
                self.assertEqual(proc.returncode,-signal.SIGTERM)
                data=json.loads(report.read_text());self.assertEqual(data['returncode'],-signal.SIGTERM);self.assertTrue(data['output_drain_complete'])
            finally:
                if proc.poll() is None: proc.kill();proc.wait()

    def test_graceful_child_exit_after_cancel_still_fails(self):
        with tempfile.TemporaryDirectory() as td:
            report=Path(td)/'r.json'
            child='import signal,sys,time;signal.signal(signal.SIGTERM,lambda *_:sys.exit(0));print("ready",flush=True);time.sleep(30)'
            proc=subprocess.Popen([sys.executable,str(SCRIPT),'--output',str(report),'--',sys.executable,'-c',child],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                self.assertEqual(proc.stdout.readline().strip(),b'ready')
                proc.send_signal(signal.SIGTERM);proc.communicate(timeout=6)
                self.assertEqual(proc.returncode,1)
                data=json.loads(report.read_text())
                self.assertEqual(data['returncode'],0)
                self.assertIn(signal.SIGTERM,data['forwarded_signals'])
                self.assertFalse(data['profile_success'])
                self.assertEqual(data['wrapper_exit_code'],1)
            finally:
                if proc.poll() is None:proc.kill();proc.wait()

    def test_silent_grandchild_after_successful_leader_is_killed(self):
        with tempfile.TemporaryDirectory() as td:
            report=Path(td)/'r.json'
            grandchild='import time;time.sleep(30)'
            child='import subprocess,sys;p=subprocess.Popen([sys.executable,"-c",'+repr(grandchild)+'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);print(p.pid,flush=True)'
            proc=subprocess.run([sys.executable,str(SCRIPT),'--output',str(report),'--',sys.executable,'-c',child],capture_output=True,text=True,timeout=10)
            pid=int(proc.stdout.strip())
            data=json.loads(report.read_text())
            self.assertEqual(data['returncode'],0)
            self.assertTrue(data['residual_group_detected'])
            self.assertFalse(data['profile_success'])
            self.assertEqual(proc.returncode,1)
            state=subprocess.run(['ps','-o','stat=','-p',str(pid)],capture_output=True,text=True,check=False).stdout.strip()
            self.assertTrue(not state or state.startswith('Z'),f'grandchild still running: {state}')

    def test_term_ignoring_child_and_grandchild_are_killed(self):
        with tempfile.TemporaryDirectory() as td:
            report=Path(td)/'r.json'
            grandchild='import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);print("ready",flush=True);time.sleep(30)'
            child='import signal,subprocess,sys,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);subprocess.Popen([sys.executable,"-c",'+repr(grandchild)+']);time.sleep(30)'
            proc=subprocess.Popen([sys.executable,str(SCRIPT),'--output',str(report),'--',sys.executable,'-c',child],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                self.assertEqual(proc.stdout.readline().strip(),b'ready')
                started=time.monotonic();proc.send_signal(signal.SIGTERM);_,err=proc.communicate(timeout=8)
                self.assertLess(time.monotonic()-started,7);self.assertEqual(proc.returncode,-signal.SIGKILL,err.decode())
                data=json.loads(report.read_text());self.assertEqual(data['returncode'],-signal.SIGKILL);self.assertTrue(data['output_drain_complete']);self.assertIn(signal.SIGTERM,data['forwarded_signals'])
            finally:
                if proc.poll() is None: proc.kill();proc.wait()

    def test_successful_leader_with_pipe_holding_grandchild_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            report=Path(td)/'r.json'
            grandchild='import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);print("ready",flush=True);time.sleep(30)'
            child='import subprocess,sys;subprocess.Popen([sys.executable,"-c",'+repr(grandchild)+'])'
            proc=subprocess.Popen([sys.executable,str(SCRIPT),'--output',str(report),'--',sys.executable,'-c',child],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                _,err=proc.communicate(timeout=8)
                self.assertEqual(proc.returncode,1,err.decode())
                data=json.loads(report.read_text());self.assertEqual(data['returncode'],0);self.assertEqual(data['wrapper_exit_code'],1);self.assertFalse(data['profile_success']);self.assertTrue(data['residual_group_detected']);self.assertTrue(data['output_drain_complete'])
            finally:
                if proc.poll() is None:proc.kill();proc.wait()

if __name__=='__main__':unittest.main()
