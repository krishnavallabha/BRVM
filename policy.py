"""Team The Misfits policy: entry point + safety shell.

Reads only the request JSON (state, memory). Every output is re-validated and any
exception or soft-time-limit breach falls back to a safe answer. Diagnostics -> stderr.

Config selection: --variant <preset> wins; else --baseline no_asks|random pick the kit
baselines; else (including the evaluator's default `--baseline greedy`) DEFAULT_CONFIG.
"""
import argparse
import copy
import json
import sys
import threading
from kit import HARD, SOFT, baseline_match, eligibility
from misfits import asks, match

SOFT_LIMIT = 6.0                 # seconds for choose(); the hard limit is 10 s per call
MEMORY_LIMIT = 800 * 1024        # bytes

PRESETS = {
    'greedy': {'ask_order': 'greedy', 'soft_asks': False, 'match': 'greedy'},
    'no_asks': {'ask_order': 'none', 'soft_asks': False, 'match': 'greedy'},
    'random': {'ask_order': 'greedy', 'soft_asks': False, 'match': 'random'},
    'maxcard': {'ask_order': 'greedy', 'soft_asks': False, 'match': 'maxcard'},
    'maxcard_quality': {'ask_order': 'greedy', 'soft_asks': False, 'match': 'maxcard_quality'},
    # Rishi Day 2: maxcard_quality matching + soft-field clarification with idle budget
    'maxcard_quality_soft': {'ask_order': 'greedy', 'soft_asks': True, 'match': 'maxcard_quality'},
    'ask_missing_hard': {'ask_order': 'missing_hard', 'soft_asks': False, 'match': 'greedy'},
    'soft_asks': {'ask_order': 'greedy', 'soft_asks': True, 'match': 'greedy'},
    'soft_asks_resolved': {'ask_order': 'greedy', 'soft_asks': 'resolved', 'match': 'greedy'},
    'ask_partners': {'ask_order': 'partners', 'soft_asks': False, 'match': 'greedy'},
    'ask_partners_soft': {'ask_order': 'partners', 'soft_asks': True, 'match': 'greedy'},
    'full': {'ask_order': 'partners', 'soft_asks': True, 'match': 'maxcard_quality'},
    'full_resolved': {'ask_order': 'partners', 'soft_asks': 'resolved', 'match': 'maxcard_quality'},
    # Day 3 ablations: full minus one feature
    'full-partners': {'ask_order': 'greedy', 'soft_asks': True, 'match': 'maxcard_quality'},
    'full-soft': {'ask_order': 'partners', 'soft_asks': False, 'match': 'maxcard_quality'},
    'full-maxcard': {'ask_order': 'partners', 'soft_asks': True, 'match': 'greedy'},
    'full-quality': {'ask_order': 'partners', 'soft_asks': True, 'match': 'maxcard'},
}
# Day 3 (16 Oct): full = partners ask order + agreed soft asks + max pairs with quality tie-break.
# +0.0084 [+0.002, +0.015] expected MSMI/100 vs greedy on 201-230; ties full_resolved at 1/2.7 the ask cost.
DEFAULT_CONFIG = PRESETS['full']


def log(msg):
    print('[policy] ' + msg, file=sys.stderr)


def fresh_memory(memory):
    """Shared namespace dict; anything malformed is reset."""
    if not isinstance(memory, dict) or memory.get('v') != 1:
        memory = {'v': 1}
    for key in ('asks', 'match'):
        if not isinstance(memory.get(key), dict):
            memory[key] = {}
    return memory


def memory_ok(memory):
    try:
        return len(json.dumps(memory, allow_nan=False).encode()) <= MEMORY_LIMIT
    except (TypeError, ValueError):
        return False


def valid_asks(state, asks_out):
    """Drop invalid asks: unknown/unavailable member, bad field, observed/declined field,
    duplicates, and anything beyond the remaining budget."""
    members = {m['member_id']: m for m in state['members'] if m['available']}
    budget = state['ask_budget_remaining']
    out, seen = [], set()
    for ask in asks_out if isinstance(asks_out, list) else []:
        if not isinstance(ask, dict):
            continue
        ident, field = ask.get('member_id'), ask.get('field')
        m = members.get(ident) if isinstance(ident, str) else None
        if m is None or (ident, field) in seen:
            continue
        if field == 'constraints':
            useful, cost = any(m['field_status'][k] == 'not_asked' for k in HARD), 3
        elif field in SOFT:
            useful, cost = m['field_status'][field] not in ('observed', 'declined'), 1
        else:
            continue
        if not useful or cost > budget:
            continue
        seen.add((ident, field))
        budget -= cost
        out.append({'member_id': ident, 'field': field})
    return out


def valid_pairs(state, pairs):
    """Drop invalid pairs: bad shape, unavailable, not feasible, repeat, person reused."""
    members = {m['member_id']: m for m in state['members'] if m['available']}
    past = {tuple(sorted((i['user_a'], i['user_b']))) for i in state['introductions']}
    out, used = [], set()
    for pair in pairs if isinstance(pairs, list) else []:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            continue
        a, b = pair
        if not (isinstance(a, str) and isinstance(b, str)) or a == b:
            continue
        if a not in members or b not in members or a in used or b in used:
            continue
        if tuple(sorted((a, b))) in past or eligibility(members[a], members[b])['status'] != 'feasible':
            continue
        used.update((a, b))
        out.append([a, b])
    return out


def run_limited(fn, *args):
    """Run fn in a daemon thread; raise on exception or SOFT_LIMIT breach."""
    box = {}

    def target():
        try:
            box['result'] = fn(*args)
        except BaseException as e:  # noqa: BLE001 - surfaced to the caller below
            box['error'] = e
    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(SOFT_LIMIT)
    if t.is_alive():
        raise TimeoutError('soft time limit %.1fs hit' % SOFT_LIMIT)
    if 'error' in box:
        raise box['error']
    return box['result']


def pick_config(mode, variant):
    if variant:
        return PRESETS[variant]
    if mode in ('no_asks', 'random'):
        return PRESETS[mode]
    return DEFAULT_CONFIG


def decide(request, mode='greedy', variant=None):
    phase = request.get('phase')
    state = request.get('state') or {}
    memory = fresh_memory(request.get('memory'))
    if not memory_ok(memory):
        log('incoming memory invalid or too large; reset')
        memory = fresh_memory(None)
    key = 'asks' if phase == 'ask' else 'pairs'
    try:
        config = pick_config(mode, variant)
        chooser = asks.choose if phase == 'ask' else match.choose
        # choose() gets its own copy, so a timed-out thread can't mutate what we return
        out, new_memory = run_limited(chooser, state, copy.deepcopy(memory), dict(config))
        out = valid_asks(state, out) if phase == 'ask' else valid_pairs(state, out)
        if not memory_ok(new_memory):
            log('returned memory invalid or too large; keeping previous memory')
            new_memory = memory
        out_mem = fresh_memory(new_memory)
        if not out_mem.get('asks') and not out_mem.get('match'):
            out_mem = {}
        return {key: out, 'memory': out_mem}
    except Exception as e:  # noqa: BLE001 - any failure -> safe fallback
        log('fallback in %s phase: %r' % (phase, e))
        fb_mem = fresh_memory(memory)
        if not fb_mem.get('asks') and not fb_mem.get('match'):
            fb_mem = {}
        if phase == 'ask':
            return {'asks': [], 'memory': fb_mem}
        try:
            return {'pairs': valid_pairs(state, baseline_match(state)), 'memory': fb_mem}
        except Exception as e2:  # noqa: BLE001
            log('greedy fallback failed too: %r' % (e2,))
            return {'pairs': [], 'memory': fb_mem}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', choices=['greedy', 'no_asks', 'random'], default='greedy')
    parser.add_argument('--variant', choices=sorted(PRESETS), default=None)
    args = parser.parse_args()
    request = json.load(sys.stdin)
    print(json.dumps(decide(request, args.baseline, args.variant), allow_nan=False))
