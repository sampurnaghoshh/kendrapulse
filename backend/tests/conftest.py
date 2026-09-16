"""Shared fixtures. The hand built scenarios here exist so tests can state one fact at a
time; the generated demo scenario is one connected component and cannot isolate anything."""

import pytest

from sim.generator import Loan, Member, Scenario, _build_graph, _layout
from sim.params import DEFAULT


def make_member(
    idx,
    kendra_id,
    income_source,
    lender,
    weekly_income=4000.0,
    income_trend=0.0,
    buffer_weeks=1.5,
    due_share=0.30,
    household_size=4,
):
    """One member with every knob explicit, so a test can say exactly what it needs."""
    due = weekly_income * due_share
    return Member(
        id=f"s{idx:03d}",
        name=f"Test Member {idx}",
        kendra_id=kendra_id,
        weekly_income=weekly_income,
        income_source=income_source,
        seasonality=tuple([1.0] * DEFAULT.weeks_per_year),
        income_trend=income_trend,
        savings_buffer=weekly_income * buffer_weeks,
        household_size=household_size,
        loans=(Loan(lender, due, due * 40),),
    )


def build_scenario(members, seed=0):
    members = tuple(members)
    return Scenario(
        members=members,
        graph=_build_graph(members),
        layout=_layout(members, len({m.kendra_id for m in members})),
        index_of={m.id: i for i, m in enumerate(members)},
        seed=seed,
    )


@pytest.fixture
def isolated_scenario():
    """Two kendras that share nothing: different income source, different lender.

    Every transmission path in the model runs through a kendra (guarantee), an income
    source (correlated shock) or a lender (top up freeze). Cutting all three leaves two
    genuinely separate connected components, which is the only setting where "this member
    could not possibly have been affected" is a claim the graph actually supports.
    """
    members = [make_member(i, "kA", "tailoring", "Sahyog") for i in range(3)]
    members += [make_member(i, "kB", "dairy", "Uday Credit") for i in range(3, 6)]
    return build_scenario(members)
