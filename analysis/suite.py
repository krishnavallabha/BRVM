"""Run many presets once each on identical worlds, with paired diffs vs reference presets (EVALUATION ONLY).

    python analysis/suite.py --presets greedy,no_asks,random,full --refs greedy,full \
        --worlds all --seeds 301-340 --output results/confirmation_301_340.json

--worlds: 'all' (the 6 families) or a comma list of families / worlds.py variants.
--detail keeps per-member rows (for q3b.py). Overall = equal-weight mean over worlds, paired per seed.
"""
import argparse, json, os, statistics as S
from multiprocessing import Pool
from compare import ROOT, VARIANTS, ci, episode, parse_seeds, register

KEYS = ('exp100', 'real100', 'intros', 'intros_d0_20', 'coverage', 'ask_cost', 'mean_call_s', 'max_call_s')


def summarise(rows, presets, refs, worlds, seeds):
    by = {(r['preset'], r['seed'], r['family']): r for r in rows}
    ov = lambda p, s, k: S.mean(by[p, s, w][k] for w in worlds)
    out = {'invalid_episodes': sum(not r['valid'] for r in rows), 'presets': {}}
    for p in presets:
        res = {'overall': {k: S.mean(ov(p, s, k) for s in seeds) for k in KEYS},
               'worlds': {w: {k: S.mean(by[p, s, w][k] for s in seeds) for k in KEYS} for w in worlds}}
        res['overall']['max_call_s'] = max(by[p, s, w]['max_call_s'] for s in seeds for w in worlds)
        for ref in refs:
            if ref == p:
                continue
            res['vs_' + ref] = {
                'overall': {m: ci([ov(p, s, m) - ov(ref, s, m) for s in seeds]) for m in ('exp100', 'real100')},
                'worlds': {w: {m: ci([by[p, s, w][m] - by[ref, s, w][m] for s in seeds]) for m in ('exp100', 'real100')}
                           for w in worlds}}
        out['presets'][p] = res
    return out


def show(summary, refs, worlds):
    for ref in refs:
        print('\npaired expected MSMI/100 vs %s (95%% CI); * = CI excludes 0' % ref)
        print('%-26s %8s %8s  %-24s' % ('preset', 'exp', 'real', 'overall diff') + ''.join('%17s' % w[:16] for w in worlds))
        for p, r in summary['presets'].items():
            d = r.get('vs_' + ref)
            cell = lambda c: '%+.4f%s' % (c['mean'], '*' if c['lo'] > 0 or c['hi'] < 0 else ' ')
            line = '%-26s %8.4f %8.4f  ' % (p, r['overall']['exp100'], r['overall']['real100'])
            if d is None:
                print(line + '(reference)')
                continue
            o = d['overall']['exp100']
            print(line + '%-24s' % ('%+.4f [%+.4f,%+.4f]' % (o['mean'], o['lo'], o['hi']))
                  + ''.join('%17s' % cell(d['worlds'][w]['exp100']) for w in worlds))
    print('\n%-26s %7s %7s %6s %7s %8s %8s' % ('preset', 'intros', 'd0-20', 'cov', 'ask', 'mean_s', 'max_s'))
    for p, r in summary['presets'].items():
        o = r['overall']
        print('%-26s %7.1f %7.1f %6.3f %7.1f %8.3f %8.3f' % (p, o['intros'], o['intros_d0_20'], o['coverage'],
                                                         o['ask_cost'], o['mean_call_s'], o['max_call_s']))
    print('invalid episodes:', summary['invalid_episodes'])


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--presets', required=True)
    p.add_argument('--refs', default='greedy')
    p.add_argument('--worlds', default='all')
    p.add_argument('--seeds', default='201-230')
    p.add_argument('--workers', type=int, default=2)
    p.add_argument('--detail', action='store_true')
    p.add_argument('--output', required=True)
    args = p.parse_args()
    presets, refs = args.presets.split(','), args.refs.split(',')
    for x in presets + refs:
        if not register(x):
            p.error('unknown preset ' + x)
    worlds = list(VARIANTS) if args.worlds == 'all' else args.worlds.split(',')
    seeds = parse_seeds(args.seeds)
    jobs = [('-', pr, s, w, args.detail) for pr in dict.fromkeys(presets + refs) for w in worlds for s in seeds]
    with Pool(args.workers) as pool:
        rows = pool.map(episode, jobs, chunksize=1)
    summary = summarise(rows, list(dict.fromkeys(presets + refs)), refs, worlds, seeds)
    show(summary, refs, worlds)
    out = os.path.join(ROOT, args.output) if not os.path.isabs(args.output) else args.output
    with open(out, 'w') as fh:
        json.dump({'presets': presets, 'refs': refs, 'worlds': worlds, 'seeds': args.seeds,
                   'configs': {x: __import__('policy').PRESETS[x] for x in dict.fromkeys(presets + refs)},
                   'summary': summary, 'episodes': rows}, fh)
    print('wrote', out)
