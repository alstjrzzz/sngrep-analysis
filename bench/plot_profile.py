#!/usr/bin/env python3
"""Summarize + plot T4 per-stage timing from profile.csv.

    python3 bench/plot_profile.py bench/results/<dir>

Prints a table (total / share% / avg-per-packet) and writes:
  - <dir>/profile_summary.txt  (the table)
  - <dir>/profile.png          (busy ms over the ramp + share bar)

The parse+group stage is split into SIP parse vs grouping when the run carries
the sub-timers (sip_parse_ns / sip_group_ns). Whichever stage dominates is what
the new architecture must parallelize.
"""
import sys
import csv
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def build_stages(header):
    # label, ns column, count column. "parse_other" is derived below.
    if 'sip_parse_ns' in header and 'sip_group_ns' in header:
        return [
            ('IP reasm', 'reasm_ip_ns', 'reasm_ip_cnt'),
            ('TCP reasm', 'reasm_tcp_ns', 'reasm_tcp_cnt'),
            ('lock wait (UI/contention)', 'lockwait_ns', 'parse_cnt'),
            ('SIP parse', 'sip_parse_ns', 'parse_cnt'),
            ('grouping', 'sip_group_ns', 'parse_cnt'),
            ('parse+group other', 'parse_other', 'parse_cnt'),
            ('dump', 'dump_ns', 'dump_cnt'),
        ]
    return [
        ('IP reasm', 'reasm_ip_ns', 'reasm_ip_cnt'),
        ('TCP reasm', 'reasm_tcp_ns', 'reasm_tcp_cnt'),
        ('lock wait (UI/contention)', 'lockwait_ns', 'parse_cnt'),
        ('parse+group', 'parse_ns', 'parse_cnt'),
        ('dump', 'dump_ns', 'dump_cnt'),
    ]


def stage_ns(row, col):
    # "parse_other" = whole parse+group stage minus the SIP parse / grouping
    # sub-timers (payload copy, allocation, etc.)
    if col == 'parse_other':
        return max(int(row['parse_ns']) - int(row['sip_parse_ns'])
                   - int(row['sip_group_ns']), 0)
    return int(row[col])


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

    stages = build_stages(rows[0].keys())
    last = rows[-1]
    totals = {lab: stage_ns(last, nsc) for lab, nsc, _ in stages}
    counts = {lab: int(last[cc]) for lab, _, cc in stages}
    grand = sum(totals.values()) or 1

    # --- text summary table ---
    lines = ["stage                         total(s)   share%    avg/pkt",
             "-------------------------------------------------------------"]
    for lab, _, _ in stages:
        tot = totals[lab]
        cnt = counts[lab]
        share = 100.0 * tot / grand
        avg_us = (tot / cnt / 1000.0) if cnt else 0.0
        lines.append("%-28s %8.2f %8.1f %9.2f us" % (lab, tot / 1e9, share, avg_us))
    summary = "\n".join(lines)
    print(summary)
    with open(os.path.join(d, 'profile_summary.txt'), 'w') as f:
        f.write(summary + "\n")

    # --- plots ---
    t0 = int(rows[0]['ts_unix_ms'])
    t = [(int(r['ts_unix_ms']) - t0) / 1000.0 for r in rows[1:]]
    series = []
    for lab, nsc, _ in stages:
        vals = [max(stage_ns(rows[i], nsc) - stage_ns(rows[i - 1], nsc), 0) / 1e6
                for i in range(1, len(rows))]
        series.append(vals)

    fig, ax = plt.subplots(2, 1, figsize=(12, 8))
    ax[0].stackplot(t, series, labels=[s[0] for s in stages])
    # sampling interval: if the stacked busy time reaches it, one core is saturated
    if len(t) > 1:
        interval_ms = 1000.0 * sorted(t[i] - t[i - 1] for i in range(1, len(t)))[len(t) // 2]
        ax[0].axhline(interval_ms, color='gray', ls='--', lw=1,
                      label='interval (1 core saturated)')
    ax[0].set_ylabel('capture-thread busy ms / interval')
    ax[0].set_xlabel('time (s)')
    ax[0].legend(loc='upper left', fontsize=8)
    ax[0].set_title('Capture-thread time breakdown - ' + os.path.basename(os.path.normpath(d)))
    ax[0].grid(True, alpha=.3)

    labels = [s[0] for s in stages]
    pct = [100.0 * totals[l] / grand for l in labels]
    ax[1].barh(labels, pct, color='tab:blue')
    ax[1].set_xlabel('% of total capture-thread time')
    ax[1].invert_yaxis()
    for i, l in enumerate(labels):
        cnt = counts[l]
        avg_us = (totals[l] / cnt / 1000.0) if cnt else 0.0
        ax[1].text(pct[i], i, '  %.1f%%  (%.1f us/pkt)' % (pct[i], avg_us),
                   va='center', fontsize=8)
    ax[1].grid(True, axis='x', alpha=.3)

    fig.tight_layout()
    out = os.path.join(d, 'profile.png')
    fig.savefig(out, dpi=110)
    print("wrote", out, "and profile_summary.txt")


if __name__ == '__main__':
    main()
