"""Q3b: who waits, who is never served (EVALUATION ONLY). Reads a suite.py --detail JSON.

    python analysis/q3b.py results/confirmation_301_340.json --presets greedy,full --output results/q3b_waiting.json

Per preset: wait (days from arrival to first introduction) median / p90 among served members,
never-served counts (all arrived, and excluding members blocked by a declined hard field),
split by TRUE response_rate tercile (analysis view) and by OBSERVED no-response rate (policy view).
"""
import argparse, collections, json, statistics as S

TRUE_BANDS = [('low (<0.69)', 0, .69), ('mid (0.69-0.84)', .69, .84), ('high (>=0.84)', .84, 1.01)]


def obs_band(nr, n):
    if n == 0:
        return 'no feedback yet'
    rate = nr / n
    return 'obs no-resp 0' if rate == 0 else ('obs no-resp <=50%' if rate <= .5 else 'obs no-resp >50%')


def stats(rows):
    waits = sorted(f - a for a, f, *_ in rows if f is not None)
    unblocked = [r for r in rows if not r[2]]
    q = lambda p: waits[min(len(waits) - 1, int(p * len(waits)))] if waits else None
    return {'members': len(rows), 'served': len(waits),
            'wait_median': S.median(waits) if waits else None, 'wait_p90': q(.9),
            'never_served': sum(f is None for _, f, *_ in rows),
            'never_served_unblocked': sum(r[1] is None for r in unblocked), 'unblocked': len(unblocked),
            'never_served_unblocked_share': (sum(r[1] is None for r in unblocked) / len(unblocked)) if unblocked else None}


def analyse(episodes, preset):
    rows = [m for e in episodes if e['preset'] == preset for m in e['members']]
    n_eps = len({(e['seed'], e['family']) for e in episodes if e['preset'] == preset})
    out = {'episodes': n_eps, 'all': stats(rows), 'by_true_response_rate': {}, 'by_observed_no_response': {}}
    for name, lo, hi in TRUE_BANDS:
        out['by_true_response_rate'][name] = stats([r for r in rows if lo <= r[3] < hi])
    groups = collections.defaultdict(list)
    for r in rows:
        groups[obs_band(r[4], r[5])].append(r)
    out['by_observed_no_response'] = {k: stats(v) for k, v in sorted(groups.items())}
    return out


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('suite_json')
    p.add_argument('--presets', default='greedy,full')
    p.add_argument('--output', required=True)
    args = p.parse_args()
    eps = json.load(open(args.suite_json))['episodes']
    res = {pr: analyse(eps, pr) for pr in args.presets.split(',')}
    fmt = lambda s: '%5d %6d %6s %5s %7d %7d/%-5d %6.3f' % (
        s['members'], s['served'], s['wait_median'], s['wait_p90'], s['never_served'],
        s['never_served_unblocked'], s['unblocked'], s['never_served_unblocked_share'] or 0)
    print('%-8s %-22s %5s %6s %6s %5s %7s %13s %6s' % ('preset', 'group', 'memb', 'served', 'w_med', 'w_p90',
                                                      'never', 'never/unblk', 'share'))
    for pr, r in res.items():
        print('%-8s %-22s %s' % (pr, 'ALL', fmt(r['all'])))
        for view in ('by_true_response_rate', 'by_observed_no_response'):
            for g, s in r[view].items():
                print('%-8s %-22s %s' % (pr, g, fmt(s)))
    json.dump({'source': args.suite_json, 'presets': res}, open(args.output, 'w'), indent=1)
    print('wrote', args.output)
