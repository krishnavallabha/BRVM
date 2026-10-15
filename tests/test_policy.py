"""Fuzz + validity tests for the policy safety shell. Run: python -m unittest -v"""
import copy
import json
import sys
import time
import unittest
from unittest import mock

import policy
from evaluate import invoke, validate_response
from kit import HARD, SOFT, Simulator, eligibility, generate
from misfits import asks, match

PRESETS = sorted(policy.PRESETS)


def check(test, state, resp, phase):
    """Every response must pass the kit's shape check and our full validity rules."""
    validate_response(resp, phase)
    test.assertLess(len(json.dumps(resp['memory'], allow_nan=False).encode()), policy.MEMORY_LIMIT)
    avail = {m['member_id']: m for m in state['members'] if m['available']}
    if phase == 'ask':
        seen, cost = set(), 0
        for a in resp['asks']:
            test.assertIn(a['member_id'], avail)
            test.assertIn(a['field'], ['constraints'] + SOFT)
            test.assertNotIn((a['member_id'], a['field']), seen)
            seen.add((a['member_id'], a['field']))
            status = avail[a['member_id']]['field_status']
            if a['field'] == 'constraints':
                test.assertTrue(any(status[k] == 'not_asked' for k in HARD))
                cost += 3
            else:
                test.assertNotIn(status[a['field']], ('observed', 'declined'))
                cost += 1
        test.assertLessEqual(cost, state['ask_budget_remaining'])
    else:
        past = {tuple(sorted((i['user_a'], i['user_b']))) for i in state['introductions']}
        used = set()
        for a, b in resp['pairs']:
            test.assertIn(a, avail)
            test.assertIn(b, avail)
            test.assertFalse({a, b} & used)
            used |= {a, b}
            test.assertNotIn(tuple(sorted((a, b))), past)
            test.assertEqual(eligibility(avail[a], avail[b])['status'], 'feasible')


def run_both(test, state, memory=None, **kw):
    """Run ask + match on one state for every preset; check each response."""
    for preset in PRESETS:
        for phase in ('ask', 'match'):
            with test.subTest(preset=preset, phase=phase):
                resp = policy.decide({'phase': phase, 'state': copy.deepcopy(state),
                                      'memory': copy.deepcopy(memory)}, variant=preset, **kw)
                check(test, state, resp, phase)


class PolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # A real 200-member episode run to day 59: the largest request we'll ever see.
        sim = Simulator(generate(211, 200, 'evaluation', 'development'))
        memory = None
        for _ in range(59):
            r = policy.decide({'phase': 'ask', 'state': sim.observe(), 'memory': memory})
            sim.resolve_asks(r['asks'])
            r = policy.decide({'phase': 'match', 'state': sim.observe(), 'memory': r['memory']})
            sim.advance(r['pairs'])
            memory = r['memory']
        cls.big, cls.big_memory = sim.observe(), memory
        cls.day0 = Simulator(generate(212, 200, 'evaluation', 'development')).observe()

    def test_empty_members(self):
        run_both(self, Simulator(generate(1, 0)).observe())

    def test_nobody_available(self):
        st = copy.deepcopy(self.day0)
        for m in st['members']:
            m['available'] = False
        run_both(self, st)
        for phase in ('ask', 'match'):
            r = policy.decide({'phase': phase, 'state': st, 'memory': None})
            self.assertEqual(r['asks' if phase == 'ask' else 'pairs'], [])

    def test_all_fields_none(self):
        st = copy.deepcopy(self.day0)
        for m in st['members']:
            m['fields'] = {k: None for k in m['fields']}
            m['field_status'] = {k: 'not_asked' for k in m['field_status']}
        run_both(self, st)
        self.assertEqual(policy.decide({'phase': 'match', 'state': st, 'memory': None})['pairs'], [])

    def test_all_fields_declined(self):
        st = copy.deepcopy(self.day0)
        for m in st['members']:
            m['fields'] = {k: None for k in m['fields']}
            m['field_status'] = {k: 'declined' for k in m['field_status']}
        run_both(self, st)
        for preset in PRESETS:
            r = policy.decide({'phase': 'ask', 'state': st, 'memory': None}, variant=preset)
            self.assertEqual(r['asks'], [])

    def test_every_pair_already_introduced(self):
        st = copy.deepcopy(self.big)
        av = [m for m in st['members'] if m['available']]
        st['introductions'] += [{'introduction_id': 'x%d_%d' % (i, j), 'user_a': a['member_id'],
                                 'user_b': b['member_id'], 'assigned_day': 0}
                                for i, a in enumerate(av) for j, b in enumerate(av) if i < j]
        run_both(self, st)
        for preset in PRESETS:
            r = policy.decide({'phase': 'match', 'state': st, 'memory': None}, variant=preset)
            self.assertEqual(r['pairs'], [])

    def test_largest_request(self):
        self.assertGreater(len(self.big['introductions']), 50)
        self.assertGreater(len(self.big['feedback']), 100)
        for preset in PRESETS:
            for phase in ('ask', 'match'):
                t0 = time.perf_counter()
                r = policy.decide({'phase': phase, 'state': copy.deepcopy(self.big),
                                   'memory': copy.deepcopy(self.big_memory)}, variant=preset)
                self.assertLess(time.perf_counter() - t0, 2.0, (preset, phase))
                check(self, self.big, r, phase)

    def test_bad_memory(self):
        for memory in (None, {}, 'junk', [1, 2], 7, {'v': 2}, {'v': 1, 'asks': 5, 'match': None},
                       {'v': 1, 'asks': {'x': [1] * 300000}}):  # last one is over the 800 KB limit
            with self.subTest(memory=str(memory)[:40]):
                run_both(self, self.day0, memory)

    def test_chooser_raises(self):
        def boom(*_):
            raise RuntimeError('boom')
        with mock.patch.object(asks, 'choose', boom), mock.patch.object(match, 'choose', boom):
            run_both(self, self.big)
            self.assertEqual(policy.decide({'phase': 'ask', 'state': self.big, 'memory': None})['asks'], [])

    def test_chooser_returns_garbage(self):
        av = [m['member_id'] for m in self.big['members'] if m['available']]
        junk = [None, 'x', ['a'], [av[0], av[0]], ['nobody', av[0]], {'member_id': 'nobody', 'field': 'constraints'},
                {'member_id': av[0], 'field': 'nope'}, [av[0], av[1], av[2]]]
        for out in (junk, None, 'str', 42):
            for mem in ({'v': 1, 'match': {'x': float('nan')}}, object(), None):
                with mock.patch.object(asks, 'choose', lambda *_: (out, mem)), \
                        mock.patch.object(match, 'choose', lambda *_: (out, mem)):
                    run_both(self, self.big)

    def test_chooser_hangs(self):
        with mock.patch.object(policy, 'SOFT_LIMIT', 0.3), \
                mock.patch.object(match, 'choose', lambda s, m, c: time.sleep(3)):
            t0 = time.perf_counter()
            r = policy.decide({'phase': 'match', 'state': self.big, 'memory': None})
            self.assertLess(time.perf_counter() - t0, 1.5)
            check(self, self.big, r, 'match')

    def test_deterministic(self):
        for preset in PRESETS:
            for phase in ('ask', 'match'):
                req = {'phase': phase, 'state': self.big, 'memory': self.big_memory}
                self.assertEqual(policy.decide(copy.deepcopy(req), variant=preset),
                                 policy.decide(copy.deepcopy(req), variant=preset))

    def test_real_process_largest_request(self):
        for phase in ('ask', 'match'):
            resp, elapsed = invoke([sys.executable, 'policy.py'],
                                   {'schema_version': '1.0.0', 'phase': phase, 'state': self.big,
                                    'memory': self.big_memory})
            check(self, self.big, resp, phase)
            self.assertLess(elapsed, 5.0)


if __name__ == '__main__':
    unittest.main()
