"""Synthetic applied-NI records must replay separately from transfer metrics."""

import copy
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import torch

from oracle.kdm6.ice_number_budget import IceNumberAppliedLedger
from oracle.kdm6.sedimentation import (
    IceSubstepState, default_substep_advection_params,
    ice_substep_advection_torch,
)


module = importlib.import_module(
    "harness.evidence.native_qnice_applied_schema_2026-11-02.replay"
)
ROOT = Path(__file__).resolve().parent
IDENTITY = {"call": "synthetic:1", "column": 0,
            "vertical_order": "sedimentation_top_first"}


def run(ni_values, work_values, dz_values, *, dtype=torch.float64,
        fall_values=None, dend_values=None, n_current=1, mstep=1,
        dt=1.0, state=None, ledger=None):
    ni = torch.tensor([ni_values], dtype=dtype) if state is None else state.ni
    qi = torch.zeros_like(ni) if state is None else state.qi
    zero = torch.zeros_like(ni)
    work = torch.tensor([work_values], dtype=dtype)
    dz = torch.tensor([dz_values], dtype=dtype)
    dend = (torch.ones_like(ni) if dend_values is None else
            torch.tensor([dend_values], dtype=dtype))
    fall = (zero if fall_values is None else fall_values if torch.is_tensor(fall_values)
            else torch.tensor([fall_values], dtype=dtype))
    return ice_substep_advection_torch(
        IceSubstepState(qi, ni), zero, fall, zero, work, dz,
        dend, mstep_col=torch.tensor([float(mstep)], dtype=dtype),
        n_current=n_current, dtcld=dt,
        params=default_substep_advection_params(), number_ledger=ledger)


def packet_from(ledger, case_id, workn_values_by_step):
    dtype = ledger.records[0].before.dtype
    workn = [torch.tensor([values], dtype=dtype)
             for values in workn_values_by_step]
    packet = module.serialize(ledger.records, case_id=case_id,
                              call_identity=IDENTITY, workn_by_step=workn)
    return packet, module.replay(packet, expected_case_id=case_id,
                                 expected_identity=IDENTITY,
                                 expected_levels=ledger.records[0].before.shape[1],
                                 expected_substeps=len(ledger.records))


class AppliedNumberReplay(unittest.TestCase):
    def test_ledger_is_noninterfering_in_both_precisions(self):
        for dtype in (torch.float32, torch.float64):
            plain = run([10, 0], [0.8, 0], [1, 1], dtype=dtype)
            ledger = IceNumberAppliedLedger()
            captured = run([10, 0], [0.8, 0], [1, 1],
                           dtype=dtype, ledger=ledger)
            integer = torch.int32 if dtype == torch.float32 else torch.int64
            for attr in ("qi", "ni"):
                self.assertTrue(torch.equal(
                    getattr(plain.state, attr).view(integer),
                    getattr(captured.state, attr).view(integer)))
            for attr in ("fall_qi", "fall_ni"):
                self.assertTrue(torch.equal(
                    getattr(plain, attr).view(integer),
                    getattr(captured, attr).view(integer)))

    def test_saved_arrival_cap_replays_but_is_not_conserved(self):
        path = ROOT / "sample_arrival_cap.json"
        raw = path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         "90f001b330e966021aa4402ff5ecb6ff913bfbbdb99ad12abdfce8aebf773014")
        packet = json.loads(raw)
        result = module.replay(packet, expected_case_id="two_layer_arrival_cap",
                               expected_identity=IDENTITY,
                               expected_levels=2, expected_substeps=1)
        step = result["substeps"][0]
        self.assertTrue(step["state_replay_raw_bits_equal"])
        self.assertEqual(step["state_replay_max_abs_residual"], 0)
        self.assertEqual(step["interface_difference_dz"], [6.0])
        self.assertEqual(step["column_change_dz"], -6.0)
        self.assertEqual(step["closure_residual_dz"], 0.0)
        self.assertFalse(result["physical_conservation_certified"])

        command = [sys.executable, "-m", module.__name__, str(path),
                   "--sha256", hashlib.sha256(raw).hexdigest(),
                   "--case-id", "two_layer_arrival_cap", "--call", "synthetic:1",
                   "--column", "0", "--levels", "2", "--substeps", "1"]
        completed = subprocess.run(command, cwd=ROOT.parents[2],
                                   capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(completed.stdout), result)

        with tempfile.TemporaryDirectory() as tmp:
            changed = Path(tmp) / "tampered.json"
            changed.write_bytes(raw.replace(b'"case_id": "two_layer_arrival_cap"',
                                            b'"case_id": "two_layer_other_cap"'))
            tampered_command = command.copy()
            tampered_command[3] = str(changed)
            result_cli = subprocess.run(tampered_command, cwd=ROOT.parents[2],
                                        capture_output=True, text=True, check=False)
            self.assertNotEqual(result_cli.returncode, 0)
            self.assertIn("independent packet SHA-256", result_cli.stderr)

    def test_uncapped_and_unequal_depth_transfer(self):
        for dz, expected_in, expected_change in (([1.0, 1.0], 2.0, 0.0),
                                                 ([2.0, 1.0], 4.0, 0.0)):
            ledger = IceNumberAppliedLedger()
            run([10, 0], [0.2, 0], dz, dend_values=[0.7, 1.3], ledger=ledger)
            packet, result = packet_from(ledger, "uncapped", [[0.2, 0.0]])
            self.assertEqual(packet["K"], 2)
            self.assertEqual(ledger.records[0].applied_in[0, 1].item(), expected_in)
            step = result["substeps"][0]
            self.assertEqual(step["interface_difference_dz"], [0.0])
            self.assertEqual(step["column_change_dz"], expected_change)
            self.assertEqual(step["closure_residual_dz"], 0.0)

    def test_top_projection_and_large_accumulator_are_distinct(self):
        ledger = IceNumberAppliedLedger()
        run([10, 2, 3], [2, 0.5, 0.25], [1, 2, 4], ledger=ledger)
        _, result = packet_from(ledger, "top_projection", [[2, 0.5, 0.25]])
        step = result["substeps"][0]
        self.assertEqual(step["top_candidate_out"], 20.0)
        self.assertEqual(step["top_scheduled_debit_before_floor"], 20.0)
        self.assertEqual(step["top_projection"], 10.0)
        self.assertEqual(step["top_realized_loss"], 10.0)
        self.assertEqual(step["column_loss_dz"], 13.0)
        self.assertEqual(step["interface_difference_dz"], [20.0, 0.0])
        self.assertEqual(step["bottom_applied_out_dz"], 3.0)
        self.assertEqual(step["projection_dz"], 10.0)
        self.assertEqual(step["closure_residual_dz"], 0.0)

        ledger = IceNumberAppliedLedger()
        run([1], [1], [1], dtype=torch.float32,
            fall_values=[2**24], ledger=ledger)
        _, result = packet_from(ledger, "rounded_accumulator", [[1]])
        step = result["substeps"][0]
        self.assertEqual(step["fall_rate_bottom"], 1.0)
        self.assertEqual(step["fall_amount_candidate_bottom"], 1.0)
        self.assertEqual(step["fall_accumulator_delta_bottom"], 0.0)
        self.assertEqual(step["column_loss_dz"], 1.0)

    def test_f32_f64_and_substep_gate(self):
        for dtype in (torch.float32, torch.float64):
            ledger = IceNumberAppliedLedger()
            first = run([10, 0], [0.2, 0], [1, 1], dtype=dtype,
                        n_current=1, mstep=1, ledger=ledger)
            run([10, 0], [0.2, 0], [1, 1], dtype=dtype,
                n_current=2, mstep=1, state=first.state,
                fall_values=first.fall_ni, ledger=ledger)
            packet, result = packet_from(ledger, "two_substeps",
                                         [[0.2, 0.0], [0.2, 0.0]])
            self.assertEqual(len(result["substeps"]), 2)
            self.assertEqual(packet["substeps"][1]["gate"],
                             module.word(0.0, packet["dtype"]))
            self.assertEqual(result["substeps"][1]["column_change_dz"], 0.0)
            altered = copy.deepcopy(packet)
            altered["substeps"][1]["fields"]["fall_rate"][0] = module.word(
                1.0, packet["dtype"])
            with self.assertRaisesRegex(ValueError, "fall rate source-order"):
                module.replay(altered, expected_case_id="two_substeps",
                              expected_identity=IDENTITY,
                              expected_levels=2, expected_substeps=2)
            altered = copy.deepcopy(packet)
            altered["substeps"][1]["fields"]["fall_before"][0] = module.word(
                0.0, packet["dtype"])
            with self.assertRaisesRegex(ValueError, "substep fall continuity"):
                module.replay(altered, expected_case_id="two_substeps",
                              expected_identity=IDENTITY,
                              expected_levels=2, expected_substeps=2)
            altered = copy.deepcopy(packet)
            altered["substeps"][1]["dtcld"] = module.word(2.0, "f64")
            with self.assertRaisesRegex(ValueError, "call-wide timestep/geometry"):
                module.replay(altered, expected_case_id="two_substeps",
                              expected_identity=IDENTITY,
                              expected_levels=2, expected_substeps=2)
            altered = copy.deepcopy(packet)
            altered["substeps"][1]["fields"]["delz"][0] = module.word(
                2.0, packet["dtype"])
            with self.assertRaisesRegex(ValueError, "call-wide timestep/geometry"):
                module.replay(altered, expected_case_id="two_substeps",
                              expected_identity=IDENTITY,
                              expected_levels=2, expected_substeps=2)

    def test_fall_rate_and_amount_differ_when_dt_is_two(self):
        ledger = IceNumberAppliedLedger()
        run([10, 0], [0.2, 0], [1, 1], dt=2.0, ledger=ledger)
        packet, result = packet_from(ledger, "dt_two", [[0.2, 0.0]])
        self.assertEqual(module.value(packet["substeps"][0]["fields"]["fall_rate"][0],
                                      "f64"), 2.0)
        self.assertEqual(result["substeps"][0]["top_candidate_out"], 4.0)
        self.assertEqual(result["substeps"][0]["top_realized_loss"], 4.0)
        self.assertEqual(result["substeps"][0]["column_change_dz"], 0.0)

    def test_f32_nonrepresentable_timestep_uses_tensor_scalar(self):
        ledger = IceNumberAppliedLedger()
        run([7.3, 0], [0.23, 0], [1, 1], dtype=torch.float32,
            dt=1.1, ledger=ledger)
        packet, result = packet_from(ledger, "f32_dt_1p1", [[0.23, 0]])
        self.assertEqual(packet["dtype"], "f32")
        self.assertTrue(result["substeps"][0]["state_replay_raw_bits_equal"])

    def test_rehashed_semantic_mutations_rejected(self):
        packet = json.loads((ROOT / "sample_arrival_cap.json").read_bytes())
        changes = [
            lambda p: p.update(dtype="f32"),
            lambda p: p["call_identity"].update(call="other-call"),
            lambda p: p["substeps"][0].update(n_current=2),
            lambda p: p["substeps"][0].update(mstep=module.word(101.0, "f64")),
            lambda p: p.update(K=1),
            lambda p: p.update(substeps=[]),
            lambda p: p["substeps"][0]["fields"]["after"].pop(),
            lambda p: p["substeps"][0]["fields"]["after"].__setitem__(0, "0000000000000000"),
            lambda p: p["substeps"][0]["fields"]["applied_in"].__setitem__(
                0, "8000000000000000"),
            lambda p: p["substeps"][0]["fields"]["fall_after"].__setitem__(
                0, module.word(9.0, "f64")),
            lambda p: p["substeps"][0]["fields"].update(unexpected=[]),
        ]
        for change in changes:
            altered = copy.deepcopy(packet)
            change(altered)
            with self.subTest(change=change), self.assertRaises(ValueError):
                module.replay(altered, expected_case_id="two_layer_arrival_cap",
                              expected_identity=IDENTITY,
                              expected_levels=2, expected_substeps=1)


if __name__ == "__main__":
    unittest.main()
