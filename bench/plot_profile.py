#!/usr/bin/env python3
"""Summarize + plot T4 per-stage timing from profile.csv.

    python3 bench/plot_profile.py bench/results/<dir>

Prints a table (total / share% / avg-per-packet) and writes:
  - <dir>/profile_summary.txt  (the table)
  - <dir>/profile.png          (per-stage share bar)

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
            ('other', 'parse_other', 'parse_cnt'),
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

    # per-packet cost by packet type (full parse path), if instrumented
    if 'sip_pkt_ns' in last and 'rtp_pkt_ns' in last:
        def per_pkt(ns_col, cnt_col):
            cnt = int(last[cnt_col])
            return ((int(last[ns_col]) / cnt / 1000.0) if cnt else 0.0), cnt
        sp_us, sp_n = per_pkt('sip_pkt_ns', 'sip_pkt_cnt')
        rt_us, rt_n = per_pkt('rtp_pkt_ns', 'rtp_pkt_cnt')
        lines += ["",
                  "per-packet cost by type (full parse path):",
                  "  SIP  %8.2f us/pkt  (n=%d)" % (sp_us, sp_n),
                  "  RTP  %8.2f us/pkt  (n=%d)" % (rt_us, rt_n)]

    summary = "\n".join(lines)
    print(summary)
    with open(os.path.join(d, 'profile_summary.txt'), 'w') as f:
        f.write(summary + "\n")

    # --- bar chart: each stage's share of capture-thread time ---
    labels = [s[0] for s in stages]
    pct = [100.0 * totals[l] / grand for l in labels]
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.barh(labels, pct, color='tab:blue')
    ax.set_xlabel('% of total capture-thread time')
    ax.invert_yaxis()
    for i, l in enumerate(labels):
        cnt = counts[l]
        avg_us = (totals[l] / cnt / 1000.0) if cnt else 0.0
        ax.text(pct[i], i, '  %.1f%%  (%.1f us/pkt)' % (pct[i], avg_us),
                va='center', fontsize=8)
    ax.grid(True, axis='x', alpha=.3)
    ax.set_title('Capture-thread time breakdown - ' + os.path.basename(os.path.normpath(d)))
    fig.tight_layout()
    out = os.path.join(d, 'profile.png')
    fig.savefig(out, dpi=110)
    print("wrote", out, "and profile_summary.txt")


if __name__ == '__main__':
    main()
