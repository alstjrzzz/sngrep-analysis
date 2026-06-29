#!/usr/bin/env python3
"""Plot T4 per-stage timing from profile.csv -> profile.png

    python3 bench/plot_profile.py bench/results/<dir>

Top panel: where the single capture thread spends time over the ramp (stacked
per-interval milliseconds per stage). Bottom panel: overall share. If one stage
(e.g. parse+group) dominates, that is what the new architecture must parallelize.
"""
import sys
import csv
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

STAGES = [
    ('reasm_ip_ns', 'IP reasm'),
    ('reasm_tcp_ns', 'TCP reasm'),
    ('lockwait_ns', 'lock wait (UI/contention)'),
    ('parse_ns', 'parse+group'),
    ('dump_ns', 'dump'),
]


def main():
    if len(sys.argv) < 2:
        print("usage: plot_profile.py RESULT_DIR")
        return
    d = sys.argv[1]
    p = os.path.join(d, 'profile.csv')
    if not os.path.exists(p):
        print("no profile.csv in", d, "(run with PROFILE=1)")
        return
    with open(p) as f:
        rows = list(csv.DictReader(f))
    if len(rows) < 2:
        print("profile.csv too short")
        return

    t0 = int(rows[0]['ts_unix_ms'])
    t = [(int(r['ts_unix_ms']) - t0) / 1000.0 for r in rows[1:]]
    series = {}
    for key, _ in STAGES:
        vals = []
        for i in range(1, len(rows)):
            vals.append(max(int(rows[i][key]) - int(rows[i - 1][key]), 0) / 1e6)  # ms
        series[key] = vals

    fig, ax = plt.subplots(2, 1, figsize=(12, 8))
    ax[0].stackplot(t, [series[k] for k, _ in STAGES], labels=[l for _, l in STAGES])
    ax[0].set_ylabel('busy ms per interval')
    ax[0].set_xlabel('time (s)')
    ax[0].legend(loc='upper left', fontsize=8)
    ax[0].set_title('Capture-thread time breakdown - ' + os.path.basename(os.path.normpath(d)))
    ax[0].grid(True, alpha=.3)

    last = rows[-1]
    totals = [int(last[k]) for k, _ in STAGES]
    s = sum(totals) or 1
    labels = [l for _, l in STAGES]
    pct = [100.0 * x / s for x in totals]
    ax[1].barh(labels, pct, color='tab:blue')
    ax[1].set_xlabel('% of total stage time (cumulative)')
    for i, x in enumerate(pct):
        ax[1].text(x, i, ' %.1f%%' % x, va='center', fontsize=8)
    ax[1].grid(True, axis='x', alpha=.3)

    fig.tight_layout()
    out = os.path.join(d, 'profile.png')
    fig.savefig(out, dpi=110)
    print("wrote", out)


if __name__ == '__main__':
    main()
