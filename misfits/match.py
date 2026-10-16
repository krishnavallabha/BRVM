import itertools
import random
import statistics

from kit import baseline_match, eligibility
from misfits import bayes, blossom  # blossom: vendored NetworkX matching, no 1 s networkx import per call

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


FIT_PRIOR = [W_GOAL_MATCH / bayes.Q_SCALE, W_PACE_MATCH / bayes.Q_SCALE,
             W_LIFESTYLE_MATCH / bayes.Q_SCALE, W_CONVERSATIONS_MATCH / bayes.Q_SCALE]
MAX_BONUS = 200.0  # all model terms together stay far below BASE_WEIGHT, so cardinality is never traded


def quality_fn(state, candidates, config):
    """Edge quality for maxcard_quality: hand-set q, or the learned fit, plus optional person and
    slot terms (each switchable for ablations; all off reproduces Day 3 `full` exactly)."""
    terms = []
    if config.get('learn_fit'):
        w, _ = bayes.fit_model(state, FIT_PRIOR)
        terms.append(lambda a, b: bayes.Q_SCALE * sum(wk * xk for wk, xk in zip(w, bayes.fit_features(a, b))))
    else:
        terms.append(pair_quality)
    kp = config.get('person_weight')
    if kp:
        score, _ = bayes.person_model(state)
        terms.append(lambda a, b: kp * (score.get(a['member_id'], 0.0) + score.get(b['member_id'], 0.0)))
    ks = config.get('slot_price')
    if ks:
        press = bayes.slot_pressure(state, candidates)
        terms.append(lambda a, b: ks * (press.get(a['member_id'], 0.0) + press.get(b['member_id'], 0.0)))
    if len(terms) == 1:
        return terms[0]
    return lambda a, b: max(-MAX_BONUS, min(MAX_BONUS, sum(t(a, b) for t in terms)))


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
            candidates = sorted(
                [m for m in state['members'] if m['available']],
                key=lambda m: m['member_id']
            )
            past = {tuple(sorted((i['user_a'], i['user_b']))) for i in state['introductions']}
            quality = quality_fn(state, candidates, config) if how == 'maxcard_quality' else None
            G = blossom.Graph()
            for m in candidates:
                G.add_node(m['member_id'])
            for a, b in itertools.combinations(candidates, 2):
                key = (a['member_id'], b['member_id'])
                if key in past:
                    continue
                if eligibility(a, b)['status'] == 'feasible':
                    w = (BASE_WEIGHT + quality(a, b)) if how == 'maxcard_quality' else 1.0
                    G.add_edge(key[0], key[1], weight=w)

            k = config.get('reserve_k')
            if k and how == 'maxcard_quality' and G.number_of_edges():
                # Q1 simple reservation: hold back a below-median-quality edge when both people
                # have >= k other feasible partners today, so they can wait for a better one.
                med = statistics.median(d['weight'] for _, _, d in G.edges(data=True))
                G.remove_edges_from([(u, v) for u, v, d in G.edges(data=True)
                                     if d['weight'] < med and G.degree(u) - 1 >= k and G.degree(v) - 1 >= k])

            matching = blossom.max_weight_matching(G, maxcardinality=True)
            return sorted([sorted(list(edge)) for edge in matching]), memory
        except Exception:
            return baseline_match(state), memory

    return baseline_match(state), memory

