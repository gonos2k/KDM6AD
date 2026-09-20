"""Raw capture checks need no Torch or private host files."""
import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from replay_native_ice_transfer import EVIDENCE,validate,check_native


def data():return json.loads(EVIDENCE.read_text())


def test_mixed_precision_native_numbers_exact():
    d=data();validate(d)
    p=json.loads((EVIDENCE.parent/'native_number_2026-09-20.json').read_text())
    for c in d['cases']:check_native(c,p)


@pytest.mark.parametrize('fault',['missing','order','nonfinite','work','approval'])
def test_corrupt_operands_rejected(fault):
    d=data()
    if fault=='missing':d['cases'][1]['rows'].pop()
    elif fault=='order':d['cases'][1]['rows'].reverse()
    elif fault=='nonfinite':d['cases'][1]['rows'][0]['workn']=float('nan')
    elif fault=='approval':d['operational_fix_applied']=True
    else:d['cases'][1]['rows'][15]['workn']=0.
    with pytest.raises(AssertionError):
        validate(d)
        p=json.loads((EVIDENCE.parent/'native_number_2026-09-20.json').read_text())
        check_native(d['cases'][1],p)
