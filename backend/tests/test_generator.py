"""The generator must produce borrowers a regulator would recognise.

These caps are the part of the model we can cite rather than defend, so they are checked
at the default demo size and again at branch scale.
"""

import networkx as nx
import pytest

from sim.generator import generate_scenario
from sim.params import DEFAULT


@pytest.fixture(scope="module")
def demo():
    return generate_scenario()


def test_demo_shape(demo):
    assert demo.n_members == 25
    assert len(demo.kendras()) == 5
    assert all(len(ids) == 5 for ids in demo.kendras().values())


def test_mfin_caps(demo):
    """MFIN industry guardrails, Nov 2024: at most 3 lenders and Rs 2,00,000 per borrower."""
    for m in demo.members:
        assert len(m.lenders) <= DEFAULT.max_lenders_per_borrower, m.id
        assert m.total_outstanding <= DEFAULT.max_total_exposure_rs + 1e-6, m.id


def test_rbi_installment_cap(demo):
    """RBI Microfinance Framework 2022: repayment obligation at most 50% of income."""
    for m in demo.members:
        assert m.weekly_due <= DEFAULT.max_installment_share * m.weekly_income + 1e-9, m.id


def test_installments_sit_below_the_cap_not_at_it(demo):
    """Underwriting to the ceiling would leave everyone permanently fragile, and then no
    label we produce later would mean anything. Members belong in the target band."""
    low, high = DEFAULT.installment_share_target
    for m in demo.members:
        assert low - 1e-9 <= m.weekly_due / m.weekly_income <= high + 1e-9, m.id


def test_seasonality_length(demo):
    for m in demo.members:
        assert len(m.seasonality) == DEFAULT.weeks_per_year


def test_seasonality_is_a_property_of_the_source(demo):
    """Two members on the same source face the same season; it is a fact about the crop,
    not about the person."""
    by_source = {}
    for m in demo.members:
        by_source.setdefault(m.income_source, []).append(m.seasonality)
    for seasonalities in by_source.values():
        assert all(s == seasonalities[0] for s in seasonalities)


def test_all_three_edge_types_present(demo):
    types = {d["type"] for _, _, d in demo.graph.edges(data=True)}
    assert types == {"guarantee", "shared_income", "shared_lender"}


def test_guarantee_edges_are_complete_within_a_kendra(demo):
    for ids in demo.kendras().values():
        for member_id in ids:
            assert set(demo.guarantee_peers(member_id)) == set(ids) - {member_id}


def test_generation_is_seeded(demo):
    again = generate_scenario()
    assert [m.id for m in again.members] == [m.id for m in demo.members]
    assert [m.name for m in again.members] == [m.name for m in demo.members]
    assert [m.weekly_income for m in again.members] == [m.weekly_income for m in demo.members]
    assert generate_scenario(seed=7).members != demo.members


def test_scales_to_a_branch():
    """40 kendras is the branch sized case the contract asks the generator to reach."""
    big = generate_scenario(n_kendras=40)
    assert big.n_members == 200
    assert len({m.name for m in big.members}) == 200  # names stay unique at scale
    for m in big.members:
        assert len(m.lenders) <= DEFAULT.max_lenders_per_borrower
        assert m.total_outstanding <= DEFAULT.max_total_exposure_rs + 1e-6
        assert m.weekly_due <= DEFAULT.max_installment_share * m.weekly_income + 1e-9
    assert {d["type"] for _, _, d in big.graph.edges(data=True)} == {
        "guarantee", "shared_income", "shared_lender",
    }


def test_layout_covers_every_member_uniquely(demo):
    """Every panel reads coordinates from here, so a missing or duplicated point would
    show up as a member silently jumping between the two Two Worlds views."""
    assert set(demo.layout) == {m.id for m in demo.members}
    assert len(set(demo.layout.values())) == demo.n_members


def test_isolated_scenario_really_is_two_components(isolated_scenario):
    """Guards the fixture the CRN isolation test depends on."""
    assert nx.number_connected_components(isolated_scenario.graph) == 2
