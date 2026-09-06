"""Meaningful acceptance checks for the bounded A4 cold profile probe."""
from __future__ import annotations

from kdm6.process_attribution import _run, cold_fixture
from scripts.diagnose_cold_profile_path import run_probe


def test_admissible_cold_number_paths_have_independent_profile_fd():
    result = run_probe()
    rows = {row["source"]: row for row in result["rows"]}
    for source in rows:
        assert rows[source]["positive_endpoints"]
        assert rows[source]["same_tapped_topology"]
        assert {"cold", "cold_limited", "state_update"}.issubset(rows[source]["stage_names"])
    for source in ("nc", "nr"):
        for field in ("T", "Q"):
            cell = rows[source]["profile"][field]
            assert cell["ad_nonzero"] and cell["fd_nonzero"]
            assert cell["fd_above_output_ulp"]
            assert cell["relative_error"] < 0.01


def test_cold_probe_records_zero_and_unverified_paths_explicitly():
    result = run_probe()
    rows = {row["source"]: row for row in result["rows"]}
    assert rows["ni"]["status"] == "zero_or_unresolved_selected_direction"
    assert all(not cell["ad_nonzero"] and not cell["fd_nonzero"]
               for cell in rows["ni"]["profile"].values())
    bg = rows["bg"]
    assert bg["status"] == "verified_selected_direction"
    assert bg["moment_pair_admissible"]
    for field in ("T", "Q", "HYDRO"):
        assert bg["profile"][field]["status"] == "verified"
    # Effective diameters are a separate quality/DSD map; this selected fixture
    # supplies no nonzero DEFF derivative, so the report must not imply one.
    assert all(not row["profile"]["DEFF"]["ad_nonzero"] and
               not row["profile"]["DEFF"]["fd_nonzero"]
               for row in result["rows"])
    assert result["contract"]["rttov_bt_or_cost"] == "unverified_no_live_rttov_invocation"


def test_named_controls_reach_postcap_rates_and_profile_cells():
    rows = {row["process"]: row for row in run_probe()["named_process_rows"]}
    for process in ("deposition", "riming"):
        row = rows[process]
        # The large deposition intervention crosses the ice budget cap; its
        # binding mask is therefore an observed topology change, while riming
        # remains smooth over all selected epsilons.
        assert row["same_tapped_topology"] is (process == "riming")
        if process == "deposition":
            assert not row["epsilon_results"]["0.1"]["same_tapped_topology"]
        assert row["nonzero_postcap_rate_derivatives"]
        assert {"T", "Q", "HYDRO"}.issubset(row["verified_fields"])
        expected_status = ("verified_selected_intervention" if process == "riming"
                           else "partial_rate_or_profile_unresolved")
        assert row["status"] == expected_status
        for epsilon_result in row["epsilon_results"].values():
            if process == "riming" or epsilon_result["epsilon"] != 0.1:
                assert epsilon_result["same_tapped_topology"]
            assert epsilon_result["rate_fd"]
    assert rows["deposition"]["interpretation"].startswith("total named-control intervention")
    assert "pidep" in rows["deposition"]["unresolved_postcap_rate_derivatives"]


def test_deposition_pidep_large_epsilon_crosses_ice_budget_cap():
    """The unresolved ε=.1 pidep FD crosses the existing ice conservation cap."""
    state, forcing = cold_fixture()
    # Keep the cap probe on the smooth off-knot profile fixture used by the
    # central-FD validation; density=500 is an intentional table-node probe.
    state = state._replace(bg=state.qg / 450.0)
    factors = {}
    binding = {}
    for alpha in (0.1, -0.1):
        _, trace, handle = _run(state, forcing, "deposition", alpha,
                                dt=20.0, graph=False)
        budget = trace.by_name("ice_mass_budget")[0]
        assert "pidep" in budget.metadata["rate_names"]
        raw = trace.by_name("cold")[-1]
        rates = raw.rates
        source = (rates.psaut - rates.pinud - rates.pidep + rates.praci
                  + rates.psaci + rates.pgaci - rates.pmulcs - rates.pmulrs
                  - rates.pmulcg - rates.pmulrg - rates.piacw)
        factors[alpha] = float((raw.state_in.qi / (source * raw.dtcld)).item())
        assert budget.operands["source"].item() == source.item() * raw.dtcld
        binding[alpha] = bool(budget.branch.item())
        handle.close()
    assert factors[0.1] < 1.0
    assert factors[-0.1] > 1.0
    assert binding == {0.1: True, -0.1: False}
