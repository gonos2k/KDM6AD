from scripts.diagnose_melt_process_path import run_probe


def test_riming_reaches_d5_graupel_melt_with_independent_fd():
    result = run_probe()
    assert result["status"] == "verified_total_riming_to_d5_path"
    assert result["source_rate"] == "riming ProcessControls group"
    assert result["raw_controlled_paacw_adj_example_rate"] != 0.0
    assert result["d5_baseline_rate"] != 0.0
    assert result["alpha_vjp_pgeml"] != 0.0
    assert result["alpha_forward_jvp_pgeml"] != 0.0
    assert result["forward_jvp_primal_pgeml"] == result["d5_baseline_rate"]
    assert result["forward_vjp_relative_error"] < 1.0e-12
    assert all(row["same_tapped_topology"] and row["relative_error"] < 0.01
               for row in result["eps"])
