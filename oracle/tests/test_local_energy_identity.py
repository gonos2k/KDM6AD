from scripts.diagnose_local_energy_identity import run_probe


def test_captured_operands_support_local_state_update_identity():
    result = run_probe()
    assert result["status"] == "verified_local_state_update_identity"
    assert result["residual_max_abs_j_kg"] < 1.0e-8
    assert result["satadj_identity_max_abs_j_kg"] < 1.0e-8
    assert set(result["operands"]) == {"cpm", "xl", "supcol"}
    assert result["ad_operands_requires_grad"] == {
        "cpm": True, "xl": True, "supcol": True,
    }
    qv = result["qv_direction"]
    assert qv["sensible_ad_j_kg"] != 0.0
    assert qv["latent_and_amount_ad_j_kg"] != 0.0
    assert qv["satadj_latent_ad_j_kg"] != 0.0
    assert qv["satadj_formula_ad_j_kg"] != 0.0
    assert qv["satadj_pcond_ad_j_kg"] != 0.0
    assert qv["satadj_pcond_status"] in {"insufficient_resolution", "unresolved_numeric", "verified"}
    for fd in qv["fd"]:
        assert fd["same_tapped_topology"]
        assert fd["sensible_relative_error"] < 1.0e-8
        assert fd["latent_and_amount_relative_error"] < 1.0e-8
        assert fd["satadj_identity_endpoint_max_abs_j_kg"] < 1.0e-8
        assert fd["satadj_pcond_status"] in {"insufficient_resolution", "unresolved_numeric", "verified"}
    resolved = result["resolved_direction"]
    assert resolved["status"] == "verified"
    for fd in resolved["fd"]:
        assert fd["ad_j_kg"] != 0.0 and fd["fd_j_kg"] != 0.0
        assert fd["actual_ad_j_kg"] != 0.0 and fd["actual_fd_j_kg"] != 0.0
        assert fd["same_tapped_topology"]
        assert fd["relative_error"] < 1.0e-8
        assert fd["actual_relative_error"] < 1.0e-8
        assert fd["identity_endpoint_max_abs_j_kg"] < 1.0e-8
    assert "satadj pcond ledger across all subcycles/full column" in result["missing_full_budget"]
