"""Observable-only Bayesian models for the match phase (modelling, kept separate from allocation).

Everything is rebuilt from the request (state['feedback'], state['introductions'], fields) on every
call: no memory, deterministic, pure standard library.

1. Person model (empirical-Bayes Beta-Binomial). Per member, from their own feedback:
     response: responded vs no_response, to introductions AND second-meeting questions
     acceptance: yes vs no among their introduction responses
   Each Beta prior is centred on the pool rate with a strength estimated by method of moments
   (binomial noise removed), clipped to [PRIOR_MIN, PRIOR_MAX]. Few observations per person, so
   posteriors stay near the prior; shrinkage is what stops the model overreacting.
   person_score(i) = log E[r_i^2] + log E[acc_i], relative to the prior member (0 = no evidence).

2. Fit model (Bayesian logistic regression, MAP by Newton): P(i says yes to j | i responded) on
   soft-field agreement features x_k = +1 equal / -0.5 different / 0 unknown. Prior means are the
   hand-set q weights / Q_SCALE, so with no data the learned fit equals pair_quality exactly.

3. Slot pressure (sampled-future capacity price): remaining feasible partners (present members not
   yet introduced) + expected future partners (recent arrival rate x days left x the share of the
   observed pool feasible with i, i.e. the sample average over resampled observed profiles),
   divided by remaining introduction slots (days left / 8).
"""
import math

from kit import eligibility

SOFT4 = ('relationship_goal', 'relationship_pace', 'lifestyle', 'conversations')
Q_SCALE = 4.0                     # pair_quality units per logit unit of acceptance
PRIOR_MIN, PRIOR_MAX, PRIOR_DEFAULT = 8.0, 50.0, 10.0  # floor 8: MoM underestimates strength with ~2 obs/member (dev seeds)
FIT_PRIOR_SD = 0.5                # sd of the Gaussian prior on each fit weight (logit units)
BUSY_DAYS = 8                     # an introduction blocks both people for 8 days


# ---------------------------------------------------------------- person model
def _beta_prior(counts):
    """counts: [(successes, trials)] -> (alpha, beta). Method of moments with binomial noise removed."""
    obs = [(s, n) for s, n in counts if n > 0]
    tot = sum(n for _, n in obs)
    if tot == 0:
        return None
    m = min(max(sum(s for s, _ in obs) / tot, .02), .98)
    k = PRIOR_DEFAULT
    if len(obs) >= 10:
        rates = [s / n for s, n in obs]
        mean_r = sum(rates) / len(rates)
        var_obs = sum((x - mean_r) ** 2 for x in rates) / (len(rates) - 1)
        noise = sum(m * (1 - m) / n for _, n in obs) / len(obs)
        var_true = var_obs - noise
        if var_true > 1e-6:
            k = m * (1 - m) / var_true - 1
    k = min(max(k, PRIOR_MIN), PRIOR_MAX)
    return m * k, (1 - m) * k


def person_counts(state):
    """member_id -> [responded, response_opportunities, yes, yes_opportunities] from observed feedback.

    Only RESOLVED opportunities count. A response is visible 1-7 days after an introduction but a
    non-response only at the 7-day deadline, so counting open introductions would inflate every
    response rate (calibration showed 0.9 predicted vs 0.7 observed). Likewise second-meeting answers
    count only once the 5-day answer window after the date has closed."""
    day = state['day']
    deadline = {i['introduction_id']: i.get('response_deadline_day', i['assigned_day'] + 7)
                for i in state.get('introductions', [])}
    date_day = {e['introduction_id']: e['occurred_day'] for e in state.get('feedback', [])
                if e.get('event') == 'date_happened' and e.get('value') is True}
    c = {}
    for e in state.get('feedback', []):
        ev = e.get('event')
        if ev not in ('introduction_response', 'second_meeting_intention') or not e.get('member_id'):
            continue
        if ev == 'introduction_response' and day < deadline.get(e.get('introduction_id'), 10 ** 6):
            continue
        if ev == 'second_meeting_intention' and day < date_day.get(e.get('introduction_id'), 10 ** 6) + 5:
            continue
        x = c.setdefault(e['member_id'], [0, 0, 0, 0])
        answered = e.get('value') is not None
        x[0] += answered
        x[1] += 1
        if e['event'] == 'introduction_response' and answered:
            x[2] += e['value'] == 'yes'
            x[3] += 1
    return c


def person_model(state):
    """-> (score dict member_id -> person_score, posterior dict for calibration)."""
    c = person_counts(state)
    pr = _beta_prior([(x[0], x[1]) for x in c.values()])
    pa = _beta_prior([(x[2], x[3]) for x in c.values()])
    if pr is None:
        return {}, {}
    pa = pa or (1.0, 1.0)

    def e_r2(a, b):
        return a * (a + 1) / ((a + b) * (a + b + 1))
    base = math.log(e_r2(*pr)) + math.log(pa[0] / (pa[0] + pa[1]))
    score, post = {}, {}
    for i, (s, n, y, ny) in c.items():
        ar, br = pr[0] + s, pr[1] + n - s
        aa, ba = pa[0] + y, pa[1] + ny - y
        score[i] = math.log(e_r2(ar, br)) + math.log(aa / (aa + ba)) - base
        post[i] = {'p_respond': ar / (ar + br), 'p_yes': aa / (aa + ba)}
    post['_prior'] = {'p_respond': pr[0] / sum(pr), 'p_yes': pa[0] / sum(pa)}
    return score, post


# ---------------------------------------------------------------- fit model
def fit_features(a, b):
    fa, fb = a['fields'], b['fields']
    x = []
    for k in SOFT4:
        u, v = fa.get(k), fb.get(k)
        x.append(0.0 if u is None or v is None else (1.0 if u == v else -.5))
    return x


def _solve(A, y):
    """Gaussian elimination with partial pivoting (tiny dense systems)."""
    n = len(y)
    M = [row[:] + [y[i]] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        M[c], M[p] = M[p], M[c]
        if abs(M[c][c]) < 1e-12:
            return [0.0] * n
        for r in range(n):
            if r != c:
                f = M[r][c] / M[c][c]
                for k in range(c, n + 1):
                    M[r][k] -= f * M[c][k]
    return [M[i][n] / M[i][i] for i in range(n)]


def fit_model(state, prior_means):
    """MAP weights [w_goal, w_pace, w_lifestyle, w_conversations] from directed accept/reject labels.
    Intercept has a weak N(0, 2^2) prior; it absorbs the base acceptance rate."""
    members = {m['member_id']: m for m in state['members']}
    pair_of = {i['introduction_id']: (i['user_a'], i['user_b']) for i in state['introductions']}
    X, Y = [], []
    for e in state.get('feedback', []):
        if e.get('event') != 'introduction_response' or e.get('value') not in ('yes', 'no'):
            continue
        pair = pair_of.get(e.get('introduction_id'))
        if not pair or pair[0] not in members or pair[1] not in members:
            continue
        X.append([1.0] + fit_features(members[pair[0]], members[pair[1]]))
        Y.append(1.0 if e['value'] == 'yes' else 0.0)
    mu = [0.0] + list(prior_means)
    prec = [1 / 4.0] + [1 / FIT_PRIOR_SD ** 2] * len(prior_means)
    w = mu[:]
    if not X:
        return list(prior_means), 0
    for _ in range(12):  # Newton steps on the log posterior
        g = [-prec[j] * (w[j] - mu[j]) for j in range(len(w))]
        H = [[(prec[j] if j == k else 0.0) for k in range(len(w))] for j in range(len(w))]
        for x, y in zip(X, Y):
            z = sum(wj * xj for wj, xj in zip(w, x))
            p = 1 / (1 + math.exp(-max(-30.0, min(30.0, z))))
            for j in range(len(w)):
                g[j] += (y - p) * x[j]
                for k in range(len(w)):
                    H[j][k] += p * (1 - p) * x[j] * x[k]
        step = _solve(H, g)
        w = [wj + sj for wj, sj in zip(w, step)]
        if max(abs(s) for s in step) < 1e-6:
            break
    return w[1:], len(Y)


# ---------------------------------------------------------------- slot pressure
def slot_pressure(state, available):
    """member_id -> log(1 + (remaining partners + expected future partners) / remaining slots)."""
    day = state['day']
    present = state['members']
    past = {tuple(sorted((i['user_a'], i['user_b']))) for i in state['introductions']}
    days_left = max(1, 60 - day)
    slots = max(1.0, days_left / BUSY_DAYS)
    recent = sum(1 for m in present if 0 < m['arrived_day'] and day - m['arrived_day'] < 7)
    rate = recent / min(7, max(1, day))
    # the "sample" of future profiles: present members whose fields are fully resolved
    known = {m['member_id'] for m in present if not any(s == 'not_asked' for s in m['field_status'].values())}
    out = {}
    for a in available:
        ia = a['member_id']
        remaining = feasible_known = 0
        for b in present:  # one eligibility pass serves both counts
            ib = b['member_id']
            if ib == ia or eligibility(a, b)['status'] != 'feasible':
                continue
            remaining += tuple(sorted((ia, ib))) not in past
            feasible_known += ib in known
        share = feasible_known / len(known) if known else 0.0
        out[ia] = math.log(1 + (remaining + share * rate * days_left) / slots)
    return out
