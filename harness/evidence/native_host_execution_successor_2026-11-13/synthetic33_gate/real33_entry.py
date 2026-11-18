"""Private worker entrypoint; release gate precedes all DSO loading."""
import json,os,pathlib

def main():
    ready=int(os.environ['RESEARCH_READY_FD']);release=int(os.environ['RESEARCH_RELEASE_FD'])
    out=pathlib.Path(os.environ['RESEARCH_OUTDIR']).resolve(strict=True)
    os.write(ready,b'R');os.close(ready)
    import real33_worker as worker
    if os.environ.get('RESEARCH_FAKE_ONLY')=='1':
        from test_real33_worker import FakeRunner
        worker.preflight=lambda:{'dso_path':'fake-only'}
        worker.Runner=FakeRunner
    result=worker.run(release,str(out))
    tmp=out/'worker_result.tmp';target=out/'worker_result.json'
    with open(tmp,'x') as f:json.dump(result,f,sort_keys=True,allow_nan=False);f.flush();os.fsync(f.fileno())
    os.link(tmp,target);os.unlink(tmp);fd=os.open(out,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)
if __name__=='__main__':main()
