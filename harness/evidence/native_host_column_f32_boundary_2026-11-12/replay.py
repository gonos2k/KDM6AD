#!/usr/bin/env python3
"""Replay archived host-selected f32 boundary evidence, without executing the host."""
import csv
import gzip
import hashlib
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import json
from pathlib import Path
import re
import struct

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE.parent
PARENT = EVIDENCE / 'native_host_column_f32_2026-11-11'
MANIFEST_SHA = '8d2185606c1e06e3dbe262607e5faf14fb1dd92f95cf00bd413f5fa604b9e974'
PARENT_REPLAY_SHA = '882ddcd7e9b6967b522eca6dd61a1151e6f47cfb3a6f01ba4917ceada0ea3c95'
BUILD_SHA = 'cb3fe4bc2d9b93dfefe03b8d60b73dd4552c4ab537f094c056b0d9a81c0efdff'
INPUT_SHA = '8aced88b4f4f967a7cde0692837617b5ed3d058ccb30de8d2acdd7c43690d8ea'
RUNNER_SHA = 'b8894b76d93fec3b8cadd1be80e043bbf04b7cf37ca29ba6aaf3105b686e4050'
DSO_SHA = '7adcb6921f6205af66c62720ce9447928a1608f5c261546183b928bebbd9dba7'
CAPTURE_SHA = 'eabb607b08760a5b757031f864f6644e5f75aa83aebdc4c32f8fdfc8c2245c95'


def need(ok, why):
    if not ok: raise ValueError(why)


def sha(raw): return hashlib.sha256(raw).hexdigest()
def read(path): return json.loads(path.read_bytes())
def read_sweep():
    raw = gzip.decompress((HERE / 'raw/sweep.json.gz').read_bytes())
    need(sha(raw) == '9c866594768764d51c42b9d7d24471bd5484a85f9b80e00f51316b6bfb88bee7', 'original sweep SHA')
    return json.loads(raw)


def parent_module():
    path = PARENT / 'replay.py'
    need(sha(path.read_bytes()) == PARENT_REPLAY_SHA, 'parent replay SHA')
    spec = importlib.util.spec_from_file_location('host_column_parent', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixed_assets():
    raw = (HERE / 'manifest.json').read_bytes()
    need(sha(raw) == MANIFEST_SHA, 'manifest SHA')
    manifest = json.loads(raw)
    need(manifest['schema'] == 'kdm6.host_selected_f32_coupled_boundary_packet.v1', 'manifest schema')
    files = manifest['files']
    actual = {str(p.relative_to(HERE)) for folder in ('producer', 'raw') for p in (HERE / folder).rglob('*') if p.is_file()}
    need(set(files) == actual, 'manifest inventory')
    for path, digest in files.items(): need(sha((HERE / path).read_bytes()) == digest, 'asset SHA: ' + path)
    receipt = read(HERE / 'raw/run_receipt.json')
    need(receipt['schema'] == 'kdm6.host_selected_f32_coupled_boundary_receipt.v1', 'receipt schema')
    need(receipt['selected_full_sha256'] == 'e3117d277a073042bbae648b87e7dd6661d14b600fc8245f6aeabc19fe715eae' and receipt['input_bin_sha256'] == INPUT_SHA, 'receipt input')
    need(receipt['sweep_sha256'] == '9c866594768764d51c42b9d7d24471bd5484a85f9b80e00f51316b6bfb88bee7'
         and receipt['executed_sweep_source_sha256'] == files['producer/sweep.py'], 'receipt assets')
    need((receipt['runner_executable_sha256'],receipt['installed_dso_sha256'],receipt['capture_dso_sha256'],receipt['parent_build_receipt_sha256']) == (RUNNER_SHA,DSO_SHA,CAPTURE_SHA,BUILD_SHA), 'receipt executable provenance')
    build = EVIDENCE / 'native_f32_activation_boundary_2026-11-11/raw/build_receipt.json'
    need(sha(build.read_bytes()) == BUILD_SHA, 'parent build SHA')
    data = read(build)
    need((data['runner_executable_sha256'],data['installed_dso_sha256'],data['capture_dso_sha256']) == (RUNNER_SHA, DSO_SHA,CAPTURE_SHA), 'parent build links')
    need(receipt['terminal_calls'] == 6 and receipt['endpoint_words'] == ['43a00285','43a00286'], 'terminal receipt')
    need(receipt['scope'] == 'same host-captured selected column, separate B=1 f32 value calls; no perturbed WRF tile or AD', 'receipt scope')
    need(receipt['initial_helper_failure'] == {'first_source_sha256':'7190031203cf005ecf8b5b4fe5ff663f06538195f1dedb3ccfb333392a558652', 'first_sweep_sha256':'03fa628494c6002d11b203017eff02a4208466654259c030a24ec1fb7227fe3c', 'reason':'fromhex() argument must be str, not int', 'interpretation':'post-bisection gap formatting error in private driver; corrected driver reran all probes'}, 'initial failed attempt receipt')
    source=(HERE/'producer/sweep.py').read_text()
    need("allowed={'activation_fraction_pow_lt_one','activation_fraction_pow_eq_one','activation_fraction_pow_gt_one','ncact_raw_lt_nccn_rate_cap','ncact_raw_eq_nccn_rate_cap','ncact_raw_gt_nccn_rate_cap'}" in source and "'gap':f32(f'{hi:08x}')-f32(f'{lo:08x}')" in source, 'executed guard and gap source')
    return receipt


def outputs(event, parent):
    arrays = event['state_output_f32_words']
    need(isinstance(arrays,list) and len(arrays)==12, 'state field count')
    result = {name: parent.vector(row,39,'state '+name) for name,row in zip(parent.INPUTS[:12],arrays)}
    precip = parent.vector(event['precip_increment_f32_words'],3,'precip')
    result.update({name:[v] for name,v in zip(('rain','snow','graupel'),precip)})
    result['rhog'] = parent.vector(event['rhog_output_f32_words'],39,'rhog')
    return result


def validate_sweep(data, selected, parent):
    need(data['schema']=='kdm6.host_selected_f32_activation_coupled_boundary.v1' and data['status']=='complete', 'sweep schema/status')
    need(data['input_sha256']==INPUT_SHA and data['selected_sha256']==parent.SELECTED_SHA and (data['runner_sha256'],data['installed_dso_sha256'],data['capture_dso_sha256'])==(RUNNER_SHA,DSO_SHA,CAPTURE_SHA), 'sweep provenance')
    input_values = [parent.value(w) for name in parent.INPUTS for w in selected['input_words_hex'][name]]
    need(len(input_values) == 624, 'selected input count')
    input_bin = b'KDM6_PRE2_INPUT' + struct.pack('<624d', *input_values) + struct.pack('<fd', 2.0, 20.0)
    need(sha(input_bin) == INPUT_SHA, 'reconstructed runner input SHA')
    base = data['base_words']
    need(base == {k:selected['input_words_hex'][k][15] for k in ('th','qv')} and data['max_word_distance']==1<<20, 'sweep base/limit')
    events = data['events']
    need(isinstance(events,list) and len(events)==23, 'event count')
    byword = {}
    baseline_trace = read(PARENT / 'raw/activation_summary.json')
    guard = parent.TRACE_BOOL - set('activation_fraction_pow_lt_one activation_fraction_pow_eq_one activation_fraction_pow_gt_one ncact_raw_lt_nccn_rate_cap ncact_raw_eq_nccn_rate_cap ncact_raw_gt_nccn_rate_cap'.split())
    for e in events:
        w=e['word']; parent.vector([w],1,'input word')
        need(e['axis']=='th' and w not in byword and 0 <= int(w,16)-int(base['th'],16) <= (1<<20), 'event axis/word')
        byword[w]=e
        actual=outputs(e,parent)
        stage=dict(baseline_trace); stage['trace']=e['trace']
        parent.validate_activation(stage,actual)
        need(all(e['trace'][name] == baseline_trace['trace'][name] for name in guard), 'guard mask changed')
    b0=byword[base['th']]
    need(b0['trace']==baseline_trace['trace'], 'baseline trace')
    parent_outputs=read(PARENT/'raw/b1_replay.json')['actual_output_words_hex']
    need(outputs(b0,parent)==parent_outputs, 'baseline outputs')
    def pred(w,k):
        trace=byword[w]['trace']
        name,limit=('sw_percent',0.48) if k=='sw' else ('activation_fraction_min_output',1.0)
        return parent.value(trace[name]['raw_hex'])>=limit
    expected_schedule=[]
    def probe(n):
        w=f'{n:08x}'
        if w not in expected_schedule: expected_schedule.append(w)
        need(w in byword, 'missing scheduled probe')
        return w
    start=int(base['th'],16); probe(start)
    for k in ('sw','fraction'):
        initial=pred(base['th'],k); need(initial,'initial predicate')
        step=1
        while step<=1<<20:
            other=start+step
            if pred(probe(other),k)!=initial: break
            step*=2
        need(step<=1<<20,'missing bracket')
        lo,hi=start,other
        left=pred(probe(lo),k)
        while hi-lo>1:
            mid=(lo+hi)//2
            if pred(probe(mid),k)==left: lo=mid
            else: hi=mid
        matches=[b for b in data['boundaries'] if b['axis']=='th' and b['predicate']==k]
        need(len(matches)==1 and matches[0]['lower']==f'{lo:08x}' and matches[0]['upper']==f'{hi:08x}' and matches[0]['gap']==parent.value(f'{hi:08x}')-parent.value(f'{lo:08x}'), 'boundary')
    need(len(data['boundaries'])==2 and expected_schedule == [e['word'] for e in events], 'probe schedule')
    for k in ('sw','fraction'):
        p=[pred(w,k) for w in sorted(byword)]
        need(p==sorted(p,reverse=True), 'sampled predicate monotonicity')
    return byword


def validate_terminals(data, byword, selected, parent):
    need(data['schema']=='kdm6.host_selected_f32_coupled_boundary_terminal.v1','terminal schema')
    calls=data['calls']; endpoints=('43a00285','43a00286')
    need(len(calls)==6 and {(c['th_input_word'],c['mode']) for c in calls}=={(w,m) for w in endpoints for m in ('installed','off','on')}, 'terminal inventory')
    original_pins = {('43a00285', 'installed'): ('d638cd575d37afbf3566f8bf53e220a76b80d2834dd224dfc6a48dfa450fb922', '8b2dadf7b26edb63fd8ded42ac0173ee721be6c79050a6210ded45fae161fb98'), ('43a00285', 'off'): ('64b58a5a78797b27a14ae312cb74fc583f3edb0ee5936e740f88dda576ae46f5', '1366dbb5db729c84cf1a8e92484fb950e80a43144de9a6ec9c331a559e05f58d'), ('43a00285', 'on'): ('64b58a5a78797b27a14ae312cb74fc583f3edb0ee5936e740f88dda576ae46f5', '89439354765bac0f8cfd3e3cce9a47c12022906893ed927be08cf82376a1f5bb'), ('43a00286', 'installed'): ('8ca09f5363dffe604b9640a7a22a3eab03b7134ecef1a5e88b4f18779815ccb8', '47e90da84ab60303d73edc71591ceee165ca614cf45e37c2d71967e873e37de9'), ('43a00286', 'off'): ('5cb1bd3721a4b9c488e5ed5f3db8a8f5cb87a0e2edb72a34209bbc768814569e', '74f309c035f2f0f4778e1c6251ce7ca804798ff16c19da08cc0244a9a37df223'), ('43a00286', 'on'): ('5cb1bd3721a4b9c488e5ed5f3db8a8f5cb87a0e2edb72a34209bbc768814569e', '91a52e59d36a15a19eae6584380c5954d6bab03afdff11791a4632007636c2af')}
    state=[w for name in parent.INPUTS[:12] for w in selected['input_words_hex'][name]]
    forcing=[w for name in parent.INPUTS[12:] for w in selected['input_words_hex'][name]]
    for item in calls:
        w,mode=item['th_input_word'],item['mode']; call=item['call']
        need(item['expected_dso_path_observed'] is True and (item['original_call_sha256'], item['loader_stderr_sha256']) == original_pins[(w,mode)], 'original call/loader receipt')
        need(call['schema']=='kdm6.native_f32_activation_probe_call.v1' and call['axis']=='th16' and call['override_word']==w and call['library_mode']==mode, 'terminal call identity')
        need(call['rc']==0 and call['value_only']==1 and call['handle_null'] is True and call['shape']==[1,39,1] and (call['dt_s'],call['xland'],call['ncmin_land'],call['ncmin_sea'])==(20,2,10,10), 'terminal controls')
        expected=state.copy(); expected[15]=w
        need(parent.vector(call['source_state_f32_words'],468,'terminal input')==expected and parent.vector(call['source_forcing_f32_words'],156,'terminal forcing')==forcing, 'terminal input mismatch')
        need(outputs(call,parent)==outputs(byword[w],parent), 'terminal output parity')
    for w in endpoints:
        path=HERE/f'raw/endpoint_captures/th_{w}.csv.gz'
        text=gzip.decompress(path.read_bytes()).decode('ascii')
        need(text.rstrip().endswith('status=complete'), 'capture complete')
        trace={}
        for row in csv.DictReader(line for line in io.StringIO(text) if not line.startswith('#')):
            if row['stage']=='fd_satadj_inner' and row['k_zero']=='23':
                need((row['runtime_call'],row['one_step_call'],row['substep'],row['b_zero'],row['B'],row['K'])==('1','1','0','0','1','39') and row['field'] not in trace,'capture identity')
                trace[row['field']]={'dtype':row['dtype'],'raw_hex':row['raw_hex']}
        need(trace==byword[w]['trace'],'capture trace mismatch')
    return 6



def private_reexecution(parent, selected, events):
    names = ('PRIVATE_F32_RUNNER', 'PRIVATE_F32_INPUT', 'PRIVATE_INSTALLED_DSO', 'PRIVATE_CAPTURE_DSO')
    values = [os.environ.get(name) for name in names]
    need(all(values) or not any(values), 'set all four PRIVATE_F32_* input paths')
    if not any(values): return 'SKIPPED'
    runner, input_path, installed, capture = [Path(v).resolve() for v in values]
    for path, digest in ((runner,RUNNER_SHA),(input_path,INPUT_SHA),(installed,DSO_SHA),(capture,CAPTURE_SHA)):
        need(sha(path.read_bytes()) == digest, 'private executable/input SHA')
    saved = read(HERE/'raw/terminal_calls.json')['calls']
    archived = {(x['th_input_word'],x['mode']):x['call'] for x in saved}
    environment = {k:v for k,v in os.environ.items() if not k.startswith('KDM6') and not k.startswith('DYLD_')}
    environment.update(OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', OMP_THREAD_LIMIT='1')
    if sys.platform == 'darwin': environment['DYLD_PRINT_LIBRARIES'] = '1'
    if os.environ.get('PRIVATE_TORCH_LIB_DIR'):
        environment['DYLD_LIBRARY_PATH'] = os.environ['PRIVATE_TORCH_LIB_DIR']
    with tempfile.TemporaryDirectory(prefix='kdm6-f32-endpoints-') as tmp:
        root=Path(tmp)
        for word in ('43a00285','43a00286'):
            for mode in ('installed','off','on'):
                directory=root/f'{word}_{mode}'; directory.mkdir()
                output=directory/'out.json'; env=environment.copy()
                if mode=='on':
                    env.update(KDM6_NATIVE_CAPTURE_DIR=str(directory), KDM6_NATIVE_CAPTURE_ALL_K='1',
                               KDM6_NATIVE_CAPTURE_CALL='1', KDM6_NATIVE_CAPTURE_B='0',
                               KDM6_NATIVE_CAPTURE_MAX_ROWS='200000', KDM6_NATIVE_CAPTURE_MAX_BYTES='134217728')
                proc=subprocess.run([str(runner),'--library',str(installed if mode=='installed' else capture),
                                     '--input',str(input_path),'--output',str(output),'--axis','th16','--word',word],
                                    env=env,capture_output=True,text=True,timeout=180)
                need(proc.returncode==0, 'private terminal execution: '+word+' '+mode+' '+proc.stderr[-1000:])
                if sys.platform == 'darwin':
                    need(str(installed if mode=='installed' else capture) in proc.stderr, 'private loader DSO: '+word+' '+mode)
                actual=read(output); original=archived[(word,mode)]
                actual.pop('library',None); actual['library_mode']=mode
                need(actual==original, 'private terminal input/control/output: '+word+' '+mode)
                if mode=='on':
                    files=list(directory.glob('native_qnice_applied_*_runtime1.csv'))
                    need(len(files)==1, 'private capture inventory')
                    text=files[0].read_text()
                    need(text.rstrip().endswith('status=complete'), 'private capture complete')
                    trace={}
                    for row in csv.DictReader(line for line in io.StringIO(text) if not line.startswith('#')):
                        if row['stage']=='fd_satadj_inner' and row['k_zero']=='23':
                            need((row['runtime_call'],row['one_step_call'],row['substep'],row['b_zero'],row['B'],row['K'])==('1','1','0','0','1','39') and row['field'] not in trace, 'private capture identity')
                            trace[row['field']]={'dtype':row['dtype'],'raw_hex':row['raw_hex']}
                    need(trace == events[word]['trace'], 'private capture trace')
    return 'PASSED'


def replay():
    fixed_assets()
    parent=parent_module(); selected=parent.load_packet()
    events=validate_sweep(read_sweep(),selected,parent)
    calls=validate_terminals(read(HERE/'raw/terminal_calls.json'),events,selected,parent)
    private_status=private_reexecution(parent,selected,events)
    return {'schema':'kdm6.host_selected_f32_coupled_boundary_replay.v1','events':len(events),'trace_fields_per_event':33,'output_words_per_event':510,'terminal_calls':calls,'endpoints':['43a00285','43a00286'],'sampled_predicates':'both flip at adjacent TH f32 words; sampled monotonicity only','scope':'separate B=1 value-only f32 calls on a host-selected column; no perturbed host tile or AD claim','private_reexecution':private_status,'initial_attempt':'failed after bisection due to fromhex integer formatting; corrected producer reran probes','scientific_status':'INCONCLUSIVE','physical_unit_status':'INCONCLUSIVE'}


if __name__=='__main__': print(json.dumps(replay(),indent=2,sort_keys=True))
