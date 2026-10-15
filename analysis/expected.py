"""Exact expected MSMI of an introduction, from the PUBLIC simulator's hidden truth.
EVALUATION/ANALYSIS ONLY: never imported by a submitted policy.
Integrates the shared pair shock (N(0, .45)) with Gauss-Hermite quadrature.
"""
import math
import numpy as np

GH_X, GH_W = np.polynomial.hermite_e.hermegauss(40)
GH_W = GH_W / GH_W.sum()
SHARED = 0.45 * GH_X


def sig(z):
    return 1 / (1 + np.exp(-z))


def accept_logit(a, b, variant, day):
    f, g = a['truth'], b['truth']
    w = {'relationship_goal': .7, 'relationship_pace': .4, 'lifestyle': .25, 'conversations': .2}
    if variant == 'shift':
        w = {'relationship_goal': .25, 'relationship_pace': .8, 'lifestyle': -.25, 'conversations': .5}
    fit = sum(v * (1 if f[k] == g[k] else -.5) for k, v in w.items())
    return -.25 + a['bias'] + fit + (-.5 if variant == 'drift' and day >= 35 else 0)


def p_date_within_30(variant):
    # date = max(resp delays U1..7) + U1..14 (+U5..12 if delayed); need <= 30
    if variant != 'delayed':
        return 1.0
    tot = ok = 0
    for d1 in range(1, 8):
        for d2 in range(1, 8):
            for g in range(1, 15):
                for e in range(5, 13):
                    tot += 1
                    ok += max(d1, d2) + g + e <= 30
    return ok / tot


_P30 = {}


def p_msmi(a, b, variant, day, logit_shift=0.0, date_variant=None):
    """logit_shift / date_variant: extra acceptance shift and date-delay regime for the
    analysis-only world variants in worlds.py (defaults reproduce the kit exactly)."""
    date_variant = date_variant or variant
    if date_variant not in _P30:
        _P30[date_variant] = p_date_within_30(date_variant)
    goal = .4 * (a['truth']['relationship_goal'] == b['truth']['relationship_goal'])
    acc = (sig(accept_logit(a, b, variant, day) + logit_shift + SHARED)
           * sig(accept_logit(b, a, variant, day) + logit_shift + SHARED))
    sec = sig(.15 + a['second_bias'] + SHARED + goal) * sig(.15 + b['second_bias'] + SHARED + goal)
    rr = a['response_rate'] * b['response_rate']
    # both respond, both accept, date happens (.78) within 30d, both answer, both yes, both on time (3/5 each)
    return float(rr * .78 * _P30[date_variant] * rr * .36 * (GH_W * acc * sec).sum())
