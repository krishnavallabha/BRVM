"""Calibration of the observable-only models (EVALUATION ONLY).

    python analysis/calibration.py --preset full --seeds 201-215 --output results/calibration_201_215.json

At every match decision, for each introduction made that day we record what misfits.bayes predicted
from the request alone (state before the introduction), then score it against what happened:
  respond  P(member responds to the introduction)   person model vs the pool-rate prior
  yes      P(member says yes | responded)            person model vs the pool-rate prior
  fit      P(member says yes | responded), logistic fit on soft-field agreement + intercept,
           learned weights vs hand-set prior weights (same intercept fitting)
Reported: reliability bins (mean predicted vs observed), Brier score, log loss, and skill vs baseline.
"""
import argparse, json, math, os, statistics as S
from multiprocessing import Pool
from compare import ROOT, VARIANTS, parse_seeds, register
import policy
import worlds
from misfits import bayes
from misfits.match import FIT_PRIOR

BINS = [0, .2, .3, .4, .5, .6, .7, .8, .9, 1.01]


def sig(z):
    return 1 / (1 + math.exp(-max(-30, min(30, z))))


def intercept_only(state, w):
    """MAP intercept for fixed weights w (so learned vs prior differ only in the fit weights)."""
    members = {m['member_id']: m for m in state['members']}
    pair_of = {i['introduction_id']: (i['user_a'], i['user_b']) for i in state['introductions']}
    rows = []
    for e in state['feedback']:
        if e.get('event') == 'introduction_response' and e.get('value') in ('yes', 'no'):
            pr = pair_of.get(e['introduction_id'])
            if pr and pr[0] in members and pr[1] in members:
                rows.append((sum(a * b for a, b in zip(w, bayes.fit_features(members[pr[0]], members[pr[1]]))),
                             e['value'] == 'yes'))
    b = 0.0
    for _ in range(25):
        g = -b / 4.0 + sum(y - sig(b + z) for z, y in rows)
        h = 1 / 4.0 + sum(sig(b + z) * (1 - sig(b + z)) for z, _ in rows)
        b += g / h
    return b


def run(args):
    preset, seed, fam = args
    register(preset)
    world, sim_class, _ = worlds.make(fam, seed)
    sim = sim_class(world)
    mem, preds = None, []
    for _ in range(60):
        for ph in ('ask', 'match'):
            st = sim.observe()
            r = policy.decide(json.loads(json.dumps({'phase': ph, 'state': st, 'memory': mem})), variant=preset)
            mem = r['memory']
            if ph == 'match' and r['pairs']:
                _, post = bayes.person_model(st)
                prior = post.get('_prior', {'p_respond': .75, 'p_yes': .4})
                w_learn, n_lab = bayes.fit_model(st, FIT_PRIOR)
                b_learn, b_prior = intercept_only(st, w_learn), intercept_only(st, FIT_PRIOR)
                byid = {m['member_id']: m for m in st['members']}
                for a, b in r['pairs']:
                    x = bayes.fit_features(byid[a], byid[b])
                    for me in (a, b):
                        q = post.get(me, prior)
                        preds.append({'day': st['day'], 'pair': sorted([a, b]), 'member': me,
                                      'p_respond': q['p_respond'], 'p_respond_prior': prior['p_respond'],
                                      'p_yes': q['p_yes'], 'p_yes_prior': prior['p_yes'],
                                      'fit_learn': sig(b_learn + sum(wk * xk for wk, xk in zip(w_learn, x))),
                                      'fit_prior': sig(b_prior + sum(wk * xk for wk, xk in zip(FIT_PRIOR, x))),
                                      'n_labels': n_lab})
            (sim.resolve_asks if ph == 'ask' else sim.advance)(r['asks' if ph == 'ask' else 'pairs'])
    for _ in range(40):
        sim.advance([])
    intro = {(i['assigned_day'], i['user_a'], i['user_b']): i['introduction_id'] for i in sim.introductions}
    resp = {(e['introduction_id'], e['member_id']): e['value'] for e in sim.events if e['event'] == 'introduction_response'}
    for p in preds:
        v = resp[(intro[(p['day'], p['pair'][0], p['pair'][1])], p['member'])]
        p['responded'], p['yes'] = v is not None, (v == 'yes') if v is not None else None
        p['family'] = fam
    return preds


def score(rows, pk, yk):
    rows = [r for r in rows if r[yk] is not None]
    if not rows:
        return None
    ys = [1.0 if r[yk] else 0.0 for r in rows]
    ps = [min(max(r[pk], 1e-6), 1 - 1e-6) for r in rows]
    bins = []
    for lo, hi in zip(BINS, BINS[1:]):
        sel = [(p, y) for p, y in zip(ps, ys) if lo <= p < hi]
        if len(sel) >= 20:
            bins.append({'bin': '%.1f-%.1f' % (lo, min(hi, 1)), 'n': len(sel),
                         'mean_pred': S.mean(p for p, _ in sel), 'observed': S.mean(y for _, y in sel)})
    return {'n': len(rows), 'brier': S.mean((p - y) ** 2 for p, y in zip(ps, ys)),
            'logloss': -S.mean(y * math.log(p) + (1 - y) * math.log(1 - p) for p, y in zip(ps, ys)),
            'mean_pred': S.mean(ps), 'observed': S.mean(ys), 'bins': bins}


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--preset', default='full')
    ap.add_argument('--seeds', default='201-215')
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--output', required=True)
    a = ap.parse_args()
    jobs = [(a.preset, s, f) for f in VARIANTS for s in parse_seeds(a.seeds)]
    with Pool(a.workers) as pool:
        rows = [p for ep in pool.map(run, jobs, chunksize=1) for p in ep]
    out = {}
    for name, pk, base, yk in (('respond', 'p_respond', 'p_respond_prior', 'responded'),
                               ('yes', 'p_yes', 'p_yes_prior', 'yes'), ('fit', 'fit_learn', 'fit_prior', 'yes')):
        m, b = score(rows, pk, yk), score(rows, base, yk)
        out[name] = {'model': m, 'baseline': b, 'brier_skill': 1 - m['brier'] / b['brier']}
        print('\n%s: n=%d  model Brier %.4f (logloss %.4f)  baseline Brier %.4f (logloss %.4f)  skill %+.2f%%'
              % (name, m['n'], m['brier'], m['logloss'], b['brier'], b['logloss'], 100 * out[name]['brier_skill']))
        print('   reliability (model):', ', '.join('%s n=%d pred %.2f obs %.2f' % (x['bin'], x['n'], x['mean_pred'], x['observed'])
                                                  for x in m['bins']))
    shift = [r for r in rows if r['family'] == 'shift']
    m, b = score(shift, 'fit_learn', 'yes'), score(shift, 'fit_prior', 'yes')
    out['fit_shift_only'] = {'model': m, 'baseline': b, 'brier_skill': 1 - m['brier'] / b['brier']}
    print('\nfit (shift family only): model Brier %.4f vs prior %.4f, skill %+.2f%%' % (m['brier'], b['brier'], 100 * out['fit_shift_only']['brier_skill']))
    path = a.output if os.path.isabs(a.output) else os.path.join(ROOT, a.output)
    json.dump({'preset': a.preset, 'seeds': a.seeds, 'summary': out}, open(path, 'w'), indent=1)
    print('wrote', path)
