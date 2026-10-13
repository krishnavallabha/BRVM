"""Fast in-process episode runner + diagnostics (development only).

Mirrors evaluate.episode() without subprocesses so we can run many seeds.
Hidden truth is read ONLY here, for analysis; policies never see it.
"""
import collections, json, statistics, sys
from multiprocessing import Pool
from kit import Simulator, generate, eligibility, HARD, SOFT
from evaluate import VARIANTS


def run(args):
    policy_name, mode, seed, variant = args
    decide = __import__(policy_name).decide
    sim = Simulator(generate(seed, 200, 'evaluation', variant))
    memory, used_budget, askable_left, idle = None, [], [], []
    for _ in range(60):
        st = sim.observe()
        r = decide(json.loads(json.dumps({'phase': 'ask', 'state': st, 'memory': memory})), mode)
        memory = r['memory']
        sim.resolve_asks(r['asks'])
        used_budget.append(sim.ask_spent)
        st = sim.observe()
        askable_left.append(sum(m['available'] and any(m['fields'][k] is None for k in HARD)
                                and not any(m['field_status'][k] == 'declined' for k in HARD) for m in st['members']))
        r = decide(json.loads(json.dumps({'phase': 'match', 'state': st, 'memory': memory})), mode)
        memory = r['memory']
        avail = [m for m in st['members'] if m['available']]
        paired = {i for p in r['pairs'] for i in p}
        idle.append(sum(m['member_id'] not in paired for m in avail))
        sim.advance(r['pairs'])
    arrived = {i for i, m in sim.members.items() if m['arrived_day'] <= 59}
    for _ in range(40):
        sim.advance([])
    met = sim.metrics()
    ms = sim.members
    # permanently blocked: some hard field declined -> never 'feasible'
    blocked = {i for i in arrived if any(ms[i]['field_status'][k] == 'declined' for k in HARD)}
    # oracle-feasible partners using truth for every non-declined field
    def tview(m):
        f = {k: (None if m['field_status'][k] == 'declined' else m['truth'][k]) for k in m['truth']}
        return dict(m, fields=f)
    tv = {i: tview(ms[i]) for i in arrived}
    has_partner = {i for i in arrived if any(j != i and eligibility(tv[i], tv[j])['status'] == 'feasible' for j in arrived)}
    served = {x for it in sim.introductions for x in (it['user_a'], it['user_b'])}
    # funnel
    ev = collections.defaultdict(list)
    for e in sim.events:
        ev[e['introduction_id']].append(e)
    f = collections.Counter()
    for it in sim.introductions:
        es = ev[it['introduction_id']]
        rs = [e for e in es if e['event'] == 'introduction_response']
        f['intros'] += 1
        f['both_responded'] += all(e['value'] is not None for e in rs)
        f['mutual'] += all(e['value'] == 'yes' for e in rs)
        ds = [e for e in es if e['event'] == 'date_happened']
        f['date_happened'] += any(e['value'] for e in ds)
        f['date_le30'] += any(e['value'] and e['occurred_day'] - it['assigned_day'] <= 30 for e in ds)
        ss = [e for e in es if e['event'] == 'second_meeting_intention']
        f['both_second_yes'] += len(ss) == 2 and all(e['value'] == 'yes' for e in ss)
        f['msmi'] += (any(e['value'] and e['occurred_day'] - it['assigned_day'] <= 30 for e in ds) and len(ss) == 2
                      and all(e['value'] == 'yes' and e['occurred_day'] - ds[0]['occurred_day'] <= 3 for e in ss))
        a, b = ms[it['user_a']], ms[it['user_b']]
        f['goal_match'] += a['truth']['relationship_goal'] == b['truth']['relationship_goal']
    N = len(arrived)
    return dict(policy=policy_name, mode=mode, seed=seed, variant=variant, N=N,
                msmi100=100 * met['mutual_second_meeting_intention'] / N,
                coverage=len(served & arrived) / N,
                blocked_frac=len(blocked) / N, oracle_cov_ceiling=len(has_partner) / N,
                ask_cost=met['ask_cost'], days_budget_unused_while_askable=sum(u < 12 and a > 0 for u, a in zip(used_budget, askable_left)),
                first_day_no_askable=next((d for d, a in enumerate(askable_left) if a == 0), None),
                mean_idle_available=statistics.mean(idle), funnel=dict(f))


def batch(policy, mode, seeds, variants=VARIANTS, procs=2):
    jobs = [(policy, mode, s, v) for v in variants for s in seeds]
    with Pool(procs) as p:
        return p.map(run, jobs)


def summary(rows):
    fam = collections.defaultdict(list)
    for r in rows:
        fam[r['variant']].append(r)
    fm = {v: statistics.mean(r['msmi100'] for r in rs) for v, rs in fam.items()}
    return statistics.mean(fm.values()), fm


if __name__ == '__main__':
    policy, mode, s0, s1 = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    rows = batch(policy, mode, range(s0, s1))
    out = f'results/diag_{policy}_{mode}_{s0}_{s1}.json'
    json.dump(rows, open(out, 'w'), indent=1)
    print(summary(rows))
