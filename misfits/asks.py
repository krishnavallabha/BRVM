"""Ask phase (owner: Rishi).

Day 1: Priority-ranked hard-constraint clarification.
       Ask for members whose hard constraints are most incomplete first (sorted by number
       of not_asked hard fields, descending). Skips members with any declined hard field
       because those cannot be recovered and asking only partially helps.

Day 2: Soft-field clarification with idle budget (soft_asks: True).
       After spending the constraint budget, use any remaining budget (up to 12 units/day)
       to ask the most-valuable soft fields for members whose hard constraints are already
       fully resolved. Fields are asked in value order:
         relationship_goal   (+3.0 / -1.5 weight in pair_quality)
         relationship_pace   (+1.5 / -0.75)
         lifestyle           (+0.5 / -0.25)
         conversations       (+0.4 / -0.2)
         emotional_availability, space_for_relationship, relocate  (tie-breaking / completeness)
       Within each field, members with the most total missing soft fields are asked first
       (they benefit most from clarification).
"""
from kit import HARD, SOFT

# Soft fields in decreasing value order (matches pair_quality weights in match.py).
SOFT_PRIORITY = [
    'relationship_goal',       # strongest weight in pair_quality
    'relationship_pace',
    'lifestyle',
    'conversations',
    'emotional_availability',
    'space_for_relationship',
    'relocate',
]


def _count_missing_hard(m):
    return sum(1 for k in HARD if m['field_status'][k] == 'not_asked')


def _count_missing_soft(m):
    return sum(1 for k in SOFT if m['field_status'][k] == 'not_asked')


def choose(state, memory, config):
    """Return (asks, memory). asks = [{'member_id': str, 'field': 'constraints' | <soft field>}]"""
    if config.get('ask_order') == 'none':
        return [], memory

    members = [m for m in state['members'] if m['available']]
    budget = state['ask_budget_remaining']
    asks = []

    # ── Day 1: Priority-ranked hard-constraint asks ────────────────────────────
    # Candidates: available members who have at least one not_asked hard field and
    # no declined hard field (a declined hard field blocks us from using constraints
    # bundle for them effectively, since the declined answer stays unknown).
    hard_candidates = [
        m for m in members
        if _count_missing_hard(m) > 0
        and not any(m['field_status'][k] == 'declined' for k in HARD)
    ]
    # Prioritise members with the most missing hard fields (most to gain from one ask).
    hard_candidates.sort(key=_count_missing_hard, reverse=True)

    for m in hard_candidates:
        if budget < 3:
            break
        asks.append({'member_id': m['member_id'], 'field': 'constraints'})
        budget -= 3

    # ── Day 2: Soft-field asks with idle budget ────────────────────────────────
    if not config.get('soft_asks') or budget <= 0:
        return asks, memory

    # Only ask soft fields for members whose hard constraints are fully resolved
    # (either observed or declined). Members still missing hard fields are blocked
    # regardless, so spending the 1-unit budget on their soft fields rarely helps.
    soft_candidates = [
        m for m in members
        if all(m['field_status'][k] in ('observed', 'declined') for k in HARD)
    ]
    # Within each field, prefer members with more total missing soft fields first
    # (they stand to benefit most from further clarification).
    soft_candidates.sort(key=_count_missing_soft, reverse=True)

    # Ask field by field in priority order. For each field, ask all candidates who
    # have not yet answered it, until the budget runs out.
    for field in SOFT_PRIORITY:
        if budget <= 0:
            break
        for m in soft_candidates:
            if budget <= 0:
                break
            if m['field_status'][field] == 'not_asked':
                asks.append({'member_id': m['member_id'], 'field': field})
                budget -= 1

    return asks, memory
