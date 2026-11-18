#!/usr/bin/env python3
"""Derive TH16-direction full-state diagnostics from the archived #583 run."""
import ast
import gzip
import hashlib
import io
import re
import struct
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / 'native_host_column_f64_da_2026-11-12'
PARENT_MANIFEST_SHA = 'c283fe5180b82db2ec7a4625f9cb7aabc6185e020bb04e818afa5162dfe79b5d'
INTERIOR_GZIP_SHA = '304c2ce5d0f93651b9f5c4ce88a327dbf39725060fe53820915eca522bebc597'
INTERIOR_SHA = '0cc5a76fcef89bd9e540e55ef2acd7cfa60f837250115dce5762bb9d1f461ddc'
FIELDS = ('th','qv','qc','qr','qi','qs','qg','nccn','nc','ni','nr','bg')
SCALE_SOURCE = HERE / 'reviewed_source/verify_state_forcing_ad.py.gz'
SCALE_SOURCE_SHA = '08f762aa5802aced370eccfa972308170b1d0a90dd0d5cb9dbc1623bd70a3f26'
FIELD_SCALES = (1., 1e-3, 1e-3, 1e-3, 1e-3, 1e-3, 1e-3, 1e8, 1e8, 1e6, 1e6, 1e-6)


def need(ok, message):
    if not ok: raise ValueError(message)


def f(word):
    return struct.unpack('>d', bytes.fromhex(word))[0]


def w(value):
    return struct.pack('>d', value).hex()


def wordvec(words, count, label):
    need(isinstance(words, list) and len(words) == count, label + ' count')
    need(all(isinstance(word, str) and re.fullmatch('[0-9a-f]{16}', word)
             and math.isfinite(f(word)) for word in words), label + ' words')
    return words



def validate_scales():
    raw = gzip.decompress(SCALE_SOURCE.read_bytes())
    need(hashlib.sha256(raw).hexdigest() == SCALE_SOURCE_SHA, 'field scale source SHA')
    tree = ast.parse(raw)
    matches = [node.value for node in tree.body if isinstance(node, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == 'OUTPUT_SCALES' for t in node.targets)]
    need(len(matches) == 1 and isinstance(matches[0], ast.Subscript)
         and isinstance(matches[0].value, ast.Call)
         and len(matches[0].value.args) == 1, 'field scale source expression')
    need(tuple(ast.literal_eval(matches[0].value.args[0])) == FIELD_SCALES, 'field scales')
    return FIELD_SCALES


def load_parent():
    manifest_raw = (PARENT / 'manifest.json').read_bytes()
    need(hashlib.sha256(manifest_raw).hexdigest() == PARENT_MANIFEST_SHA, 'parent manifest SHA')
    manifest = json.loads(manifest_raw)
    need(manifest['schema'] == 'kdm6.native_host_column_f64_da_packet.v1'
         and manifest['files']['raw/interior_ad_fd.json.gz'] == INTERIOR_GZIP_SHA, 'parent manifest link')
    compressed = (PARENT / 'raw/interior_ad_fd.json.gz').read_bytes()
    need(hashlib.sha256(compressed).hexdigest() == INTERIOR_GZIP_SHA, 'parent compressed interior SHA')
    raw = gzip.decompress(compressed)
    need(hashlib.sha256(raw).hexdigest() == INTERIOR_SHA, 'parent interior original SHA')
    return json.loads(raw)


def derive(data):
    scales = validate_scales()
    need(data['schema'] == 'kdm6.host_selected_f64_interior_ad_fd.v1', 'interior schema')
    need([c['name'] for c in data['centers']] == ['lower','upper'], 'centers')
    rows = []
    summaries = []
    for center in data['centers']:
        need([d['h_requested'] for d in center['differences']] == [1e-3,1e-4,1e-5], 'step inventory')
        center_words = wordvec(center['graph']['output_words'],468,'center output')
        jvp_words = wordvec(center['graph']['jvp_words'],468,'center JVP')
        need(center_words == center['value_only']['output_words'], 'center graph/value')
        x0 = f(center['th_word'])
        for diff in center['differences']:
            h=diff['h_requested']; lo_word,hi_word=diff['lower_word'],diff['upper_word']
            need(lo_word == w(x0-h) and hi_word == w(x0+h), 'represented input words')
            denominator=f(hi_word)-f(lo_word)
            need(denominator > 0 and denominator == diff['denominator'], 'represented denominator')
            lows=wordvec(diff['lower']['output_words'],468,'lower output')
            highs=wordvec(diff['upper']['output_words'],468,'upper output')
            counts = {'equal_words_zero_jvp':0,'equal_words_nonzero_jvp':0,'distinct_words':0}
            for index,(cw,jw,lw,uw) in enumerate(zip(center_words,jvp_words,lows,highs)):
                y0,j,yl,yu=map(f,(cw,jw,lw,uw))
                change=yu-yl; fd=change/denominator; error=fd-j
                output_residual=change-j*denominator
                scale=max(abs(y0),abs(yl),abs(yu),1.0)
                ulp=max(math.ulp(y0),math.ulp(yl),math.ulp(yu))
                normalized=abs(output_residual)/scale
                field_scale=scales[index//39]
                field_scaled_derivative_error=abs(error)/field_scale
                field_scaled_output_residual=abs(output_residual)/field_scale
                ulps=abs(output_residual)/ulp
                need(all(math.isfinite(x) for x in (fd,error,output_residual,normalized,field_scaled_derivative_error,field_scaled_output_residual,ulps)), 'nonfinite derived diagnostic')
                category=('equal_words_zero_jvp' if j==0.0 else 'equal_words_nonzero_jvp') if lw==uw else 'distinct_words'
                counts[category]+=1
                rows.append({'center':center['name'],'h_requested':h,'denominator':denominator,
                             'field':FIELDS[index//39],'level_bottom_first':index%39+1,'packed_index':index,
                             'lower_word':lw,'upper_word':uw,'center_word':cw,'jvp_word':jw,
                             'central_fd':fd,'jvp':j,'absolute_derivative_error':abs(error),
                             'output_residual':output_residual,'output_scale':scale,
                             'unit_scale_normalized_output_error':normalized,'output_ulp_residual':ulps,
                             'field_scale':field_scale,'field_scaled_absolute_derivative_error':field_scaled_derivative_error,
                             'field_scaled_absolute_output_residual':field_scaled_output_residual,
                             'signal':category})
            summaries.append({'center':center['name'],'h_requested':h,'denominator':denominator,'signal_counts':counts})
    return {'schema':'kdm6.native_host_full_output_fd.v1',
            'parent_interior_original_sha256':INTERIOR_SHA,
            'scope':'archived single-column f64 TH16 unit direction; 468 outputs per step, not full Jacobian; no model calls',
            'normalization':'abs((y_plus-y_minus)-JVP*(x_plus-x_minus)) / max(abs(y_center),abs(y_minus),abs(y_plus),1 native output unit); the floor is numerical, not a physical uncertainty or common cross-field unit',
            'field_scale_source_sha256':SCALE_SOURCE_SHA,
            'field_scales':dict(zip(FIELDS,FIELD_SCALES)),
            'field_scale_note':'Numerical scales declared in harness/verify_state_forcing_ad.py; these do not establish physical units or uncertainties.',
            'ulp_definition':'absolute output residual divided by maximum f64 ulp at center and endpoints',
            'signal_note':'equal endpoint words are unresolved even when JVP is zero; zero JVP is an observed AD value, not proof of exact zero sensitivity',
            'selected_mask_scope':'captured activation-stage masks only; no all-process branch stability claim',
            'summaries':summaries,'rows':rows}


def encode(result):
    payload = (json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode='wb', filename='', mtime=0) as stream:
        stream.write(payload)
    return buffer.getvalue()


def main():
    output = HERE / 'full_output_fd.json.gz'
    output.write_bytes(encode(derive(load_parent())))
    print(f'Wrote {output}')

if __name__=='__main__': main()
