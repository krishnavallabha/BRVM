"""Ask phase (owner: Rishi). Day 1 stub: reproduces kit greedy exactly."""
from kit import baseline_asks


def choose(state, memory, config):
    """Return (asks, memory). asks = [{'member_id': str, 'field': 'constraints' | <soft field>}]"""
    if config.get('ask_order') == 'none':
        return [], memory
    return baseline_asks(state), memory
