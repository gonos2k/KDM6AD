#!/usr/bin/env python3
"""Check source-site draft integrity, not instrumentation readiness."""

import hashlib
import io
import json
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / "native_host_preflight_2026-11-12"
CATALOG_SHA = "05d2291d1060ddee582c443d719035b8e4a84a1c8293c4385ed5208e60aa331d"
CONTRACT_SHA = "f55dcc442868e83a6a7d1521e0ce9fd77dbc6f9ad9cacca27e8c18fd367ba2f7"
ARCHIVE_SHA = "663871cbb48154ea6c63a18991710e955bdec5d7ac5cda9d32bc0e0dd68c2347"
SPECIES = ("qr", "nr", "qs", "qg", "brs", "qi", "ni")


def need(ok, why):
    if not ok:
        raise ValueError(why)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def validate(d, parent, archive):
    canonical_raw = (HERE / "atomic_catalog_draft.json").read_bytes()
    need(sha(canonical_raw) == CATALOG_SHA, "canonical catalog SHA")
    need(
        d["schema"] == "kdm6.native_host_atomic_capture_catalog.draft.v1"
        and d["status"] == "DRAFT_BLOCKED"
        and d["scientific_status"] == d["physical_unit_status"] == "INCONCLUSIVE",
        "draft status",
    )
    need(
        d["parent_contract_sha256"] == CONTRACT_SHA
        and d["source_archive_sha256"] == ARCHIVE_SHA
        and sha(archive) == ARCHIVE_SHA,
        "parent/source provenance",
    )
    need(
        d["source_sha256"] == parent["source_sha256"]
        and d["identity"] == parent["identity"],
        "source/identity contract",
    )
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        names = z.namelist()
        need(
            len(names) == len(set(names)) == 10
            and set(names) == set(d["source_sha256"]),
            "source archive inventory",
        )
        sources = {}
        for name in names:
            raw = z.read(name)
            need(
                sha(raw) == d["source_sha256"][name] and name.startswith("libtorch/"),
                "source SHA",
            )
            need(
                not any(x in raw for x in (b"/Users/", b"/private/", b"/opt/")),
                "private path in source",
            )
            sources[name] = raw.decode().splitlines()

    def ref(item, include_exact=False):
        loc = item["source_site"]
        file, line, anchor = loc["file"], loc["line"], loc["anchor"]
        need(
            file in sources
            and type(line) is int
            and 1 <= line <= len(sources[file])
            and anchor in sources[file][line - 1],
            "source site",
        )
        if include_exact:
            need(
                item["source_line_exact"] == sources[file][line - 1].strip(),
                "exact source line",
            )

    groups = d["groups"]
    atoms = d["atoms"]
    masks = d["proposed_masks"]
    required_groups = {x["id"] for fields in parent["groups"].values() for x in fields}
    need(
        len(groups) == 28
        and len({g["group_id"] for g in groups}) == 28
        and {g["group_id"] for g in groups} == required_groups,
        "28-group coverage",
    )
    need(
        len(atoms) == 191 and len({a["atomic_id"] for a in atoms}) == len(atoms),
        "atomic inventory",
    )
    byid = {a["atomic_id"]: a for a in atoms}
    referenced = []
    for group in groups:
        need(
            group["status"] == "BLOCKED"
            and group["blocked_reason"]
            and group["atom_ids"],
            "group blocker/atoms",
        )
        for aid in group["atom_ids"]:
            need(
                aid in byid and byid[aid]["requirement_id"] == group["group_id"],
                "atom group linkage",
            )
            referenced.append(aid)
    need(
        len(referenced) == len(set(referenced)) == len(atoms),
        "all atoms linked exactly once",
    )
    for atom in atoms:
        ref(atom, True)
        c = atom["consumer"]["location"]
        ref({"source_site": c})
        need(
            atom["binding_status"].startswith("UNRESOLVED")
            and atom["blocked_reason"]
            and atom["inactive_rule"]
            and atom["dtype"]
            and atom["shape"]
            and atom["identity"]
            and atom["vertical"],
            "atomic blocker and identity",
        )
        need(
            atom["record_availability"]["value"] == "BLOCKED_NOT_EMITTED"
            and atom["record_availability"]["live_tangent"] == "BLOCKED_NOT_EMITTED",
            "do not assert live capture",
        )
    expected_masks = {"mask." + x["id"] for x in parent["proposed_new_masks"]}
    need(
        len(masks) == 19
        and len({m["atomic_id"] for m in masks}) == 19
        and {m["atomic_id"] for m in masks} == expected_masks,
        "mask inventory",
    )
    for mask in masks:
        ref(mask, True)
        need(
            mask["binding_status"] == "UNRESOLVED_NEW_MASK_NOT_EMITTED"
            and mask["value_availability"] == "BLOCKED_NOT_EMITTED"
            and mask["adapter_compatibility"]
            == "NOT_SUPPORTED_BY_CURRENT_BASELINE_ADAPTER"
            and mask["inactive_rule"],
            "mask blocked",
        )
    for name in (
        "rate_min_operands.operand.cap_inline",
        "rate_min_operands.operand.min_before_sw",
        "activation_fraction_min.operand.pow_inline",
        "activation_fraction_min.operand.one_inline",
    ):
        need(
            byid[name]["binding_status"] == "UNRESOLVED_EXACT_NODE_MATERIALIZATION",
            "inline operand status",
        )
    for species in SPECIES:
        for kind in ("realized_departure", "realized_arrival", "actual_bottom_export"):
            atom = byid[f"transport_{species}.unresolved.{kind}"]
            need(
                atom["binding_status"] == "UNRESOLVED_APPLIED_ATTRIBUTION"
                and atom["dtype"].startswith("UNRESOLVED"),
                "applied transport attribution",
            )
        for phase in ("top", "k"):
            atom = byid[f"transport_{species}.supplement.fall_{phase}"]
            need(
                "before clamp" in atom["blocked_reason"]
                and "candidate" in atom["blocked_reason"],
                "candidate fall warning",
            )
    for field in ("qv", "qc", "qr", "qi", "qs", "qg"):
        need(
            "water_before_after.supplement.entry_" + field in byid
            and "water_before_after.supplement.exit_" + field in byid,
            "individual water coordinate",
        )
    for term in (
        "nraut",
        "nccol",
        "nracw",
        "niacw",
        "naacw_first",
        "naacw_second",
        "ninuc",
        "nfrzdtc",
        "pimlt_ni",
    ):
        need(
            "nc_named_rate_terms.supplement." + term in byid,
            "individual NC rate/amount operand",
        )
    for name in ("brs_acc_entry", "brs_melt", "brs_cold", "brs_warm", "brs_clamp"):
        need("progb_bg_volume.supplement." + name in byid, "BG source-order nodes")
    for name in (
        "dep_sum",
        "frz_sum",
        "cold_heat",
        "vap_sum",
        "warm_heat",
        "selected_heat",
        "temperature_final",
    ):
        need("phase_change_heat.supplement." + name in byid, "heat source nodes")
    need(d == json.loads(canonical_raw), "canonical catalog mismatch")
    return {
        "status": "DRAFT_BLOCKED",
        "groups": len(groups),
        "atomic_sites_and_blockers": len(atoms),
        "new_masks": len(masks),
        "capture_emitted": False,
        "scientific_status": "INCONCLUSIVE",
        "physical_unit_status": "INCONCLUSIVE",
    }


def main():
    raw = (HERE / "atomic_catalog_draft.json").read_bytes()
    parent = (PARENT / "field_contract.json").read_bytes()
    need(sha(raw) == CATALOG_SHA and sha(parent) == CONTRACT_SHA, "catalog/parent SHA")
    print(
        json.dumps(
            validate(
                json.loads(raw),
                json.loads(parent),
                (PARENT / "field_contract_sources.zip").read_bytes(),
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
