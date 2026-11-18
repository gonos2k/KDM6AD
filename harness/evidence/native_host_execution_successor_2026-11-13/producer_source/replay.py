#!/usr/bin/env python3
"""Reconstruct the isolated source in a temporary tree; never run/build a model."""
import hashlib,io,json,re,subprocess,tarfile,tempfile
from contextlib import contextmanager
from pathlib import Path,PurePosixPath

HERE=Path(__file__).resolve().parent
ARCHIVE_SHA='7ac32efbbe58dc2c6b4793dc40f0c22a3434d63b55026e2c629cfc936166041f'
PATCH_SHA='8788add86cfe01f678f27d90e24496b63cd30ce65cc5c2c8b4eee25244a9863d'
MANIFEST_SHA='ad19651e4571f75e30b62668f4c3097b9c6018dae19ea4b653442830cafa1fef'


def need(ok,why):
    if not ok:raise ValueError(why)
def sha(raw):return hashlib.sha256(raw).hexdigest()

def safe_file(name):
    need(isinstance(name,str) and re.fullmatch(r'libtorch/[A-Za-z0-9_.+/-]+',name) is not None,'unsafe path')
    parts=name.split('/')
    need(all(x not in ('','.','..') for x in parts) and not PurePosixPath(name).is_absolute(),'unsafe path')
    return name

def validate_manifest(m):
    need(m['schema']=='kdm6.batch5.isolated_source_manifest.v1' and m['base_commit']=='ebe0260b','manifest schema/base')
    base=m['base_file_sha256'];target=m['target_file_sha256']
    need(isinstance(base,dict) and isinstance(target,dict) and len(base)==68 and len(target)==76,'manifest file counts')
    for name,digest in list(base.items())+list(target.items()):
        safe_file(name);need(isinstance(digest,str) and re.fullmatch('[0-9a-f]{64}',digest) is not None,'file SHA')
    need('libtorch/BATCH5_NARROW_SOURCE_AUDIT.md' not in target and 'libtorch/AGENTS.md' in target,'public/private inventory')
    return base,target

def extract_base(archive_raw,base,directory):
    directories={'libtorch'}
    for name in base:
        path=PurePosixPath(name).parent
        while str(path)!='.':directories.add(str(path));path=path.parent
    found=set();dirs=set();total=0
    with tarfile.open(fileobj=io.BytesIO(archive_raw),mode='r:gz') as t:
        for member in t:
            name=member.name
            if member.isdir():
                need(name in directories and name not in dirs,'unexpected or duplicate archive directory');dirs.add(name);continue
            safe_file(name)
            need(member.isfile() and name in base and name not in found,'unexpected/duplicate/nonregular archive file')
            need(0<=member.size<=10_000_000,'archive member size');total+=member.size;need(total<=50_000_000,'archive total size')
            source=t.extractfile(member);need(source is not None,'missing archive bytes');raw=source.read()
            need(len(raw)==member.size and sha(raw)==base[name],'base source SHA '+name)
            destination=directory/name;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(raw);found.add(name)
    need(found==set(base),'archive file inventory')

def validate_patch(patch,base,target):
    try:lines=patch.decode('utf-8').splitlines()
    except UnicodeDecodeError as exc:raise ValueError('invalid patch encoding') from exc
    expected={p for p in set(base)|set(target) if base.get(p)!=target.get(p)}
    seen=set();current=None;header=True
    for line in lines:
        if line.startswith('diff --git '):
            m=re.fullmatch(r'diff --git a/(libtorch/[A-Za-z0-9_.+/-]+) b/(libtorch/[A-Za-z0-9_.+/-]+)',line)
            need(m is not None and m.group(1)==m.group(2),'unsafe patch path')
            name=safe_file(m.group(1));need(name in expected and name not in seen,'unexpected/duplicate patch file');seen.add(name);current=name;header=True
        elif line.startswith(('rename from ','rename to ','copy from ','copy to ','old mode ','new mode ')):
            raise ValueError('unsupported patch path/mode')
        elif line.startswith(('new file mode ','deleted file mode ')):
            need(current is not None and line=='new file mode 100644' and current not in base and current in target,'unsupported patch file mode')
        elif header and line.startswith('index '):
            need(re.fullmatch(r'index [0-9a-f]{40}\.\.[0-9a-f]{40}(?: 100644)?',line) is not None,'unsupported patch index/mode')
        elif line.startswith('@@ ') or line=='GIT binary patch':header=False
        elif header and (line.startswith('--- ') or line.startswith('+++ ')):
            need(current is not None,'orphan patch header');prefix=line[:4];ref=line[4:]
            permitted=('/dev/null','a/'+current) if prefix=='--- ' else ('/dev/null','b/'+current)
            need(ref in permitted,'patch header path mismatch')
    need(seen==expected,'patch changed-file inventory')
    return seen

def reconstruct(archive_raw,patch_raw,manifest,directory):
    base,target=validate_manifest(manifest);extract_base(archive_raw,base,directory);validate_patch(patch_raw,base,target)
    # No repository/history or network is used; git apply operates only in this
    # freshly created temporary tree after explicit path/mode validation.
    for args in (['git','apply','--no-index','--check','-'],['git','apply','--no-index','-']):
        try:r=subprocess.run(args,input=patch_raw,cwd=directory,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=30)
        except FileNotFoundError as exc:raise RuntimeError('git executable required for offline patch application') from exc
        need(r.returncode==0,'offline patch application failed: '+r.stderr.decode(errors='replace')[-1000:])
    root=directory/'libtorch';found=set()
    for path in root.rglob('*'):
        need(not path.is_symlink(),'unexpected symlink')
        if path.is_file():
            name=str(path.relative_to(directory));safe_file(name);need(name in target,'unexpected reconstructed file')
            need(sha(path.read_bytes())==target[name],'reconstructed source SHA '+name);found.add(name)
        else:need(path.is_dir(),'unexpected reconstructed filesystem entry')
    need(found==set(target),'reconstructed file inventory')
    return {'base_files':len(base),'reconstructed_files':len(found),'changed_files':len(validate_patch(patch_raw,base,target))}

@contextmanager
def reconstructed_tree():
    ar=(HERE/'base_libtorch.tar.gz').read_bytes();patch=(HERE/'v5_changes.patch').read_bytes();mr=(HERE/'source_manifest.json').read_bytes()
    need(sha(ar)==ARCHIVE_SHA and sha(patch)==PATCH_SHA and sha(mr)==MANIFEST_SHA,'packet asset SHA')
    manifest=json.loads(mr)
    with tempfile.TemporaryDirectory(prefix='kdm6-source-replay-') as d:
        result=reconstruct(ar,patch,manifest,Path(d))
        yield Path(d)/'libtorch',result

def replay():
    with reconstructed_tree() as (_,result):
        pass
    return {'schema':'kdm6.batch5.isolated_source_replay.v1',**result,'scope':'offline source reconstruction only; no compiler, model, DSO or host execution','installed_build_identity':'NOT_ESTABLISHED','scientific_status':'INCONCLUSIVE','physical_unit_status':'INCONCLUSIVE'}

if __name__=='__main__':print(json.dumps(replay(),indent=2,sort_keys=True))
