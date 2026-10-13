"""Headroom analysis with exact expected MSMI (analysis only)."""
import itertools, json, sys, statistics as S, collections
import networkx as nx
from multiprocessing import Pool
from kit import Simulator, generate, eligibility, baseline_asks, baseline_match
from expected import p_msmi
import policy as base

VARIANTS=('development','sparse','cold_start','delayed','shift','drift')

def feasible_edges(st):
    av=[m for m in st['members'] if m['available']]
    past={tuple(sorted((i['user_a'],i['user_b']))) for i in st['introductions']}
    for a,b in itertools.combinations(av,2):
        k=tuple(sorted((a['member_id'],b['member_id'])))
        if k not in past and eligibility(a,b)['status']=='feasible': yield k

def match_oracle(st,sim,how):
    v=sim.world['variant'];E=[(a,b,p_msmi(sim.members[a],sim.members[b],v,sim.day)) for a,b in feasible_edges(st)]
    if how=='mwm':
        G=nx.Graph();G.add_weighted_edges_from(E);return [list(e) for e in nx.max_weight_matching(G)]
    used=set();out=[]
    for a,b,_ in sorted(E,key=lambda e:-e[2]):
        if a not in used and b not in used: out.append([a,b]);used|={a,b}
    return out

def run(args):
    name,seed,variant=args
    sim=Simulator(generate(seed,200,'evaluation',variant))
    for _ in range(60):
        st=sim.observe()
        sim.resolve_asks([] if name=='no_asks' else baseline_asks(st))
        st=sim.observe()
        if name in('greedy','no_asks'): pairs=baseline_match(st)
        elif name=='random': pairs=base.decide({'phase':'match','state':st,'memory':None},'random')['pairs']
        else: pairs=match_oracle(st,sim,name.split('_')[1])
        sim.advance(pairs)
    N=sum(m['arrived_day']<=59 for m in sim.members.values())
    exp=sum(p_msmi(sim.members[i['user_a']],sim.members[i['user_b']],variant,i['assigned_day']) for i in sim.introductions)
    for _ in range(40): sim.advance([])
    return dict(name=name,seed=seed,variant=variant,N=N,intros=len(sim.introductions),
                exp100=100*exp/N,real100=sim.metrics()['msmi_per_100_arrived_members'])

if __name__=='__main__':
    names=sys.argv[1].split(',');seeds=range(int(sys.argv[2]),int(sys.argv[3]))
    jobs=[(n,s,v) for n in names for v in VARIANTS for s in seeds]
    with Pool(2) as p: rows=p.map(run,jobs)
    json.dump(rows,open(sys.argv[4],'w'),indent=1)
    for n in names:
        rs=[r for r in rows if r['name']==n]
        fam=lambda k:{v:S.mean(r[k] for r in rs if r['variant']==v) for v in VARIANTS}
        e,rl=fam('exp100'),fam('real100')
        print(n,'EXPECTED',round(S.mean(e.values()),4),{k:round(x,3) for k,x in e.items()},'| realised',round(S.mean(rl.values()),4),'| intros',round(S.mean(r['intros'] for r in rs),1))
