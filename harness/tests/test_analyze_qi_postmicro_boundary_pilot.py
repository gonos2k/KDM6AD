from pathlib import Path
import pytest
from harness.analyze_qi_postmicro_boundary_pilot import analyze, read_trace


def trace(pilot, alpha=False):
    lines=['# KDM6AD_QI_POST_BDY_V1','# VAL step stage i k j field raw_word_hex',f'GATES 3 {pilot} 1 1']
    for stage in ('BEFORE','AFTER'):
        for k in range(30,34):
            outflow = k == 33
            for i in (1,2):
                qi = '00000002' if alpha and i == 1 and k == 33 else '00000000'
                if not alpha and k == 33:
                    qi = '00000001' if i == 1 else '00000003'
                if pilot and stage == 'AFTER' and i == 1:
                    qi = '00000003' if not alpha and k == 33 else '00000000'
                # Negative zero deliberately exercises strict < 0, not the sign bit.
                velocity = 'BF800000' if i == 1 and outflow else '80000000'
                for field,word in [('QI',qi),('NI','00000000'),('RU_M',velocity)]:
                    lines.append(f'VAL 3 {stage} {i} {k} 168 {field} {word}')
            lines.append(f'BRANCH 3 {stage} {k} 168 WEST_OUTFLOW_U_LT_ZERO {int(outflow)}')
    return '\n'.join(lines)+'\n'


def files(tmp_path):
    result={}
    for case in ('control','alpha025'):
        for mode in ('off','on'):
            path=tmp_path/f'{case}_{mode}.tsv'
            path.write_text(trace(int(mode=='on'),case=='alpha025'))
            result[(case,mode)] = path
    return result


def test_saved_word_map_and_alpha_witness(tmp_path):
    paths=files(tmp_path)
    result=analyze(paths)
    assert result['alpha025_k33_target_qi']['before']=='00000002'
    assert result['alpha025_k33_target_qi']['after']=='00000000'
    assert result['parent_solve_verified'] is False
    assert 'no full-boundary' in result['scope']


@pytest.mark.parametrize('old,new',[
    ('BRANCH 3 BEFORE 30 168 WEST_OUTFLOW_U_LT_ZERO 0','BRANCH 3 BEFORE 30 168 WEST_OUTFLOW_U_LT_ZERO 1'),
    ('VAL 3 AFTER 2 33 168 QI 00000000','VAL 3 AFTER 2 33 168 QI 00000001'),
    ('VAL 3 AFTER 1 33 168 QI 00000000','VAL 3 AFTER 1 33 168 QI 00000002'),
    ('GATES 3 1 1 1','GATES 3 1 1 0'),
    ('VAL 3 BEFORE 1 30 168 NI 00000000\n',''),
])
def test_rejects_branch_donor_mapping_gate_and_inventory(tmp_path,old,new):
    path=tmp_path/'trace.tsv'; original=trace(1,True)
    assert old in original
    path.write_text(original.replace(old,new,1))
    with pytest.raises(ValueError): read_trace(path,1)


def test_rejects_off_state_change_and_unsynchronized_input(tmp_path):
    paths=files(tmp_path)
    path=paths[('alpha025','off')]
    path.write_text(path.read_text().replace('VAL 3 AFTER 1 33 168 QI 00000002','VAL 3 AFTER 1 33 168 QI 00000000'))
    with pytest.raises(ValueError): analyze(paths)
    paths=files(tmp_path)
    path=paths[('control','off')]
    path.write_text(path.read_text().replace('VAL 3 BEFORE 2 33 168 NI 00000000','VAL 3 BEFORE 2 33 168 NI 00000001').replace('VAL 3 AFTER 2 33 168 NI 00000000','VAL 3 AFTER 2 33 168 NI 00000001'))
    with pytest.raises(ValueError): analyze(paths)


def test_post_finish_donor_comparison_accepts_and_rejects(tmp_path, monkeypatch):
    import harness.analyze_qi_donor_transient as donor_module
    paths=files(tmp_path)
    donor_path=tmp_path/'donor.tsv'; donor_path.write_text('mock donor trace')
    words={(0,'POST_FINISH',i,field):'00000000' for i in (1,2) for field in ('QI','NI')}
    monkeypatch.setattr(donor_module,'read_trace',lambda _: words)
    assert analyze(paths,{'alpha025':donor_path})['donor_compared']==['alpha025']
    words[(0,'POST_FINISH',1,'QI')]='00000002'
    with pytest.raises(ValueError,match='POST_FINISH'): analyze(paths,{'alpha025':donor_path})


def test_parent_source_pin_rejects_unrelated_source(tmp_path):
    paths=files(tmp_path)
    source=tmp_path/'source.f90'; source.write_text('unrelated')
    with pytest.raises(ValueError,match='source pin'): analyze(paths,parent_source=source)
