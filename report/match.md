# Match phase: maximum pairs, quality tie-breaks, waiting (Q1) and who waits (Q3b)

Team The Misfits · owner: Siddharth Malkania (Day 3 experiments run and written up with Krishna, 16 Oct).
All worlds are synthetic. None of these numbers describe real people.

**Yardstick.** Unless stated otherwise, comparisons use paired *expected* MSMI per 100 arrived members (`analysis/expected.py`). Both policies run on identical worlds. The 95% CI is on the per-seed paired difference, and the overall figure is the equal-weight mean over the 6 families. This yardstick has about 10× lower paired noise than realised MSMI, and it was validated against realised outcomes on 360 episodes (`FINDINGS.md` §6). Realised MSMI is reported alongside.

## 1. Design

Each day the match phase builds the **feasible graph**: available members as nodes, and an edge for every pair with `kit.eligibility == 'feasible'` that has not been introduced before. It then returns a matching on that graph. `policy.py` re-checks every returned pair (availability, feasibility, repeats, a person used twice) and falls back to kit greedy on any error or soft-time-limit breach.

| Config `match` | What it does |
|---|---|
| `greedy` | kit baseline: sort edges by the number of equal observed soft fields, take greedily |
| `maxcard` | `networkx.max_weight_matching(G, maxcardinality=True)` with unit weights: the most pairs per day |
| `maxcard_quality` | same, with weight `1000 + q(i, j)`: still the most pairs, and quality only breaks ties between maximum matchings |

`q(i, j)` is a **hand-set prior over observed soft fields only**, with 0 when a field is unknown. `relationship_goal` is +3 / −1.5 (equal / different), `relationship_pace` +1.5 / −0.75, `lifestyle` +0.5 / −0.25, and `conversations` +0.4 / −0.2. These are not learned values. They follow the public knowledge that goal fit is the strongest acceptance factor. Because the base weight of 1000 dominates any `q`, cardinality is never traded for quality.

**Runtime.** Edmonds' blossom algorithm on graphs of at most 200 nodes: mean 0.10–0.35 s per in-process call, worst case below 2.5 s under full CPU load. There is a 3 s internal guard that falls back to greedy. `networkx` is imported lazily, because the policy process restarts on every call and the import costs about 1 s.

## 2. Item 2: maximum pairs, and quality tie-breaks (seeds 201–230 × 6)

| Comparison | Overall diff [95% CI] | Introductions / episode |
|---|---|---|
| greedy → `maxcard` | −0.0052 [−0.0110, +0.0006] | 72.4 → 72.3 |
| `maxcard` → `maxcard_quality` | **+0.0056 [+0.0009, +0.0103]** | 72.3 → 72.3 |
| greedy → `maxcard_quality` | +0.0004 [−0.0051, +0.0060] | 72.4 → 72.3 |

- **Maximum cardinality alone does not add introductions.** The daily feasible graph is tiny and mostly a forest (about 2.5 partners per member), so greedy already finds a maximum or near-maximum matching. Unit weights then throw away greedy's soft-fit ordering, which is why `maxcard` is slightly worse.
- **Quality tie-breaks recover that,** with exactly the same number of introductions. On their own they only reach parity with greedy.
- The matcher earns its place **in combination with the ask phase**, because soft answers feed `q`. See §3.

## 3. Contribution inside the final policy (confirmation seeds 301–340, first use)

Final policy `full` = partners ask order + soft asks (goal, pace) + `maxcard_quality`. Remove-one ablations, 240 episodes each, 0 invalid (`results/confirmation_301_340.json`):

| Preset | vs greedy [95% CI] | vs full [95% CI] |
|---|---|---|
| **full** | **+0.0092 [+0.0011, +0.0174]** | — |
| full − maxcard (kit greedy matcher, which also orders by soft fit) | +0.0086 [+0.0017, +0.0154] | −0.0007 [−0.0070, +0.0056] |
| full − quality (unit-weight `maxcard`) | +0.0011 [−0.0061, +0.0083] | **−0.0082 [−0.0142, −0.0021]** |

**What the matcher contributes.** It is the *soft-fit awareness*, not the maximum cardinality.
- Swapping the quality tie-break for unit weights wipes out the whole gain of `full`.
- Swapping max-pairs for kit greedy, which also ranks by observed soft-field agreement, costs nothing measurable: introductions are 77.2 vs 76.7.
- On sparse feasible graphs the two matchers find nearly the same number of pairs. What matters is that, among those pairs, the ones with known goal and pace agreement are chosen. That is also why the matcher only pays off once the ask phase spends idle budget on goal and pace.
- We keep `maxcard_quality` rather than greedy because it guarantees the maximum number of pairs when graphs are denser (dense worlds: 207 introductions per episode), at no cost here.

## 4. Q1: does waiting ever help? (reservation prices)

**Setup.** "λ = 0" is our default: match everything maximal today. **Simple reservation** (`reserve_k`): before matching, drop an edge if *both* endpoints have at least `k` other feasible partners today *and* the edge's quality is below the day's median edge quality. The idea is that both people can afford to wait for a better partner. We tested this on standard worlds and on **denser stress worlds** (`analysis/worlds.py: dense`): every member accepts 2–3 zones, ages ±12, and a single-gender `who_to_meet` gets a second gender with probability 0.5. The kit itself is not edited.

Dense worlds have about 3× the introductions (207 vs 72 per episode) and about 3× the expected MSMI (1.14 vs 0.37 per 100), so choice genuinely exists.

| World (seeds) | vs λ = 0 | Overall diff [95% CI] | Introductions / episode |
|---|---|---|---|
| dense (201–260) | k = 1 | +0.0035 [−0.0146, +0.0216] | 207.4 → 202.8 |
| dense (201–260) | k = 2 | −0.0004 [−0.0154, +0.0145] | 207.4 → 205.1 |
| dense (201–260) | k = 3 | +0.0067 [−0.0079, +0.0214] | 207.4 → 207.3 |
| standard, 6 families (201–230) | k = 3 | +0.0005 [−0.0005, +0.0016] | 72.4 → 72.4 (rarely triggers: few members have ≥ 3 other partners on one day) |

Files: `results/q1_dense_201_260.json`, `results/q1_standard_201_230.json`. k was tuned on the dense worlds, where choice exists, and the best value (k = 3) was then checked on standard worlds.

**Answer: no.** No reservation level gives a gain distinguishable from zero, even in dense worlds. The mechanics explain why:
- an introduction blocks both people for only 8 days, whatever the outcome;
- the horizon is 60 days, and outcomes are dominated by individual tendencies and response rates rather than pair fit;
- so a skipped pair is a lost chance that later better pairs rarely make up for.

The sampled-future LP-dual variant was not attempted. The headroom bound (a perfect-information myopic matcher gains only about +7% over greedy) and these results suggest little to gain. This is a negative result, reported as such.

## 5. Q3b: who waits, and who is never served

`analysis/q3b.py` on the confirmation episodes (seeds 301–340 × 6, 240 episodes and 48,000 members per policy) → `results/q3b_waiting.json`. Wait = days from arrival to first introduction, among served members. "Unblocked" = no declined hard field. Members with a declined hard field can never be introduced by any valid policy.

| Policy | Served | Wait median / p90 (days) | Never served | Never served, unblocked |
|---|---|---|---|---|
| greedy | 16,707 | 4 / 16 | 31,293 | 14,776 / 31,483 (46.9%) |
| full | 16,766 | 3 / 16 | 31,234 | 14,717 / 31,483 (46.7%) |

**By true responsiveness** (`response_rate` terciles; analysis-only view the policy never sees):

| Group | greedy: served share, wait median / p90 | full: served share, wait median / p90 |
|---|---|---|
| low (< 0.69) | 33.6%, 4 / 16 | 33.8%, 3 / 16 |
| mid (0.69–0.84) | 35.9%, 4 / 16 | 36.0%, 3 / 17 |
| high (≥ 0.84) | 34.8%, 5 / 16 | 34.9%, 3 / 16 |

**By observed no-response rate** (the policy's own view; served members only, since unserved members have no feedback):

| Group | greedy: members, wait median / p90 | full: members, wait median / p90 |
|---|---|---|
| no observed no-response | 10,277, 5 / 17 | 10,450, 4 / 17 |
| ≤ 50% no-response | 3,800, 2 / 12 | 3,797, 1 / 11 |
| > 50% no-response | 2,630, 5 / 19 | 2,519, 4 / 18 |

**Findings.**
- **Who is never served is decided by constraints, not by the policy.** About half (53%) of never-served members declined a hard field (permanently blocked). The rest are mostly members with no reciprocally feasible partner who is available at the right time. Both policies serve the same people within 0.2 percentage points; `full` serves about 0.25 more members per episode.
- **`full` shortens the typical wait by about one day** (median 4 → 3) through its partner-count ask order, which unlocks connectable members first. The 90th percentile is unchanged at about 16 days: the slow tail is late arrivals and members whose only partners are busy.
- **No disparity by responsiveness.** Served shares and waits are flat across true response-rate terciles, for both policies. Neither policy uses responsiveness, so unresponsive members are not deprioritised, and responsive ones are not favoured either.
- **In the observed view, members with > 50% no-responses wait longest at the p90** (18–19 days). This is a timing artefact, not discrimination: no-responses are revealed only at the 7-day deadline, and people with few introductions show extreme rates. A policy that down-weighted observed non-responders (Siddharth's optional Day 2 idea, not implemented) could raise MSMI. It would make this tail longer and should be judged against that fairness cost.

## 6. Limitations

- `q(i, j)` is a hand-set prior. With about 0.7% of introductions ending in MSMI there is too little signal to learn pair weights reliably within an episode.
- The dense worlds are our own construction. They test whether waiting *can* help when choice exists. They are not a forecast of the private worlds.
- Expected MSMI is computed from the public simulator's mechanics. The private worlds may differ in ways no public-simulator yardstick can see.
