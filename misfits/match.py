import itertools
import random
import time

from kit import baseline_match, eligibility

# Hand-set soft-compatibility prior weights (Day 2)
BASE_WEIGHT = 1000.0
W_GOAL_MATCH = 3.0
W_GOAL_MISMATCH = -1.5
W_PACE_MATCH = 1.5
W_PACE_MISMATCH = -0.75
W_LIFESTYLE_MATCH = 0.5
W_LIFESTYLE_MISMATCH = -0.25
W_CONVERSATIONS_MATCH = 0.4
W_CONVERSATIONS_MISMATCH = -0.2


def pair_quality(a, b):
    """Compute soft-field compatibility prior q(i, j) from observed fields only.
    Returns 0.0 for unobserved fields."""
    fa, fb = a['fields'], b['fields']
    q = 0.0

    goal_a, goal_b = fa.get('relationship_goal'), fb.get('relationship_goal')
    if goal_a is not None and goal_b is not None:
        q += W_GOAL_MATCH if goal_a == goal_b else W_GOAL_MISMATCH

    pace_a, pace_b = fa.get('relationship_pace'), fb.get('relationship_pace')
    if pace_a is not None and pace_b is not None:
        q += W_PACE_MATCH if pace_a == pace_b else W_PACE_MISMATCH

    life_a, life_b = fa.get('lifestyle'), fb.get('lifestyle')
    if life_a is not None and life_b is not None:
        q += W_LIFESTYLE_MATCH if life_a == life_b else W_LIFESTYLE_MISMATCH

    conv_a, conv_b = fa.get('conversations'), fb.get('conversations')
    if conv_a is not None and conv_b is not None:
        q += W_CONVERSATIONS_MATCH if conv_a == conv_b else W_CONVERSATIONS_MISMATCH

    return q


def choose(state, memory, config):
    """Return (pairs, memory). pairs = [[id_a, id_b], ...]"""
    how = config.get('match')
    if how == 'random':
        candidates = [m for m in state['members'] if m['available']]
        past = {tuple(sorted((i['user_a'], i['user_b']))) for i in state['introductions']}
        edges = [tuple(sorted((a['member_id'], b['member_id'])))
                 for a, b in itertools.combinations(candidates, 2)
                 if eligibility(a, b)['status'] == 'feasible'
                 and tuple(sorted((a['member_id'], b['member_id']))) not in past]
        random.Random(17 + state['day']).shuffle(edges)
        pairs, used = [], set()
        for pair in edges:
            if not used.intersection(pair):
                pairs.append(list(pair))
                used.update(pair)
        return pairs, memory

    if how in ('maxcard', 'maxcard_quality'):
        try:
            import networkx as nx  # lazy: ~1 s import, and the process restarts every call
        except ImportError:
            return baseline_match(state), memory
        t0 = time.perf_counter()
        try:
            candidates = sorted(
                [m for m in state['members'] if m['available']],
                key=lambda m: m['member_id']
            )
            past = {tuple(sorted((i['user_a'], i['user_b']))) for i in state['introductions']}
            G = nx.Graph()
            for m in candidates:
                G.add_node(m['member_id'])
            for a, b in itertools.combinations(candidates, 2):
                key = (a['member_id'], b['member_id'])
                if key in past:
                    continue
                if eligibility(a, b)['status'] == 'feasible':
                    w = (BASE_WEIGHT + pair_quality(a, b)) if how == 'maxcard_quality' else 1.0
                    G.add_edge(key[0], key[1], weight=w)

            matching = nx.max_weight_matching(G, maxcardinality=True)
            pairs = sorted([sorted(list(edge)) for edge in matching])

            if time.perf_counter() - t0 > 3.0:
                return baseline_match(state), memory
            return pairs, memory
        except Exception:
            return baseline_match(state), memory

    return baseline_match(state), memory

