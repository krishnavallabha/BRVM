"""Build the paper's figures from the committed result JSONs (vector PDFs in paper/figures/).

    python paper/make_figures.py
"""
import json
import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'paper', 'figures')
os.makedirs(OUT, exist_ok=True)
R = lambda name: json.load(open(os.path.join(ROOT, 'results', name), encoding='utf-8'))

# validated reference palette, categorical slots 1-3 in fixed order (all-pairs safe)
C1, C2, C3 = '#2a78d6', '#eb6834', '#1baf7a'
INK, INK2, GRID = '#0b0b0b', '#52514e', '#d9d8d4'
plt.rcParams.update({
    'font.family': 'STIXGeneral', 'mathtext.fontset': 'stix', 'font.size': 8.5,
    'axes.edgecolor': INK2, 'axes.labelcolor': INK, 'xtick.color': INK2, 'ytick.color': INK2,
    'axes.spines.top': False, 'axes.spines.right': False, 'axes.linewidth': 0.6,
    'xtick.major.width': 0.6, 'ytick.major.width': 0.6, 'legend.frameon': False,
    'pdf.fonttype': 42, 'savefig.bbox': 'tight', 'savefig.pad_inches': 0.02,
})
FAM = ['development', 'sparse', 'cold_start', 'delayed', 'shift', 'drift']
FAM_LABEL = ['standard', 'sparse', 'cold start', 'delayed', 'shifted\nweights', 'changing\nresponse']


def save(fig, name):
    fig.savefig(os.path.join(OUT, name))
    plt.close(fig)


def forest(ax, rows, colors, labels, offsets):
    """rows: list (per series) of [(mean, lo, hi)] per category, plotted as horizontal CI dots."""
    n = len(rows[0])
    for s, (series, col, lab, off) in enumerate(zip(rows, colors, labels, offsets)):
        for i, (m, lo, hi) in enumerate(series):
            y = n - 1 - i + off
            ax.plot([lo, hi], [y, y], color=col, lw=1.6, solid_capstyle='round', zorder=2)
            ax.plot([m], [y], 'o', ms=5, color=col, mec='white', mew=1.0, zorder=3, label=lab if i == 0 else None)
    ax.axvline(0, color=INK2, lw=0.7, ls=(0, (3, 2)), zorder=1)
    ax.grid(axis='x', color=GRID, lw=0.5)
    ax.set_axisbelow(True)


# ---------------------------------------------------------------- Fig. 1: per-family gains, fresh seeds
c = R('confirmation_341_380.json')['summary']['presets']
get = lambda p, f: (lambda d: (d['mean'], d['lo'], d['hi']))(
    (c[p]['vs_greedy']['overall'] if f == 'all' else c[p]['vs_greedy']['worlds'][f])['exp100'])
fig, ax = plt.subplots(figsize=(3.35, 2.9))
cats = FAM + ['all']
forest(ax, [[get('full', f) for f in cats], [get('full_person_learn', f) for f in cats]],
       [C1, C2], ['full (core)', 'full + Bayesian layer (shipped)'], [0.14, -0.14])
ax.set_yticks(range(len(cats)))
ax.set_yticklabels(list(reversed([l.replace('\n', ' ') for l in FAM_LABEL] + ['mean of families'])))
ax.get_yticklabels()[0].set_fontweight('bold')
ax.axhline(0.5, color=GRID, lw=0.6)
ax.set_xlabel('difference vs greedy (expected MSMI / 100, 95% CI)')
ax.legend(loc='lower center', bbox_to_anchor=(0.42, 1.0), ncol=2, fontsize=7.5, handletextpad=0.3, columnspacing=1.0)
save(fig, 'fig_families.pdf')

# ---------------------------------------------------------------- Fig. 2: where the value is
h = R('headroom2_201_215.json')['summary']['full']['overall']
used, ex, both, drift = h['used100'], h['unused_exit100'], h['unused100'] - h['unused_exit100'], h['drift_loss100']
fig, ax = plt.subplots(figsize=(3.35, 1.25))
segs = [(used, C1, 'captured'), (both, C2, 'never scheduled (both present)'), (ex, C3, 'never scheduled (one exits)')]
x = 0
for v, col, lab in segs:
    ax.barh([0], [v], left=x, color=col, height=0.5, edgecolor='white', linewidth=2)
    x += v
ax.annotate('captured\n%.3f' % used, (used / 2, 0), ha='center', va='center', color='white', fontsize=8, fontweight='bold')
ax.annotate('unused, both present %.3f' % both, (used + both / 2, 0.42), ha='center', va='bottom', color=INK, fontsize=7.5)
ax.annotate('one exits %.3f' % ex, (used + both + ex / 2, -0.42), ha='center', va='top', color=INK, fontsize=7.5)
ax.set_xlim(0, x * 1.02)
ax.set_ylim(-0.9, 0.9)
ax.set_yticks([])
ax.spines['left'].set_visible(False)
ax.set_xlabel('expected MSMI per 100 members')
save(fig, 'fig_headroom.pdf')

# ---------------------------------------------------------------- Fig. 3: calibration (reliability diagrams)
cal = R('calibration_201_215.json')['summary']
fig, axes = plt.subplots(1, 3, figsize=(6.9, 2.15), sharey=False)
for ax, key, title in zip(axes, ('respond', 'yes', 'fit'),
                          ('P(responds)  person model', 'P(yes | responded)  person model', 'P(yes | responded)  fit model')):
    m = cal[key]['model']
    xs = [b['mean_pred'] for b in m['bins']]
    ys = [b['observed'] for b in m['bins']]
    ns = [b['n'] for b in m['bins']]
    lo = min(xs + ys) - .05
    hi = max(xs + ys) + .05
    ax.plot([lo, hi], [lo, hi], color=INK2, lw=0.7, ls=(0, (3, 2)))
    ax.plot(xs, ys, color=C1, lw=1.6, zorder=2)
    for x_, y_, n_ in zip(xs, ys, ns):
        ax.plot([x_], [y_], 'o', ms=3 + 5 * (n_ / max(ns)) ** .5, color=C1, mec='white', mew=0.8, zorder=3)
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_title(title, fontsize=8.5, color=INK)
    ax.set_xlabel('mean predicted')
    ax.grid(color=GRID, lw=0.5)
    ax.set_axisbelow(True)
    ax.text(0.04, 0.94, 'Brier skill %+.1f%%' % (100 * cal[key]['brier_skill']), transform=ax.transAxes,
            va='top', fontsize=7.5, color=INK2)
axes[0].set_ylabel('observed frequency')
save(fig, 'fig_calibration.pdf')

# ---------------------------------------------------------------- Fig. 4: Q1 waiting does not pay
d = R('q1_dense_201_260.json')['summary']['presets']
s = R('q1_standard_201_230.json')['summary']['presets']
sl = R('slot_dense_mixed_201_260.json')['summary']['presets']
dv = R('bayes_dev_201_230.json')['summary']['presets']
ci = lambda x: (x['mean'], x['lo'], x['hi'])
rows = [
    ('reservation k=1, dense', ci(d['full@reserve_k=1']['vs_full']['overall']['exp100'])),
    ('reservation k=2, dense', ci(d['full@reserve_k=2']['vs_full']['overall']['exp100'])),
    ('reservation k=3, dense', ci(d['full@reserve_k=3']['vs_full']['overall']['exp100'])),
    ('reservation k=3, standard', ci(s['full@reserve_k=3']['vs_full']['overall']['exp100'])),
    ('reservation k=3, dense + mixed arrivals', ci(sl['full@reserve_k=3']['vs_full']['overall']['exp100'])),
    (r'sampled-future price $\lambda=-1$, standard', ci(dv['full_slot@slot_price=-1']['vs_full']['overall']['exp100'])),
    (r'sampled-future price $\lambda=+1$, standard', ci(dv['full_slot']['vs_full']['overall']['exp100'])),
    (r'sampled-future price $\lambda=-1$, dense + mixed', ci(sl['full_slot@slot_price=-1']['vs_full']['overall']['exp100'])),
]
fig, ax = plt.subplots(figsize=(3.35, 2.45))
forest(ax, [[r[1] for r in rows]], [C1], [None], [0])
ax.set_yticks(range(len(rows)))
ax.set_yticklabels([r[0] for r in reversed(rows)], fontsize=7.5)
ax.set_xlabel(r'paired difference vs $\lambda=0$ (never wait), 95% CI')
save(fig, 'fig_q1.pdf')

# ---------------------------------------------------------------- Fig. 5: remove-one ablations
a = R('confirmation_301_340.json')['summary']['presets']
abl = [('partner-count question order', 'full-partners'), ('soft (goal, pace) questions', 'full-soft'),
       ('maximum cardinality', 'full-maxcard'), ('quality tie-break', 'full-quality')]
fig, ax = plt.subplots(figsize=(3.35, 1.55))
forest(ax, [[ci(a[p]['vs_full']['overall']['exp100']) for _, p in abl]], [C1], [None], [0])
ax.set_yticks(range(len(abl)))
ax.set_yticklabels(['$-$ ' + l for l, _ in reversed(abl)])
ax.set_xlabel('difference vs full when removed (95% CI)')
save(fig, 'fig_ablation.pdf')

print('figures written to', OUT, sorted(os.listdir(OUT)))
