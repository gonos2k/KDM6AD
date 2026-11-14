"""Parameterized research preflight. Manifest remains private; no DSO is loaded."""
import hashlib,json,os,pathlib,re
import fixture33

# Include the optional census machinery conservatively even while its real-mode
# activation remains blocked; the manifest pins every selectable local helper.
EXECUTION_SOURCE_FILES=(
    'fixture_plan.py','fixture33.py','selector_manifest_spec_v1.py',
    'graph_runner.py','real33_worker.py','real33_entry.py','real33_contract.py',
    'real33_supervisor_draft.py','real33_orchestrate.py','witness33.py',
    'trace33.py','freeze33.py','fake_watchdog/watchdog.py',
    'census_helper.py','darwin_census_provider.py',
)

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()

def validate_dso_binding(manifest):
    """Bind execution and loader identity to one canonical path and digest."""
    assets=manifest.get('assets');dso=manifest.get('dso_path');digest=manifest.get('dso_sha256')
    approved=manifest.get('approved_loaded_images');required=manifest.get('required_loaded_images')
    if type(assets) is not dict or type(dso) is not str or not pathlib.Path(dso).is_absolute() or str(pathlib.Path(dso).resolve(strict=True))!=dso or type(digest) is not str or not re.fullmatch('[0-9a-f]{64}',digest):raise ValueError('invalid canonical DSO identity')
    if type(approved) is not dict or type(required) is not list or dso not in required or assets.get(dso)!=digest or approved.get(dso)!=digest:raise ValueError('DSO path/hash binding mismatch')
    if sum(value==digest for value in approved.values())!=1:raise ValueError('ambiguous DSO loader digest')
    return dso,digest

def preflight():
    name=os.environ.get('RESEARCH_PRIVATE_MANIFEST');pin=os.environ.get('RESEARCH_MANIFEST_SHA256')
    if not name or not pin or not re.fullmatch('[0-9a-f]{64}',pin):raise ValueError('independent manifest pin required')
    path=pathlib.Path(name).resolve(strict=True)
    if sha(path)!=pin:raise ValueError('manifest pin mismatch')
    manifest=json.loads(path.read_text())
    if manifest.get('schema')!='kdm6.synthetic33.private.v1' or manifest.get('status')!='REVIEWED_PINNED':raise ValueError('unreviewed private manifest')
    if manifest.get('slots')!=fixture33.validate():raise ValueError('slot plan mismatch')
    dso,dso_digest=validate_dso_binding(manifest)
    assets=manifest.get('assets');interpreter=manifest.get('interpreter')
    if type(assets) is not dict or type(dso) is not str or dso not in assets or type(interpreter) is not str or interpreter not in assets:raise ValueError('missing asset pins')
    for name,digest in assets.items():
        p=pathlib.Path(name)
        if not p.is_absolute() or str(p.resolve(strict=True))!=name or not re.fullmatch('[0-9a-f]{64}',digest) or sha(p)!=digest:raise ValueError('asset pin mismatch')
    root=pathlib.Path(__file__).resolve().parent
    if any(str((root/q).resolve(strict=True)) not in assets for q in EXECUTION_SOURCE_FILES):raise ValueError('missing script pins')
    return {'status':'SPEC_ONLY_UNVERIFIED_RUNTIME_LOADER','dso_path':dso,'dso_sha256':dso_digest,'interpreter':interpreter,'calls':manifest['slots']}
