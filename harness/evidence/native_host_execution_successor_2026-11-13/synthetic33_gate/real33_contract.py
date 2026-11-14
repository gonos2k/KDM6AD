"""Parameterized research preflight. Manifest remains private; no DSO is loaded."""
import hashlib,json,os,pathlib,re
import fixture33

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()

def preflight():
    name=os.environ.get('RESEARCH_PRIVATE_MANIFEST');pin=os.environ.get('RESEARCH_MANIFEST_SHA256')
    if not name or not pin or not re.fullmatch('[0-9a-f]{64}',pin):raise ValueError('independent manifest pin required')
    path=pathlib.Path(name).resolve(strict=True)
    if sha(path)!=pin:raise ValueError('manifest pin mismatch')
    manifest=json.loads(path.read_text())
    if manifest.get('schema')!='kdm6.synthetic33.private.v1' or manifest.get('status')!='REVIEWED_PINNED':raise ValueError('unreviewed private manifest')
    if manifest.get('slots')!=fixture33.validate():raise ValueError('slot plan mismatch')
    assets=manifest.get('assets');dso=manifest.get('dso_path');interpreter=manifest.get('interpreter')
    if type(assets) is not dict or type(dso) is not str or dso not in assets or type(interpreter) is not str or interpreter not in assets:raise ValueError('missing asset pins')
    for name,digest in assets.items():
        p=pathlib.Path(name)
        if not p.is_absolute() or str(p.resolve(strict=True))!=name or not re.fullmatch('[0-9a-f]{64}',digest) or sha(p)!=digest:raise ValueError('asset pin mismatch')
    required=('fixture_plan.py','fixture33.py','graph_runner.py','real33_worker.py','real33_entry.py','real33_contract.py','real33_supervisor_draft.py','real33_orchestrate.py','witness33.py','trace33.py','freeze33.py','fake_watchdog/watchdog.py')
    root=pathlib.Path(__file__).resolve().parent
    if any(str((root/q).resolve(strict=True)) not in assets for q in required):raise ValueError('missing script pins')
    return {'status':'SPEC_ONLY_UNVERIFIED_RUNTIME_LOADER','dso_path':dso,'dso_sha256':assets[dso],'interpreter':interpreter,'calls':manifest['slots']}
