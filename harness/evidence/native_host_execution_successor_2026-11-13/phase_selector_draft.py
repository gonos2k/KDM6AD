"""Phase-aware source selector draft; no runtime coverage is claimed."""

import hashlib
import json
import pathlib
import re
from producer_source_batch6_layers import replay as source_replay

HERE = pathlib.Path(__file__).resolve().parent
SNAPSHOT_SHA = "033558eb6f771beb76d6ba8ebbc1aa126c4abafd4eb6d53dcabd3361cb8a1038"
FILES = {
    "src/coordinator.cpp": "b701fcbdd3fa9aed0749ec686a6f307a446a55b661403eec30cfc86b1587e831",
    "src/runtime.cpp": "de72d0ca088cf013c0ce9b524960c01f47c2d87a23250672cab567cb8bc823db",
    "src/thermo.cpp": "59adb67b3e1fc915761e42ad39593c80aa48a0686423d8c01035ad8c133325a3",
    "include/kdm6/batch6_a2_named_hooks.h": "83ead03c848c6b260c7ffc01b7a7c83bbdde9876180c104895ce7f278f210f94",
}
# The A4 base's other two hook-bearing sources remain unchanged in A5.
FILES.update(
    {
        "src/progb.cpp": "d118534b5280dbe4149b23920c24b58837bf681ac99a4aeaab4ba6894b82b8e5",
        "src/satadj.cpp": "d3bfd8c9919bd5cf5d8c6f7fea320ff5572ba558118bf6affa0df37859b406ab",
    }
)
SITE = re.compile(
    r'batch5::a2_named::(record|scalar_f64|scalar_integral)\(("[^"]+"|label),\s*"([^"]+)",\s*"([^"]+)"(.*)'
)


def need(x, msg):
    if not x:
        raise ValueError(msg)


def census_from_source(SRC):
    result = []
    for f, sha in FILES.items():
        data = (SRC / f).read_bytes()
        need(hashlib.sha256(data).hexdigest() == sha, "source hash " + f)
        if not f.startswith("src/"):
            continue
        for line_no, line in enumerate(data.decode().splitlines(), 1):
            m = SITE.search(line)
            if not m:
                continue
            fn, stage, field, hook, tail = m.groups()
            scope = (
                "scalar"
                if fn.startswith("scalar")
                else ("column" if "Scope::COLUMN" in tail else "layer")
            )
            role = (
                "control_scalar"
                if scope == "scalar"
                else "consumed_bool"
                if "Role::CONSUMED_BOOL_TENSOR" in tail
                else "diagnostic_comparison"
                if "Role::DIAGNOSTIC_COMPARISON" in tail
                else "operand"
            )
            stage = stage.strip('"') if stage != "label" else "{runtime_site_label}"
            result.append(
                {
                    "source_file": f,
                    "line": line_no,
                    "stage": stage,
                    "field": field,
                    "source_hook": hook,
                    "scope": scope,
                    "role": role,
                    "allowed_dtype": (
                        ["bool"]
                        if role in ("consumed_bool", "diagnostic_comparison")
                        else ["f32", "f64"]
                        if role == "operand"
                        else ["bool"]
                        if "Dtype::BOOL" in tail
                        else ["i64"]
                        if "Dtype::I64" in tail
                        else ["f64"]
                    ),
                    "condition": "OPTIONAL_BRANCH"
                    if hook.endswith((".ncmin", ".nc_ge_ncmin"))
                    and stage in ("nc_snap1", "nc_snap2")
                    else "SOURCE_PATH_REQUIRED_WHEN_REACHED",
                    "fixture_requirement": "PROPOSED_NOT_OBSERVED"
                    if "A5_" in line
                    or stage
                    in ("a5_phase_mask", "a5_heat_mask", "sedimentation_schedule")
                    else "SOURCE_ONLY_NOT_PER_SELECTOR_PROVEN",
                }
            )
    ids = [(x["stage"], x["field"], x["source_hook"], x["role"]) for x in result]
    need(len(ids) == len(set(ids)), "duplicate selector")
    need(len(result) == 98, "hook site inventory")
    v1 = []
    for f in ("src/coordinator.cpp", "src/runtime.cpp"):
        for line_no, line in enumerate((SRC / f).read_text().splitlines(), 1):
            match = re.search(
                r'batch5::full\("(a7_[^"]+)",\s*"([^"]+)",\s*([^,]+),\s*true\);', line
            )
            if match:
                stage, field, expr = match.groups()
                v1.append(
                    {
                        "source_file": f,
                        "line": line_no,
                        "stage": stage,
                        "field": field,
                        "source_expression": expr,
                        "scope": "layer",
                        "role": "v1_tensor",
                        "dtype": "f32_or_f64_source",
                        "status": "SOURCE_ONLY_NOT_OBSERVED",
                    }
                )
    need(
        len(v1) == 18 and len({(x["stage"], x["field"]) for x in v1}) == 18,
        "A7 v1 site inventory",
    )
    return {
        "schema": "kdm6.batch6.phase_selector_draft.v1",
        "a7_source_snapshot_sha256": SNAPSHOT_SHA,
        "a7_v1_fields": v1,
        "status": "DRAFT_BLOCKED",
        "source_sha256": FILES,
        "selector_families": result,
        "contexts": {
            "runtime_entry": {
                "one_step_call": 0,
                "outer_loop": 0,
                "family": "runtime",
                "n": 0,
            },
            "outer_and_sedimentation": {
                "one_step_call": 0,
                "outer_loop": "observed",
                "family": "observed",
                "n": "observed; never infer missing n",
            },
            "microphysics": {
                "one_step_call": "observed positive call counter",
                "outer_loop": "observed",
                "family": "microphysics unless source switches",
                "n": "observed",
            },
            "runtime_exit": {
                "one_step_call": "last observed one-step count, not reset by phase",
                "outer_loop": "last observed outer",
                "family": "runtime_exit",
                "n": 0,
            },
            "ordinal": "contiguous per full source key including phase/scope/level/role; not globally zero",
            "layer": "B=1 K=39 b=0 k=0..38 native=39-k",
            "column": "B=1 b=0 k/native absent",
            "scalar": "B/K/b/k/native absent",
        },
        "fixture_limits": "A4 CTest 5/5 is five synthetic tests, not five separately verified native columns; current synthetic value parity checks total v2 count and metadata, not per-selector census. A5 source is not executed. No selector required from an already archived stream without per-site evidence.",
        "absence": "No NOT_EVALUATED inferred from scalar optional or unentered loop; optional false control proves only its own observed value; vectorized unselected torch.where arms may have executed.",
        "graph": "Graph selectors and input/seed linkage unverified; no derivative certification",
        "scientific_status": "INCONCLUSIVE",
        "physical_unit_status": "INCONCLUSIVE",
    }


def census():
    snapshot = HERE / "producer_source_batch6_layers" / "a7_ledger_snapshot.json"
    need(
        hashlib.sha256(snapshot.read_bytes()).hexdigest() == SNAPSHOT_SHA,
        "A7 snapshot SHA",
    )
    with source_replay.reconstructed_tree() as (root, _):
        return census_from_source(root)


def validate_observed(records, manifest):
    # Structural sanity only; an empty list or incomplete observed schedule is not coverage.
    need(isinstance(records, list) and bool(records), "empty record stream")
    selectors = manifest["selector_families"]
    next_ordinal = {}
    for r in records:
        matches = [
            x
            for x in selectors
            if x["field"] == r["field"]
            and x["source_hook"] == r["source_hook"]
            and x["role"] == r["role"]
            and x["scope"] == r["scope"]
            and (
                x["stage"] == r["stage"]
                or (
                    x["stage"] == "{runtime_site_label}"
                    and r["stage"]
                    in ("nc_snap1_lambda", "nc_snap2_lambda", "nc_dsd_lambda")
                )
            )
        ]
        need(len(matches) == 1, "unknown source selector")
        need(r["dtype"] in matches[0]["allowed_dtype"], "dtype")
        need(
            isinstance(r["input_id"], str)
            and bool(r["input_id"])
            and r["mode"] in ("capture_on_value", "center_joint_graph"),
            "input/mode",
        )
        need(
            r["role"]
            in ("consumed_bool", "diagnostic_comparison", "operand", "control_scalar"),
            "unsupported absence or role",
        )
        scope = r["scope"]
        need(scope in ("layer", "column", "scalar"), "scope")
        if scope == "layer":
            need(
                (r["B"], r["K"], r["b"], r["native"]) == (1, 39, 0, 39 - r["k"])
                and 0 <= r["k"] < 39,
                "layer",
            )
        elif scope == "column":
            need(
                (r["B"], r["K"], r["b"], r["k"], r["native"]) == (1, -1, 0, -1, -1),
                "column",
            )
        else:
            need(
                (r["B"], r["K"], r["b"], r["k"], r["native"]) == (-1, -1, -1, -1, -1),
                "scalar",
            )
        family = r["family"]
        step = r["one_step_call"]
        n = r["n"]
        need(step >= 0 and n >= 0 and r["outer"] >= 0 and r["epoch"] > 0, "context")
        stage = r["stage"]
        if stage == "entry":
            need(
                family == "runtime" and step == 0 and r["outer"] == 0 and n == 0,
                "entry phase",
            )
        elif stage == "sedimentation_gate":
            required_family = {
                "active_main": "sedimentation_main",
                "mstep_main": "sedimentation_main",
                "active_ice": "sedimentation_ice",
                "mstep_ice": "sedimentation_ice",
            }.get(r["field"])
            need(
                required_family is not None
                and family == required_family
                and step == 0
                and n >= 1,
                "sedimentation selector phase",
            )
        elif stage == "sedimentation_schedule":
            need(
                family == "sedimentation_preslope" and step == 0 and n == 0,
                "schedule phase",
            )
        elif stage in {
            "nc_snap1",
            "nc_snap2",
            "nc_snap1_lambda",
            "nc_snap2_lambda",
            "nc_dsd_lambda",
            "cleanup_mask",
            "dsd_inner",
            "activation",
            "rate_cap",
            "a5_phase_mask",
            "a5_heat_mask",
            "satadj_inner",
        }:
            need(
                family == "microphysics" and step >= 1 and n == 0,
                "microphysics selector phase",
            )
        else:
            raise ValueError("unsupported selector phase pending source review")
        key = tuple(
            r[x]
            for x in (
                "input_id",
                "mode",
                "epoch",
                "runtime_call",
                "one_step_call",
                "outer",
                "family",
                "n",
                "scope",
                "B",
                "K",
                "b",
                "k",
                "stage",
                "field",
                "source_hook",
                "role",
            )
        )
        need(r["ordinal"] == next_ordinal.get(key, 0), "ordinal")
        next_ordinal[key] = r["ordinal"] + 1
    return {"status": "STRUCTURE_ONLY_INCOMPLETE", "records": len(records)}


if __name__ == "__main__":
    print(json.dumps(census(), indent=2, sort_keys=True))
