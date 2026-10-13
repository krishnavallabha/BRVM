"""Match phase (owner: Siddharth). Day 1 stub: reproduces kit greedy / random exactly."""
import itertools
import random
from kit import baseline_match, eligibility


def choose(state, memory, config):
    """Return (pairs, memory). pairs = [[id_a, id_b], ...]"""
    if config.get('match') != 'random':
        return baseline_match(state), memory
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
