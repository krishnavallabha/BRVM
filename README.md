# Bayesian Reservation-Value Matching (BRVM)

### Sequential Reciprocal Introductions Under Uncertainty

**Team The Misfits** | Applied Machine Learning Programme & Hackathon
**Organised by:** Romeo & Juliet Ltd. × IIT Madras
**Research Round:** | October 2026



## Overview

**Bayesian Reservation-Value Matching (BRVM)** is a proposed Bayesian decision-making framework for sequential reciprocal matching under uncertainty.

The system addresses a dynamic matching problem in which an agent must decide:

* **Who to match:** Select compatible pairs while respecting all hard eligibility constraints.
* **When to match:** Determine whether an introduction is worth making now or whether waiting for better opportunities is preferable.
* **What to ask:** Identify which missing information should be requested to improve future matching decisions.
* **How to learn:** Adapt to individual behaviour, delayed feedback, and changing environmental conditions.

Unlike conventional greedy matching algorithms that select the highest-scoring pairs independently, BRVM combines Bayesian outcome modelling, global maximum-weight matching, reservation values, Thompson sampling, and value-of-information-driven clarification.

The objective is to maximise **Mutual Second-Meeting Intention (MSMI) per 100 arrived members**, while maintaining valid actions, efficient inference, and robust performance across different simulated environments.

> **Research status:** This repository documents the BRVM research approach and its proposed evaluation framework. Empirical performance improvements are hypotheses to be tested, not established results.

---

## Problem Statement

The sequential matching environment presents several challenges:

1. **Reciprocal preferences:** Both individuals must accept an introduction.
2. **Incomplete information:** Important profile fields may be missing, unresolved, or explicitly declined.
3. **Delayed outcomes:** Acceptance, scheduling, and second-meeting decisions occur over different time windows.
4. **Dynamic populations:** New individuals arrive while previously available individuals remain unmatched.
5. **Opportunity cost:** An introduction can occupy both individuals for up to seven days, potentially preventing better matches.
6. **Selective feedback:** Outcomes are observed primarily for pairs that the policy chooses to introduce.
7. **Distribution shift:** Response rates, geographical constraints, and outcome patterns can change across scenario families.
8. **Strict execution constraints:** Invalid actions, malformed responses, runtime failures, or timeouts can invalidate an episode.

A policy must therefore optimise not only pair compatibility but also allocation, information acquisition, uncertainty, and future opportunity costs.

---

## Our Approach

BRVM organises the matching process into six logical layers.

| Layer | Component                          | Purpose                                                         |
| ----- | ---------------------------------- | --------------------------------------------------------------- |
| 0     | Validity and safety shell          | Enforce output validity, runtime limits, and memory constraints |
| 1     | Reciprocal feasibility             | Identify feasible, infeasible, and information-blocked pairs    |
| 2     | Bayesian outcome model             | Estimate staged outcome probabilities and represent uncertainty |
| 3     | Reservation-value allocation       | Select globally optimal, non-overlapping introductions          |
| 4     | Value-of-information clarification | Allocate the daily clarification budget to valuable questions   |
| 5     | Scenario-aware meta-policy         | Adapt policy parameters to the observed environment             |

The architecture separates feasibility, prediction, allocation, and clarification so that individual components can be evaluated independently.

---

## Core Technical Contributions

### 1. Hierarchical Bayesian Outcome Modelling

BRVM models Mutual Second-Meeting Intention as a sequence of conditional events rather than treating it as a single prediction target.

The proposed factorisation is:

$$
\begin{aligned}
P(\text{MSMI}) ={}&
P(\text{mutual acceptance})\\
&\times P(\text{date within 30 days}\mid\text{mutual acceptance})\\
&\times P(\text{both say Yes within 3 days}\mid\text{date})
\end{aligned}
$$

The model captures three stages:

* **Stage 1:** Reciprocal acceptance, including the possibility of non-response.
* **Stage 2:** Whether a date occurs within the specified 30-day window.
* **Stage 3:** Whether both individuals indicate a second-meeting intention within three days of the date.

The hierarchical structure incorporates:

* Global model coefficients.
* Individual-level willingness and responsiveness effects.
* Individual-level appeal effects.
* Episode-level offsets for changing response conditions.
* Explicit features describing missing and declined information.
* Correlation between reciprocal acceptance outcomes.

The research proposes Bayesian inference during offline training and lightweight posterior approximations for deployment.

Online updates allow the policy to learn from observed outcomes without repeatedly fitting the entire model.

### 2. Reciprocal Feasibility as a Hard Constraint

BRVM distinguishes three pair states:

| State      | Definition                                                        | Policy behaviour             |
| ---------- | ----------------------------------------------------------------- | ---------------------------- |
| Feasible   | All currently verifiable hard constraints are satisfied           | Eligible for matching        |
| Infeasible | At least one known hard constraint is violated                    | Discarded                    |
| Blocked    | No known violation exists, but required information is unresolved | Considered for clarification |

Feasibility is enforced independently of predicted outcome probability.

The policy does not override the supplied eligibility function, interpret missing values as rejection, or infer preferences from age or gender.

**A high predicted MSMI probability can never make an infeasible pair eligible.**

### 3. Reservation Values: Knowing When to Wait

A key idea behind BRVM is that matching someone now has an opportunity cost.

An individual may have better potential partners arriving in the near future. Matching them immediately could prevent those future opportunities from being realised.

BRVM represents this opportunity cost using a reservation value, denoted by \(\lambda_i\).

Reservation values are estimated through a sample-average approximation:

1. Sample plausible future arrival scenarios.
2. Construct an opportunity graph containing currently available individuals and simulated arrivals.
3. Assign expected outcome values to candidate edges.
4. Solve a linear-programming relaxation of the matching problem.
5. Extract dual prices associated with individual capacity constraints.
6. Average these prices across sampled scenarios.

A higher reservation value indicates that keeping an individual available may be more valuable.

The proposed method therefore allows BRVM to distinguish between individuals who should be matched promptly and those for whom waiting may be beneficial.

### 4. Opportunity-Adjusted Edge Scoring

Each feasible pair receives an opportunity-adjusted weight:

$$
w(i,j)=\tilde{p}(i,j)-\kappa(\lambda_i+\lambda_j)
+\epsilon(s_i+s_j)
$$

Where:

* \(\tilde{p}(i,j)\) is a Thompson-sampled probability of MSMI.
* \(\lambda_i,\lambda_j\) are the reservation values of the two individuals.
* \(\kappa\) controls the influence of future opportunity costs.
* \(s_i,s_j\) represent scarcity scores.
* \(\epsilon\) controls the scarcity bonus.

Only positive-weight edges are retained.

If no suitable positive-weight edges remain, the policy may choose not to make an introduction.

This is intentional: **matching immediately is not always better than waiting.**

### 5. Global Maximum-Weight Matching

Selecting the individually highest-scoring pairs can produce a suboptimal allocation because multiple candidate pairs may compete for the same individual.

BRVM constructs a general, non-bipartite graph of eligible, positive-weight edges and solves a maximum-weight matching problem.

The proposed implementation uses **Edmonds' Blossom algorithm** through NetworkX.

This ensures that:

* Each individual appears in at most one selected pair per batch.
* The combined value of the selected introductions is maximised over the retained graph.
* Allocation accounts for competition between candidate pairs.

Top-\(k\) edge pruning and a runtime-aware fallback are proposed to control computational cost.

### 6. Thompson Sampling for Exploration

BRVM uses Thompson sampling to account for uncertainty in predicted outcomes.

Instead of always allocating according to posterior mean probabilities, the policy samples model parameters and relevant individual effects from their approximate posterior distributions.

The sampled values are then used to score feasible pairs.

This approach is intended to balance:

* **Exploitation:** Selecting pairs with strong estimated outcomes.
* **Exploration:** Giving uncertain individuals and pairs opportunities to generate informative feedback.

Sampling is restricted to feasible pairs, so uncertainty affects allocation without overriding hard constraints.

The exploration temperature is proposed to decrease towards the end of the decision horizon, when there is less time to benefit from additional learning.

### 7. Value-of-Information Clarification

BRVM treats clarification as a resource-allocation problem.

Each day, the policy has a fixed clarification budget of **12 units**.

The proposed clarification actions include:

* **Hard-constraint bundles:** Cost 3 units.
* **Individual soft-field questions:** Cost 1 unit.

For a candidate question \(a\), the proposed value-of-information score is:

$$
VOI(a)=H(i,t)
\left[
\sum_o P(o)V(\text{after }o)-V(\text{now})
\right]
$$

Where:

* \(P(o)\) is the predicted probability of a possible answer.
* \(V(\text{after }o)\) is the expected matching value after observing that answer.
* \(V(\text{now})\) is the current matching value.
* \(H(i,t)\) discounts questions according to the remaining useful decision horizon.

Questions are selected using a 0/1 knapsack optimisation subject to the daily budget.

The policy avoids spending resources on questions with non-positive estimated value and does not repeatedly ask about fields that individuals have already declined.

### 8. Scenario-Aware Adaptation

The research considers six scenario families:

1. Standard conditions.
2. Sparse geography.
3. Cold start.
4. Delayed dates.
5. Shifted outcome weights.
6. Changing response conditions.

BRVM proposes a lightweight meta-policy that infers the likely scenario family from observable signals, including:

* Arrival rates.
* Feasible-graph density.
* Geographical diversity.
* Missing-field frequency.
* Observed response rates and delays.
* Empirical scheduling delays.

A multinomial logistic classifier estimates the probability of each scenario family. These probabilities are used to blend family-specific hyperparameter configurations.

The goal is to improve robustness without relying on hidden simulator information.

---

## Daily Decision Workflow

BRVM follows the two-phase interaction protocol.

### Phase 1: Clarification

1. Load the carried policy memory.
2. Update posterior estimates using newly observed feedback.
3. Estimate the current scenario and select hyperparameters.
4. Recompute reciprocal feasibility.
5. Identify blocked pairs and valuable clarification candidates.
6. Select questions within the 12-unit budget.
7. Validate the proposed questions.
8. Return the questions and updated policy memory.

### Phase 2: Matching

1. Load the latest state, including newly disclosed answers.
2. Update the relevant posterior estimates.
3. Recompute pair feasibility.
4. Estimate reservation values where computationally feasible.
5. Sample uncertain outcome probabilities.
6. Calculate opportunity-adjusted edge weights.
7. Prune low-value edges when necessary.
8. Solve the maximum-weight matching problem.
9. Independently revalidate every selected pair.
10. Record explanations in diagnostic logs and return valid pairs.

The policy carries its learned state between requests through serialised memory rather than relying on persistent filesystem storage.

---

## Validity, Reliability, and Runtime

BRVM treats execution validity as a first-class engineering requirement.

The proposed validity shell includes:

* Independent validation of every proposed pair.
* Exception handling with an always-valid empty-response fallback.
* Runtime guards and a simpler matching fallback.
* Enforcement of the 12-unit clarification budget.
* Memory pruning to remain within the protocol's memory limit.
* Deterministic random seeds for reproducible runs.
* Tests for empty populations, missing profiles, unavailable individuals, and already-introduced pairs.

The research targets a 10-second invocation limit, with a soft deadline intended to trigger simpler computation before a hard timeout.

The target is to keep median inference time below three seconds, subject to empirical verification.

---

## Experimental Design

BRVM is designed to be evaluated against the supplied baseline policies under controlled simulator conditions.

### Baselines

* **Greedy:** The supplied greedy matching policy.
* **No clarification:** A baseline that does not ask additional questions.
* **Random feasible:** A policy that selects feasible pairs randomly.
* **BRVM-lite:** A simplified variant using global matching on posterior mean probabilities without reservation values or value-of-information clarification.

### Research Hypotheses

| ID | Hypothesis                                                                                                                 |
| -- | -------------------------------------------------------------------------------------------------------------------------- |
| H1 | Global maximum-weight matching improves MSMI over greedy pair ranking.                                                     |
| H2 | Reservation values improve decisions by accounting for the opportunity cost of matching immediately.                       |
| H3 | Thompson sampling improves learning and allocation under uncertainty, especially during cold start and distribution shift. |
| H4 | Value-of-information clarification improves MSMI per clarification unit.                                                   |
| H5 | Online updates and scenario-aware adaptation reduce performance degradation under changing conditions.                     |
| H6 | Modelling correlated reciprocal acceptance improves pair ranking compared with assuming independence.                      |
| H7 | A scarcity-aware bonus improves coverage with negligible loss in MSMI.                                                     |

These are research hypotheses rather than experimentally confirmed findings.

### Ablation Studies

The proposed evaluation includes the following component removals and substitutions:

| Ablation | Modification                                                            |
| -------- | ----------------------------------------------------------------------- |
| A1       | Replace Blossom matching with greedy ranking                            |
| A2       | Remove reservation values                                               |
| A3       | Replace LP-dual reservation values with heuristic values                |
| A4       | Replace Thompson sampling with posterior mean probabilities             |
| A5       | Replace VOI-based questions with random questions                       |
| A6       | Disable clarification                                                   |
| A7       | Disable online posterior updates                                        |
| A8       | Replace correlated acceptance modelling with an independence assumption |
| A9       | Replace the scenario-aware meta-policy with one parameter configuration |
| A10      | Remove conversation-derived features                                    |
| A11      | Remove the scarcity bonus                                               |

### Evaluation Metrics

The proposed evaluation reports:

* MSMI count.
* MSMI per 100 arrived members.
* Assignment and mutual-acceptance counts.
* Successful date scheduling.
* Member coverage.
* Clarification cost and question counts.
* Missing feedback and non-response rates.
* Time to first introduction.
* Number of unserved members.
* Median, p99, and maximum inference time.
* Calibration metrics for optional probability estimates.

Results are intended to be reported by scenario family and overall, using equal weighting across the six family-level means.

Paired comparisons on identical random seeds and bootstrap confidence intervals are proposed to quantify uncertainty.

---

## Technology Stack

The research specifies or proposes the following technologies for the system:

| Technology                 | Intended use                                         |
| -------------------------- | ---------------------------------------------------- |
| Python                     | Core policy implementation                           |
| NumPy                      | Numerical computation and model artefacts            |
| SciPy                      | Numerical optimisation and linear programming        |
| HiGHS                      | Linear-programming solver                            |
| NetworkX                   | General-graph maximum-weight matching                |
| Optuna                     | Bayesian hyperparameter optimisation                 |
| Docker                     | Reproducible execution environment                   |
| Bayesian inference methods | Offline model estimation and posterior approximation |

The research proposes keeping heavyweight training dependencies outside the inference environment.

The final implementation should pin dependency versions and document applicable software licences.

---

## Engineering Constraints

The target execution environment imposes the following constraints:

| Constraint                            | Requirement                                |
| ------------------------------------- | ------------------------------------------ |
| Runtime                               | 10 seconds per invocation                  |
| CPU                                   | 2 CPU cores                                |
| Memory                                | 1 GiB                                      |
| Request, response, and carried memory | 1 MiB limit                                |
| Inference environment                 | CPU only                                   |
| Filesystem and networking             | No persistent filesystem or network access |
| Inference assets                      | At most 2 GiB                              |
| Daily clarification budget            | 12 units                                   |

These constraints influence model representation, online updating, graph pruning, and fallback behaviour.

---

## Limitations and Scope

BRVM is a research proposal designed for a synthetic sequential matching environment.

Important limitations include:

* **Synthetic outcomes:** Simulator performance does not establish real-world relationship prediction capability.
* **Selective feedback:** Outcomes are primarily observed for introduced pairs, which limits straightforward unbiased offline evaluation.
* **Delayed observations:** Outcome labels must respect their observation windows to avoid premature or censored labels.
* **Model misspecification:** Incorrect outcome assumptions may produce unreliable pair rankings.
* **Distribution shift:** Changes in the simulated environment may reduce predictive quality.
* **Opportunity-cost trade-offs:** Reservation values can delay introductions for individuals with many promising alternatives.
* **Computational constraints:** More sophisticated allocation and clarification calculations may need to be skipped when runtime limits are approached.

Any real-world deployment would require appropriate authorisation, independent validation, current eligibility checks, and human oversight.

---

## Repository Status

This README describes the proposed architecture and experimental plan from the BRVM Round 1 research document.

The research document does not report empirical performance improvements. Claims about superiority over the baselines must therefore remain provisional until supported by completed experiments.

Implementation details, dependency versions, commands, model artefacts, and actual results should be added as they become available in the repository.

---

## Team

**Team The Misfits**

* Rishi Mehrotra
* Siddharth Malkania
* Krishna Vallabha Goswami

**Programme:** Applied Machine Learning Programme & Hackathon
**Organisers:** Romeo & Juliet Ltd. × IIT Madras
**Research date:** 9 October 2026

---

## References

The research builds on established work in graph matching, Bayesian inference, bandit algorithms, information theory, and dynamic allocation.

1. Edmonds, J. (1965). *Paths, Trees, and Flowers.* Canadian Journal of Mathematics, 17, 449–467.
2. Thompson, W. R. (1933). *On the Likelihood That One Unknown Probability Exceeds Another in View of the Evidence of Two Samples.* Biometrika, 25(3/4), 285–294.
3. Russo, D., Van Roy, B., Kazerouni, A., Osband, I., & Wen, Z. (2018). *A Tutorial on Thompson Sampling.* Foundations and Trends in Machine Learning, 11(1), 1–96.
4. Howard, R. A. (1966). *Information Value Theory.* IEEE Transactions on Systems Science and Cybernetics, 2(1), 22–26.
5. Gelman, A., et al. (2013). *Bayesian Data Analysis* (3rd ed.). CRC Press.
6. Dickerson, J. P., Procaccia, A. D., & Sandholm, T. (2012). *Dynamic Matching via Weighted Myopia with Application to Kidney Exchange.* AAAI.
7. Ashlagi, I., Burq, M., Jaillet, P., & Manshadi, V. (2019). *On Matching and Thickness in Heterogeneous Dynamic Markets.* Operations Research, 67(4), 927–949.
8. Akiba, T., et al. (2019). *Optuna: A Next-Generation Hyperparameter Optimization Framework.* KDD.
9. Pizzato, L., et al. (2010). *RECON: A Reciprocal Recommender for Online Dating.* ACM RecSys.
10. Huangfu, Q., & Hall, J. A. J. (2018). *Parallelizing the Dual Revised Simplex Method.* Mathematical Programming Computation, 10(1), 119–142.

---

*Bayesian Reservation-Value Matching: making sequential matching decisions by balancing compatibility, uncertainty, information, and the value of waiting.*
