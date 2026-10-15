"""World variants for experiments (EVALUATION ONLY). kit.py is never edited: we wrap generate()
and subclass Simulator. make(name, seed) -> (world, simulator_class, expected_fn(a, b, day)).

  development, sparse, cold_start, delayed, shift, drift   the 6 standard families
  dense             Q1: development + every member accepts 2-3 zones, ages +-12, 2+ genders more often
  q2_sparse_delayed Q2: sparse population with delayed dates
  q2_switch30       Q2: standard until day 29, then drift-style acceptance (-0.5) and delayed dates
  q2_mixed_arrivals Q2: 40% arrive on day 0, the rest spread over days 1-40
"""
import copy
import math
import random
from kit import GENDERS, Simulator, generate
from evaluate import VARIANTS
from expected import p_msmi

ZONES = ['zone_a', 'zone_b', 'zone_c', 'zone_d']
SWITCH_DAY = 30


def _sync_observed(m, keys):
    for k in keys:
        if m['fields'][k] is not None:
            m['fields'][k] = copy.deepcopy(m['truth'][k])


def dense(seed):
    w = generate(seed, 200, 'evaluation', 'development')
    r = random.Random(seed * 7919 + 1)
    for m in w['members']:
        t = m['truth']
        t['acceptable_zones'] = [m['zone']] + r.sample([z for z in ZONES if z != m['zone']], r.randint(1, 2))
        t['age_min'], t['age_max'] = max(18, m['age'] - 12), min(65, m['age'] + 12)
        if len(t['who_to_meet']) == 1 and r.random() < .5:
            t['who_to_meet'] = t['who_to_meet'] + [r.choice([g for g in GENDERS if g not in t['who_to_meet']])]
        _sync_observed(m, ('acceptable_zones', 'age_min', 'age_max', 'who_to_meet'))
    return w


def mixed_arrivals(seed):
    w = generate(seed, 200, 'evaluation', 'development')
    r = random.Random(seed * 104729 + 3)
    for m in w['members']:
        a = 0 if r.random() < .4 else r.randint(1, 40)
        m['arrived_day'] = a
        m['field_observed_day'] = {k: (a if v is not None else None) for k, v in m['fields'].items()}
    return w


class SwitchSimulator(Simulator):
    """Standard until SWITCH_DAY, then acceptance logit -0.5 and delayed dates."""
    def _prob(self, a, b, shared):
        p = super()._prob(a, b, shared)
        if self.day < SWITCH_DAY:
            return p
        return 1 / (1 + math.exp(-(math.log(p / (1 - p)) - .5)))

    def advance(self, pairs):
        self.world['variant'] = 'delayed' if self.day >= SWITCH_DAY else 'development'
        super().advance(pairs)


def make(name, seed):
    if name in VARIANTS:
        return generate(seed, 200, 'evaluation', name), Simulator, lambda a, b, d: p_msmi(a, b, name, d)
    if name == 'dense':
        return dense(seed), Simulator, lambda a, b, d: p_msmi(a, b, 'development', d)
    if name == 'q2_sparse_delayed':
        w = generate(seed, 200, 'evaluation', 'sparse')
        w['variant'] = 'delayed'  # population generated sparse, simulator dynamics delayed
        return w, Simulator, lambda a, b, d: p_msmi(a, b, 'delayed', d)
    if name == 'q2_switch30':
        return (generate(seed, 200, 'evaluation', 'development'), SwitchSimulator,
                lambda a, b, d: p_msmi(a, b, 'development', d) if d < SWITCH_DAY
                else p_msmi(a, b, 'development', d, logit_shift=-.5, date_variant='delayed'))
    if name == 'q2_mixed_arrivals':
        return mixed_arrivals(seed), Simulator, lambda a, b, d: p_msmi(a, b, 'development', d)
    raise ValueError('unknown world ' + name)
