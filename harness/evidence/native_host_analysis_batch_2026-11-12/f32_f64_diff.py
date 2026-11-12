#!/usr/bin/env python3
"""Classify saved selected-column f32/f64 output differences; executes no KDM code."""
import gzip
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parent.parent
F32 = ROOT / 'native_host_column_f32_2026-11-11/raw'
F64 = ROOT / 'native_host_column_f64_da_2026-11-12/raw/baseline_probe.json.gz'
FIELDS = ('th','qv','qc','qr','qi','qs','qg','nccn','nc','ni','nr','bg')
FORCING = ('rho','pii','p','delz')
SELECTED_SHA = 'e3117d277a073042bbae648b87e7dd6661d14b600fc8245f6aeabc19fe715eae'
DSO_SHA = '7adcb6921f6205af66c62720ce9447928a1608f5c261546183b928bebbd9dba7'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def decode32(word):
    return struct.unpack('>f', bytes.fromhex(word))[0]

def decode64(word):
    return struct.unpack('>d', bytes.fromhex(word))[0]

def encode32(value):
    return struct.pack('>f', value).hex()

def encode64(value):
    return struct.pack('>d', value).hex()

def ordered32(word):
    # Monotonic integer encoding of finite IEEE words; signed zeros adjacent.
    u = int(word, 16)
    return (~u & 0xffffffff) if u & 0x80000000 else (u | 0x80000000)

def analyze(selected, replay, f64, selected_sha):
    if selected_sha != SELECTED_SHA or f64['source']['selected_full_sha256'] != selected_sha:
        raise ValueError('selected input hash mismatch')
    if replay['selected_json_sha256'] != selected_sha or replay['tile_sha256'] != selected['source_tile_sha256'] or f64['source']['source_tile_sha256'] != selected['source_tile_sha256']:
        raise ValueError('parent lineage mismatch')
    if replay['dso_sha256'] != DSO_SHA or f64['source']['library_sha256'] != DSO_SHA:
        raise ValueError('installed DSO mismatch')
    if replay['return_code'] != 0 or not replay['handle_null'] or f64['cases'][0]['value_only']['rc'] != 0:
        raise ValueError('failed baseline call')
    controls=f64['controls']
    if (controls['im'],controls['kme'],controls['jme'],controls['dt'],controls['xland_f32'],controls['ncmin_land'],controls['ncmin_sea']) != (1,39,1,20,2,10,10) or selected['xland_word_hex'] != '40000000' or (selected['dt'],selected['ncmin_land'],selected['ncmin_sea']) != (20,10,10):
        raise ValueError('control mismatch')
    inputs = [w for field in FIELDS+FORCING for w in selected['input_words_hex'][field]]
    if len(inputs)!=624 or any(len(selected['input_words_hex'][k])!=39 for k in FIELDS+FORCING):
        raise ValueError('input shape mismatch')
    values=list(map(decode32, inputs))
    if not all(map(math.isfinite, values)) or inputs != f64['source']['input_f32_words'] or [encode64(x) for x in values] != f64['source']['input_widened_f64_words']:
        raise ValueError('widened input mismatch')
    base=f64['cases'][0]
    if base['name'] != 'baseline' or [encode64(x) for x in values[:468]] != base['input_state_f64_words']:
        raise ValueError('f64 baseline input mismatch')
    f32words=[w for k in FIELDS for w in replay['actual_output_words_hex'][k]]
    tilewords=[w for k in FIELDS for w in selected['output_words_hex'][k]]
    f64words=base['value_only']['output_f64_words']
    if len(f32words)!=468 or len(f64words)!=468 or f32words!=tilewords:
        raise ValueError('baseline outputs mismatch or wrong shape')
    diffs=[]
    for i,(fw,dw) in enumerate(zip(f32words,f64words)):
        fv,dv=decode32(fw),decode64(dw)
        if not math.isfinite(fv) or not math.isfinite(dv): raise ValueError('nonfinite output')
        rounded=encode32(dv)
        if fw != rounded:
            rv=decode32(rounded)
            diffs.append({'field':FIELDS[i//39], 'native_level_1based':i%39+1,'packed_index_zero':i,'f32_word':fw,'f64_word':dw,'f64_rounded_f32_word':rounded,'f32_value':fv,'f64_value':dv,'f64_rounded_f32_value':rv,'rounded_ulp_distance':abs(ordered32(rounded)-ordered32(fw)),'rounded_ulp_signed_f64_minus_f32':ordered32(rounded)-ordered32(fw),'f64_minus_f32':dv-fv,'absolute_f64_minus_f32':abs(dv-fv),'relative_to_f32':abs(dv-fv)/abs(fv) if fv else None})
    expected=f64['separate_f32_baseline_comparison']
    if expected['operational_f32_output_words']!=f32words or expected['f64_output_rounded_to_f32_words'] != [encode32(decode64(w)) for w in f64words] or expected['rounded_different_count']!=len(diffs):
        raise ValueError('saved comparison mismatch')
    byfield=Counter(x['field'] for x in diffs);bylevel=Counter(x['native_level_1based'] for x in diffs)
    return {'schema':'kdm6.native_host.f32_f64_baseline_output_diff.v1','scope':'Saved B=1 selected native column, f32 operational and f64 DA value-only outputs. No stage attribution or new KDM calls.', 'lineage':{'selected_sha256':selected_sha,'source_tile_sha256':selected['source_tile_sha256'],'installed_dso_sha256':DSO_SHA,'state_and_forcing_f32_words':624,'exact_f64_widenings_verified':624,'b1_f32_vs_selected_tile_output_words_exact':468,'shape':[1,39,1],'dt_s':20,'xland':2,'ncmin_land':10,'ncmin_sea':10},'summary':{'word_count':468,'rounded_equal_count':468-len(diffs),'rounded_mismatch_count':len(diffs),'mismatches_by_field':{k:byfield[k] for k in FIELDS},'mismatches_by_native_level':{str(k):bylevel[k] for k in range(1,40)},'selected_activation_level_16':bylevel[16],'adjacent_levels_15_17':bylevel[15]+bylevel[17],'outside_levels_15_17':sum(v for k,v in bylevel.items() if k not in (15,16,17)),'largest_rounded_ulp_distance':max((x['rounded_ulp_distance'] for x in diffs),default=0),'largest_absolute_difference_by_field':{k:max((x['absolute_f64_minus_f32'] for x in diffs if x['field']==k),default=0) for k in FIELDS}},'mismatches':diffs,'interpretation':'Rounded output word differences compare separately executed f32 and f64 maps; concentration at a level does not identify a process or stage cause.'}

def main():
    selected_path=F32/'selected_full.json'; replay_path=F32/'b1_replay.json'
    with selected_path.open() as f: selected=json.load(f)
    with replay_path.open() as f: replay=json.load(f)
    with gzip.open(F64,'rt') as f: fp64=json.load(f)
    result=analyze(selected,replay,fp64,sha(selected_path))
    result['source_files']={'selected_full_sha256':sha(selected_path),'b1_replay_sha256':sha(replay_path),'baseline_probe_gzip_sha256':sha(F64)}
    payload = (json.dumps(result,indent=2,allow_nan=False) + '\n').encode('utf-8')
    output = Path(__file__).with_suffix('.json.gz')
    with output.open('wb') as raw:
        with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as compressed:
            compressed.write(payload)

if __name__=='__main__': main()
