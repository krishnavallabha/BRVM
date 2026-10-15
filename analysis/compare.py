"""Paired in-process comparison of two policy config presets (EVALUATION ONLY).

    python analysis/compare.py --a greedy --b <preset> --seeds 201-230

Both presets run on identical worlds (same seed x family). Main metric: exact expected
MSMI/100 (expected.p_msmi, reads simulator truth, analysis only); realised MSMI alongside.
"""
import argparse, json, math, os, statistics as S, sys, time
from multiprocessing import Pool

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from kit import HARD  # noqa: E402
from evaluate import VARIANTS  # noqa: E402
import policy  # noqa: E402
import worlds  # noqa: E402

Z95 = 1.96  # ponytail: normal approx; for n=30 the t quantile (2.045) widens the CI ~4%


def register(preset):
    """'base@key=val,key=val' -> add a tuning preset (base config with numeric overrides)."""
    if preset not in policy.PRESETS and '@' in preset:
        base, _, kv = preset.partition('@')
        policy.PRESETS[preset] = dict(policy.PRESETS[base], **{k: float(v) for k, v in
                                                               (x.split('=') for x in kv.split(','))})
    return preset in policy.PRESETS


def episode(args):
    """args = (role, preset, seed, world[, detail]). world: a family or a worlds.py variant.
    detail=True adds per-member rows for waiting/fairness analysis (q3b.py)."""
    role, preset, seed, family = args[:4]
    detail = len(args) > 4 and args[4]
    register(preset)
    world, sim_class, expected = worlds.make(family, seed)
    sim = sim_class(world)
    memory, times, error = None, [], None
    try:
        for _ in range(60):
            for phase in ('ask', 'match'):
                req = json.loads(json.dumps({'phase': phase, 'state': sim.observe(), 'memory': memory}))
                t0 = time.perf_counter()
                r = policy.decide(req, variant=preset)
                times.append(time.perf_counter() - t0)
                memory = r['memory']
                if phase == 'ask':
                    sim.resolve_asks(r['asks'])
                else:
                    sim.advance(r['pairs'])
    except ValueError as e:  # simulator rejected an action -> invalid episode
        error = str(e)
    arrived = {i for i, m in sim.members.items() if m['arrived_day'] <= 59}
    ps = [expected(sim.members[i['user_a']], sim.members[i['user_b']], i['assigned_day'])
          for i in sim.introductions]
    exp = sum(ps)
    served = {x for i in sim.introductions for x in (i['user_a'], i['user_b'])}
    for _ in range(40):
        sim.advance([])
    met, n = sim.metrics(), len(arrived)
    out = dict(role=role, preset=preset, seed=seed, family=family, valid=error is None, error=error, N=n,
                exp100=100 * exp / n, real100=100 * met['mutual_second_meeting_intention'] / n,
                intros=len(sim.introductions), intros_d0_20=sum(i['assigned_day'] <= 20 for i in sim.introductions),
                coverage=len(served & arrived) / n,
                exp_count=exp, exp_var=sum(q * (1 - q) for q in ps),
                real_count=met['mutual_second_meeting_intention'], ask_cost=met['ask_cost'],
                mean_call_s=S.mean(times), max_call_s=max(times))
    if detail:
        # [arrived_day, first_intro_day | None, blocked (declined hard field), true response_rate,
        #  observed no-responses, observed responses]  (the last two are what the policy can see)
        first, resp = {}, {}
        for i in sim.introductions:
            for x in (i['user_a'], i['user_b']):
                first.setdefault(x, i['assigned_day'])
        for e in sim.events:
            if e['event'] == 'introduction_response':
                r = resp.setdefault(e['member_id'], [0, 0])
                r[0] += e.get('missing_reason') == 'no_response'
                r[1] += 1
        out['members'] = [[m['arrived_day'], first.get(i), any(m['field_status'][k] == 'declined' for k in HARD),
                           m['response_rate']] + resp.get(i, [0, 0])
                          for i, m in sim.members.items() if i in arrived]
    return out


def ci(diffs):
    m = S.mean(diffs)
    h = Z95 * S.stdev(diffs) / math.sqrt(len(diffs)) if len(diffs) > 1 else float('nan')
    return {'mean': m, 'lo': m - h, 'hi': m + h, 'sd': S.stdev(diffs) if len(diffs) > 1 else 0.0}


def summarise(rows, seeds, families):
    by = {(r['role'], r['seed'], r['family']): r for r in rows}
    keys = ('exp100', 'real100', 'intros', 'intros_d0_20', 'coverage', 'ask_cost')
    out = {'families': {}, 'invalid_episodes': sum(not r['valid'] for r in rows),
           'max_call_s': {p: max(r['max_call_s'] for r in rows if r['role'] == p) for p in 'AB'},
           'mean_call_s': {p: S.mean(r['mean_call_s'] for r in rows if r['role'] == p) for p in 'AB'}}
    for f in families:
        fam = {p: {k: S.mean(by[p, s, f][k] for s in seeds) for k in keys} for p in 'AB'}
        fam['diff_exp100'] = ci([by['B', s, f]['exp100'] - by['A', s, f]['exp100'] for s in seeds])
        fam['diff_real100'] = ci([by['B', s, f]['real100'] - by['A', s, f]['real100'] for s in seeds])
        out['families'][f] = fam
    # overall = equal-weight mean over families, paired per seed (the official aggregation)
    ov = lambda p, s, k: S.mean(by[p, s, f][k] for f in families)
    out['overall'] = {p: {k: S.mean(ov(p, s, k) for s in seeds) for k in keys} for p in 'AB'}
    out['overall']['diff_exp100'] = ci([ov('B', s, 'exp100') - ov('A', s, 'exp100') for s in seeds])
    out['overall']['diff_real100'] = ci([ov('B', s, 'real100') - ov('A', s, 'real100') for s in seeds])
    return out


def show(summary):
    hdr = '%-12s %8s %8s %26s %8s %8s %7s %7s %6s %6s %6s %6s'
    print(hdr % ('family', 'expA', 'expB', 'diff exp [95% CI]', 'realA', 'realB', 'intrA', 'intrB',
                 'covA', 'covB', 'askA', 'askB'))
    rows = list(summary['families'].items()) + [('OVERALL', summary['overall'])]
    for name, s in rows:
        a, b, d = 'A', 'B', s['diff_exp100']
        print('%-12s %8.4f %8.4f %+9.4f [%+7.4f,%+7.4f] %8.4f %8.4f %7.1f %7.1f %6.3f %6.3f %6.1f %6.1f' % (
            name, s[a]['exp100'], s[b]['exp100'], d['mean'], d['lo'], d['hi'], s[a]['real100'], s[b]['real100'],
            s[a]['intros'], s[b]['intros'], s[a]['coverage'], s[b]['coverage'], s[a]['ask_cost'], s[b]['ask_cost']))
    print('invalid episodes: %d | call time mean/max (s): %s | intros days 0-20 A/B: %.1f / %.1f' % (
        summary['invalid_episodes'],
        {p: (round(summary['mean_call_s'][p], 4), round(summary['max_call_s'][p], 3)) for p in 'AB'},
        summary['overall']['A']['intros_d0_20'], summary['overall']['B']['intros_d0_20']))


def parse_seeds(text):
    lo, _, hi = text.partition('-')
    return list(range(int(lo), int(hi or lo) + 1))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--a', default='greedy')
    p.add_argument('--b', required=True)
    p.add_argument('--seeds', default='201-230', help='inclusive range, e.g. 201-230')
    p.add_argument('--families', default='all')
    p.add_argument('--workers', type=int, default=2)
    p.add_argument('--output')
    args = p.parse_args()
    for preset in (args.a, args.b):
        if not register(preset):
            p.error('unknown preset %r; known: %s' % (preset, sorted(policy.PRESETS)))
    seeds = parse_seeds(args.seeds)
    families = list(VARIANTS) if args.families == 'all' else args.families.split(',')
    jobs = [(role, pr, s, f) for role, pr in (('A', args.a), ('B', args.b)) for f in families for s in seeds]
    with Pool(args.workers) as pool:
        rows = pool.map(episode, jobs)
    summary = summarise(rows, seeds, families)
    print('A = %s, B = %s, seeds %s' % (args.a, args.b, args.seeds))
    show(summary)
    out = args.output or os.path.join(ROOT, 'results', 'compare_%s_vs_%s_%s.json' % (args.a, args.b, args.seeds))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w') as fh:
        json.dump({'a': args.a, 'b': args.b, 'seeds': args.seeds, 'summary': summary, 'episodes': rows}, fh, indent=1)
    print('wrote', out)
