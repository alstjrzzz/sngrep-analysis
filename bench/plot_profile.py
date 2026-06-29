#!/usr/bin/env python3
"""Summarize + plot T4 per-stage timing from profile.csv.

    python3 bench/plot_profile.py bench/results/<dir>

Prints a table (total / share% / avg-per-packet) and writes:
  - <dir>/profile_summary.txt  (the table)
  - <dir>/profile.png          (stacked time over the ramp + share bar)

If one stage (e.g. parse+group) dominates, that is what the new architecture
must parallelize.
"""
import sys
import csv
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# label, ns column, count column (lock wait is charged per parse call)
STAGES = [
    ('IP reasm', 'reasm_ip_ns', 'reasm_ip_cnt'),
    ('TCP reasm', 'reasm_tcp_ns', 'reasm_tcp_cnt'),
    ('lock wait (UI/contention)', 'lockwait_ns', 'parse_cnt'),
    ('parse+group', 'parse_ns', 'parse_cnt'),
    ('dump', 'dump_ns', 'dump_cnt'),
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

    last = rows[-1]
    totals = {lab: int(last[nsc]) for lab, nsc, _ in STAGES}
    counts = {lab: int(last[cc]) for lab, _, cc in STAGES}
    grand = sum(totals.values()) or 1

    # --- text summary table ---
    lines = ["stage                         total(s)   share%    avg/pkt",
             "-------------------------------------------------------------"]
    for lab, _, _ in STAGES:
        tot = totals[lab]
        cnt = counts[lab]
        share = 100.0 * tot / grand
        avg_us = (tot / cnt / 1000.0) if cnt else 0.0
        lines.append("%-28s %8.2f %8.1f %9.2f us" % (lab, tot / 1e9, share, avg_us))
    # parse vs group drill-down (inside the parse+group stage), if instrumented
    if 'sip_parse_ns' in last and 'sip_group_ns' in last:
        sp, sg = int(last['sip_parse_ns']), int(last['sip_group_ns'])
        sub = (sp + sg) or 1
        lines += ["",
                  "within parse+group (T4 drill-down):",
                  "  SIP parse   %8.2f s   %5.1f%%" % (sp / 1e9, 100.0 * sp / sub),
                  "  grouping    %8.2f s   %5.1f%%" % (sg / 1e9, 100.0 * sg / sub)]

    summary = "\n".join(lines)
    print(summary)
    with open(os.path.join(d, 'profile_summary.txt'), 'w') as f:
        f.write(summary + "\n")

    # --- plots ---
    t0 = int(rows[0]['ts_unix_ms'])
    t = [(int(r['ts_unix_ms']) - t0) / 1000.0 for r in rows[1:]]
    series = []
    for lab, nsc, _ in STAGES:
        vals = [max(int(rows[i][nsc]) - int(rows[i - 1][nsc]), 0) / 1e6 for i in range(1, len(rows))]
        series.append(vals)

    fig, ax = plt.subplots(2, 1, figsize=(12, 8))
    ax[0].stackplot(t, series, labels=[s[0] for s in STAGES])
    ax[0].set_ylabel('busy ms per interval')
    ax[0].set_xlabel('time (s)')
    ax[0].legend(loc='upper left', fontsize=8)
    ax[0].set_title('Capture-thread time breakdown - ' + os.path.basename(os.path.normpath(d)))
    ax[0].grid(True, alpha=.3)

    labels = [s[0] for s in STAGES]
    pct = [100.0 * totals[l] / grand for l in labels]
    ax[1].barh(labels, pct, color='tab:blue')
    ax[1].set_xlabel('% of total stage time')
    for i, l in enumerate(labels):
        cnt = counts[l]
        avg_us = (totals[l] / cnt / 1000.0) if cnt else 0.0
        ax[1].text(pct[i], i, '  %.1f%%  (%.1f us/pkt)' % (pct[i], avg_us), va='center', fontsize=8)
    ax[1].grid(True, axis='x', alpha=.3)

    fig.tight_layout()
    out = os.path.join(d, 'profile.png')
    fig.savefig(out, dpi=110)
    print("wrote", out, "and profile_summary.txt")


if __name__ == '__main__':
    main()
