"""Match phase (owner: Siddharth)."""
import itertools
import random
import time
import networkx as nx
from kit import baseline_match, eligibility


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

    if how == 'maxcard':
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
                    G.add_edge(key[0], key[1], weight=1)

            matching = nx.max_weight_matching(G, maxcardinality=True)
            pairs = sorted([sorted(list(edge)) for edge in matching])

            if time.perf_counter() - t0 > 3.0:
                return baseline_match(state), memory
            return pairs, memory
        except Exception:
            return baseline_match(state), memory

    return baseline_match(state), memory
