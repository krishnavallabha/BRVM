"""Ask phase (owner: Rishi).

Ask-order modes  (config key 'ask_order'):
  'none'         – no asks (kit no_asks baseline).
  'greedy'       – kit baseline_asks exactly: first budget // 3 eligible members,
                   no reordering.  Reproducible with kit greedy.
  'missing_hard' – Day 1: sort by most not_asked hard fields (most blocked first).
  'partners'     – Day 3 default: sort by likely partner count (members not yet
                   infeasible) plus RECENT_BONUS for arrivals within RECENT_DAYS days,
                   ties broken by member_id.

Soft-ask modes  (config key 'soft_asks'):
  False / absent   – no soft asks.
  'agreed'         – Day 3 default: relationship_goal then relationship_pace, only for
                     members whose hard constraints are fully resolved AND who currently
                     have >= MIN_FEASIBLE feasible partners.  Ask cost ~+12/episode.
  'resolved' / True – Day 2 broad: all soft fields in priority order for any member
                     whose hard constraints are fully resolved.  ~3x higher ask cost.
"""
from kit import HARD, SOFT, baseline_asks, eligibility

RECENT_BONUS = 10     # score bonus for members who arrived recently
RECENT_DAYS  = 3      # "recently" window (days)
MIN_FEASIBLE = 2      # minimum feasible partners required for 'agreed' soft asks

# Soft fields in decreasing pair-quality-weight order (matches match.py pair_quality).
SOFT_PRIORITY = [
    'relationship_goal',      # +3.0 / -1.5
    'relationship_pace',      # +1.5 / -0.75
    'lifestyle',              # +0.5 / -0.25
    'conversations',          # +0.4 / -0.2
    'emotional_availability',
    'space_for_relationship',
    'relocate',
]

# Only these two fields are asked in 'agreed' mode.
AGREED_SOFT = ['relationship_goal', 'relationship_pace']


# ── helpers ───────────────────────────────────────────────────────────────────

def _count_not_asked_hard(m):
    return sum(1 for k in HARD if m['field_status'][k] == 'not_asked')


def _hard_candidates(members):
    """Available members with >= 1 not_asked hard field and no declined hard field."""
    return [
        m for m in members
        if _count_not_asked_hard(m) > 0
        and not any(m['field_status'][k] == 'declined' for k in HARD)
    ]


def _partner_score(m, all_members, day):
    """Likely partner count (not yet infeasible) plus arrival bonus."""
    count = sum(
        1 for o in all_members
        if o['member_id'] != m['member_id']
        and eligibility(m, o)['status'] != 'infeasible'
    )
    bonus = RECENT_BONUS if (day - m['arrived_day']) <= RECENT_DAYS else 0
    return count + bonus


def _feasible_count(m, all_members):
    """Number of available members currently feasible with m."""
    return sum(
        1 for o in all_members
        if o['member_id'] != m['member_id']
        and eligibility(m, o)['status'] == 'feasible'
    )


# ── hard-ask strategies ───────────────────────────────────────────────────────

def _hard_asks_partners(members, budget, day):
    """Partners ordering: descending score, member_id tie-break."""
    candidates = _hard_candidates(members)
    if not candidates:
        return [], budget
    ranked = sorted(candidates, key=lambda m: (-_partner_score(m, members, day), m['member_id']))
    asks = []
    for m in ranked:
        if budget < 3:
            break
        asks.append({'member_id': m['member_id'], 'field': 'constraints'})
        budget -= 3
    return asks, budget


def _hard_asks_missing(members, budget):
    """Missing-hard ordering: most not_asked hard fields first."""
    ranked = sorted(_hard_candidates(members), key=_count_not_asked_hard, reverse=True)
    asks = []
    for m in ranked:
        if budget < 3:
            break
        asks.append({'member_id': m['member_id'], 'field': 'constraints'})
        budget -= 3
    return asks, budget


# ── soft-ask strategies ───────────────────────────────────────────────────────

def _soft_asks_agreed(members, budget):
    """'agreed': goal then pace, for members with hard resolved and >= MIN_FEASIBLE partners."""
    if budget <= 0:
        return []
    resolved = [
        m for m in members
        if all(m['field_status'][k] in ('observed', 'declined') for k in HARD)
    ]
    asks = []
    for field in AGREED_SOFT:
        if budget <= 0:
            break
        for m in resolved:
            if budget <= 0:
                break
            if m['field_status'][field] != 'not_asked':
                continue
            if _feasible_count(m, members) >= MIN_FEASIBLE:
                asks.append({'member_id': m['member_id'], 'field': field})
                budget -= 1
    return asks


def _soft_asks_resolved(members, budget):
    """'resolved': all soft fields in priority order for any member with hard resolved."""
    if budget <= 0:
        return []
    candidates = sorted(
        [m for m in members if all(m['field_status'][k] in ('observed', 'declined') for k in HARD)],
        key=lambda m: sum(1 for k in SOFT if m['field_status'][k] == 'not_asked'),
        reverse=True,
    )
    asks = []
    for field in SOFT_PRIORITY:
        if budget <= 0:
            break
        for m in candidates:
            if budget <= 0:
                break
            if m['field_status'][field] == 'not_asked':
                asks.append({'member_id': m['member_id'], 'field': field})
                budget -= 1
    return asks


# ── entry point ───────────────────────────────────────────────────────────────

def choose(state, memory, config):
    """Return (asks, memory). asks = [{'member_id': str, 'field': 'constraints' | <soft>}]"""
    ask_order = config.get('ask_order', 'greedy')
    soft_mode = config.get('soft_asks', False)

    if ask_order == 'none':
        return [], memory

    members = [m for m in state['members'] if m['available']]
    budget  = state['ask_budget_remaining']

    # ── hard-constraint asks ───────────────────────────────────────────────────
    if ask_order == 'partners':
        hard, budget = _hard_asks_partners(members, budget, state.get('day', 0))
    elif ask_order == 'missing_hard':
        hard, budget = _hard_asks_missing(members, budget)
    else:
        # 'greedy': exact kit baseline — no reordering, reproducible
        hard   = baseline_asks(state)
        budget -= 3 * len(hard)

    # ── soft-field asks (idle budget) ─────────────────────────────────────────
    if soft_mode == 'agreed':
        soft = _soft_asks_agreed(members, budget)
    elif soft_mode in ('resolved', True):
        soft = _soft_asks_resolved(members, budget)
    else:
        soft = []

    return hard + soft, memory
