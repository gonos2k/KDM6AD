#!/usr/bin/env python3
"""Validate a source-only capture contract; no physics or host execution."""

import hashlib
import io
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent
CONTRACT_SHA = "f55dcc442868e83a6a7d1521e0ce9fd77dbc6f9ad9cacca27e8c18fd367ba2f7"
ARCHIVE_SHA = "663871cbb48154ea6c63a18991710e955bdec5d7ac5cda9d32bc0e0dd68c2347"
GROUPS = {
    "nc_zero",
    "pii_chain",
    "rate_cap_tie",
    "same_call_water",
    "sedimentation",
    "named_process",
    "heat_bg",
}
TRANSPORT = {
    "transport_qr",
    "transport_nr",
    "transport_qs",
    "transport_qg",
    "transport_brs",
    "transport_qi",
    "transport_ni",
}
ESSENTIAL = {
    "nc_entry_pre_post",
    "nc_snap1",
    "nc_snap2",
    "nc_update_reclass",
    "nc_cleanup_dsd",
    "pii_to_temperature",
    "cpm_xl",
    "water_saturation",
    "satadj_condensation",
    "activation_fraction_min",
    "rate_min_operands",
    "applied_activation_transfer",
    "water_before_after",
    "total_rain_fnresult",
    "water_closure_measure",
    "surface_flux_candidates",
    "nc_named_rate_terms",
    "water_named_rate_apply",
    "temperature_latent_terms",
    "phase_change_heat",
    "progb_bg_volume",
} | TRANSPORT
MASKS = {
    "entry_nc_floor",
    "entry_nccn_bounds",
    "snap1_per_cell_gate",
    "snap2_per_cell_gate",
    "lambda_active",
    "lambda_bounds",
    "dsd_ncmin",
    "dsd_ncmax",
    "cleanup_qc",
    "temperature_floor",
    "water_es_cap",
    "satadj_paths",
    "safe_pow_floor",
    "ncact_preclamp",
    "nccn_cap_clamp",
    "main_transport_gate",
    "ice_transport_gate",
    "warm_cold_gate",
    "progb_density_gate",
}


def need(ok, why):
    if not ok:
        raise ValueError(why)


def validate(contract, archive_raw):
    need(
        contract["schema"] == "kdm6.native_host_concrete_field_contract.v1"
        and contract["status"] == "SPEC_ONLY"
        and contract["scientific_status"]
        == contract["physical_unit_status"]
        == "INCONCLUSIVE",
        "contract status",
    )
    need(
        hashlib.sha256(archive_raw).hexdigest()
        == ARCHIVE_SHA
        == contract["source_archive_sha256"],
        "source archive SHA",
    )
    with zipfile.ZipFile(io.BytesIO(archive_raw)) as z:
        names = z.namelist()
        need(
            len(names) == len(set(names)) == 10
            and set(names) == set(contract["source_sha256"]),
            "source inventory",
        )
        sources = {}
        for name in names:
            raw = z.read(name)
            need(
                hashlib.sha256(raw).hexdigest() == contract["source_sha256"][name],
                "source SHA " + name,
            )
            need(
                name.startswith("libtorch/")
                and not any(x in raw for x in (b"/Users/", b"/private/", b"/opt/")),
                "public source/path hygiene",
            )
            sources[name] = raw.decode().splitlines()

    def source(ref):
        name, line, anchor = ref["file"], ref["line"], ref["anchor"]
        need(
            name in sources
            and type(line) is int
            and 1 <= line <= len(sources[name])
            and anchor in sources[name][line - 1],
            "source location " + str(name) + ":" + str(line),
        )

    need(set(contract["groups"]) == GROUPS, "seven groups")
    fields = [f for group in contract["groups"].values() for f in group]
    need(
        len(fields) == 28
        and len({f["id"] for f in fields}) == 28
        and {f["id"] for f in fields} == ESSENTIAL,
        "measurement inventory",
    )
    for field in fields:
        need(
            field["implementation_status"] == "BLOCKED"
            and field["blocked_reason"]
            and field["inactive_rule"]
            and field["branch_or_boundary"]
            and field["expression_or_tensor"],
            "blocked implementation/branch contract",
        )
        need(
            set(field["required_record_kinds"])
            in ({"value", "live_tangent"}, {"value", "live_tangent", "mask"})
            and field["source_locations"],
            "record kinds/source",
        )
        for ref in field["source_locations"]:
            source(ref)
    sediment = {x["id"]: x for x in contract["groups"]["sedimentation"]}
    for key in TRANSPORT:
        field = sediment[key]
        need(
            "k=0" in field["inactive_rule"]
            and "not applied" in field["blocked_reason"]
            and len(field["source_locations"]) == 6,
            "transport top/inactive/candidate contract",
        )
    masks = contract["proposed_new_masks"]
    need(
        len(masks) == len(MASKS) and {x["id"] for x in masks} == MASKS,
        "proposed mask inventory",
    )
    for mask in masks:
        need(
            mask["group"] in GROUPS
            and mask["implementation_status"] == "BLOCKED"
            and mask["adapter_compatibility"]
            == "NOT_SUPPORTED_BY_CURRENT_BASELINE_ADAPTER"
            and mask["required_comparison"],
            "new mask status",
        )
        source(mask["source"])
    identity = contract["identity"]
    need(
        {
            "input_id",
            "mode",
            "runtime_call",
            "one_step_call",
            "outer_loop",
            "substep_family",
            "substep_n",
            "b_zero",
            "k_zero",
            "native_level_bottom_first",
            "stage",
            "field",
            "record_kind",
            "derivative_mode",
            "direction_id",
            "seed_sha256",
            "cotangent_id",
            "event_ordinal",
        }
        <= set(identity["required"]),
        "record identity",
    )
    need(
        "39-k_zero" in identity["vertical"]
        and "column" in identity["surface"]
        and "no detach" in identity["tangent"],
        "identity/liveness scope",
    )
    return {
        "status": "SPEC_ONLY",
        "groups": len(GROUPS),
        "measurements": len(fields),
        "proposed_masks": len(masks),
        "new_measurements": "BLOCKED",
        "scientific_status": "INCONCLUSIVE",
        "physical_unit_status": "INCONCLUSIVE",
    }


def main():
    raw = (HERE / "field_contract.json").read_bytes()
    need(hashlib.sha256(raw).hexdigest() == CONTRACT_SHA, "contract SHA")
    print(
        json.dumps(
            validate(
                json.loads(raw), (HERE / "field_contract_sources.zip").read_bytes()
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
