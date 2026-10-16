"""Step 0: where is the remaining value? (EVALUATION ONLY, reads simulator truth)

    python analysis/headroom2.py --presets greedy,full --seeds 201-215 --output results/headroom2_201_215.json

Per episode, with exact expected MSMI p(i, j, day):
  used        sum of p over the introductions made
  unused      feasible-at-end pairs (final observed fields, both arrived by day 59) never introduced,
              valued at the day both were first present; split by whether either member exited
  drift_loss  for used intros on/after day 35: p(day 34) - p(actual day)   (timing loss)
  person/pair variance of log p over all feasible pairs explained by response rates alone
              (log r_a^2 r_b^2), by acceptance biases alone, and by relationship_goal match alone
"""
import argparse, itertools, json, math, os, statistics as S
from multiprocessing import Pool
from compare import ROOT, VARIANTS, parse_seeds, register
import policy
import worlds
from kit import eligibility


def r2(y, x):
    if len(y) < 3 or S.pstdev(x) == 0 or S.pstdev(y) == 0:
        return 0.0
    return S.correlation(x, y) ** 2


def run(args):
    preset, seed, fam = args
    register(preset)
    world, sim_class, expected = worlds.make(fam, seed)
    sim = sim_class(world)
    mem = None
    for _ in range(60):
        for ph in ('ask', 'match'):
            r = policy.decide(json.loads(json.dumps({'phase': ph, 'state': sim.observe(), 'memory': mem})), variant=preset)
            mem = r['memory']
            (sim.resolve_asks if ph == 'ask' else sim.advance)(r['asks' if ph == 'ask' else 'pairs'])
    ms = sim.members
    arrived = [m for m in ms.values() if m['arrived_day'] <= 59]
    n = len(arrived)
    past = {tuple(sorted((i['user_a'], i['user_b']))) for i in sim.introductions}
    used = sum(expected(ms[i['user_a']], ms[i['user_b']], i['assigned_day']) for i in sim.introductions)
    drift = sum(expected(ms[i['user_a']], ms[i['user_b']], 34) - expected(ms[i['user_a']], ms[i['user_b']], i['assigned_day'])
                for i in sim.introductions if i['assigned_day'] >= 35)
    unused = unused_exit = 0.0
    n_unused = 0
    logp, lrr, lbias, goal = [], [], [], []
    for a, b in itertools.combinations(arrived, 2):
        if eligibility(a, b)['status'] != 'feasible':
            continue
        day = max(a['arrived_day'], b['arrived_day'])
        p = expected(a, b, day)
        logp.append(math.log(p))
        lrr.append(math.log(a['response_rate'] ** 2 * b['response_rate'] ** 2))
        lbias.append(a['bias'] + b['bias'] + a['second_bias'] + b['second_bias'])
        goal.append(float(a['truth']['relationship_goal'] == b['truth']['relationship_goal']))
        if tuple(sorted((a['member_id'], b['member_id']))) not in past:
            n_unused += 1
            unused += p
            if min(a['exit_day'], b['exit_day']) <= 59:
                unused_exit += p
    return dict(preset=preset, seed=seed, family=fam, N=n, intros=len(sim.introductions), unused_edges=n_unused,
                used100=100 * used / n, unused100=100 * unused / n, unused_exit100=100 * unused_exit / n,
                drift_loss100=100 * drift / n, feasible_edges=len(logp),
                r2_response=r2(logp, lrr), r2_bias=r2(logp, lbias), r2_goal=r2(logp, goal))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--presets', default='greedy,full')
    p.add_argument('--seeds', default='201-215')
    p.add_argument('--workers', type=int, default=4)
    p.add_argument('--output', required=True)
    a = p.parse_args()
    jobs = [(pr, s, f) for pr in a.presets.split(',') for f in VARIANTS for s in parse_seeds(a.seeds)]
    with Pool(a.workers) as pool:
        rows = pool.map(run, jobs, chunksize=1)
    keys = ('used100', 'unused100', 'unused_exit100', 'drift_loss100', 'intros', 'unused_edges', 'feasible_edges',
            'r2_response', 'r2_bias', 'r2_goal')
    out = {}
    for pr in a.presets.split(','):
        fam = {f: {k: S.mean(r[k] for r in rows if r['preset'] == pr and r['family'] == f) for k in keys} for f in VARIANTS}
        out[pr] = {'families': fam, 'overall': {k: S.mean(fam[f][k] for f in VARIANTS) for k in keys}}
        print('\n' + pr)
        print('%-12s %8s %8s %8s %8s %7s %7s %7s %6s %6s %6s' % ('family', 'used', 'unused', 'unus_ex', 'drift', 'intros',
                                                               'unusedE', 'feasE', 'R2_rr', 'R2_bia', 'R2_gol'))
        for f, v in list(fam.items()) + [('OVERALL', out[pr]['overall'])]:
            print('%-12s %8.4f %8.4f %8.4f %8.4f %7.1f %7.1f %7.1f %6.2f %6.2f %6.2f' % (
                f, v['used100'], v['unused100'], v['unused_exit100'], v['drift_loss100'], v['intros'],
                v['unused_edges'], v['feasible_edges'], v['r2_response'], v['r2_bias'], v['r2_goal']))
    path = a.output if os.path.isabs(a.output) else os.path.join(ROOT, a.output)
    json.dump({'summary': out, 'episodes': rows}, open(path, 'w'), indent=1)
    print('wrote', path)
