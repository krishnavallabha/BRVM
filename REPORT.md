# Technical report: sequential reciprocal matching under uncertainty

**Team The Misfits** (Krishna Vallabha Goswami, Rishi Mehrotra, Siddharth Malkania) · Round 2 build · October 2026
Synthetic data only: nothing in this report is evidence about real people (§8).

Every number below comes from a committed JSON file in `results/`, and the commands to regenerate it are in [README.md](README.md). The full lab notebook is [FINDINGS.md](FINDINGS.md). Match-phase details are in [report/match.md](report/match.md).

---

## Summary

1. **Measure before modelling.** We built an exact *expected*-MSMI yardstick from the public simulator's mechanics (evaluation only) and validated it against realised outcomes on 360 episodes. It cuts paired noise about 10× (SD 0.44 → 0.04 per episode), so a ±1% effect can be detected at all.
2. **The ceiling is low.** A matcher that knows every true probability gains only about +7% over greedy. Clarification is the big lever: no questions loses about 70%.
3. **What we ship (`full_person_learn`):** partner-count question order, cheap goal and pace questions, and maximum pairs whose tie-breaks use observed soft-field fit, a hierarchical Bayesian model of each person's responsiveness and acceptance, and an online-learned fit model.
   - The simple core (`full`) beats greedy by **+0.0092 [+0.0011, +0.0174]** on reserved seeds 301–340 and by +0.0073 [+0.0009, +0.0138] on fresh seeds 341–380.
   - The Bayesian layer adds **+0.0041 [+0.0012, +0.0071]** on 341–380, for **+0.0115 [+0.0044, +0.0186] over greedy (+3.0%)**, with no family clearly worse.
   - It is valid in every episode we ran: the real subprocess protocol (0.46 s per call) and the **final container check (6/6 valid, 0.95 s median per call, actions identical to the local run)**.
4. **Honest answers to the reviewer.** Q1: waiting, whether simple reservation or our own sampled-future prices, never measurably helps. Q2: the gain survives overlapping and switching conditions without recognising families. Q3b: no disparity by responsiveness. Calibration of the observable models is reported.
5. **Bayesian layer (Round 1 BRVM, revisited).** Person-level Beta-Binomial models and an online fit model are calibrated and adapt in the `shift` family. After two calibration fixes their matching gain was confirmed on fresh seeds 341–380, and they ship. Sampled-future slot prices were tested and dropped.

---

## 1. Hypothesis, objective and decision structure

**Objective.** Maximise MSMI per 100 arrived members, the official primary score: both accept, a date within 30 days, and both say yes again within 3 days. Tie-breakers follow the official order. Validity in all 120 private episodes comes first.

**Hypothesis (Round 2, after measuring).** Selection headroom is small because the feasible graph is tiny (about 2.5 partners per member). So value comes from (a) unlocking feasible pairs sooner through better *clarification*, and (b) choosing, among equally large daily matchings, the pairs whose *observed* soft fields agree.

**Reciprocal eligibility.** A pair is introduced only if `kit.eligibility(a, b)['status'] == 'feasible'`: every hard field known for both, all reciprocal checks passing, both available, never introduced before, nobody used twice in a day. Unknown never means compatible, and a declined hard field means never feasible. `policy.py` re-checks every pair and *drops* any failure.

**Allocation.** Each day: the maximum number of pairs on the feasible graph (Edmonds' blossom), with edge weight `1000 + q_hat(i, j) + 2 (s_i + s_j)`, so quality only breaks ties between maximum matchings.
- `q_hat` is soft-field fit from the online Bayesian logistic model. Its prior is the hand-set weights (goal +3/−1.5, pace +1.5/−0.75, small lifestyle and conversation terms, 0 when unknown), so with no feedback it equals the hand-set `q`.
- `s_i = log E[r_i^2] + log E[acc_i]` is member i's posterior response-and-acceptance score relative to the pool (§5.4).

**Waiting.** λ = 0: we never hold back a feasible pair. Q1 (§6) shows that waiting does not pay in these worlds.

**Clarification.** 12 units per day.
- Hard bundles (3 units) go to members with the most *likely* partners: other members not yet `infeasible` with them, with unknown fields not blocking. New arrivals (last 3 days) get +10.
- Left-over budget goes to `relationship_goal`, then `relationship_pace` (1 unit each), only for members with ≥ 2 feasible partners, since a soft answer can change a choice only when there is more than one option.

**Probability estimates.** These are optional. The Bayesian layer (§5.4) predicts three targets per introduction, each at decision time from the request alone:
- *directional response*: P(member responds within the 7-day window);
- *directional acceptance*: P(member says yes | responded);
- *directional acceptance from fit*: P(i says yes to j | i responded).

Joint (mutual) acceptance is not claimed as a product of directional probabilities, because the simulator's shared pair shock correlates the two.

## 2. Observations, missingness and leakage

- **Inputs:** only the request JSON (`state`, `memory`), as POLICY_INTERFACE.md requires. The policy imports nothing from `analysis/`, reads no hidden fields (`truth`, `bias`, `response_rate`), no seeds and no organiser files. `analysis/` is never copied into the image.
- **Missing and declined answers:** `field_status` separates `not_asked`, `observed` and `declined`. Declined hard fields make a member permanently ineligible; the shell never asks a declined or observed field. About 34% of members decline a hard field, which caps coverage at about 36%.
- **Delayed feedback:** responses arrive 1–7 days after an introduction, non-responses only at the 7-day deadline, and second-meeting answers up to 5 days after a date. The person model counts an opportunity **only once it is resolved**. Counting open introductions inflated every response rate (calibration showed 0.9 predicted vs 0.7 observed), and this fix is in `misfits/bayes.py`.
- **Selective labels:** we observe outcomes only for pairs we introduced. Missing responses are not treated as rejections. The fit model learns only from explicit yes/no answers.
- **Leakage prevention in evaluation:** the expected-MSMI yardstick reads simulator truth, but only in `analysis/`, after decisions are made. Development used seeds 201–260; confirmation seeds 301–340 and 341–380 were each used once, after the design was frozen.

## 3. Training, inference assets, randomness, dependencies, tools

- **No offline training and no inference assets.** All models are fitted online from the request on every call, with no memory needed.
- **Randomness: none.** The default policy is deterministic. Ties in the matcher are broken by the deterministic blossom order.
- **Dependencies:** the standard library only. Maximum-weight matching is vendored from NetworkX 3.6.1 (BSD-3) in `misfits/blossom.py`, because the per-call `import networkx` cost about 1 s and pushed container calls towards the 10 s limit (§5.6). It was verified identical to `networkx.max_weight_matching` on 6,000 random graphs and on full policy episodes.
- **External data:** none. **Coding tools:** see AI-tool attribution at the end.

## 4. Baselines on identical seeds and all six families

### 4.1 Official evaluator, public seeds 101–103 × 6 (real subprocess protocol)

All 18 episodes are valid for every policy. Files: `results/final.json` (shipped default), `final_full.json`, `final_greedy.json`, `final_random.json`, `final_no_asks.json`; expected values from `expected_101_103_final.json`. The greedy actions are identical to the kit's.

| Policy | Score (realised) | Expected MSMI / 100 | Intros / ep | Mutual acc. / ep | Dates / ep | MSMI / ep | Coverage | Unserved / ep | Wait median / p90 | Missing feedback / ep | Ask cost |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **full_person_learn (shipped)** | 0.3056 | 0.3727 | 79.9 | 11.67 | 9.06 | 0.61 | **0.376** | 124.8 | 4 / 16 | 42.6 | 219 |
| full (Day 3 core) | 0.2778 | 0.3620 | 78.5 | 11.94 | 9.22 | 0.56 | 0.375 | 125.1 | 4 / 16 | 41.8 | 220 |
| greedy | 0.3889 | 0.3728 | 79.8 | 11.00 | 8.61 | 0.78 | 0.372 | 125.7 | 4 / 16 | 45.5 | 207 |
| random | 0.2778 | 0.3695 | 80.5 | 10.67 | 8.78 | 0.56 | 0.377 | 124.7 | 5 / 16 | 41.9 | 207 |
| no_asks | 0.1389 | 0.1162 | 24.3 | 3.50 | 2.67 | 0.28 | 0.143 | 171.4 | 0 / 13 | 13.3 | 0 |

**On 18 episodes the realised score is mostly luck.**
- The whole table rests on 10–14 MSMI events per policy.
- Our policies have *more* mutual acceptances and dates than greedy, but lost some of the final "both say yes again" draws.
- The per-episode SD of MSMI / 100 is 0.27–0.35, so gaps of 0.1 are well within noise.
- In expectation the shipped policy ties greedy on these 3 seeds (0.3727 vs 0.3728), and n = 3 cannot separate a ±1% effect. The two 40-seed confirmations below are the evidence.

### 4.2 Paired confirmation on reserved seeds 301–340 × 6 (240 episodes per policy, 0 invalid)

File: `results/confirmation_301_340.json`, run in-process. Expected MSMI / 100, with 95% CI on the per-seed paired difference.

| Policy | Expected | Realised | vs greedy | Intros (days 0–20) | Coverage | Ask cost |
|---|---|---|---|---|---|---|
| greedy | 0.3841 | 0.4521 | — | 76.5 (46.1) | 0.348 | 196 |
| no_asks | 0.1109 | 0.1062 | −0.2732 [−0.290, −0.257] | 22.3 (16.2) | 0.126 | 0 |
| random | 0.3864 | 0.3854 | +0.0024 [−0.003, +0.008] | 77.1 (46.1) | 0.349 | 196 |
| **full** | **0.3933** | 0.4354 | **+0.0092 [+0.0011, +0.0174]** | 76.7 (46.9) | 0.349 | 209 |

No family's CI lies entirely below 0, and `delayed` is clearly positive (+0.017). This matches the dev seeds (+0.0084 on 201–230).

### 4.3 Scenario-level outcomes (all six families)

**Expected MSMI / 100 per family, fresh seeds 341–380** (40 seeds per family; `results/confirmation_341_380.json`):

| Family | greedy | full | **full_person_learn (shipped)** | shipped vs greedy [95% CI] |
|---|---|---|---|---|
| development (standard) | 0.4686 | 0.4738 | **0.4817** | +0.0131 [−0.0006, +0.0269] |
| sparse geography | 0.1165 | 0.1164 | **0.1159** | −0.0006 [−0.0018, +0.0006] |
| cold start | 0.3805 | 0.3973 | **0.3997** | **+0.0193 [+0.0062, +0.0324]** |
| delayed dates | 0.4407 | 0.4501 | **0.4555** | **+0.0148 [+0.0046, +0.0251]** |
| shifted outcome weights | 0.4167 | 0.4193 | **0.4240** | +0.0073 [−0.0044, +0.0189] |
| changing response conditions (drift) | 0.4443 | 0.4544 | **0.4593** | **+0.0150 [+0.0024, +0.0276]** |
| **equal-weight mean** | 0.3779 | 0.3852 | **0.3894** | **+0.0115 [+0.0044, +0.0186]** |

The shipped policy is clearly better in three families and positive in two more. In `sparse` there is almost nothing to choose between (about 22 introductions per episode), so every policy ties.

**Realised MSMI / 100 and coverage per family, official evaluator, seeds 101–103** (3 seeds per family, so these are indicative only; `results/final*.json`):

| Family | greedy | random | no_asks | **shipped** |
|---|---|---|---|---|
| development | 0.500 / 0.432 | 0.333 / 0.440 | 0.167 / 0.183 | **0.333 / 0.435** |
| sparse | 0.167 / 0.145 | 0.167 / 0.145 | 0.000 / 0.043 | **0.000 / 0.145** |
| cold_start | 0.167 / 0.360 | 0.167 / 0.363 | 0.000 / 0.080 | **0.000 / 0.368** |
| delayed | 0.500 / 0.430 | 0.167 / 0.438 | 0.333 / 0.183 | **0.667 / 0.437** |
| shift | 0.500 / 0.432 | 0.500 / 0.433 | 0.167 / 0.183 | **0.500 / 0.437** |
| drift | 0.500 / 0.432 | 0.333 / 0.440 | 0.167 / 0.183 | **0.333 / 0.435** |

Each cell is MSMI / 100 / coverage. Every MSMI cell is 0, 1, 2, 3 or 4 events over 3 episodes, so family-level realised scores at n = 3 are dominated by chance. The shipped policy has the highest or tied-highest coverage in five of six families.

**Yardstick validity** (`results/yardstick_validation.json`, greedy, 360 episodes): realised 241 against 265.7 expected MSMI (ratio 0.91, z = −1.53). Every family's CI contains 0.

## 5. Ablations and design claims

### 5.1 Remove-one ablations of `full` (seeds 301–340)

| Removed | vs full [95% CI] |
|---|---|
| partner-count question order | −0.0012 [−0.0087, +0.0063] |
| soft (goal and pace) questions | −0.0011 [−0.0030, +0.0007] |
| maximum cardinality (kit greedy matcher instead) | −0.0007 [−0.0070, +0.0056] |
| **quality tie-break (unit-weight max pairs)** | **−0.0082 [−0.0142, −0.0021]** |
| all clarification (no_asks) | −0.2824 [−0.300, −0.264] |

**Causal reading.**
- The load-bearing design claim is that **allocation must use observed soft-field agreement**. Unit-weight maximum matching throws away the whole gain.
- Question order, soft questions and maximum cardinality are largely substitutes: any two of the three already give about +0.008 over greedy. That is consistent with the low headroom ceiling.
- Clarification as a whole is indispensable.

### 5.2 Where the remaining value is (`results/headroom2_201_215.json`)

Per 100 members, `full`:
- **captured: 0.372**;
- **feasible but never introduced: 0.101**, of which 0.032 involves a member who exits and 0.069 has both members present throughout;
- **timing loss from drift: 0.004**.

Across feasible pairs, variance in log success probability is explained 24% by response rates, 27% by acceptance and second-meeting tendencies, and 36% by goal match (only 11% in `shift`).

### 5.3 Question order and soft questions (dev seeds 201–230)

| Comparison | Diff [95% CI] | Ask cost |
|---|---|---|
| greedy → partners order (bonus 10, swept over 0/10/25/50) | +0.0023 [−0.004, +0.008] | 196 → 196 |
| greedy → soft questions (agreed design) | +0.0018 [−0.001, +0.004] | 196 → 208 |
| greedy → broad soft questions (every field, anyone resolved) | +0.0061 [+0.003, +0.010] | 196 → 556 |
| full → full with broad soft questions | −0.0004 [−0.003, +0.002] | 208 → 557 |

Inside `full`, broad questioning adds nothing, at 2.7× the ask cost (a tie-breaker). So the agreed narrow design ships.

### 5.4 Bayesian layer (`misfits/bayes.py`, all switchable, all observable-only)

**The models:**
- **Person model:** per-member Beta–Binomial posteriors for responding and for saying yes, using resolved feedback only. The prior mean is the pool rate. The prior *strength* is averaged over a grid weighted by beta-binomial marginal likelihood (hierarchical empirical Bayes). A single best strength jumped between 8 and 400 from episode to episode, because with about 2 observations per member the evidence is flat. Edge bonus: `w · (log E[r²] + log E[acc])` relative to the prior.
- **Fit model:** Bayesian logistic regression (MAP by Newton) of a yes answer on soft-field agreement. The prior means are our hand-set weights / 4, so with no data it equals `q`.
- **Slot prices:** remaining plus sampled-future partners (expected arrivals × the share of the observed pool feasible with the member), divided by remaining introduction slots.

**Calibration** (`results/calibration_201_215.json`, about 13,000 predictions at decision time):
- Response: Brier skill +0.7% vs the pool-rate baseline.
- Yes: +0.55%.
- Fit: +0.15% overall, **+1.7% in `shift`**, where pace matters more than goal. The fit adapts without recognising the family; elsewhere it costs a little.
- All three are monotone. The first run was overconfident at the tails, which motivated the averaged shrinkage.

**Matching effect** (dev seeds 201–230 vs `full`):
- person (w = 2): +0.0020 [−0.0023, +0.0063];
- learned fit: +0.0012 [−0.0016, +0.0039];
- slot price: λ = −1 gives +0.0026, λ = +1 gives −0.0026. *Keeping* scarce members free beats *prioritising* them.

**A tie-breaking effect in `cold_start`** (`results/coldstart_diag_201_260.json`):
- Every new term lost about −0.01 in `cold_start`, whatever its sign or strength.
- A *meaningless* deterministic tie-break did the same (−0.0063 on 201–230 and −0.0071 on fresh 231–260), costing about 1 introduction per episode.
- So in sparse, mostly-unknown graphs, *which* of several equally large matchings is chosen changes future availability. The default blossom order happens to schedule `cold_start` slightly better.
- The person model's `cold_start` loss shrank to −0.0013 on fresh seeds.

**Final confirmation on fresh seeds 341–380** (`results/confirmation_341_380.json`; rule fixed in advance: adopt only if the overall CI vs `full` is above 0 and no family is clearly worse):

| Policy | vs full [95% CI] | vs greedy [95% CI] | Families vs full |
|---|---|---|---|
| greedy | −0.0073 [−0.0138, −0.0009] | — | cold_start clearly worse |
| full | — | +0.0073 [+0.0009, +0.0138] | (third independent confirmation of `full`) |
| full_person (w = 2) | **+0.0036 [+0.0011, +0.0061]** | +0.0109 [+0.0044, +0.0174] | development, delayed, drift clearly better; none clearly worse |
| full_learn | +0.0020 [−0.0003, +0.0042] | +0.0093 [+0.0021, +0.0165] | none clearly different |
| **full_person_learn (shipped)** | **+0.0041 [+0.0012, +0.0071]** | **+0.0115 [+0.0044, +0.0186]** | development clearly better; none clearly worse (cold_start +0.0024) |

All 240 episodes per policy are valid, introductions are unchanged (74.2–74.5 per episode), and the worst in-process call is under 1.0 s.
- Both candidates containing the person model pass the rule. The team chose `full_person_learn`: the learned fit costs nothing at run time, and it is the component that adapts to shifted outcome weights (`shift` calibration skill +1.7%). That is insurance if the private worlds' coefficients differ from the public simulator's.
- Strictly on evidence, the fit's own contribution is not significant (+0.0020, CI touches 0).
- With the averaged shrinkage, the earlier `cold_start` losses disappeared (+0.0024).

### 5.5 Q1: does waiting ever help? (Siddharth; `report/match.md` §4)

| World (seeds) | Variant vs λ = 0 | Diff [95% CI] |
|---|---|---|
| dense, 2–3 zones, ages ±12, more multi-gender (201–260) | simple reservation k = 1 / 2 / 3 | +0.0035 / −0.0004 / +0.0067, all CIs contain 0 |
| standard × 6 (201–230) | simple reservation k = 3 | +0.0005 [−0.0005, +0.0016] |
| dense + unseen arrival mixture (201–260) | simple reservation k = 3 | +0.0034 [−0.004, +0.011] |
| dense + unseen arrival mixture (201–260) | **sampled-future slot prices** (λ = −1) | −0.0029 [−0.012, +0.006] |

**No.** Neither simple reservation nor our own sampled-future prices beat λ = 0, even on dense graphs and unseen arrival mixtures. An introduction blocks people for only 8 days, and outcomes depend more on individual tendencies than on pair fit, so a skipped pair is rarely recovered by a better one. This is the comparison the reviewer asked for, and the simpler method (λ = 0) wins.

### 5.6 Runtime and robustness

- An early container run of the Day 3 build (networkx era) timed out in 2 of 6 episodes (3.2–4.2 s per call). A re-run on the same machine was valid at 1.07 s per call (`results/day3_container_check.json`).
- **Final container check of the shipped build** (`results/container_check.json`, Docker, seed 101 × 6 families): **6/6 valid, median 0.95 s and max 1.07 s per call**. Every episode's `action_sha256` is identical to the local official run of `full_person_learn` (`results/final.json`), so the container runs exactly the evaluated policy.
- We removed the main cost (the per-call `networkx` import, vendoring instead), cut the soft limit from 6 s to 3 s, and made the match fallback deadline-aware: past 4.5 s it returns no pairs rather than computing greedy.
- Local subprocess timing on the previously failing families: median 0.42–0.65 s, worst 0.95 s per call. In-process worst case over 240 confirmation episodes: under 1.8 s under full CPU load.
- **Tests:** 36 (`tests/test_policy.py` plus kit tests). They cover empty pools, nobody available, all fields unknown or declined, every pair already introduced, the largest request, malformed or oversized memory, choosers that raise, return garbage, return NaN memory or hang, the no-time-left fallback, determinism, and vendored-matcher equivalence. A mutation check (validators disabled) makes 30 sub-tests fail.

## 6. Reviewer questions

- **Q1 (sampled-future prices vs zero and simple reservation):** see §5.5. The sign result in §5.4 is the useful lesson: the opportunity cost of using a scarce member is real but small, and it never outweighs the cost of an idle day.
- **Q2 (overlapping and changing conditions, no family recognition)** (`results/q2_changing.json`, seeds 201–260; `full` vs greedy):
  - sparse + delayed: −0.0006 [−0.002, +0.001], nothing to choose between;
  - **switch on day 30** to drift-style acceptance and delayed dates: **+0.0123 [+0.004, +0.021]**;
  - mixed arrivals (40% on day 0, the rest over days 1–40): +0.0079 [−0.002, +0.018];
  - overall: **+0.0065 [+0.002, +0.011]**.

  The online fit model additionally adapts its weights in `shift` (§5.4).
- **Q3a (can complementary questions defeat an independent-item planner?)** **Yes, in principle; our planner avoids the trap.** Details in `report/asks.md` §4 and `results/q3a_complementary.json` (seeds 201–215 × 6):
  - **Exact test:** in the 90 initial pools there are **953 truly compatible pairs blocked by *both* members' missing hard fields**. Asking only one half makes **0** of them feasible; asking both makes all 953 feasible. An independent-item planner that values a question by the pairs it unlocks alone scores each half at **exactly 0**, so it would never ask them.
  - **Scale:** such pairs are **22% of all feasible pairs (43% in `cold_start`)**.
  - **Our ordering:** the partner-count order counts partners who are *not yet infeasible* (unknown fields don't block), so each half gets positive value. Under both greedy and the shipped policy, **100%** of these pairs end up with both people asked.
  - **Speed:** the shipped ordering unlocks them sooner. The wait from co-presence to unlock has median **4 days vs 6** for greedy (p90 12 vs 13), and same-day completion rises from 5% to 8%.
- **Q3b (who waits)** (`results/q3b_waiting.json`, seeds 301–340):
  - median wait 4 → 3 days with `full`; p90 16 in both;
  - never-served is driven by constraints: 53% of never-served members declined a hard field;
  - served shares are flat across true response-rate terciles (33.6% / 35.9% / 34.8% greedy; 33.8% / 36.0% / 34.9% full), so there is no responsiveness disparity;
  - members with > 50% observed no-responses wait longest at p90 (18–19 days), a deadline-timing artefact.

  **Do response penalties leave members waiting disproportionately?** No. The shipped policy's person model down-weights members observed not responding, and we measured it on fresh seeds 341–380 (`results/q3b_waiting_341_380.json`):
  - served shares by true response-rate tercile are greedy 33.5% / 34.2% / 33.4%, full 33.6% / 34.3% / 33.5%, shipped 33.7% / 34.3% / 33.6%;
  - members with > 50% observed no-responses wait median / p90 6 / 20 days under greedy, 4 / 18 under full and 5 / 17 under the shipped policy.

  The penalty only changes ties between equally large matchings, so it reorders *who goes first* but does not exclude anyone.

## 7. Failure cases and uncertainty

- **Sparse supply** (`sparse`, sparse + delayed): about 22 introductions per episode, and every method ties, because there is nothing to choose between. The score is bounded by geography, not policy.
- **Withheld (declined) answers:** about 34% of members can never be introduced, a hard ceiling on coverage (about 0.36) for any valid policy.
- **Cold start:** more missing fields lead to more ties in the matcher, and the tie-breaking order measurably changes scheduling (§5.4). Our asks prioritise connectable members to shorten this phase.
- **Delays:** delayed dates occasionally miss the 30-day date window (P ≈ 0.978 instead of 1), and mutual acceptances keep both people busy for longer, which slows rematching. `full` is clearly positive there (+0.017 on 301–340).
- **Shifted weights:** the hand-set fit prior is wrong in `shift` (pace > goal); the online fit model corrects it partly (§5.4).
- **Contested candidates:** members with several feasible partners are where selection matters. The maximum matching guarantees nobody is double-booked, and quality breaks ties.
- **Low event counts:** about 0.7% of introductions become an MSMI, so a 120-episode realised ranking carries a per-team noise of about ±0.04 against effects of about ±0.01. That is why every comparison here is paired and uses expected MSMI, and why the 18-episode official numbers (§4.1) must not be over-read.

## 8. What synthetic outcomes cannot establish, and the path to product use

These worlds are generated by a published simulator with invented coefficients. Our findings are claims about *this simulator*:
- the low headroom;
- the value of goal and pace questions;
- the uselessness of waiting;
- the tie-breaking effect.

They are not claims about how real people respond, accept or bond. Before any authorised product use (docs/INTEGRATION.md), a production adapter must:
1. map real profile and consent data into the observation contract, with real-time hard-constraint checks;
2. re-estimate every prior (including the hand-set `q`) on authorised outcome data, with calibration checked on held-out observations;
3. review fairness of waiting and serving across protected groups, which this synthetic schema does not model;
4. keep a human in the loop for introductions.

No synthetic probability here is a calibrated estimate for a real member.

## Provenance, licences, AI-tool attribution

- Kit code and data: the organisers' repository at `a8e26b3`, unchanged (LICENSE, DATA_LICENSE.md).
- `misfits/blossom.py`: NetworkX 3.6.1 `max_weight_matching`, BSD-3-Clause, notice included.
- No external data or pretrained models.
- **AI tools:** Claude Code (Anthropic) assisted with writing code, running experiments and drafting this report, under the team's direction. The team designed the approach (Round 1 BRVM proposal), reviewed every change, ran the evaluations and is responsible for all conclusions.

**Team contributions:**
- Krishna: shell, yardstick, tests, merges, confirmations, Q2, Bayesian layer, report.
- Siddharth: maximum-pairs matcher and quality weights, Q1, Q3b, `report/match.md`.
- Rishi: question order and soft questions, Docker and container checks, Q3a.
