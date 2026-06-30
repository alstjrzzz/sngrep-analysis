#!/usr/bin/env python3
"""Plot a benchmark run: drop curve + throughput + CPU/RAM + per-core CPU.

    python3 bench/plot.py bench/results/<run_dir>

Writes the combined <run_dir>/report.png and one image per panel
(<run_dir>/report_pps.png, _loss.png, _cpu.png, _cores.png) so each panel can
be cited on its own. The per-core panel is a heatmap: if one core sits at 100%
while the total stays low, that is the single-thread sngrep limit (not resource
starvation); if every core is pegged, CPU contention is in play.
"""
import sys
import csv
import os
import numpy as np
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
    base = os.path.basename(os.path.normpath(d))
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
        dt = rel(stats[1]['ts_unix_ms'])
        if dt > 0:
            interval = dt

    t = [rel(r['ts_unix_ms']) for r in stats]
    pps = [float(r['d_recv']) / interval for r in stats]
    dps = [float(r['d_drop']) / interval for r in stats]
    dpc = [float(r['drop_pct']) for r in stats]

    if sysd:
        st = [rel(r['ts_unix_ms']) for r in sysd]
        cpu_all = [float(r['cpu_all_pct']) for r in sysd]
        cores = [k for k in sysd[0]
                 if k.startswith('cpu') and k.endswith('_pct') and k != 'cpu_all_pct']

        def mem_pct(r):
            used = float(r['mem_used_mb'])
            tot = used + float(r['mem_avail_mb'])
            return 100.0 * used / tot if tot else 0.0
        mem = [mem_pct(r) for r in sysd]
        core_grid = np.array([[float(r[c]) for r in sysd] for c in cores])

    def norm_ms(ts):
        # tolerate stage timestamps written in ns (older runs) vs ms (stats)
        ts = int(ts)
        while ts > t0 * 100:
            ts //= 1000
        return ts

    stage_marks = []
    for s in stages:
        try:
            x = (norm_ms(s['ts_unix_ms']) - t0) / 1000.0
        except (ValueError, KeyError):
            continue
        stage_marks.append((x, s.get('rate_cps', '')))

    def add_stage_lines(ax, labels=False):
        for x, rate in stage_marks:
            ax.axvline(x, color='gray', ls='--', alpha=.4)
        if labels:
            top = ax.get_ylim()[1]
            for x, rate in stage_marks:
                ax.text(x, top * 0.97, rate, fontsize=7, rotation=90,
                        va='top', color='gray')

    # --- per-panel drawing functions (ax, fig) ---
    def p_pps(ax, fig):
        ax.plot(t, pps, label='received pps', color='tab:blue')
        ax.plot(t, dps, label='dropped pps', color='tab:red')
        ax.set_ylabel('packets/s')
        ax.legend(loc='upper left')
        ax.grid(True, alpha=.3)

    def p_loss(ax, fig):
        ax.plot(t, dpc, color='tab:purple')
        ax.set_ylabel('loss ratio %\n(cum drop / cum recv)')
        ax.grid(True, alpha=.3)

    def p_cpu(ax, fig):
        ax.plot(st, cpu_all, label='CPU total %', color='tab:green')
        ax.plot(st, mem, label='RAM %', color='tab:orange')
        ax.set_ylabel('usage %')
        ax.set_ylim(0, 100)
        ax.grid(True, alpha=.3)
        ax.legend(loc='upper left')

    def p_cores(ax, fig):
        im = ax.pcolormesh(np.array(st), np.arange(len(cores)), core_grid,
                           cmap='RdYlGn_r', vmin=0, vmax=100, shading='nearest')
        ax.set_yticks(range(len(cores)))
        ax.set_yticklabels([c.replace('_pct', '') for c in cores])
        ax.set_ylabel('per-core CPU')
        cax = ax.inset_axes([1.012, 0.0, 0.012, 1.0])
        fig.colorbar(im, cax=cax, label='CPU %')

    panels = [('pps', p_pps, 'received / dropped pps'),
              ('loss', p_loss, 'cumulative loss ratio')]
    if sysd:
        panels += [('cpu', p_cpu, 'CPU total and RAM'),
                   ('cores', p_cores, 'per-core CPU')]

    xlabel = 'time (s)  (vertical dashes = cps stage boundaries)'

    # --- combined figure ---
    fig, axes = plt.subplots(len(panels), 1, figsize=(12, 2.6 * len(panels)),
                             sharex=True, constrained_layout=True)
    if len(panels) == 1:
        axes = [axes]
    for (name, fn, title), a in zip(panels, axes):
        fn(a, fig)
    for a in axes:
        add_stage_lines(a)
    add_stage_lines(axes[0], labels=True)
    axes[0].set_title('sngrep capture benchmark - ' + base)
    axes[-1].set_xlabel(xlabel + ', labeled on top')
    fig.savefig(os.path.join(d, 'report.png'), dpi=110)
    plt.close(fig)
    print("wrote", os.path.join(d, 'report.png'))

    # --- one figure per panel ---
    for name, fn, title in panels:
        f, a = plt.subplots(figsize=(12, 3.4), constrained_layout=True)
        fn(a, f)
        add_stage_lines(a, labels=True)
        a.set_title('%s - %s' % (title, base))
        a.set_xlabel(xlabel)
        out = os.path.join(d, 'report_%s.png' % name)
        f.savefig(out, dpi=110)
        plt.close(f)
        print("wrote", out)


if __name__ == '__main__':
    main()
