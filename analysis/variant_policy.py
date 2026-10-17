"""Run any policy.py preset through the official evaluator (EVALUATION ONLY, never in the image).

evaluate.py can only pass --baseline to the policy, so the preset comes from an environment
variable that the evaluator's subprocess inherits:

    POLICY_VARIANT=greedy python evaluate.py --policy analysis/variant_policy.py \
        --seeds 101,102,103 --variants all --output results/final_greedy.json
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import policy  # noqa: E402

if __name__ == '__main__':
    print(json.dumps(policy.decide(json.load(sys.stdin), variant=os.environ.get('POLICY_VARIANT', 'greedy')),
                     allow_nan=False))
