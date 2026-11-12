"""Synthetic-only fixtures: no model, DSO or actual execution receipt."""

import copy
import json
import unittest

import receipt_schema as rs


def data_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def add(assets, path, value):
    raw = data_bytes(value)
    assets[path] = raw
    return {"path": path, "sha256": rs.sha(raw)}


def synthetic_bundle():
    p, inv = rs.load_plan()
    assets = {}
    fake_dso = "a" * 64
    build = {
        "new_instrumented_dso_sha256": fake_dso,
        "installed_dso_sha256": p["build_requirements"]["installed_dso_sha256"],
        "controls": p["controls"],
        "compiler_identity": "synthetic compiler",
        "compiler_flags": ["-ffp-contract=off"],
        "test_assertions_enabled": True,
        "modified_source_sha256": {
            name: "b" * 64
            for name in (
                "libtorch/src/runtime.cpp",
                "libtorch/src/coordinator.cpp",
                "libtorch/src/sedimentation.cpp",
            )
        },
        "dependency_sha256": {
            name: "c" * 64
            for name in (
                "libtorch.dylib",
                "libtorch_cpu.dylib",
                "libc10.dylib",
                "libomp.dylib",
            )
        },
    }
    build["modified_source_assets"] = {}
    for name in build["modified_source_sha256"]:
        ref = add(
            assets,
            "sources/" + name.rsplit("/", 1)[-1] + ".json",
            {"synthetic_source": name},
        )
        build["modified_source_assets"][name] = ref
        build["modified_source_sha256"][name] = ref["sha256"]
    seeds = {}
    ids = {}
    for name, meta in p["direction_seeds"].items():
        arr = [rs.ZERO] * 624
        arr[rs.FIELDS.index(name) * 39 + 15] = meta["scale_f64_word"]
        ident = ("jvp", name, "none")
        seed = {
            "schema": "kdm6.derivative_seed.v1",
            "id": "jvp:" + name,
            "derivative_mode": "jvp",
            "direction_id": name,
            "cotangent_id": "none",
            "words": arr,
            "seed_sha256": rs.word_sha(arr),
        }
        seeds[seed["id"]] = add(assets, "seeds/" + name + ".json", seed)
        ids[ident] = seed["seed_sha256"]
    arr = [rs.ZERO] * 468
    arr[8 * 39 + 15] = rs.ONE
    seed = {
        "schema": "kdm6.derivative_seed.v1",
        "id": "vjp:state:nc:15",
        "derivative_mode": "vjp",
        "direction_id": "none",
        "cotangent_id": "state:nc:15",
        "words": arr,
        "seed_sha256": rs.word_sha(arr),
    }
    seeds[seed["id"]] = add(assets, "seeds/vjp.json", seed)
    ids[("vjp", "none", "state:nc:15")] = seed["seed_sha256"]
    inputs = {x["id"]: x for x in p["inputs"]}
    calls = []
    seq = {}
    for call in p["calls"]:
        out = {
            "sequence": call["sequence"],
            "input_id": call["input_id"],
            "mode": call["mode"],
        }
        if call["status"] == "PLANNED_OPTIONAL":
            out.update(status="skipped", reason="synthetic budget", output_asset=None)
        else:
            seq[(out["input_id"], out["mode"])] = out["sequence"]
            payload = {
                "schema": "kdm6.future_call_raw.v1",
                **out,
                "dso_sha256": fake_dso,
                "input_words": inputs[out["input_id"]]["words"],
                "state_output_words": [rs.ZERO] * 468,
            }
            if call["mode"] == "center_joint_graph":
                payload["graph_handle_id"] = "synthetic-handle:" + call["input_id"]
                payload["effective_jvp_output_sha256"] = {
                    key: rs.word_sha([rs.ZERO] * 468)
                    for key, spec in rs.effective_seed_specs().items()
                    if spec["center"] == call["input_id"]
                }
            out.update(
                status="completed",
                return_code=0,
                output_asset=add(assets, f"calls/{call['sequence']}.json", payload),
            )
        calls.append(out)
    records = []

    def emit(input_id, mode, group, idx, kind, seedid=("none", "none", "none")):
        requirement = inv["groups"][group]["new_requirements"][idx]
        stage = f"{group}_{idx}"
        field = kind + "_" + "_".join(seedid)
        row = {
            "input_id": input_id,
            "mode": mode,
            "call_sequence": seq[(input_id, mode)],
            "runtime_call": 1,
            "one_step_call": 1,
            "substep": 0,
            "b_zero": 0,
            "k_zero": 23,
            "native_level_bottom_first": 16,
            "stage": stage,
            "field": field,
            "record_kind": kind,
            "derivative_mode": seedid[0],
            "direction_id": seedid[1],
            "cotangent_id": seedid[2],
            "seed_sha256": ids[seedid] if kind == "live_tangent" else "none",
            "event_ordinal": 0,
            "record_id": str(len(records)),
            "group": group,
            "requirement_index": idx,
            "requirement": requirement,
            "availability": "present",
            "inactive_reason": None,
            "inactive_mask_id": None,
            "dtype": "bool" if kind == "mask" else "f64",
            "raw_hex": "1" if kind == "mask" else rs.ZERO,
        }
        records.append(row)

    for group, groupdata in inv["groups"].items():
        for idx in range(len(groupdata["new_requirements"])):
            for input_id in inputs:
                for kind in ("value", "mask"):
                    emit(input_id, "capture_on_value", group, idx, kind)
            for center in ("baseline", "lower", "upper"):
                for seedid in ids:
                    emit(
                        center, "center_joint_graph", group, idx, "live_tangent", seedid
                    )
    effective_assets = {}
    for ident, spec in rs.effective_seed_specs().items():
        seed_words = spec["effective_direction_words"]
        jvp_words = [rs.ZERO] * 468
        payload = {
            "schema": "kdm6.effective_jvp_payload.v1",
            "id": ident,
            "center": spec["center"],
            "direction": spec["direction"],
            "step_id": spec["step_id"],
            "graph_sequence": seq[(spec["center"], "center_joint_graph")],
            "graph_handle_id": "synthetic-handle:" + spec["center"],
            "jvp_return_code": 0,
            "evaluation_input_words": spec["evaluation_input_words"],
            "effective_direction_words": seed_words,
            "seed_sha256": rs.word_sha(seed_words),
            "graph_forward_output_words": [rs.ZERO] * 468,
            "jvp_output_words": jvp_words,
            "jvp_output_sha256": rs.word_sha(jvp_words),
        }
        effective_assets[ident] = add(assets, "effective/" + ident + ".json", payload)
    receipt = {
        "schema": "kdm6.native_host_capture_receipt.v1",
        "plan_gzip_sha256": rs.PLAN_GZ_SHA,
        "base_source_hashes": p["build_requirements"]["source_pins"],
        "build": build,
        "elapsed_seconds": 100,
        "seed_assets": seeds,
        "effective_jvp_assets": effective_assets,
        "calls": calls,
        "capture_records_asset": add(
            assets,
            "records.json",
            {"schema": "kdm6.future_capture_records.v1", "records": records},
        ),
    }
    return receipt, assets


def synthetic_scheduler(receipt):
    canonical, _ = rs.load_plan()
    canonical["build_requirements"]["instrumented_dso_sha256"] = receipt["build"][
        "new_instrumented_dso_sha256"
    ]
    calls = []
    for row in receipt["calls"]:
        out = {k: row[k] for k in ("sequence", "input_id", "mode", "status")}
        out["required"] = row["sequence"] <= 93
        if row["status"] == "completed":
            out.update(
                returncode=0,
                output_path=row["output_asset"]["path"],
                output_sha256=row["output_asset"]["sha256"],
            )
        else:
            out["reason"] = row["reason"]
        calls.append(out)
    return {
        "schema": "kdm6.native_host_preflight.execution_budget.v1",
        "status": "SYNTHETIC_COMPLETED_UNVERIFIED",
        "execution_scope": "SYNTHETIC_TEST_ONLY",
        "plan_gzip_sha256": rs.PLAN_GZ_SHA,
        "plan_sha256": rs.sha(
            json.dumps(
                canonical, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
        ),
        "dso_sha256": receipt["build"]["new_instrumented_dso_sha256"],
        "controls": canonical["controls"],
        "limits": canonical["limits"],
        "elapsed_seconds": 100,
        "calls": calls,
    }


class ReceiptSchemaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt, cls.assets = synthetic_bundle()

    def bundle(self):
        return copy.deepcopy(self.receipt), dict(self.assets)

    def test_complete_synthetic_bundle_never_becomes_eligible(self):
        result = rs.validate(*self.bundle())
        self.assertEqual(result["status"], "NOT_ELIGIBLE_UNVERIFIED_PROVENANCE")
        self.assertEqual(
            result["effective_jvp_linkage"],
            "REPRESENTED_SEEDS_AND_GRAPH_FORWARD_LINKED_UNVERIFIED",
        )
        self.assertEqual(result["effective_jvp_payloads"], 21)
        self.assertEqual(result["live_intermediate_effective_tangents"], "NOT_LINKED")
        self.assertIs(result["fd_gate_ready"], False)
        self.assertEqual(
            (result["calls"], result["inputs"], result["seed_payloads"]), (100, 45, 5)
        )

    def test_missing_calls_and_wrong_order(self):
        receipt, assets = self.bundle()
        receipt["calls"].pop()
        with self.assertRaisesRegex(ValueError, "complete call ledger"):
            rs.validate(receipt, assets)
        receipt, assets = self.bundle()
        receipt["calls"][0], receipt["calls"][1] = (
            receipt["calls"][1],
            receipt["calls"][0],
        )
        with self.assertRaisesRegex(ValueError, "call identity/order"):
            rs.validate(receipt, assets)
        receipt, assets = self.bundle()
        receipt["calls"][0]["status"] = "skipped"
        receipt["calls"][0]["reason"] = "not run"
        receipt["calls"][0]["output_asset"] = None
        with self.assertRaisesRegex(ValueError, "invalid skipped"):
            rs.validate(receipt, assets)

    def test_rehashed_input_or_output_mismatch_rejected(self):
        for field in ("input_words", "state_output_words"):
            receipt, assets = self.bundle()
            call = receipt["calls"][1]
            ref = call["output_asset"]
            payload = json.loads(assets[ref["path"]])
            payload[field][0] = rs.ONE
            call["output_asset"] = add(assets, ref["path"], payload)
            with self.subTest(field=field), self.assertRaises(ValueError):
                rs.validate(receipt, assets)

    def test_rehashed_wrong_jvp_or_cotangent_rejected(self):
        for key in ("jvp:nc", "vjp:state:nc:15"):
            receipt, assets = self.bundle()
            ref = receipt["seed_assets"][key]
            seed = json.loads(assets[ref["path"]])
            seed["words"][0] = rs.ONE
            seed["seed_sha256"] = rs.word_sha(seed["words"])
            receipt["seed_assets"][key] = add(assets, ref["path"], seed)
            with (
                self.subTest(seed=key),
                self.assertRaisesRegex(ValueError, "seed words|cotangent words"),
            ):
                rs.validate(receipt, assets)

    def test_missing_coverage_and_misbound_record_seed(self):
        for mutation in ("missing", "misbound", "duplicate"):
            receipt, assets = self.bundle()
            ref = receipt["capture_records_asset"]
            payload = json.loads(assets[ref["path"]])
            rows = payload["records"]
            if mutation == "missing":
                rows.pop(0)
            elif mutation == "misbound":
                next(x for x in rows if x["record_kind"] == "live_tangent")[
                    "seed_sha256"
                ] = "a" * 64
            else:
                rows.append(copy.deepcopy(rows[0]))
            receipt["capture_records_asset"] = add(assets, ref["path"], payload)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                rs.validate(receipt, assets)

    def test_effective_jvp_missing_or_rehashed_misbindings_rejected(self):
        receipt, assets = self.bundle()
        receipt["effective_jvp_assets"].pop(next(iter(receipt["effective_jvp_assets"])))
        with self.assertRaisesRegex(ValueError, "effective JVP inventory"):
            rs.validate(receipt, assets)
        for mutation in (
            "seed",
            "input",
            "forward",
            "graph",
            "handle",
            "jvp_rc",
            "output_hash",
        ):
            receipt, assets = self.bundle()
            ident = next(iter(receipt["effective_jvp_assets"]))
            ref = receipt["effective_jvp_assets"][ident]
            payload = json.loads(assets[ref["path"]])
            if mutation == "seed":
                payload["effective_direction_words"][0] = rs.ONE
                payload["seed_sha256"] = rs.word_sha(
                    payload["effective_direction_words"]
                )
            elif mutation == "input":
                payload["evaluation_input_words"][0] = rs.ZERO
            elif mutation == "forward":
                payload["graph_forward_output_words"][0] = rs.ONE
            elif mutation == "graph":
                payload["graph_sequence"] += 1
            elif mutation == "handle":
                payload["graph_handle_id"] = "wrong-handle"
            elif mutation == "jvp_rc":
                payload["jvp_return_code"] = 1
            else:
                payload["jvp_output_words"][0] = rs.ONE
                payload["jvp_output_sha256"] = rs.word_sha(payload["jvp_output_words"])
            receipt["effective_jvp_assets"][ident] = add(assets, ref["path"], payload)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                rs.validate(receipt, assets)

    def test_scheduler_bridge_identity_and_asset_mismatch(self):
        receipt, assets = self.bundle()
        scheduler = synthetic_scheduler(receipt)
        self.assertEqual(
            rs.validate_scheduler_bridge(receipt, scheduler, assets)[
                "scheduler_binding"
            ],
            "SYNTHETIC_ONLY_UNVERIFIED",
        )
        for mutation in ("plan", "gzip", "dso", "call", "path", "sha", "scope"):
            altered = copy.deepcopy(scheduler)
            if mutation == "plan":
                altered["plan_sha256"] = "a" * 64
            elif mutation == "gzip":
                altered["plan_gzip_sha256"] = "d" * 64
            elif mutation == "dso":
                altered["dso_sha256"] = "b" * 64
            elif mutation == "call":
                altered["calls"][0]["input_id"] = "upper"
            elif mutation == "path":
                altered["calls"][0]["output_path"] = "wrong.json"
            elif mutation == "sha":
                altered["calls"][0]["output_sha256"] = "c" * 64
            else:
                altered["execution_scope"] = "REAL"
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                rs.validate_scheduler_bridge(receipt, altered, assets)

    def test_inactive_reason_must_bind_a_same_requirement_false_mask(self):
        receipt, assets = self.bundle()
        ref = receipt["capture_records_asset"]
        payload = json.loads(assets[ref["path"]])
        rows = payload["records"]
        row = next(x for x in rows if x["record_kind"] == "value")
        mask = next(
            x
            for x in rows
            if x["record_kind"] == "mask"
            and x["input_id"] == row["input_id"]
            and x["group"] == row["group"]
            and x["requirement_index"] == row["requirement_index"]
        )
        mask["raw_hex"] = "0"
        row.update(
            availability="inactive",
            inactive_reason="synthetic inactive branch",
            inactive_mask_id=mask["record_id"],
            raw_hex=None,
        )
        receipt["capture_records_asset"] = add(assets, ref["path"], payload)
        self.assertEqual(
            rs.validate(receipt, assets)["status"], "NOT_ELIGIBLE_UNVERIFIED_PROVENANCE"
        )
        row["inactive_mask_id"] = next(
            x["record_id"]
            for x in rows
            if x["record_kind"] == "mask"
            and x["input_id"] == row["input_id"]
            and x["group"] != row["group"]
        )
        receipt["capture_records_asset"] = add(assets, ref["path"], payload)
        with self.assertRaisesRegex(ValueError, "inactive mask evidence"):
            rs.validate(receipt, assets)

    def test_modified_source_asset_hash_rejected_when_rehashed_only_as_asset(self):
        receipt, assets = self.bundle()
        name = next(iter(receipt["build"]["modified_source_assets"]))
        ref = receipt["build"]["modified_source_assets"][name]
        receipt["build"]["modified_source_assets"][name] = add(
            assets, ref["path"], {"synthetic_source": "changed"}
        )
        with self.assertRaisesRegex(ValueError, "modified source asset hash"):
            rs.validate(receipt, assets)

    def test_inactive_mask_must_share_full_context_after_rehash(self):
        for mutation in ("level", "substep", "call", "runtime_call", "stage"):
            receipt, assets = self.bundle()
            ref = receipt["capture_records_asset"]
            payload = json.loads(assets[ref["path"]])
            rows = payload["records"]
            row = next(x for x in rows if x["record_kind"] == "value")
            mask = next(
                x
                for x in rows
                if x["record_kind"] == "mask"
                and x["input_id"] == row["input_id"]
                and x["group"] == row["group"]
                and x["requirement_index"] == row["requirement_index"]
            )
            mask["raw_hex"] = "0"
            row.update(
                availability="inactive",
                inactive_reason="branch inactive",
                inactive_mask_id=mask["record_id"],
                raw_hex=None,
            )
            if mutation == "level":
                mask["k_zero"] = 22
                mask["native_level_bottom_first"] = 17
            elif mutation == "substep":
                mask["substep"] = 1
            elif mutation == "call":
                mask["call_sequence"] += 2
            elif mutation == "runtime_call":
                mask["runtime_call"] += 1
            else:
                mask["stage"] += "_other"
            receipt["capture_records_asset"] = add(assets, ref["path"], payload)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                rs.validate(receipt, assets)

    def test_inactive_mask_and_live_tangent_are_not_supported(self):
        for kind in ("mask", "live_tangent"):
            receipt, assets = self.bundle()
            ref = receipt["capture_records_asset"]
            payload = json.loads(assets[ref["path"]])
            row = next(x for x in payload["records"] if x["record_kind"] == kind)
            row.update(
                availability="inactive",
                inactive_reason="unknown semantics",
                inactive_mask_id="some-mask",
                raw_hex=None,
            )
            receipt["capture_records_asset"] = add(assets, ref["path"], payload)
            with (
                self.subTest(kind=kind),
                self.assertRaisesRegex(
                    ValueError, "inactive mask or live tangent unsupported"
                ),
            ):
                rs.validate(receipt, assets)

    def test_inactive_field_requires_matching_mask(self):
        receipt, assets = self.bundle()
        ref = receipt["capture_records_asset"]
        payload = json.loads(assets[ref["path"]])
        row = next(x for x in payload["records"] if x["record_kind"] == "value")
        row.update(
            availability="inactive",
            inactive_reason="branch inactive",
            inactive_mask_id="nonexistent",
            raw_hex=None,
        )
        receipt["capture_records_asset"] = add(assets, ref["path"], payload)
        with self.assertRaisesRegex(ValueError, "inactive mask evidence"):
            rs.validate(receipt, assets)


if __name__ == "__main__":
    unittest.main()
