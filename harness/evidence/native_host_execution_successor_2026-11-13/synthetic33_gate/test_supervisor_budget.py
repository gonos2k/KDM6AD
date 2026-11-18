"""Synthetic plan/manifest/witness query-budget consistency."""
import copy
import tempfile
import unittest
from unittest.mock import patch

import fixture33
import graph_runner
import real33_supervisor_draft as supervisor
import selector_manifest_spec_v1 as selectors
import witness33
import real33_worker
from test_real33_worker import FakeRunner


class BudgetTest(unittest.TestCase):
    def test_plan_manifest_supervisor_and_witness_match(self):
        slots=fixture33.validate()
        with tempfile.TemporaryDirectory() as directory, patch.object(supervisor,'preflight',return_value={'calls':slots}):
            plan=supervisor.prepare(directory)
            self.assertEqual(plan['limits']['query_per_fixture'],{'graph_primal':3,'jvp':6,'vjp':3})
            expected={k:plan['limits'][k] for k in ('graph_primal','jvp','vjp')}
            self.assertEqual(expected,{'graph_primal':9,'jvp':18,'vjp':9})
            manifest=selectors.proposed_manifest()['budget']
            self.assertEqual((manifest['graph_primal'],manifest['intermediate_jvp'],manifest['intermediate_vjp']),(9,18,9))
            runner=FakeRunner('fake')
            assets=[]
            for slot in slots:
                if slot['mode']!='center_joint_graph':
                    continue
                result=runner._call(slot['fixture'],slot['mode'],fixture33.center(slot['fixture']),[fixture33.direction(k) for k in fixture33.DIRECTIONS],None,slot['seq'])
                for entry in result['selectors'].values():
                    if 'jvp_statuses' in entry:
                        entry['abi_jvp_statuses']=entry.pop('jvp_statuses');entry['direction_connectivity']=['CONNECTED','CONNECTED']
                assets.append({'slot':slot,'result':real33_worker.encode(result)})
            self.assertEqual(witness33.checked_results(assets),expected)

    def test_all_consumers_reject_mutated_budget_before_queries(self):
        class Fake:
            FAKE_ONLY_NO_CDLL=True
        fake=Fake()
        with patch.dict(selectors.BUDGET,{'intermediate_jvp':17}):
            with self.assertRaisesRegex(ValueError,'budget'):
                graph_runner.query_graph_set(fake,None,0,[],[[],[]])
            with self.assertRaisesRegex(ValueError,'budget'):
                witness33.checked_results([])
        counts={'graph_primal':3,'jvp':6,'vjp':3}
        with self.assertRaisesRegex(RuntimeError,'budget'):
            graph_runner.query_graph_set(fake,None,0,[('x',{},0)],[[],[]],counts)
        self.assertEqual(counts,{'graph_primal':3,'jvp':6,'vjp':3})

    def test_mismatch_fails_closed(self):
        slots=fixture33.validate()
        for key,value in (('seq',True),('offset',0),('offset',False),('offset',-0.0)):
            bad_type=copy.deepcopy(slots);bad_type[0][key]=value
            self.assertFalse(fixture33.same_plan_exact(bad_type))
            with self.assertRaises(ValueError):selectors.query_budget(bad_type)
            with tempfile.TemporaryDirectory() as directory,patch.object(supervisor,'preflight',return_value={'calls':bad_type}):
                with self.assertRaisesRegex(RuntimeError,'plan mismatch'):supervisor.prepare(directory)
        bad=copy.deepcopy(slots);bad[2]['mode']='capture_on_value'
        with self.assertRaises(ValueError):selectors.query_budget(bad)
        with patch.dict(selectors.BUDGET,{'graph_primal':3}):
            with self.assertRaisesRegex(ValueError,'budget'):selectors.query_budget(slots)
        with tempfile.TemporaryDirectory() as directory,patch.object(supervisor,'preflight',return_value={'calls':bad}):
            with self.assertRaisesRegex(RuntimeError,'plan mismatch'):supervisor.prepare(directory)


if __name__=='__main__':unittest.main()
