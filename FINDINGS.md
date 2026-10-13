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

## 6. Yardstick validation (greedy, seeds 201–260 × 6 families = 360 episodes, 13 Oct)

`python analysis/yardstick.py --preset greedy --seeds 201-260` → `results/yardstick_validation.json`.
z = (realised − expected) / sqrt(Σ p(1−p)); CI = 95% CI of the per-episode difference (realised − expected) per 100.

| Family | Expected MSMI | Realised MSMI | R/E | z | Exp / 100 | Real / 100 | Diff / 100 [95% CI] |
|---|---|---|---|---|---|---|---|
| development | 55.4 | 51 | 0.92 | −0.60 | 0.462 | 0.425 | −0.037 [−0.169, +0.096] |
| sparse | 14.4 | 19 | 1.32 | +1.23 | 0.120 | 0.158 | +0.039 [−0.038, +0.115] |
| cold_start | 43.8 | 36 | 0.82 | −1.20 | 0.365 | 0.300 | −0.065 [−0.159, +0.029] |
| delayed | 51.6 | 41 | 0.80 | −1.49 | 0.430 | 0.342 | −0.088 [−0.191, +0.015] |
| shift | 48.2 | 47 | 0.98 | −0.17 | 0.402 | 0.392 | −0.010 [−0.138, +0.118] |
| drift | 52.3 | 47 | 0.90 | −0.74 | 0.436 | 0.392 | −0.044 [−0.170, +0.082] |
| **Overall** | **265.7** | **241** | **0.91** | **−1.53** | **0.369** | **0.335** | **−0.034 [−0.080, +0.011]** |

**Verdict: the yardstick is consistent with realised outcomes.** Every family's CI contains 0 and no |z| exceeds 1.5, so there is no evidence of bias and nothing in `expected.py` needs fixing. Realised MSMI does come in below expected in 5 of 6 families (overall ratio 0.91, z = −1.53, p ≈ 0.13), and `delayed` is the closest call (z = −1.49), so it is worth re-checking once more episodes accumulate (the Day 3 confirmation on 301–340 adds 240). A code re-read of `expected.py` against `kit.py` (date window, the 0.78 date chance, the 3/5 on-time chance, both response-rate draws, the shared shock, drift from the assigned day; exits and pauses don't affect outcomes after an introduction) found no mismatch. The earlier 0.348 vs 0.233 gap on 201–205 was small-sample noise. Use expected MSMI for comparisons, and keep reporting realised alongside it.

## 7. Day 1 skeleton check (13 Oct)

- New `policy.py` (safety shell + `misfits/` greedy stubs), official evaluator, seeds 101–103 × 6: **0.3889**, coverage 0.3717, ask cost 206.7, all 18 episodes valid, and **every episode's `action_sha256` is identical to the kit greedy run** (`results/day1_policy_check.json` vs `results/greedy.json`).
- `analysis/compare.py --a greedy --b greedy`: paired difference exactly 0 in every family (deterministic). Mean call time about 0.08 s, max about 0.3 s in-process.

## 8. Item 2: Maximum-pairs matching (Siddharth Day 1, 14 Oct)

`python analysis/compare.py --a greedy --b maxcard --seeds 201-230` → `results/compare_greedy_vs_maxcard_201-230.json`.
Global maximum-weight matching on the feasible graph using Edmonds' blossom algorithm (`networkx.max_weight_matching(G, maxcardinality=True)`) with unit edge weights ($w=1$).

| Family | expA (greedy) | expB (maxcard) | Diff exp [95% CI] | realA | realB | intrA | intrB | covA | covB | askA | askB |
|---|---|---|---|---|---|---|---|---|---|---|---|
| development | 0.4506 | 0.4357 | −0.0149 [−0.0257, −0.0041] | 0.3833 | 0.3167 | 86.0 | 85.2 | 0.364 | 0.364 | 188.9 | 188.9 |
| sparse | 0.1149 | 0.1139 | −0.0009 [−0.0028, +0.0010] | 0.1000 | 0.1000 | 21.9 | 21.9 | 0.171 | 0.171 | 188.5 | 188.5 |
| cold_start | 0.3531 | 0.3606 | +0.0074 [−0.0068, +0.0217] | 0.2500 | 0.2833 | 72.0 | 73.0 | 0.314 | 0.313 | 231.7 | 231.7 |
| delayed | 0.4144 | 0.4052 | −0.0092 [−0.0200, +0.0015] | 0.3500 | 0.4500 | 81.5 | 81.6 | 0.362 | 0.363 | 188.9 | 188.9 |
| shift | 0.3913 | 0.3885 | −0.0027 [−0.0162, +0.0107] | 0.4333 | 0.3167 | 86.8 | 86.6 | 0.364 | 0.366 | 188.9 | 188.9 |
| drift | 0.4222 | 0.4114 | −0.0108 [−0.0204, −0.0011] | 0.3500 | 0.3167 | 86.3 | 85.8 | 0.364 | 0.365 | 188.9 | 188.9 |
| **OVERALL** | **0.3577** | **0.3526** | **−0.0052 [−0.0110, +0.0006]** | **0.3111** | **0.2972** | **72.4** | **72.3** | **0.323** | **0.324** | **196.0** | **196.0** |

- **Runtime & Reliability**: 0 invalid episodes out of 360. Per-call inference time inside Python is fast: mean call time is 0.0605 s (max 0.228 s), well below the 3.0 s fallback threshold.
- **Verdict & Recommendation**: Do not replace greedy with standalone unit-weight `maxcard` yet. Because the daily feasible graph is sparse and mostly tree-like, maximum cardinality alone yields virtually the same number of introductions as greedy (72.3 vs 72.4) and identical coverage (0.324 vs 0.323). However, greedy sorts edges by observed soft-field matches, whereas unit-weight `maxcard` treats all edges as identical ($w = 1$), occasionally selecting lower-compatibility pairs. This precisely validates the Day 2 design: keep the global maximum-cardinality matching engine, but layer soft-compatibility quality weights ($weight = 1000 + q(i, j)$) to break ties in favor of high-quality introductions.

