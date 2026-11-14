import copy
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "draft", HERE / "condition_consumer_v2.py"
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
spec = importlib.util.spec_from_file_location(
    "fixture", HERE.parent / "native_host_preflight_2026-11-12" / "test_fd_gate.py"
)
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)


def contract():
    masks = sorted(m.MASKS)
    sites = [
        dict(
            id=x,
            mask=x,
            stage="test",
            field=x,
            source_hook="source." + x,
            family="main",
            scope="column",
            role="consumed_bool",
            dtype="bool",
            allowed_false_gates=[],
        )
        for x in masks
    ]
    sites[1]["allowed_false_gates"] = [sites[0]["id"]]
    return dict(schema=m.SCHEMA, status="SPEC_ONLY", sites=sites)


def capture(cid, sequence, n=1):
    call = dict(
        input_id=cid,
        sequence=sequence,
        mode="capture_on_value",
        context_epoch=10 + sequence,
        one_step_call=2,
    )
    rows = []
    for sub in range(1, n + 1):
        for s in contract()["sites"]:
            rows.append(
                dict(
                    site_id=s["id"],
                    input_id=cid,
                    mode=call["mode"],
                    context_epoch=call["context_epoch"],
                    runtime_call=sequence,
                    one_step_call=2,
                    outer_loop=1,
                    family="main",
                    substep_n=sub,
                    scope="column",
                    B=1,
                    K=-1,
                    b_zero=0,
                    k_zero=-1,
                    native_level_bottom_first=-1,
                    event_ordinal=0,
                    stage=s["stage"],
                    field=s["field"],
                    source_hook=s["source_hook"],
                    role="consumed_bool",
                    dtype="bool",
                    raw=True,
                    reason="none",
                    causal_index=None,
                )
            )
    return dict(
        call=call,
        capture=dict(
            schema=m.SCHEMA,
            status="SPEC_ONLY",
            call=call.copy(),
            schedule=[
                dict(outer_loop=1, family="main", substeps=n),
                dict(outer_loop=1, family="ice", substeps=0),
            ],
            records=rows,
        ),
    )


def setup(stencil="central"):
    d = f.example(stencil=stencil)
    # Retain the baseline-size inventory while exercising the same gate path.
    for o in [d["center"]] + [
        s[r]
        for s in d["samples"]
        for r in ("lower", "upper") + (("plus2",) if stencil == "forward" else ())
    ]:
        o["masks"] = {"v1mask%d" % i: True for i in range(1170)}
        o["schedule"] = {"v1schedule%d" % i: f.m.word(1) for i in range(195)}
    bindings = {"center": "center", "samples": {}}
    captures = {"center": capture("center", 0)}
    for s in d["samples"]:
        roles = ("lower", "upper") + (("plus2",) if stencil == "forward" else ())
        bindings["samples"][s["id"]] = {}
        for r in roles:
            cid = s["id"] + ":" + r
            bindings["samples"][s["id"]][r] = cid
            captures[cid] = capture(cid, len(captures))
    return d, bindings, captures


class ContractTests(unittest.TestCase):
    def test_gate_mask_and_schedule_and_preserve_v1(self):
        d, x, c = setup()
        a = m.add_conditions(d, x, c, contract())
        self.assertEqual(
            f.m.evaluate(a, allow_synthetic=True)["tag"], "LOCAL_NUMERIC_CONSISTENT"
        )
        self.assertEqual(
            {
                k: v
                for k, v in a["center"]["masks"].items()
                if not k.startswith(m.PREFIX)
            },
            d["center"]["masks"],
        )
        self.assertEqual(a["center"]["schedule"], d["center"]["schedule"])
        cid = x["samples"]["0"]["upper"]
        c[cid]["capture"]["records"][0]["raw"] = False
        self.assertEqual(
            f.m.evaluate(m.add_conditions(d, x, c, contract()), allow_synthetic=True)[
                "tag"
            ],
            "BRANCH_CROSSING",
        )
        c[cid] = capture(cid, c[cid]["call"]["sequence"], 2)
        self.assertEqual(
            f.m.evaluate(m.add_conditions(d, x, c, contract()), allow_synthetic=True)[
                "tag"
            ],
            "BRANCH_CROSSING",
        )

    def test_causal_proof(self):
        entry = capture("center", 0)
        rows = entry["capture"]["records"]
        rows[0]["raw"] = False
        rows[1].update(
            role="not_evaluated",
            dtype="none",
            raw=None,
            reason="gate_false",
            causal_index=0,
        )
        self.assertEqual(
            m.validate(contract(), entry["capture"], entry["call"])["eligibility"],
            "NOT_ELIGIBLE",
        )
        rows[0]["raw"] = True
        with self.assertRaises(ValueError):
            m.validate(contract(), entry["capture"], entry["call"])
        rows[0]["raw"] = False
        rows[1]["reason"] = "optional_absent"
        with self.assertRaises(ValueError):
            m.validate(contract(), entry["capture"], entry["call"])

    def test_missing_duplicates_wrong_binding_and_nonfinite(self):
        for mutation in ("missing", "duplicate", "wrong_call", "nonfinite", "wrong_shape"):
            entry = capture("center", 0)
            ct = contract()
            rows = entry["capture"]["records"]
            if mutation == "missing":
                rows.pop()
            if mutation == "duplicate":
                rows.append(copy.deepcopy(rows[0]))
            if mutation == "wrong_call":
                rows[0]["context_epoch"] += 1
            if mutation == "wrong_shape":
                rows[0]["K"] = 39
            if mutation == "nonfinite":
                ct["sites"][0].update(role="operand", dtype="f64")
                rows[0].update(role="operand", dtype="f64", raw="7ff0000000000000")
                ct["sites"][1]["allowed_false_gates"] = []
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                m.validate(ct, entry["capture"], entry["call"])

    def test_alias_rejected(self):
        d, x, c = setup()
        x["samples"]["0"]["upper"] = x["center"]
        with self.assertRaisesRegex(ValueError, "call alias"):
            m.add_conditions(d, x, c, contract())

    def test_nonfinite_word_rejected(self):
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            m._word("f64", "7ff0000000000000")

    def test_forward_plus2_crossing(self):
        d, x, c = setup("forward")
        cid = x["samples"]["0"]["plus2"]
        c[cid]["capture"]["records"][0]["raw"] = False
        result = f.m.evaluate(
            m.add_conditions(d, x, c, contract()), allow_synthetic=True
        )
        self.assertEqual(result["tag"], "BRANCH_CROSSING")

    def test_zero_substeps_veto_classification(self):
        d, bindings, captures = setup()
        for cid, item in list(captures.items()):
            captures[cid] = capture(cid, item["call"]["sequence"], 0)
        with self.assertRaisesRegex(ValueError, "NOT_OBSERVED"):
            m.add_conditions(d, bindings, captures, contract())

    def test_diagnostic_only_stability_and_crossing(self):
        d, bindings, captures = setup()
        ct = contract()
        ct["sites"][1]["role"] = "diagnostic_bool"
        for item in captures.values():
            item["capture"]["records"][1]["role"] = "diagnostic_bool"
        data = m.add_conditions(d, bindings, captures, ct)
        self.assertEqual(f.m.evaluate(data, allow_synthetic=True)["tag"], "LOCAL_NUMERIC_CONSISTENT")
        cid = bindings["samples"]["0"]["upper"]
        captures[cid]["capture"]["records"][1]["raw"] = False
        data = m.add_conditions(d, bindings, captures, ct)
        self.assertEqual(f.m.evaluate(data, allow_synthetic=True)["tag"], "BRANCH_CROSSING")


if __name__ == "__main__":
    unittest.main()
