"""Q3a: questions that only help together (EVALUATION ONLY; uses truth to label pairs).

    python analysis/q3a.py --presets greedy,full_person_learn --seeds 201-215 --output results/q3a_complementary.json

A pair is "blocked by both" when, on the first day both members are present, each has at least one
not_asked hard field. Neither question alone can make it feasible (kit.eligibility needs every hard
field of BOTH people), so an independent-item planner, one that values a question by the feasible
pairs it unlocks on its own, gives each half exactly zero. We measure:

  part A (synthetic, exact): for every such pair that is truly compatible, the status after asking
          only A, only B, and both; the independent-item value of each half is 0, of both is 1.
  part B (real episodes): how many eventually-feasible pairs were blocked by both, what share of
          all feasible pairs that is, the day each was unlocked (the later of the two constraint
          asks), the lag between the two asks, and whether the policy got both people asked.
"""
import argparse, copy, itertools, json, os, statistics as S
from multiprocessing import Pool
from compare import ROOT, VARIANTS, parse_seeds, register
import policy
import worlds
from kit import HARD, eligibility


def reveal(m):
    """Copy of member m with every non-declined hard field revealed from truth (what a constraints ask does)."""
    m = copy.deepcopy(m)
    for k in HARD:
        if m['field_status'][k] != 'declined':
            m['fields'][k] = copy.deepcopy(m['truth'][k])
            m['field_status'][k] = 'observed'
    return m


def blocked(m):
    return any(m['field_status'][k] == 'not_asked' for k in HARD) and not any(m['field_status'][k] == 'declined' for k in HARD)


def synthetic(seed, fam):
    """Part A on the initial pool: exact statuses for truly compatible blocked-by-both pairs."""
    world, _, _ = worlds.make(fam, seed)
    ms = [m for m in world['members'] if m['arrived_day'] == 0]
    n = alone_feasible = both_feasible = 0
    for a, b in itertools.combinations(ms, 2):
        if not (blocked(a) and blocked(b)):
            continue
        ra, rb = reveal(a), reveal(b)
        if eligibility(ra, rb)['status'] != 'feasible':
            continue  # not compatible even when fully known: no question can unlock it
        n += 1
        alone_feasible += (eligibility(ra, b)['status'] == 'feasible') + (eligibility(a, rb)['status'] == 'feasible')
        both_feasible += 1
    return n, alone_feasible, both_feasible


def run(args):
    preset, seed, fam = args
    register(preset)
    world, sim_class, _ = worlds.make(fam, seed)
    sim = sim_class(world)
    first_status = {}
    mem = None
    for _ in range(60):
        st = sim.observe()
        for m in st['members']:
            first_status.setdefault(m['member_id'], copy.deepcopy(m['field_status']))
        for ph in ('ask', 'match'):
            r = policy.decide(json.loads(json.dumps({'phase': ph, 'state': sim.observe(), 'memory': mem})), variant=preset)
            mem = r['memory']
            (sim.resolve_asks if ph == 'ask' else sim.advance)(r['asks' if ph == 'ask' else 'pairs'])
    ask_day = {}
    for e in sim.ask_log:
        if e['field'] == 'constraints':
            ask_day.setdefault(e['member_id'], e['observed_day'])
    ms = {i: m for i, m in sim.members.items() if m['arrived_day'] <= 59}
    feasible_end = both_blocked = asked_both = 0
    unlock, lag, wait = [], [], []
    for a, b in itertools.combinations(ms.values(), 2):
        if eligibility(a, b)['status'] != 'feasible':
            continue
        feasible_end += 1
        fa, fb = first_status.get(a['member_id']), first_status.get(b['member_id'])
        if not fa or not fb:
            continue
        ba = any(fa[k] == 'not_asked' for k in HARD)
        bb = any(fb[k] == 'not_asked' for k in HARD)
        if not (ba and bb):
            continue
        both_blocked += 1
        da, db = ask_day.get(a['member_id']), ask_day.get(b['member_id'])
        if da is None or db is None:
            continue
        asked_both += 1
        present = max(a['arrived_day'], b['arrived_day'])
        unlock.append(max(da, db))
        lag.append(abs(da - db))
        wait.append(max(da, db) - present)
    return dict(preset=preset, seed=seed, family=fam, feasible_pairs=feasible_end, blocked_by_both=both_blocked,
                asked_both=asked_both, unlock_days=unlock, ask_lags=lag, unlock_waits=wait)


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else None


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--presets', default='greedy,full_person_learn')
    ap.add_argument('--seeds', default='201-215')
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--output', required=True)
    a = ap.parse_args()
    seeds = parse_seeds(a.seeds)
    with Pool(a.workers) as pool:
        syn = pool.starmap(synthetic, [(s, f) for f in VARIANTS for s in seeds])
        rows = pool.map(run, [(p, s, f) for p in a.presets.split(',') for f in VARIANTS for s in seeds], chunksize=1)
    n = sum(x[0] for x in syn)
    part_a = {'compatible_blocked_by_both_pairs': n,
              'feasible_after_asking_one_half_only': sum(x[1] for x in syn),
              'feasible_after_asking_both': sum(x[2] for x in syn),
              'independent_item_value_per_half': 0.0 if n else None, 'joint_value': 1.0 if n else None}
    print('PART A (initial pools, %d worlds): %d truly compatible pairs blocked by both; feasible after asking one half: %d; '
          'after both: %d -> independent-item value of each half = 0, joint value = 1'
          % (len(syn), n, part_a['feasible_after_asking_one_half_only'], part_a['feasible_after_asking_both']))
    out = {'part_a': part_a, 'part_b': {}}
    for p in a.presets.split(','):
        rs = [r for r in rows if r['preset'] == p]
        fam = {}
        for f in VARIANTS:
            fr = [r for r in rs if r['family'] == f]
            fam[f] = {'blocked_share_of_feasible': sum(r['blocked_by_both'] for r in fr) / max(1, sum(r['feasible_pairs'] for r in fr)),
                      'asked_both_share': sum(r['asked_both'] for r in fr) / max(1, sum(r['blocked_by_both'] for r in fr))}
        U = [x for r in rs for x in r['unlock_days']]
        L = [x for r in rs for x in r['ask_lags']]
        W = [x for r in rs for x in r['unlock_waits']]
        tot = {'episodes': len(rs), 'feasible_pairs': sum(r['feasible_pairs'] for r in rs),
               'blocked_by_both': sum(r['blocked_by_both'] for r in rs), 'asked_both': sum(r['asked_both'] for r in rs),
               'unlock_day_median': pct(U, .5), 'unlock_day_p90': pct(U, .9),
               'ask_lag_median': pct(L, .5), 'ask_lag_p90': pct(L, .9), 'same_day_share': sum(x == 0 for x in L) / max(1, len(L)),
               'wait_from_copresence_median': pct(W, .5), 'wait_from_copresence_p90': pct(W, .9), 'families': fam}
        tot['blocked_share_of_feasible'] = tot['blocked_by_both'] / max(1, tot['feasible_pairs'])
        tot['asked_both_share'] = tot['asked_both'] / max(1, tot['blocked_by_both'])
        out['part_b'][p] = tot
        print('\n%s: %d episodes | feasible pairs %d, blocked by both %d (%.0f%%), both asked %.1f%% | unlock day median %s p90 %s | '
              'lag between the two asks median %s p90 %s (same day %.0f%%) | wait from co-presence median %s p90 %s'
              % (p, tot['episodes'], tot['feasible_pairs'], tot['blocked_by_both'], 100 * tot['blocked_share_of_feasible'],
                 100 * tot['asked_both_share'], tot['unlock_day_median'], tot['unlock_day_p90'], tot['ask_lag_median'],
                 tot['ask_lag_p90'], 100 * tot['same_day_share'], tot['wait_from_copresence_median'], tot['wait_from_copresence_p90']))
        print('   blocked-by-both share by family:', {f: round(v['blocked_share_of_feasible'], 2) for f, v in fam.items()})
    path = a.output if os.path.isabs(a.output) else os.path.join(ROOT, a.output)
    json.dump(out, open(path, 'w'), indent=1)
    print('wrote', path)
