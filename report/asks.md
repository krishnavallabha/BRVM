# Ask phase: question order, soft questions and complementary questions (Q3a)

Team The Misfits · owner: Rishi Mehrotra (experiments run and written up with Krishna, 15–17 Oct).
All worlds are synthetic. None of these numbers describe real people.

**Yardstick:** paired *expected* MSMI per 100 arrived members (`analysis/expected.py`), identical worlds for every policy, a 95% CI on the per-seed paired difference, and an equal-weight mean over the 6 families (see REPORT.md §4).

## 1. Why the ask phase matters most

- Without questions, expected MSMI falls by **71%** (`no_asks` −0.2732 vs greedy on 301–340). Clarification is the single biggest lever in this problem.
- A pair can be introduced only when *every* hard field of *both* people is known. A `constraints` ask (3 units) reveals all non-declined hard fields; a soft-field ask costs 1 unit. The daily budget is 12 units, so at most 4 hard bundles a day.
- At the start about 45 members need a bundle, which takes roughly 11 days. All askable members are asked by about day 12–17, after which most of the budget is idle.

So two decisions matter: **who gets the 4 bundles first**, and **what to do with the idle budget**.

## 2. Design (`misfits/asks.py`)

| Config | Behaviour |
|---|---|
| `ask_order: 'greedy'` | kit `baseline_asks`: the first `budget // 3` eligible members in list order (reproduces the kit exactly) |
| `ask_order: 'partners'` (shipped) | score = **likely partner count**, the other available members (not introduced before) whose pair is anything but `infeasible`, so unknown fields don't block; plus **+10** for arrivals in the last 3 days; ties by `member_id`; take the top `budget // 3` |
| `ask_order: 'missing_hard'` | Day 1 variant: most `not_asked` hard fields first |
| `soft_asks: True` (shipped) | left-over budget on `relationship_goal`, then `relationship_pace`, only for members with **≥ 2 feasible available partners**, most partners first. A soft answer can change a choice only when there is more than one option |
| `soft_asks: 'resolved'` | Day 2 broad variant: every soft field in priority order, for anyone whose hard fields are resolved |

Candidates are always available members with a `not_asked` hard field and no declined hard field. The shell (`policy.py`) re-checks every ask: available member, valid field, never `observed` or `declined`, no duplicates, total cost ≤ budget. Partner counts use one eligibility pass per call, and the worst ask-phase call is under 0.5 s.

## 3. Results

### 3.1 Item 1: question order (dev seeds 201–230 × 6)

| vs greedy | Diff [95% CI] | Intros days 0–20 (greedy 42.2) |
|---|---|---|
| `missing_hard` | +0.0013 [−0.0028, +0.0055] | — |
| partners, bonus 0 | +0.0015 [−0.0047, +0.0077] | 43.0 |
| **partners, bonus 10 (chosen)** | +0.0023 [−0.0036, +0.0083] | 43.1 |
| partners, bonus 25 | +0.0017 [−0.0041, +0.0076] | 43.1 |
| partners, bonus 50 | +0.0006 [−0.0060, +0.0072] | 42.9 |

On its own the ordering is a small, non-significant lift that brings introductions forward. Likely partner counts are about 25–85, so a bonus of 10 nudges new arrivals up without overriding connectivity. Inside the final policy, removing it costs −0.0012 [−0.0087, +0.0063] (REPORT.md §5.1). Its clearest benefit is Q3a (§4): it unlocks complementary pairs sooner.

### 3.2 Item 3: soft questions and ask cost (dev seeds 201–230 × 6)

| Comparison | Diff [95% CI] | Ask cost / episode |
|---|---|---|
| greedy → soft questions (agreed design) | +0.0018 [−0.0007, +0.0043] | 196 → 208 |
| greedy → broad soft questions | **+0.0061 [+0.0025, +0.0098]** | 196 → **556** |
| `maxcard_quality` → + broad soft questions | **+0.0034 [+0.0007, +0.0060]** | 196 → 555 |
| partners → partners + agreed soft questions | **+0.0043 [+0.0019, +0.0067]** | 196 → 208 |
| full (agreed) → full with broad soft questions | −0.0004 [−0.0025, +0.0017] | 208 → **557** |

**Reading.**
- Soft questions pay only when the match phase uses the answers. That happens through the kit greedy soft-field ordering or our quality tie-break, and through the person and fit models in the shipped policy.
- On their own, broad questions look best (+0.0061). Inside the final policy they add **nothing** over the narrow agreed design, at **2.7× the ask cost**. Lower ask cost is an official tie-breaker, so the agreed design ships: +12 units per episode instead of +360.

## 4. Q3a: can complementary questions defeat an independent-item planner?

**Setup** (`analysis/q3a.py`, `results/q3a_complementary.json`, seeds 201–215 × 6 = 90 worlds). A pair is *blocked by both* when, on the first day both members are present, each has a `not_asked` hard field. `kit.eligibility` needs every hard field of both people, so neither question alone can make the pair feasible.

**Part A, exact test on the initial pools.** We took every pair blocked by both that is truly compatible once fully known (truth is used only to label pairs). For each we revealed one member's hard fields, then the other's, then both.

| | Pairs |
|---|---|
| Truly compatible pairs blocked by both | **953** |
| Feasible after asking only one member | **0** |
| Feasible after asking both | **953** |

An **independent-item planner**, one that values a question by the feasible pairs it unlocks *on its own*, gives each half a value of **exactly 0** and the pair as a whole a value of 1. If it only asks questions with positive value, it never unlocks these pairs.

**Part B, how much this matters in real episodes** (90 episodes per policy):

| Policy | Feasible pairs | Blocked by both | Both asked | Wait from co-presence to unlock, median / p90 | Lag between the two asks, median / p90 | Same-day completion |
|---|---|---|---|---|---|---|
| greedy order | 8,287 | 1,801 (**22%**) | 100% | 6 / 13 days | 5 / 14 days | 5% |
| **partners order (shipped)** | 8,287 | 1,801 (**22%**) | 100% | **4 / 12 days** | 5 / 13 days | 8% |

By family, blocked-by-both pairs are 17% of feasible pairs in development, delayed, shift and drift, 24% in sparse, and **43% in cold start**.

**Answer.**
- **Yes:** complementary questions defeat an independent-item planner. About a fifth of all feasible pairs, and almost half in cold start, would be invisible to it.
- **Our planner is not independent-item.** The partner-count score counts partners who are *not yet infeasible*, treating unknown fields as possibly compatible. So both halves of a complementary pair score positively and both get asked (100%).
- It also does this **sooner** than list order: the median wait to unlock is 4 days instead of 6.
- Because every askable member is eventually asked within about 17 days, the gain is in *timing*, not in how many pairs are ultimately unlocked. A planner with joint value-of-information (pairs of questions valued together) could shorten the lag further. We did not build one, because the measured headroom is small and its runtime risk is real.

## 5. Limitations

- The partner count uses public attributes and observed fields only. It cannot see declined-but-compatible members, who can never be unlocked anyway.
- The +10 arrival bonus was tuned on dev seeds 201–230; it is a heuristic, not a learned value.
- Q3a labels compatibility with simulator truth, which is legitimate for evaluation but never available to the policy.
