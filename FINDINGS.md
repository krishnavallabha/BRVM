# Round 2 — first findings (12 Oct 2026)

Team The Misfits. Kit: `RomeoJulietLove/The-Sequential-Matching-Problem` @ `a8e26b3`.

## 1. Baselines reproduce exactly (official evaluator, seeds 101–103 × 6 variants)

| Policy | Primary score | Coverage | Ask cost |
|---|---|---|---|
| greedy | 0.3889 | 0.372 | 206.7 |
| random | 0.2778 | 0.377 | 206.7 |
| no_asks | 0.1389 | 0.143 | 0 |

Matches Team 2's published numbers. Files: `results/greedy.json`, `random.json`, `no_asks.json`.

## 2. Where members are lost (greedy, seeds 201–210 × 6 variants, `harness.py`)

| Variant | Coverage | Coverage ceiling* | Members blocked by a declined hard field |
|---|---|---|---|
| development | 0.350 | 0.361 | 34% |
| sparse | 0.172 | 0.173 | 33% |
| cold_start | 0.316 | 0.319 | 41% |
| delayed / shift / drift | ≈0.35 | 0.361 | 34% |

*Members with at least one partner who is feasible under full truth (declined fields stay unknown).

- **Greedy already serves almost everyone who can ever be served.** Coverage is capped by declined hard fields, which keep a member blocked forever.
- All askable members are asked by about day 12–17. After that, most of the 12-unit daily budget sits idle.
- **The feasible graph is tiny:** 11–200 feasible pairs per 200-member pool, a mean of about 2.5 partners per member. Greedy uses 70–100% of them (all of them in sparse worlds).

Funnel over 4,283 greedy introductions:

| Stage | Count | % of introductions |
|---|---|---|
| Both responded | 2,465 | 57.6% |
| Mutual acceptance | 676 | 15.8% |
| Date happened | 537 | 12.5% |
| Both said Yes again | 147 | 3.4% |
| **MSMI** (both on time) | 31 | **0.72%** |

## 3. Headroom: exact expected MSMI (`expected.py`, `analysis.py`, seeds 201–205 × 6)

`expected.py` computes each introduction's exact expected MSMI from the public simulator's internals. It is used **for evaluation only** and never imported by a policy.

| Policy | Expected MSMI / 100 | Realised MSMI / 100 |
|---|---|---|
| no_asks | 0.121 | 0.067 |
| greedy | 0.348 | 0.233 |
| random | 0.362 | 0.217 |
| oracle greedy (true pair probabilities) | 0.360 | 0.317 |
| oracle max-weight matching (true probabilities) | **0.372** | 0.317 |

- **In expectation, greedy is not better than random.** Greedy's public-seed lead (0.389 vs 0.278) is luck.
- **Even a policy that knows every true probability gains only about +7% over greedy** with myopic matching. Selection headroom is small because there are few pairs to choose between.
- Asking is the one big lever: no_asks loses about 65%.

## 4. Noise

| Quantity | Per-episode SD |
|---|---|
| Realised MSMI / 100 (greedy) | 0.41 |
| Paired difference, oracle MWM − greedy, realised | 0.44 |
| Paired difference, oracle MWM − greedy, **expected** | **0.041** |

The expected-value yardstick cuts paired noise about 10×, so it needs about 100× fewer seeds. With realised outcomes, detecting a +0.025 gain would take more than 1,000 episodes. The private ranking of 120 episodes cannot reliably separate competent policies.

## 5. Implications for our Round 2 plan

1. Evaluate everything on **expected MSMI with paired worlds**, and report realised MSMI alongside it.
2. Sampled-future reservation prices (reviewer question 1): on these sparse graphs, the bound on any myopic selection is +7%. Test the reservation-price ladder on **denser stress worlds**, where choice actually exists, and report the honest result.
3. The levers we can actually learn are pair quality from feedback (person responsiveness and acceptance tendency) and cheap soft-field asks with the idle budget (relationship goal and pace). Ask *ordering* is a possible further lever.
4. Fairness (reviewer question 3): track who waits and who is never served, broken down by responsiveness.
