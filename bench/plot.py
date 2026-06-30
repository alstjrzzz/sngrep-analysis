#!/usr/bin/env python3
"""Plot a benchmark run: drop curve + throughput + CPU/RAM overlay.

    python3 bench/plot.py bench/results/<run_dir>

Writes <run_dir>/report.png. A separate panel draws per-core CPU: if one core
sits at 100% while the total stays low, that is the single-thread sngrep limit
(not resource starvation); if every core is pegged, CPU contention is in play.
"""
import sys
import csv
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def load(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return list(csv.DictReader(f))


def main():
    if len(sys.argv) < 2:
        print("usage: plot.py RESULT_DIR")
        sys.exit(1)
    d = sys.argv[1]
    stats = load(os.path.join(d, 'stats.csv'))
    sysd = load(os.path.join(d, 'sys.csv'))
    stages = load(os.path.join(d, 'stages.csv'))
    if not stats:
        print("no stats.csv rows in", d)
        sys.exit(1)

    t0 = int(stats[0]['ts_unix_ms'])
    rel = lambda ts: (int(ts) - t0) / 1000.0

    interval = 0.25
    if len(stats) > 1:
        dt = (int(stats[1]['ts_unix_ms']) - t0) / 1000.0
        if dt > 0:
            interval = dt

    t = [rel(r['ts_unix_ms']) for r in stats]
    pps = [float(r['d_recv']) / interval for r in stats]
    dps = [float(r['d_drop']) / interval for r in stats]
    dpc = [float(r['drop_pct']) for r in stats]

    npanel = 4 if sysd else 2
    fig, ax = plt.subplots(npanel, 1, figsize=(12, 2.6 * npanel), sharex=True)

    ax[0].plot(t, pps, label='received pps', color='tab:blue')
    ax[0].plot(t, dps, label='dropped pps', color='tab:red')
    ax[0].set_ylabel('packets/s')
    ax[0].legend(loc='upper left')
    ax[0].grid(True, alpha=.3)
    ax[0].set_title('sngrep capture benchmark - ' + os.path.basename(os.path.normpath(d)))

    ax[1].plot(t, dpc, color='tab:purple')
    ax[1].set_ylabel('loss ratio %\n(cum drop / cum recv)')
    ax[1].grid(True, alpha=.3)

    if sysd:
        st = [rel(r['ts_unix_ms']) for r in sysd]

        def mem_pct(r):
            used = float(r['mem_used_mb'])
            tot = used + float(r['mem_avail_mb'])
            return 100.0 * used / tot if tot else 0.0

        # total CPU and RAM, both as %
        ax[2].plot(st, [float(r['cpu_all_pct']) for r in sysd],
                   label='CPU total %', color='tab:green')
        ax[2].plot(st, [mem_pct(r) for r in sysd], label='RAM %', color='tab:orange')
        ax[2].set_ylabel('usage %')
        ax[2].set_ylim(0, 100)
        ax[2].grid(True, alpha=.3)
        ax[2].legend(loc='upper left')

        # per-core CPU on its own panel so a single pegged core is visible
        cores = [k for k in sysd[0]
                 if k.startswith('cpu') and k.endswith('_pct') and k != 'cpu_all_pct']
        for c in cores:
            ax[3].plot(st, [float(r[c]) for r in sysd], label=c.replace('_pct', ''))
        ax[3].set_ylabel('per-core CPU %')
        ax[3].set_ylim(0, 100)
        ax[3].grid(True, alpha=.3)
        ax[3].legend(loc='upper left', ncol=len(cores))

    def norm_ms(ts):
        # tolerate stage timestamps written in ns (older runs) vs ms (stats)
        ts = int(ts)
        while ts > t0 * 100:
            ts //= 1000
        return ts

    for s in stages:
        try:
            x = (norm_ms(s['ts_unix_ms']) - t0) / 1000.0
        except (ValueError, KeyError):
            continue
        for a in ax:
            a.axvline(x, color='gray', ls='--', alpha=.4)
        ax[0].text(x, ax[0].get_ylim()[1] * 0.97, s.get('rate_cps', ''),
                   fontsize=7, rotation=90, va='top', color='gray')

    ax[-1].set_xlabel('time (s)')
    fig.tight_layout()
    out = os.path.join(d, 'report.png')
    fig.savefig(out, dpi=110)
    print("wrote", out)


if __name__ == '__main__':
    main()
