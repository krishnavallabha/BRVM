"""Ask phase: question ordering and soft-field clarification.

config['ask_order'] (3-unit hard bundles, at most budget // 3 per day):
  'greedy'       kit baseline_asks order — reproduces the kit baseline exactly
  'partners'     likely partner count (pairs not yet 'infeasible' with any available member),
                 + ARRIVAL_BONUS for arrivals in the last 3 days; ties by member_id
  'missing_hard' sort by most not_asked hard fields first
  'none'         no asks at all

config['soft_asks'] (1-unit asks with the budget left over):
  False / None   off
  True           relationship_goal then relationship_pace, only for members
                 with >= 2 feasible available partners, most partners first
  'resolved'     every soft field in SOFT_PRIORITY order, for members whose hard
                 fields are all observed/declined, most missing soft fields first
"""
from kit import HARD, SOFT, baseline_asks, eligibility

ARRIVAL_BONUS = 10     # added to a new arrival's likely-partner count
SOFT_FIELDS = ['relationship_goal', 'relationship_pace']  # strongest acceptance factors

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


def _partner_counts(members, past):
    """-> (likely, feasible): per member, the number of other available members (never introduced)
    whose pair is not 'infeasible' / is 'feasible'. One eligibility pass serves both."""
    likely = {m['member_id']: 0 for m in members}
    feasible = dict(likely)
    for i, a in enumerate(members):
        for b in members[i + 1:]:
            ia, ib = a['member_id'], b['member_id']
            if tuple(sorted((ia, ib))) in past:
                continue
            status = eligibility(a, b)['status']
            if status != 'infeasible':
                likely[ia] += 1
                likely[ib] += 1
            if status == 'feasible':
                feasible[ia] += 1
                feasible[ib] += 1
    return likely, feasible


def choose(state, memory, config):
    """Return (asks, memory). asks = [{'member_id': str, 'field': 'constraints' | <soft field>}]"""
    order = config.get('ask_order')
    if order == 'none':
        return [], memory

    members = [m for m in state['members'] if m['available']]
    budget = state['ask_budget_remaining']
    past = {tuple(sorted((i['user_a'], i['user_b']))) for i in state['introductions']}
    counts = []  # lazy (likely, feasible) partner counts, computed at most once per call

    def partner_counts():
        if not counts:
            counts.extend(_partner_counts(members, past))
        return counts

    hard_candidates = [
        m for m in members
        if _count_missing_hard(m) > 0
        and not any(m['field_status'][k] == 'declined' for k in HARD)
    ]

    # Hard-constraint bundles (3 units each)
    if order == 'partners':
        # Likely partner count: unknown fields don't block (anything but 'infeasible'),
        # plus a bonus for members who arrived in the last 3 days.
        likely = partner_counts()[0]
        bonus = config.get('arrival_bonus', ARRIVAL_BONUS)
        score = {m['member_id']: likely[m['member_id']] + (bonus if state['day'] - m['arrived_day'] <= 2 else 0)
                 for m in hard_candidates}
        hard_candidates.sort(key=lambda m: (-score[m['member_id']], m['member_id']))
    elif order == 'missing_hard':
        # Prioritise members with the most missing hard fields (most to gain from one ask).
        hard_candidates.sort(key=_count_missing_hard, reverse=True)
    if order in ('partners', 'missing_hard'):
        asks = [{'member_id': m['member_id'], 'field': 'constraints'} for m in hard_candidates[:budget // 3]]
    else:  # 'greedy': kit order, so the greedy preset stays exactly the kit baseline
        asks = baseline_asks(state)
    budget -= 3 * len(asks)

    # Soft-field asks with idle budget (1 unit each)
    soft = config.get('soft_asks')
    if not soft or budget <= 0:
        return asks, memory

    if soft == 'resolved':
        # All soft fields in priority order; members with hard fields fully resolved,
        # most missing soft fields first.
        candidates = [m for m in members if all(m['field_status'][k] in ('observed', 'declined') for k in HARD)]
        candidates.sort(key=_count_missing_soft, reverse=True)
        fields = SOFT_PRIORITY
    else:
        # A soft answer can only change a choice when there is more than one option,
        # so ask only members with >= 2 feasible available partners, most partners first.
        feasible = partner_counts()[1]
        candidates = sorted((m for m in members if feasible[m['member_id']] >= 2),
                            key=lambda m: (-feasible[m['member_id']], m['member_id']))
        fields = SOFT_FIELDS
    for field in fields:
        for m in candidates:
            if budget <= 0:
                return asks, memory
            if m['field_status'][field] == 'not_asked':
                asks.append({'member_id': m['member_id'], 'field': field})
                budget -= 1
    return asks, memory
