"""Validate the expected-MSMI yardstick against realised MSMI (EVALUATION ONLY).

    python analysis/yardstick.py --preset greedy --seeds 201-260

If expected.p_msmi is unbiased, total realised MSMI ~ total expected. Two checks per family:
  z  = (R - E) / sqrt(sum p(1-p))       (Poisson-binomial; independent intros given the world)
  CI = 95% CI of the mean per-episode difference (realised - expected), model-free.
"""
import argparse, json, math, os, statistics as S
from multiprocessing import Pool
from compare import ROOT, VARIANTS, episode, parse_seeds, Z95


def check(rows):
    E = sum(r['exp_count'] for r in rows)
    R = sum(r['real_count'] for r in rows)
    var = sum(r['exp_var'] for r in rows)
    d = [r['real100'] - r['exp100'] for r in rows]
    h = Z95 * S.stdev(d) / math.sqrt(len(d))
    return {'episodes': len(rows), 'expected_msmi': E, 'realised_msmi': R, 'ratio': R / E if E else None,
            'z': (R - E) / math.sqrt(var) if var else None,
            'expected100': S.mean(r['exp100'] for r in rows), 'realised100': S.mean(r['real100'] for r in rows),
            'diff100_mean': S.mean(d), 'diff100_ci': [S.mean(d) - h, S.mean(d) + h]}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--preset', default='greedy')
    p.add_argument('--seeds', default='201-260')
    p.add_argument('--workers', type=int, default=2)
    p.add_argument('--output', default=os.path.join(ROOT, 'results', 'yardstick_validation.json'))
    args = p.parse_args()
    jobs = [('A', args.preset, s, f) for f in VARIANTS for s in parse_seeds(args.seeds)]
    with Pool(args.workers) as pool:
        rows = pool.map(episode, jobs)
    out = {'preset': args.preset, 'seeds': args.seeds, 'invalid_episodes': sum(not r['valid'] for r in rows),
           'families': {f: check([r for r in rows if r['family'] == f]) for f in VARIANTS}, 'overall': check(rows)}
    print('%-12s %5s %9s %9s %6s %6s %9s %9s %24s' % ('family', 'eps', 'E[msmi]', 'R[msmi]', 'R/E', 'z',
                                                     'exp/100', 'real/100', 'diff/100 [95% CI]'))
    for name, c in list(out['families'].items()) + [('OVERALL', out['overall'])]:
        print('%-12s %5d %9.2f %9d %6.3f %+6.2f %9.4f %9.4f %+8.4f [%+.4f,%+.4f]' % (
            name, c['episodes'], c['expected_msmi'], c['realised_msmi'], c['ratio'], c['z'],
            c['expected100'], c['realised100'], c['diff100_mean'], *c['diff100_ci']))
    json.dump(dict(out, episodes=rows), open(args.output, 'w'), indent=1)
    print('wrote', args.output)
