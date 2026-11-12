#!/usr/bin/env python3
"""Validate archived single-column f64 evidence; no host or library execution."""
import csv, gzip, hashlib, importlib.util, io, json, math, re, struct, zipfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
EVIDENCE=HERE.parent
MANIFEST='c283fe5180b82db2ec7a4625f9cb7aabc6185e020bb04e818afa5162dfe79b5d'
PARENT=EVIDENCE/'native_host_column_f32_2026-11-11'
PARENT_REPLAY='882ddcd7e9b6967b522eca6dd61a1151e6f47cfb3a6f01ba4917ceada0ea3c95'

def need(ok,why):
    if not ok: raise ValueError(why)
def sha(x): return hashlib.sha256(x).hexdigest()
def read(p): return json.loads(p.read_bytes())
def f(w): return struct.unpack('>d',bytes.fromhex(w.zfill(16)))[0]
def w(x): return struct.pack('>d',x).hex()
def f32(x): return struct.pack('>f',x).hex()
def wordvec(a,n,label):
    need(isinstance(a,list) and len(a)==n,label+' count')
    need(all(isinstance(x,str) and re.fullmatch('[0-9a-f]{16}',x) and math.isfinite(f(x)) for x in a),label+' words')
    return a

def assets():
    raw=(HERE/'manifest.json').read_bytes();need(sha(raw)==MANIFEST,'manifest SHA')
    m=json.loads(raw);need(m['schema']=='kdm6.native_host_column_f64_da_packet.v1','manifest schema')
    files=m['files'];actual={str(p.relative_to(HERE)) for folder in ('raw','producer','operator','reviewed_source') for p in (HERE/folder).rglob('*') if p.is_file()}
    need(set(files)==actual,'manifest inventory')
    for n,h in files.items(): need(sha((HERE/n).read_bytes())==h,'asset SHA '+n)
    br=read(HERE/'raw/baseline_receipt.json');rr=read(HERE/'raw/boundary_receipt.json');cr=read(HERE/'raw/capture_receipt.json')
    need(br['schema']=='kdm6.host_selected_f64_da_ctypes_receipt.v1' and rr['schema']=='kdm6.host_selected_f64_da_boundary.receipt.v1' and cr['schema']=='kdm6.host_selected_f64_da_boundary.capture_calls.v1','receipt schemas')
    need(cr['parent_receipt_sha256']==files['raw/boundary_receipt.json'],'capture receipt link')
    need(br['script_sha256']==files['producer/baseline_probe.py'] and rr['files']['probe.py']==files['producer/boundary_probe.py'] and rr['files']['interior_ad_fd.py']==files['producer/interior_ad_fd.py'],'producer links')
    data=[]
    for name,digest in [('baseline_probe',br['result_sha256']),('boundary',rr['files']['result.json']),('interior_ad_fd',rr['files']['interior_ad_fd.json'])]:
        raw=gzip.decompress((HERE/f'raw/{name}.json.gz').read_bytes());need(sha(raw)==digest,'original JSON SHA '+name);data.append(json.loads(raw))
    return br,rr,cr,*data

def parent():
    p=PARENT/'replay.py';need(sha(p.read_bytes())==PARENT_REPLAY,'parent replay SHA')
    spec=importlib.util.spec_from_file_location('native_host_f32_parent',p);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod,mod.load_packet()

BOOL=set('sw_positive activation_fraction_pow_lt_one activation_fraction_pow_eq_one activation_fraction_pow_gt_one ncact_raw_lt_nccn_rate_cap ncact_raw_eq_nccn_rate_cap ncact_raw_gt_nccn_rate_cap cloud_complete_evap nccn_floor_active nccn_cap_active'.split())
FLOAT=set('qv_input qs1 sw_percent sw_ratio activation_fraction_one activation_fraction_pow safe_pow_clamped_base_diagnostic activation_fraction_min_output activated_fraction ncact_raw ncact_preclamp_fma ncact_clamped_numerator ncact_nccn_rate_cap ncact_min_output ncact nc_input nccn_input nc_after_activation nccn_after_activation nc_evap_amount nc_final nccn_final_raw nccn_final'.split())
MASK=set('sw_positive activation_fraction_pow_lt_one activation_fraction_pow_eq_one activation_fraction_pow_gt_one ncact_raw_lt_nccn_rate_cap ncact_raw_eq_nccn_rate_cap ncact_raw_gt_nccn_rate_cap'.split())

def trace_check(t,out):
    need(set(t)==BOOL|FLOAT,'trace fields')
    for k in BOOL: need(t[k]['dtype']=='bool' and t[k]['raw_hex'] in ('0','1'),'mask '+k)
    for k in FLOAT:
        x=t[k]; raw=x['raw_hex'];need(x['dtype']=='f64' and isinstance(raw,str) and re.fullmatch('[0-9a-f]{1,16}',raw) and math.isfinite(f(raw)),'trace '+k)
    v=lambda k:f(t[k]['raw_hex']); flag=lambda k:t[k]['raw_hex']=='1'
    def exact(k,x):need(int(t[k]['raw_hex'],16)==int(w(x),16),'arithmetic '+k)
    sw=(v('qv_input')/max(v('qs1'),1e-9)-1.0)*100.0;exact('sw_percent',sw)
    ratio=max(sw/0.48,0.0);exact('sw_ratio',ratio);exact('safe_pow_clamped_base_diagnostic',max(ratio,1e-15));exact('activation_fraction_one',1.0)
    p=math.pow(max(ratio,1e-15),0.6);need(abs(int(w(p),16)-int(t['activation_fraction_pow']['raw_hex'],16))<=16,'pow within 16 ULP')
    fraction=min(1.,v('activation_fraction_pow'));exact('activation_fraction_min_output',fraction);exact('activated_fraction',fraction)
    nc,nccn=v('nc_input'),v('nccn_input'); pre=-nc+(nccn+nc)*fraction;exact('ncact_preclamp_fma',pre)
    numerator=max(pre,0.);exact('ncact_clamped_numerator',numerator)
    raw=numerator/20.;cap=max(nccn,0.)/20.;exact('ncact_raw',raw);exact('ncact_nccn_rate_cap',cap);exact('ncact_min_output',min(raw,cap));exact('ncact',min(raw,cap) if sw>0 else 0.)
    nca=max(nc+v('ncact')*20.,0.);nccna=max(nccn-v('ncact')*20.,0.);exact('nc_after_activation',nca);exact('nccn_after_activation',nccna)
    evap=nca*float(flag('cloud_complete_evap'));exact('nc_evap_amount',evap);ncf=max(nca-evap,0.);nccnf=nccna+evap;exact('nc_final',ncf);exact('nccn_final_raw',nccnf);exact('nccn_final',min(max(nccnf,1e8),2e10))
    need(flag('sw_positive')==(sw>0) and flag('nccn_floor_active')==(nccnf<1e8) and flag('nccn_cap_active')==(nccnf>2e10),'guard masks')
    for stem,a,b in [('activation_fraction_pow',v('activation_fraction_pow'),1.),('ncact_raw',raw,cap)]:
        suffix='_one' if stem.startswith('activation') else '_nccn_rate_cap'
        for comp,expected in [('lt',a<b),('eq',a==b),('gt',a>b)]:need(flag(stem+'_'+comp+suffix)==expected,'comparison mask')
    need(int(t['nc_final']['raw_hex'],16)==int(out[8*39+15],16) and int(t['nccn_final']['raw_hex'],16)==int(out[7*39+15],16),'NC/NCCN output link')

def check_base(base,bound,mod,selected):
    need(base['schema']=='kdm6.host_selected_f64_da_ctypes_probe.v1' and bound['schema']=='kdm6.host_selected_f64_da_boundary.v1','base/boundary schema')
    need(base['source']['selected_full_sha256']==bound['parent_sha256']==mod.SELECTED_SHA and bound['source_tile_sha256']==mod.TILE_SHA and base['source']['library_sha256']==bound['installed_dso_sha256']==mod.DSO_SHA, 'selected/DSO provenance')
    need(bound['baseline_probe_sha256']==read(HERE/'raw/baseline_receipt.json')['result_sha256'] and bound['source_sha256']==read(HERE/'raw/boundary_receipt.json')['files']['probe.py'] and bound['roundtrip_f32_exact'] is True, 'boundary source links')
    need(bound['controls']=={'shape':[1,39,1],'dt':20,'xland':2,'ncmin_land':10,'ncmin_sea':10,'thread_counts':1,'physics_environment':'KDM6 variables unset; capture controls only'}, 'boundary controls')
    inputs=[x for name in mod.INPUTS for x in selected['input_words_hex'][name]]
    need(len(inputs)==624 and base['source']['input_f32_words']==inputs and bound['input_words_f32']==inputs,'selected input words')
    widened=[w(mod.value(x)) for x in inputs];need(base['source']['input_widened_f64_words']==widened and all(f32(f(y))==x for x,y in zip(inputs,widened)),'f32 widening/roundtrip')
    case=base['cases'][0];need(case['name']=='baseline' and case['input_state_f64_words']==widened[:468],'baseline input')
    value=case['value_only']; graph=case['graph']
    need(value['rc']==0 and value['handle_nonnull'] is False and graph['rc']==graph['jvp_rc']==graph['vjp_rc']==graph['close_rc']==0 and graph['handle_nonnull'] is True and graph['handle_null_after_close'] is True and graph['jvp_finite_count']==graph['vjp_finite_count']==468, 'baseline ABI status')
    j=wordvec(graph['jvp_f64_words'],468,'baseline JVP');v=wordvec(graph['vjp_f64_words'],468,'baseline VJP')
    need(graph['selected_jvp_nc16']==f(j[8*39+15]) and graph['selected_vjp_th16']==f(v[15]), 'baseline derivative selections')
    out=wordvec(value['output_f64_words'],468,'baseline output');need(out==graph['output_f64_words'] and case['value_graph_bitwise_equal'] is True,'baseline graph/value')
    comparison=base['separate_f32_baseline_comparison']; rounded=[f32(f(x)) for x in out]; operation=[x for name in mod.INPUTS[:12] for x in selected['output_words_hex'][name]]
    need(comparison['f64_output_rounded_to_f32_words']==rounded and comparison['operational_f32_output_words']==operation,'separate f32 outputs')
    equal=sum(a==b for a,b in zip(rounded,operation));need((comparison['count'],comparison['rounded_equal_count'],comparison['rounded_different_count'])==(468,equal,468-equal),'f32 comparison count')
    return case

def check_boundary(d):
    ev=d['events'];need(len(ev)==60,'event count');by={}
    for e in ev:
        key=e['th_word'];wordvec([key],1,'TH word');need(key not in by and e['mode']=='capture_on' and e['rc']==0 and not e['handle_nonnull'] and e['handle_null_after'] is True,'event status');by[key]=e
        out=wordvec(e['output_words'],468,'event output');trace_check(e['trace'],out)
    def pred(word,k):
        t=by[word]['trace'];return f(t['sw_percent']['raw_hex'])>=0.48 if k=='sw' else f(t['activation_fraction_min_output']['raw_hex'])>=1.
    for b in d['boundaries']:
        lo,hi=b['lower_word'],b['upper_word'];need((lo,hi)==('4074005089907cc6','4074005089907cc7') and int(hi,16)-int(lo,16)==1 and b['gap']==f(hi)-f(lo) and pred(lo,b['predicate']) and not pred(hi,b['predicate']),'boundary predicates')
    need({x['predicate'] for x in d['boundaries']}=={'sw','fraction'} and len(d['boundaries'])==2,'boundary inventory')
    for k in ('sw','fraction'):
        p=[pred(x,k) for x in sorted(by) if x<= '4074100000000000'];need(p==sorted(p,reverse=True),'sampled monotone')
    parity=d['parity'];need(len(parity)==60 and {p['word'] for p in parity}==set(by),'parity inventory')
    for p in parity:
        need(set(p['exact'])=={'installed_value','installed_graph','capture_value','capture_graph'} and all(v is True for v in p['exact'].values()),'parity receipt')
        for mode,x in p['return_codes'].items():need(x['rc']==0 and x['close_rc']==(0 if mode.endswith('graph') else None),'parity status')
    return by

def check_schedule(d,by,base):
    seen=[]
    def probe(x):
        if x not in seen: seen.append(x)
        need(x in by,'scheduled event missing')
        return by[x]
    def pred(x,k):
        t=probe(x)['trace'];return f(t['sw_percent']['raw_hex'])>=.48 if k=='sw' else f(t['activation_fraction_min_output']['raw_hex'])>=1.
    start=base['cases'][0]['th16_f64_word']; end=w(321.)
    for k in ('sw','fraction'):
        need(pred(start,k) and not pred(end,k),'search initial bracket')
        a,b=int(start,16),int(end,16)
        while b-a>1:
            m=(a+b)//2
            if pred(f'{m:016x}',k):a=m
            else:b=m
        match=next(x for x in d['boundaries'] if x['predicate']==k)
        need((f'{a:016x}',f'{b:016x}')==(match['lower_word'],match['upper_word']),'search bisection')
    need([x['name'] for x in d['centers']]==['lower','upper'],'center inventory')
    for center in d['centers']:
        cw=center['word']; c=probe(cw); cv=f(cw)
        expected=f('4074005089907cc6')-.01 if center['name']=='lower' else f('4074005089907cc7')+.01
        need(cv==expected and center['value']==cv,'center value')
        need(center['sw_percent']==f(c['trace']['sw_percent']['raw_hex']) and center['fraction_pow']==f(c['trace']['activation_fraction_pow']['raw_hex']),'center trace')
        ps=center['probes'];need([(p['h'],p['sign']) for p in ps]==[(h,s) for h in (.001,.0001,.00001) for s in (-1,1)],'probe grid')
        for p in ps:
            pw=w(cv+p['sign']*p['h']);need(p['word']==pw,'probe represented word')
            t=probe(pw)['trace'];need(all(t[k]==c['trace'][k] for k in BOOL) and p['same_selected_activation_masks'] is True,'sampled selected masks')
    need(seen==[e['th_word'] for e in d['events']],'complete probe schedule')

def check_zip(rr,cr,by):
    expected={x['path']:x['sha256'] for x in rr['independent_parity_calls']}
    for c in cr['calls']:
        expected[c['output_path']]=c['output_sha256'];expected[c['capture_gzip_path']]=c['capture_gzip_sha256']
    need(len(expected)==28 and len(rr['independent_parity_calls'])==20 and len(cr['calls'])==4,'archive receipt inventory')
    words={'4073ff66c0000000','4074002793cded6a','4074005089907cc6','4074005089907cc7','407400797f530c23'}
    need({(x['command'][-1],x['command'][-2]) for x in rr['independent_parity_calls']}=={(word,mode) for word in words for mode in ('installed_value','installed_graph','capture_value','capture_graph')}, 'archive modes/words')
    need({x['th_word'] for x in cr['calls']}==words-{'4073ff66c0000000'}, 'capture endpoints/centers')
    with zipfile.ZipFile(HERE/'raw/parity_calls.zip') as z:
        need(len(z.namelist())==len(set(z.namelist())) and set(z.namelist())==set(expected),'archive inventory')
        for name,digest in expected.items():need(sha(z.read(name))==digest,'archive member SHA '+name)
        for entry in rr['independent_parity_calls']:
            name=entry['path'];x=json.loads(z.read(name));key=x['th_word'];mode=x['mode']
            need(name==f'parity_calls/{key}_{mode}.json' and entry['command'][-2:]==[mode,key],'archive call identity')
            need(x['rc']==0 and x['handle_null_after'] is True and x['handle_nonnull']==mode.endswith('graph') and x['close_rc']==(0 if mode.endswith('graph') else None),'archived call status')
            need(wordvec(x['output_words'],468,'parity outputs')==by[key]['output_words'],'archived call output')
        for c in cr['calls']:
            key=c['th_word'];x=json.loads(z.read(c['output_path']));need(x['th_word']==key and x['mode']=='capture_on' and x['rc']==0 and x['handle_nonnull'] is False and x['handle_null_after'] is True and x['close_rc'] is None,'capture-on status')
            need(wordvec(x['output_words'],468,'capture outputs')==by[key]['output_words'],'capture-on output')
            raw=gzip.decompress(z.read(c['capture_gzip_path']));need(sha(raw)==c['capture_csv_sha256'] and raw.rstrip().endswith(b'status=complete'),'capture CSV SHA/complete')
            t={}
            for row in csv.DictReader(line for line in io.StringIO(raw.decode()) if not line.startswith('#')):
                if row['stage']=='fd_satadj_inner' and row['k_zero']=='23':
                    need((row['runtime_call'],row['one_step_call'],row['substep'],row['b_zero'],row['B'],row['K'])==('1','1','0','0','1','39') and row['field'] not in t,'capture identity')
                    t[row['field']]={'dtype':row['dtype'],'raw_hex':row['raw_hex']}
            need(t==by[key]['trace'],'capture trace')

def check_interior(d,bound,by):
    need(d['schema']=='kdm6.host_selected_f64_interior_ad_fd.v1' and d['boundary_sha256']==read(HERE/'raw/boundary_receipt.json')['files']['result.json'] and d['parent_sha256']==bound['parent_sha256'] and d['library_sha256']==bound['installed_dso_sha256'] and d['script_sha256']==read(HERE/'raw/boundary_receipt.json')['files']['interior_ad_fd.py'],'interior provenance')
    need(d['controls']=={'shape':[1,39,1],'dt':20,'xland':2,'ncmin_land':10,'ncmin_sea':10,'threads':1,'physics_environment':'KDM6 variables unset'} and d['seed']=='TH16 unit JVP; NC16 unit VJP; forcing fixed','interior controls/seeds')
    need([c['name'] for c in d['centers']]==['lower','upper'],'interior centers')
    results={}
    for c in d['centers']:
        name=c['name'];key=c['th_word']; center_record=next(x for x in bound['centers'] if x['name']==name)
        need(key==center_record['word'], 'interior center identity')
        center=by[key];t=center['trace'];masks={k:t[k] for k in MASK}
        need(c['selected_activation_masks']==masks and c['th_value']==f(key),'center masks/value')
        g=c['graph'];v=c['value_only'];out=wordvec(g['output_words'],468,'graph output');need(out==wordvec(v['output_words'],468,'value output')==center['output_words'],'interior graph/value')
        need(g['rc']==g['jvp_rc']==g['vjp_rc']==g['close_rc']==0 and g['handle_nonnull_before_close'] is True and g['handle_null_after_close'] is True and v['rc']==0 and v['handle_nonnull_before_close'] is False,'AD call status')
        need(g['jvp_finite_count']==g['vjp_finite_count']==468,'AD finite counts')
        j=wordvec(g['jvp_words'],468,'JVP');vv=wordvec(g['vjp_words'],468,'VJP');jv=f(j[8*39+15]);vj=f(vv[15]);need(math.isclose(jv,vj,rel_tol=1e-12,abs_tol=1e-12) and g['nc16_jvp']==jv and g['th16_vjp']==vj,'JVP VJP dot')
        need([x['h_requested'] for x in c['differences']]==[.001,.0001,.00001],'FD steps')
        grid={(p['h'],p['sign']):p['word'] for p in center_record['probes']}
        for delta in c['differences']:
            lw,uw=delta['lower_word'],delta['upper_word']; h=delta['h_requested']
            need(lw==w(f(key)-h)==grid[(h,-1)] and uw==w(f(key)+h)==grid[(h,1)], 'FD probe grid')
            lo,up=by[lw],by[uw]
            need(delta['lower']['output_words']==lo['output_words'] and delta['upper']['output_words']==up['output_words'],'FD archived outputs')
            a,b=f(lw),f(uw);den=b-a;need(den>0 and delta['denominator']==den and delta['lower_delta']==a-f(key) and delta['upper_delta']==b-f(key),'FD actual denominator')
            for side,event in [('lower',lo),('upper',up)]:
                need(delta[side+'_masks']=={k:event['trace'][k] for k in MASK}==masks and all(event['trace'][k]==t[k] for k in BOOL),'captured activation-stage FD masks')
            ylo=f(lo['output_words'][8*39+15]);yhi=f(up['output_words'][8*39+15]);fd=(yhi-ylo)/den
            need(delta['nc16_lower']==ylo and delta['nc16_upper']==yhi and delta['output_difference']==yhi-ylo and delta['central_difference']==fd and delta['jvp']==jv and delta['vjp_dot_v']==vj,'FD recomputation')
            distinct=lo['output_words'][8*39+15]!=up['output_words'][8*39+15];need(delta['resolved_distinct_output_words']==distinct,'FD resolution')
            if name=='lower':need(not distinct,'lower unresolved signal')
            if name=='upper' and delta['h_requested']==1e-5:
                residual=abs(fd-jv)/abs(jv);need(distinct and residual<1e-6,'upper relative FD residual');results['upper_h_1e-5_relative_residual']=residual
        results[name+'_nc16_jvp']=jv
    return results

def check_operator():
    receipt=read(HERE/'raw/operator_receipt.json'); data=read(HERE/'raw/operator_result.json')
    need(receipt['schema']=='kdm6.f64_rate_min_operator_experiment.v1' and data['schema']=='kdm6.f64_rate_min_operator_results.v1','operator schemas')
    need(data['scope']=='isolated f64 operator; no whole-column derivative or physics claim' and data['tie_conclusion']=='JVP uses mean of operand tangents and VJP splits cotangent equally; one-sided directional value differences disagree in general at a tie.', 'operator scope/conclusion')
    baseline_receipt=read(HERE/'raw/baseline_receipt.json')
    need(receipt['installed_dso_sha256']=='7adcb6921f6205af66c62720ce9447928a1608f5c261546183b928bebbd9dba7' and receipt['torch_library_sha256']==baseline_receipt['torch_dependency_sha256'], 'operator DSO/dependency links')
    need(receipt['source_coordinator_sha256']=='cf41d3133d9300cb2230a035f735a66b67ba1500b6dc3caeaa64cca7347cef5d', 'operator local review source receipt')
    coordinator_raw=gzip.decompress((HERE/'reviewed_source/coordinator.cpp.gz').read_bytes())
    need(sha(coordinator_raw)=='2a9d9df17dd9bab8d8288bd2d2c6e57ebd7dc65b15d688c06c523cd825b0c932', 'archived research coordinator SHA')
    need(b'torch::minimum(ncact_raw, torch::clamp(state.nccn, /*min=*/0.0) / dtcld)' in coordinator_raw, 'archived research rate-cap expression')
    for local,source in [('main.cpp','operator/main.cpp'),('CMakeLists.txt','operator/CMakeLists.txt'),('result.csv','operator/result.csv'),('build/CMakeCache.txt','operator/CMakeCache.txt.gz'),('build/CMakeFiles/rate_min_operator.dir/flags.make','operator/flags.make.gz'),('installed_otool.txt','operator/installed_otool.txt'),('build.log','operator/build.log'),('configure.log','operator/configure.log.gz')]:
        raw=(HERE/source).read_bytes()
        if source.endswith('.gz'):raw=gzip.decompress(raw)
        need(receipt['files'][local]==sha(raw),'operator receipt asset '+local)
    need(receipt['files']['result.json']==sha((HERE/'raw/operator_result.json').read_bytes()),'operator result SHA')
    rows=list(csv.DictReader((HERE/'operator/result.csv').read_text().splitlines()));need(rows==data['rows'] and len(rows)==9,'operator row inventory')
    flags=gzip.decompress((HERE/'operator/flags.make.gz').read_bytes()).decode()
    need('-ffp-contract=off' in flags and '-DNDEBUG' not in flags,'operator flags')
    loader_raw=gzip.decompress((HERE/'operator/loader.stderr.gz').read_bytes());need(sha(loader_raw)==receipt['files']['loader.stderr'],'operator loader SHA')
    loader=loader_raw.decode();otool=(HERE/'operator/installed_otool.txt').read_text()
    for path in receipt['loader_observed_paths']:need(path in loader and '@rpath/'+Path(path).name in otool,'operator loader')
    for row in rows:
        a,b,da,db,val,j,g1,g2,fp,fm=[float(row[k]) for k in ('raw','cap','d_raw','d_cap','value','jvp','vjp_raw','vjp_cap','forward_difference','backward_difference')]
        need(all(math.isfinite(x) for x in (a,b,da,db,val,j,g1,g2,fp,fm)),'operator finite')
        ga=1. if a<b else .5 if a==b else 0.;gb=1.-ga
        one=(min(da,db),max(da,db)) if a==b else ((da,da) if a<b else (db,db))
        need(val==min(a,b) and g1==ga and g2==gb and j==ga*da+gb*db and abs(fp-one[0])<1e-8 and abs(fm-one[1])<1e-8,'operator AD/FD')
    need({(x['case'],x['d_raw'],x['d_cap']) for x in rows}=={(case,str(a),str(b)) for case in ('raw_lt_cap','raw_eq_cap','raw_gt_cap') for a,b in ((1,0),(0,1),(2,-1))},'operator cases')

def replay():
    br,rr,cr,base,bound,interior=assets();mod,selected=parent();b=check_base(base,bound,mod,selected)
    by=check_boundary(bound);need(by[b['th16_f64_word']]['output_words']==b['value_only']['output_f64_words'],'baseline event output')
    check_schedule(bound,by,base);check_zip(rr,cr,by);diagnostics=check_interior(interior,bound,by);check_operator()
    return {'schema':'kdm6.native_host_column_f64_da_public_replay.v1','input_f32_words_exactly_widened':624,'boundary_events':60,'trace_fields_per_event':33,'archive_members_checked':28,'state_words_per_call':468,'interior':diagnostics,'lower_fd_signal':'unresolved: equal NC16 output words','operator_scope':'isolated two-operand f64 minimum; not whole-column AD; coordinator SHA is local review source only, not installed-build proof', 'mask_scope':'all 10 captured activation-stage Boolean masks stable at sampled interior probes; no all-process claim','scientific_status':'INCONCLUSIVE','physical_unit_status':'INCONCLUSIVE','scope':'single selected native column; no host-tile derivative or f32 AD claim'}

if __name__=='__main__':print(json.dumps(replay(),indent=2,sort_keys=True))
