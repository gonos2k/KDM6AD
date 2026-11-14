"""Parameterized pin check; no local or private paths are embedded."""
import json,pathlib,os
from real33_contract import sha

def validate_frozen(path,independent_sha256):
    p=pathlib.Path(path).resolve(strict=True)
    if sha(p)!=independent_sha256:raise ValueError('manifest SHA mismatch')
    m=json.loads(p.read_text())
    if m.get('schema')!='kdm6.synthetic33.private.v1' or m.get('status')!='REVIEWED_PINNED':raise ValueError('unreviewed manifest')
    if os.environ.get('RESEARCH_PRIVATE_MANIFEST')!=str(p) or os.environ.get('RESEARCH_MANIFEST_SHA256')!=independent_sha256:raise ValueError('private manifest environment mismatch')
    from real33_contract import preflight
    preflight()
    return {'status':'PIN_CONSISTENT_NOT_EXECUTION_AUTHORITY','manifest_sha256':independent_sha256}
