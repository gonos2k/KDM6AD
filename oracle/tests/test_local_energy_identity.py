from scripts.diagnose_local_energy_identity import run_probe


def test_captured_operands_support_local_state_update_identity():
    result = run_probe()
    assert result["status"] == "verified_local_state_update_identity"
    assert result["residual_max_abs_j_kg"] < 1.0e-8
    assert set(result["operands"]) == {"cpm", "xl", "supcol"}
    assert result["ad_operands_requires_grad"] == {
        "cpm": True, "xl": True, "supcol": True,
    }
    qv = result["qv_direction"]
    assert qv["sensible_ad_j_kg"] != 0.0
    assert qv["latent_and_amount_ad_j_kg"] != 0.0
    for fd in qv["fd"]:
        assert fd["same_tapped_topology"]
        assert fd["sensible_relative_error"] < 1.0e-8
        assert fd["latent_and_amount_relative_error"] < 1.0e-8
    assert "satadj pcond latent ledger" in result["missing_full_budget"]
