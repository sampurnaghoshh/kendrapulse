"""Every tunable number in KendraPulse, with its source or its reason.

Two rules govern this file:

1. Nothing is a module-level mutable global. `Params` is a frozen dataclass so Phase 3
   stability can build a perturbed copy with `dataclasses.replace(...)` without any run
   mutating the numbers another run is reading. `sim/` stays pure.
2. Every field carries a SOURCE (a regulation or published guardrail we can cite to a
   judge) or a REASON (a modelling choice we picked, and why). If a number appears
   anywhere else in the codebase without living here first, that is a bug.
"""

from dataclasses import dataclass, field

# --------------------------------------------------------------------------------------
# Draw channels. Indices into the third axis of draws[member, week, channel].
#
# These are append-only. A tuned demo seed depends on which channel sits at which index,
# so inserting a channel in the middle would silently reshuffle everybody's dice and
# change the story. New channels take CH_RESERVE, or a new index after it.
# --------------------------------------------------------------------------------------
CH_COVER = 0  # will this peer step in for a neighbour's shortfall this week
CH_COVER_SIZE = 1  # if she does, what fraction of her capacity does she commit
CH_INCOME_NOISE = 2  # idiosyncratic weekly wobble in informal income
CH_LENDER = 3  # does a paused lender's top up freeze bite this member this week
CH_EXPENSE = 4  # household expense wobble
CH_RESERVE = 5  # unused; keeps indices stable when a channel is added later
N_CHANNELS = 6


@dataclass(frozen=True)
class Params:
    """All simulation constants. Frozen: perturb with dataclasses.replace, never in place."""

    # ----------------------------------------------------------------------------------
    # A. Regulatory calibration. HARD limits, enforced by the generator and asserted in
    #    tests. These are the numbers we can defend with a citation, so stability never
    #    perturbs them: a regulator's cap is not a dice roll.
    # ----------------------------------------------------------------------------------
    max_lenders_per_borrower: int = 3  # SOURCE: MFIN industry guardrails, Nov 2024
    max_total_exposure_rs: float = 200_000.0  # SOURCE: MFIN industry guardrails, Nov 2024
    # SOURCE: RBI Regulatory Framework for Microfinance Loans, 2022. Repayment obligation
    # capped at 50% of monthly household income. This is a CEILING we must never cross.
    max_installment_share: float = 0.50
    # REASON: where the generator actually places members. Underwriting to the ceiling
    # would leave a no shock baseline permanently fragile, and then every label we
    # produce later is just noise about people who were already drowning.
    installment_share_target: tuple[float, float] = (0.22, 0.35)

    # ----------------------------------------------------------------------------------
    # B. Horizon and stress thresholds
    # ----------------------------------------------------------------------------------
    horizon_weeks: int = 12  # REASON: build contract; one quarter of weekly collections
    weeks_per_year: int = 52  # REASON: length of the seasonality array
    amber: float = 0.35  # REASON: flagged. Roughly a third of a week's due unmet, or a
    # buffer down to two thirds, or a milder mix of both
    red: float = 0.65  # REASON: sustained shortfall with the cushion largely gone

    # ----------------------------------------------------------------------------------
    # C. Stress score weights
    # ----------------------------------------------------------------------------------
    w_shortfall: float = 0.60  # REASON: the missed payment is what a field officer sees
    w_buffer: float = 0.40  # REASON: a member who pays in full by burning her savings is
    # not fine, she is becoming fragile. Without this term the guarantee channel would be
    # invisible until it was already a default.
    stress_memory: float = 0.50  # REASON: distress does not reset every Monday. Last
    # week's stress decays by half rather than vanishing.

    # ----------------------------------------------------------------------------------
    # D. Household cash mechanics
    # ----------------------------------------------------------------------------------
    expense_floor_share: float = 0.52  # REASON: share of household income that is
    # non negotiable consumption and never available for repayment. Calibrated, not
    # guessed: at 0.35 every household carried so much slack that a 70% income loss for
    # six weeks never once reached amber, which made the whole model inert.
    expense_per_extra_member: float = 0.02  # REASON: each household member beyond
    # `expense_baseline_household` adds this much of income to the consumption floor
    expense_baseline_household: int = 4  # REASON: household size the floor is quoted at
    buffer_draw_cap: float = 0.50  # REASON: a household will not empty its entire
    # savings into one week's installment; it holds something back
    buffer_topup_rate: float = 0.05  # REASON: share of any surplus that becomes savings
    income_noise_halfwidth: float = 0.08  # REASON: informal income varies week to week.
    # Uniform on [1 - h, 1 + h], not a normal draw, because the draws array is uniform
    # and a half width is easier to explain to a judge than a standard deviation.
    expense_noise_halfwidth: float = 0.10  # REASON: as above, for consumption

    # ----------------------------------------------------------------------------------
    # E. Guarantee channel: the joint liability peers inside a kendra
    # ----------------------------------------------------------------------------------
    p_cover: float = 0.55  # REASON: a peer steps in more often than not, but joint
    # liability in practice is social pressure, not an automatic guarantee
    cover_capacity_share: float = 0.30  # REASON: the most of her own money a peer will
    # commit to somebody else in one week, as a share of CASH ON HAND PLUS BUFFER. It
    # spans both pockets because cover is settled at the meeting out of the cash she
    # brought for her own installment first, and only then out of savings.
    cover_min_peer_stress_block: float = 0.35  # REASON: a peer who is already flagged
    # does not rescue anyone. Numerically equal to `amber` today, but kept separate so
    # stability can perturb the two independently.

    # ----------------------------------------------------------------------------------
    # F. Shared lender channel
    # ----------------------------------------------------------------------------------
    lender_pause_threshold: float = 0.30  # REASON: share of a kendra's due left unpaid
    # at which a lender stops writing new top ups against that group
    lender_pause_buffer_hit: float = 0.25  # REASON: buffer lost by a linked member in
    # ANOTHER kendra when her lender freezes. This is the cross kendra contagion path.
    p_lender_pause_bites: float = 0.60  # REASON: a freeze only hurts the members who were
    # actually relying on a top up that week, so it does not hit every linked member

    # ----------------------------------------------------------------------------------
    # G. Shock defaults: type -> (severity, duration_weeks).
    #    Severity is the fraction of income lost, except festival_spend which is an
    #    expense side shock (see `expense_side_shocks`).
    #    A dataclass field holding a dict needs default_factory; a bare dict default
    #    raises at class definition time.
    #    REASON for the values: chosen so the seeded demo separates the three labels
    #    cleanly. They are scenario INPUTS. Tuning them is allowed; special casing a code
    #    path for the demo is not.
    # ----------------------------------------------------------------------------------
    shock_defaults: dict[str, tuple[float, int]] = field(
        default_factory=lambda: {
            "health": (0.65, 4),  # earner cannot work, plus a medical bill
            "crop_loss": (0.70, 6),  # one harvest gone, recovery takes a season
            "job_loss": (0.80, 4),  # near total income loss, shortest to re-enter
            "festival_spend": (0.30, 2),  # expense side: a lump obligation, not lost income
            "weak_monsoon": (0.50, 8),  # hits everyone on an income source together
        }
    )
    # Shocks that raise expenses instead of (or as well as) cutting income.
    expense_side_shocks: tuple[str, ...] = ("festival_spend",)
    health_expense_share: float = 0.25  # REASON: a health shock cuts income AND adds a
    # medical bill worth this share of baseline income each week it lasts

    # ----------------------------------------------------------------------------------
    # H. Declared now, consumed in Phase 3. They live here so params.py stays the single
    #    home for tunables and Phase 3 does not have to invent a second one.
    # ----------------------------------------------------------------------------------
    carry_cost_rate: float = 0.0035  # REASON: weekly cost to the lender of deferred
    # principal, roughly an 18% annual cost of funds
    scheme_delay_weeks: int = 3  # REASON: a government scheme linkage does not pay out
    # the week you apply. Without this delay it would dominate the smallest fix ranking
    # for free, which would be a dishonest demo.
    r_window_weeks: int = 4  # REASON: weeks to look ahead when counting onward flags

    # ----------------------------------------------------------------------------------
    # I. Generator shape. Not physics, but tunable, so it belongs here.
    # ----------------------------------------------------------------------------------
    buffer_weeks_range: tuple[float, float] = (0.8, 2.0)  # REASON: savings expressed in
    # weeks of income. Liquid savings in this segment are thin, and the number has to be
    # thin for a shock to bite inside a 12 week horizon at all: at 1.5 to 4.0 weeks a
    # severe crop loss merely dented the cushion and nobody ever flagged.
    seasonality_amplitude: float = 0.15  # REASON: lean season dip for agricultural
    # income sources; non agricultural sources are flat
    trend_range: tuple[float, float] = (-0.002, 0.002)  # REASON: ordinary weekly drift
    declining_trend: float = -0.030  # REASON: applied to the few members deliberately
    # given a slipping income, so Phase 2 has genuine INDEPENDENT cases to find
    declining_share: float = 0.10  # REASON: share of members given that slipping trend


DEFAULT = Params()


# Scalar fields Phase 3 stability multiplies by U(0.7, 1.3).
#
# Deliberately EXCLUDED: everything in group A (regulatory caps are not uncertain
# quantities), horizon_weeks and weeks_per_year (array shape, not a value), and the
# generator shape in group I (perturbing the scenario itself would change who the
# borrowers are, not how confident we are about the physics).
#
# Shock severities live inside a dict, so stability perturbs those separately.
PERTURBABLE: tuple[str, ...] = (
    "amber",
    "red",
    "w_shortfall",
    "w_buffer",
    "stress_memory",
    "expense_floor_share",
    "buffer_draw_cap",
    "buffer_topup_rate",
    "income_noise_halfwidth",
    "expense_noise_halfwidth",
    "p_cover",
    "cover_capacity_share",
    "cover_min_peer_stress_block",
    "lender_pause_threshold",
    "lender_pause_buffer_hit",
    "p_lender_pause_bites",
    "health_expense_share",
)
