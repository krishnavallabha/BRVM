# CLAUDE.md — Team The Misfits · The Sequential Matching Problem (Round 2 build)

You are helping Team **The Misfits** (Krishna Vallabha Goswami, Rishi Mehrotra, Siddharth Malkania) build the Round 2 entry for **The Sequential Matching Problem**, the Applied Machine Learning Programme & Hackathon by Romeo & Juliet Ltd. × IIT Madras.

**How to use this file:** the user will say something like *"do Krishna Day 1"*, *"do Siddharth Day 2"*, or *"do Rishi Day 3"*. Find that block in **§8 Task board** and carry it out completely. Follow the rules in §3–§6, and finish with the "Done when" check for that block. If a task depends on another person's earlier task that doesn't exist yet, build a minimal stub that meets the interface in §5, and say so.

---

## 1. The challenge (summary)

- Each simulated day, a policy process gets a JSON request and must return either **asks** (clarification questions) or **pairs** (introductions). The day runs `ask` phase → `match` phase. There are 60 decision days, then a 40-day follow-up.
- **Primary score:** MSMI (mutual second-meeting intention) per 100 arrived members. It is averaged within each of the 6 scenario families (`development, sparse, cold_start, delayed, shift, drift`) over 20 private seeds, then averaged equally across families.
- **Tie-breakers, in order:** coverage, mutual acceptances per 100, lower ask cost, lower inference time.
- **Validity is all-or-nothing.** Any invalid ask or pair, malformed output, crash, or timeout over 10 s in any of the 120 private episodes makes the entry ineligible. **Robustness comes before everything else.**
- **Deadline:** pin the final commit SHA in the repo's Final submission issue by **18 Oct 2026, 23:59 IST**. Our internal target is the evening of 18 Oct.
- Kit: `https://github.com/RomeoJulietLove/The-Sequential-Matching-Problem` (commit `a8e26b3`). Read `PROBLEM_STATEMENT.md`, `docs/POLICY_INTERFACE.md`, `docs/DATA_CONTRACT.md` and `docs/SUBMISSION.md` when needed.

## 2. What we already know (our measured findings, 12 Oct)

The full write-up is in `FINDINGS.md`.

- **Baselines reproduce exactly** (official evaluator, seeds 101–103 × 6 families): greedy **0.3889**, random **0.2778**, no_asks **0.1389**.
- **Coverage is already at its ceiling.** About 34% of members decline at least one hard field and stay blocked forever. Greedy serves about 35% of members against a ceiling of about 36%.
- **The feasible graph is tiny:** 11–200 feasible pairs per 200-member pool, about 2.5 partners per member. Greedy uses 70–100% of them.
- **Measured by exact expected MSMI** (`analysis/expected.py`): greedy 0.348, random 0.362, oracle max-weight matching with true probabilities 0.372. **The most any myopic selection can gain is about +7%.** Asking is the big lever: without asks the expected score drops by about 65%.
- **Noise:** realised MSMI has a per-episode SD of about 0.41, and paired differences have an SD of about 0.44. The *expected* MSMI yardstick cuts paired SD to about 0.04 (≈10× lower). **Use it for every comparison**, and report realised MSMI alongside it.
- Funnel for greedy, per introduction: both respond 57.6% → mutual 15.8% → date 12.5% → both Yes again 3.4% → MSMI 0.72%.

### Simulator mechanics that matter (from `kit.py`)

- A member is **feasible** only when every hard field (`HARD`) is known for both people and all reciprocal checks pass. A declined hard field means the member is **never** feasible.
- A `constraints` ask costs 3 units and reveals all non-declined hard fields. A soft-field ask costs 1 unit. The budget is 12 units per day, so at most 4 hard bundles a day.
- After an introduction, both people are **busy for 8 days**, whatever the answer. After mutual acceptance they are busy until the date + 6 days. After an MSMI they are paused for good.
- Acceptance depends on the person's hidden tendency plus soft-field fit. `relationship_goal` match is the strongest factor (+0.7 match / −0.35 mismatch; in the `shift` family it is pace +0.8). Goal match also raises the chance of a second-meeting Yes.
- About 70% of members arrive on day 0 and the rest on days 1–20. About 12% exit at a random day between 22 and 60.

## 3. Hard rules (never break these)

1. **The policy may read only the request JSON** (`state`, `memory`). It must never import or read `expected.py`, `harness.py`, `analysis.py`, simulator internals, `truth`, `bias`, `response_rate`, world seeds, or organiser files. Doing so disqualifies the entry.
2. Every returned pair must be re-checked with `kit.eligibility(a, b)['status'] == 'feasible'`. Both people must be available, the pair must not have been introduced before, and nobody may appear twice in the batch. **Drop** any bad pair; never try to repair it.
3. Asks must name available members only, with no duplicates (member, field), total cost ≤ `state['ask_budget_remaining']`, and fields restricted to `'constraints'` or the names in `kit.SOFT`. Never ask a field whose status is `declined` or `observed`.
4. Any exception, or the soft time limit (6 s) being hit, means returning a safe fallback: in the ask phase `{"asks": [], "memory": memory}`, in the match phase the baseline greedy match (itself re-checked). Diagnostics go to **stderr only**.
5. Memory must be JSON-serialisable, finite (no NaN or Infinity), and stay under 800 KB.
6. Behaviour must be deterministic. Any randomness is seeded from `state['day']` and the phase.
7. **No logic specific to a scenario family.** The policy must not try to guess which family it is in.
8. **Seed discipline:** develop on seeds **201–230**. Seeds **301–340** are reserved for the Day 3 confirmation and nobody touches them before then. Seeds 101–103 are for reproducing the published numbers only.
9. Keep it simple. Fewest files, standard library first. `networkx` is the only extra dependency allowed, pinned in `requirements.txt`.

## 4. Repository layout (target)

```
/ (kit files: kit.py, evaluate.py, verify_data.py, data/, docs/, tests …)
policy.py              # entry point + safety shell (Krishna)
misfits/__init__.py
misfits/asks.py        # ask phase (Rishi)
misfits/match.py       # match phase (Siddharth)
analysis/harness.py    # fast in-process runner + diagnostics      (EVAL ONLY)
analysis/expected.py   # exact expected MSMI from simulator truth  (EVAL ONLY)
analysis/analysis.py   # headroom/oracle comparisons               (EVAL ONLY)
analysis/compare.py    # paired comparison of policy variants      (Krishna Day 1)
tests/test_policy.py   # fuzz + validity tests (Krishna Day 2)
results/               # committed JSON results (force-add; ignored by default)
FINDINGS.md, REPORT.md, README.md, CLAUDE.md
Dockerfile, requirements.txt
```

The evaluation-only files live in `analysis/`. **The Dockerfile must never copy `analysis/`.**

## 5. Interface contract (agreed — do not change without telling the team)

```python
# misfits/asks.py
def choose(state: dict, memory: dict, config: dict) -> tuple[list[dict], dict]:
    """Return (asks, memory). asks = [{'member_id': str, 'field': 'constraints' | <soft field>}]"""

# misfits/match.py
def choose(state: dict, memory: dict, config: dict) -> tuple[list[list[str]], dict]:
    """Return (pairs, memory). pairs = [[id_a, id_b], ...]"""
```

`policy.py` owns `decide(request, mode)`. It calls the right `choose()` inside the safety shell and then validates the output (§3). `config` is a dict of feature switches used for ablations, for example:

```python
DEFAULT_CONFIG = {'ask_order': 'partners', 'soft_asks': True, 'match': 'maxcard_quality'}
```

`mode` keeps the kit's `--baseline greedy|no_asks|random` working, and adds `--variant <name>` to select a config preset for ablations. Each feature must be switchable off, so that greedy is just a config.

Memory layout (shared namespace dict): `memory = {'v': 1, 'asks': {...}, 'match': {...}}`. Each owner writes only their own key.

## 6. How we evaluate (everyone)

- **Fast paired comparison (main tool):** `python analysis/compare.py --a greedy --b <variant> --seeds 201-230`. This runs both policies in-process on identical worlds and reports for each family: mean expected MSMI/100, the paired difference with its 95% CI, realised MSMI/100, introductions, coverage and ask cost.
- **Official check:** `python evaluate.py --seeds 101,102,103 --variants all --output results/<name>.json`, run through the real subprocess protocol.
- **Keep a feature only if** its paired expected-MSMI difference against the current best is positive overall, no family gets clearly worse (CI entirely below 0), and there are zero invalid episodes.
- Any added time per call must be measured. Target under 2 s per call locally.

---

## 7. Background tasks already done (do not redo)

- Kit cloned, baselines reproduced (`results/greedy.json`, `random.json`, `no_asks.json`).
- `analysis/harness.py`, `analysis/expected.py`, `analysis/analysis.py` written. Headroom results are in `results/headroom_201_205.json`.

---

## 8. Task board

### Krishna — Day 1 (Wed 14 Oct): skeleton, shell, yardstick

1. Create the team repo from the kit, keeping the kit files unchanged. Copy in `analysis/`, `FINDINGS.md` and `CLAUDE.md`. Add `misfits/` with `asks.py` and `match.py` **stubs that reproduce greedy exactly** (stub asks = `kit.baseline_asks`, stub match = `kit.baseline_match`).
2. Rewrite `policy.py` as the entry point plus the safety shell, as described in §3 and §5:
   - `decide(request, mode='greedy', variant=None)`: pick a config, call `asks.choose` or `match.choose`, validate the output, and fall back on any exception or time-limit breach.
   - Validators: `valid_asks(state, asks)` and `valid_pairs(state, pairs)`, which drop invalid items. For pairs, use `kit.eligibility`, availability, past pairs and no reuse within the batch.
   - Keep the `--baseline` argument, and add a `--variant` argument.
3. Write `analysis/compare.py`: a paired, in-process comparison of two configs over a seed range and all 6 families, using `expected.p_msmi`. Include a CI on the paired difference, and use multiprocessing with 2 workers.
4. **Validate the yardstick:** run greedy on seeds 201–260 × 6 families (360 episodes) and compare the sum of expected MSMI with realised MSMI, overall and per family. Write the result to `results/yardstick_validation.json` plus a short paragraph in `FINDINGS.md`. If expected and realised disagree beyond the CI, investigate `expected.py` (date window, on-time probability, exits and pauses) before anyone relies on it.

**Done when:** `python evaluate.py --seeds 101,102,103 --variants all` with the new `policy.py` gives **exactly 0.3889** (greedy behaviour), `compare.py greedy vs greedy` shows a difference of 0, and the yardstick validation is written up. Commit and push.

### Rishi — Day 1 (Wed 14 Oct): item 1, question order

Goal: use the 4 hard bundles per day on the members most likely to unlock introductions, so they start being matched sooner.

1. In `misfits/asks.py`, add config `ask_order: 'partners'`. Candidates are available members with any hard field `None` and no hard field `declined`, the same set as greedy.
2. Score each candidate by its **likely partner count**: the number of other available members (observed or not) who pass every check that is *currently checkable* in both directions using only observed fields and public attributes (`gender`, `age`, `zone`). Count a pair as possible if `kit.eligibility` returns anything other than `infeasible`. Use `eligibility()` directly, so unknown fields don't block.
3. Add a bonus for members who arrived in the last 3 days (`state['day'] - arrived_day <= 2`) so new arrivals aren't left at the back of the queue. Make the bonus size a config value and tune it on seeds 201–230 only.
4. Order by score (ties broken by `member_id`) and take the top `budget // 3`.
5. Compare `compare.py --a greedy --b ask_partners --seeds 201-230`. Also report introductions made in days 0–20 compared with greedy.

**Done when:** you have a paired comparison table, call time under 1 s, and a short note in `FINDINGS.md` saying whether to keep it. Commit to the `rishi` branch and open a PR.

### Siddharth — Day 1 (Wed 14 Oct): item 2, maximum-pairs matching

Goal: introduce as many feasible pairs per day as possible, because more introductions raise expected MSMI.

1. In `misfits/match.py`, add config `match: 'maxcard'`. Build the feasible graph each day: available members, `kit.eligibility == 'feasible'`, and not previously introduced.
2. Run `networkx.max_weight_matching(G, maxcardinality=True)` with every edge weight equal to 1. Sort the output pairs for determinism.
3. **Time it:** measure the call on the densest development seeds. If any call goes over 3 s, fall back to `kit.baseline_match`.
4. Compare `compare.py --a greedy --b maxcard --seeds 201-230`. Report introductions per episode, expected MSMI and coverage.
5. Add `networkx` pinned in `requirements.txt` (use `networkx==3.4.2` unless the team picks another, and record its BSD-3 licence).

**Done when:** you have a paired comparison table, timings, and a note in `FINDINGS.md`. Commit to the `siddharth` branch and open a PR.

### Krishna — Day 2 (Thu 15 Oct): fuzz tests, merge, first pin

1. Write `tests/test_policy.py` (unittest), calling `policy.decide` directly with:
   - an empty `members` list, both phases
   - nobody available
   - all fields `None`, all declined
   - every pair already introduced
   - the largest request (200 members, many introductions and feedback rows)
   - `memory` set to `None`, `{}`, or a malformed dict, which must not crash
   - any `asks.choose`/`match.choose` monkey-patched to raise an error, which must fall back to valid output
   - each result passed through the kit's `evaluate.validate_response`, with pairs re-checked for feasibility.
2. Merge the Day 1 PRs that passed their "Done when". Run `python -m unittest -v`, `python verify_data.py`, and the official evaluator on 101–103.
3. Once Rishi's Day 2 container check passes, **pin the first valid build**: commit the SHA and write it down in `FINDINGS.md`.

**Done when:** all tests pass, the merged policy is valid across 101–103 × 6, and the first SHA is recorded.

### Rishi — Day 2 (Thu 15 Oct): item 3 soft questions + Docker

**Item 3: spend the idle budget on soft fields**
1. Config `soft_asks: True`. After hard bundles are chosen, spend the remaining budget on 1-unit soft asks: `relationship_goal` first, then `relationship_pace`.
2. Only ask members who are feasible with **at least 2** available partners. A soft answer can only change a choice when there is more than one option. Ask those with the most feasible partners first.
3. Never ask a field that is `observed` or `declined`, and never duplicate an ask.
4. Compare: `greedy` vs `soft_asks` and `ask_partners` vs `ask_partners+soft_asks`. Report the extra ask cost (it's a tie-breaker). Coordinate with Siddharth, because the value only shows once the match phase uses these answers.

**Docker**
5. Update the `Dockerfile` so it copies `kit.py policy.py misfits/` and **not** `analysis/`. Run `pip install --no-cache-dir -r requirements.txt` at build time. Keep the base `python:3.12.7-slim` and `USER 65534:65534`.
6. `docker build -t sequential-policy:misfits .` then `python evaluate.py --image sequential-policy:misfits --seeds 101 --output results/container_check.json`.
7. Record the time per call inside the container (median and max) from `inference_seconds` divided by 120 calls, in `FINDINGS.md`.

**Done when:** you have a soft-ask comparison table, the container runs a valid episode, and timings are recorded.

### Siddharth — Day 2 (Thu 15 Oct): quality weights on top of max pairs

1. Config `match: 'maxcard_quality'`. Keep the **maximum number of pairs**, and use quality only to break ties: weight = `1000 + q(i, j)`, with `maxcardinality=True`.
2. Build `q(i, j)` from **observed** soft fields only: +3 if `relationship_goal` is known and equal for both, −1.5 if known and different, +1.5 / −0.75 for `relationship_pace`, small terms for `lifestyle` and `conversations`, and 0 when a field is unknown. Write the weights as named constants, because these are a hand-set prior, not learned values.
3. Optional, only if time allows: down-weight members with repeated `no_response` in `state['feedback']`. Store a smoothed per-member count in `memory['match']`, using observable feedback only.
4. Compare `maxcard` vs `maxcard_quality`, both with and without Rishi's `soft_asks`. Confirm that introductions per day are unchanged.

**Done when:** you have comparison tables and the introduction count is confirmed unchanged. Open a PR.

### Krishna — Day 3 (Fri 16 Oct): merge, confirm, Q2

1. Merge every feature that passed. Set `DEFAULT_CONFIG` to the best combination.
2. **Confirmation run, using the reserved seeds for the first time:** seeds 301–340 × 6 families, both expected and realised, for `greedy`, `no_asks`, `random`, `full`, and each ablation (`full` minus `ask_partners`, minus `soft_asks`, minus `maxcard`, minus quality). Save to `results/confirmation_301_340.json` and write a summary table.
3. Run the official evaluator for `full` on 101–103 × 6 → `results/final.json`, plus the three baselines on the same seeds.
4. **Q2 experiment (changing and overlapping conditions):** in `analysis/`, create world variants without editing `kit.py`, by subclassing `Simulator` and wrapping `generate`:
   - **sparse + delayed** together
   - **switch on day 30:** standard until day 29, then drift-style acceptance (−0.5) and delayed dates
   - **mixed arrivals:** 40% on day 0 and the rest spread over days 1–40.

   Show that `full` keeps its advantage over greedy (or doesn't) with no family-specific logic. Save to `results/q2_changing.json`.
5. After Rishi's container check, **pin the second build** and record the SHA.

**Done when:** the confirmation, final and Q2 results are saved, and the second SHA is pinned.

### Rishi — Day 3 (Fri 16 Oct): Q3a questions that only help together + report

1. **Q3a:** build test cases where a pair is blocked by *both* members' missing hard bundles. Show that scoring each question on its own gives zero value to each half, and check whether our partner-count ordering still gets both people asked. Quantify with a small synthetic setup and on real seeds: count pairs unblocked only after both people were asked, and how many days that took. Save to `results/q3a_complementary.json`.
2. Container-check the merged build before Krishna pins it.
3. Write the report sections (1–2 pages) on the ask phase design, item 1 and item 3 results, ask cost, and Q3a, in `report/asks.md`.

### Siddharth — Day 3 (Fri 16 Oct): Q1 reservation prices + Q3b who waits + report

1. **Q1:** create **denser stress worlds** in `analysis/`, wrapping `generate` without editing the kit: wider acceptable zones (every member accepts 2–3 zones), wider age ranges (±12), and `who_to_meet` with 2+ genders more often. Compare on these and on standard worlds:
   - λ = 0, our default
   - simple reservation: skip an edge if both endpoints have ≥ k other feasible partners and quality is below the median, with k tuned on 201–230
   - optional: sampled-future LP duals, only if time allows.

   Report whether waiting ever helps. Either answer is a valid result. Save to `results/q1_reservation.json`.
2. **Q3b:** for `full` vs `greedy`, report waiting time to first introduction (median and 90th percentile), never-served counts, and the same split by member responsiveness. Use observed non-response rates for the policy view, and true `response_rate` in analysis only. Save to `results/q3b_waiting.json`.
3. Write the report sections (1–2 pages) on the match phase, items 2 and quality, Q1 and Q3b, in `report/match.md`.

### 17–18 Oct (buffer)

- **Krishna:** assemble `REPORT.md` following `examples/REPORT_GUIDE.md`:
  - hypothesis and objective
  - observations and leakage
  - method
  - baselines on identical seeds × 6 families
  - funnel, coverage, waits, ask cost, missing feedback, runtime
  - ablations
  - Q1–Q3
  - failure cases (sparse, withheld answers, delays, shifts, contested candidates)
  - limitations and synthetic-data caveats
  - provenance and licences
  - AI-tool attribution.

  Also write `README.md` with exact commands, Python and dependency versions, and the **declared training seeds (201–260 development, 301–340 confirmation) and inference seed**.
- **Rishi:** final run of the `docs/SUBMISSION.md` sequence, including Docker.
- **Everyone:** review the report. Force-add `results/*.json` (ignored by default). **Pin the final 40-character SHA in the Final submission issue on the evening of 18 Oct.**

---

## 9. Report framing (key messages)

1. A low-noise **expected-MSMI yardstick**, validated against realised outcomes, which cuts paired noise about 10×.
2. **Headroom bound:** a perfect-information myopic matcher gains only about +7% over greedy, so complexity must earn its place.
3. Simple, robust features (question order, maximum pairs, cheap soft asks), each backed by an ablation.
4. Honest answers to the reviewer's Q1–Q3, including any negative results.
5. Synthetic data: none of these numbers say anything about real people.
